from linkedin_tool.normalization.fuzzy import resolve_with_fuzzy_simple, resolve_with_fuzzy_seniority
from linkedin_tool.normalization.keys import build_posting_key_map
from linkedin_tool.normalization.repository import NormalizationRepository
from linkedin_tool.normalization.llm import GroqLLMNormalizer
from linkedin_tool.setting import NormalizationConfig
from linkedin_tool.schema import NormalizationResult, NormalizationSummary, ScrapeResult
from linkedin_tool.log import print_message
from time import sleep

def _chunks(items: list[str], size: int):
    for i in range(0, len(items), size):
        
        # yield pauses a function and returns a value to the caller,
        # but remembers where it left off so it can resume later
        yield items[i : i + size]

def _build_unresolved_sets(
    posting_key_map: dict[int, dict[str, str]],
    map_key_to_value: dict[str, dict[object, str]],
) -> dict[str, set[object]]:
    """
    check for existing key in the map. If key is not in the current normalization map, then add it to the unresolved set.
    Return a map with domain as key and unresolved set as value
    """
    
    unresolved = {d: set() for d in NormalizationConfig.DOMAINS.value}
    for _, domain_keys in posting_key_map.items():
        # domain_keys is a map of title, location, and seniority
        for d in NormalizationConfig.DOMAINS.value:
            
            if d=="seniority":
                seniority_map = map_key_to_value["seniority"]
                
                seniority = domain_keys.get(d, "")
                if (False, seniority) in seniority_map:
                    continue

                raw_title = domain_keys.get("title", "")
                if (True, raw_title) in seniority_map:
                    continue
                
                if seniority!="not applicable":
                    unresolved[d].add((False, seniority))
                else:
                    unresolved[d].add((True, raw_title))
                
            else:
                k = domain_keys.get(d, "")
                
                if k not in map_key_to_value[d]:
                # try to look up for the key in the existing normalization map
                # if key is not in the map, then add it to unresolved
                    unresolved[d].add(k)
    
    return unresolved

def _build_normalization_result(
    posting_key_map: dict[int, dict[str, str]],
    map_key_to_value: dict[str, dict[object, str]],
    unresolved: dict[str, set[object]],
    resolved_by_method: dict[str, int],
    error: str | None = ""
) -> NormalizationResult:
    ready_ids: list[int] = []
    for raw_id, keys in posting_key_map.items():
        ready = True
        for d in NormalizationConfig.DOMAINS.value:
            key = keys[d]
            if d=="seniority":
                if key=="not applicable" and (True, keys["title"]) not in map_key_to_value[d]:
                    ready = False
                    break
                if key!="not applicable" and (False, key) not in map_key_to_value[d]:
                    ready = False
                    break
                    
            else:    
                if key not in map_key_to_value[d]:
                    ready = False
                    break
        if ready:
            ready_ids.append(raw_id)
    
    if error:
        status = ScrapeResult.FAILED
    else:
        status = ScrapeResult.SUCCESSFUL

    return NormalizationResult(
        result=status,
        ready_job_posting_raw_ids=ready_ids,
        summary=NormalizationSummary(
            total_candidates=len(posting_key_map),
            ready_count=len(ready_ids),
            unresolved_by_domain={d: len(unresolved[d]) for d in NormalizationConfig.DOMAINS.value},
            resolved_by_method=resolved_by_method,
        ),
        error=error
    )

def run_normalization_pipeline(
    repo: NormalizationRepository,
    scrape_run_ids: list[int],
    llm_normalizer: GroqLLMNormalizer,
) -> NormalizationResult:
    print_message("Normalization", "start pipeline")

    rows = repo.fetch_candidate_raw_postings(scrape_run_ids)
    if not rows:
        print_message("Normalization", "finish pipeline")
        return NormalizationResult()

    posting_key_map = build_posting_key_map(rows)

    map_key_to_value = {
        d: repo.fetch_map_key_to_value(d) for d in NormalizationConfig.DOMAINS.value
    }

    resolved_by_method = {method: 0 for method in NormalizationConfig.METHODS.value}

    # Stage 1: map lookup
    print_message("Normalization", "starting stage 1: map lookup")
    unresolved = _build_unresolved_sets(posting_key_map, map_key_to_value)
    for d in NormalizationConfig.DOMAINS.value:
        if d == "seniority":
            all_keys = {
                (True, keys["title"]) if keys["seniority"] == "not applicable"
                else (False, keys["seniority"])
                for keys in posting_key_map.values()
            }
        else:
            all_keys = {
                keys[d]
                for keys in posting_key_map.values()
            }

        unresolved_key_count = len(unresolved[d])
        resolved_by_method["map"] += max(0, len(all_keys) - unresolved_key_count)
    print_message("Normalization", "finished stage 1: map lookup")

    # Stage 2: fuzzy match
    print_message("Normalization", "starting stage 2: fuzzy matching")
    for d in NormalizationConfig.DOMAINS.value:
        if not unresolved[d]:
            continue

        if d == "seniority":
            fuzzy_resolved = resolve_with_fuzzy_seniority(
                unresolved_keys=unresolved[d],
                known_key_to_value=map_key_to_value[d],
                threshold_value=NormalizationConfig.FUZZY_VAL_THRESH.value,
                threshold_key=NormalizationConfig.FUZZY_KEY_THRESH.value,
            )
        else:
            fuzzy_resolved = resolve_with_fuzzy_simple(
                unresolved_keys=unresolved[d],
                known_key_to_value=map_key_to_value[d],
                threshold_value=NormalizationConfig.FUZZY_VAL_THRESH.value,
                threshold_key=NormalizationConfig.FUZZY_KEY_THRESH.value,
            )

        if fuzzy_resolved:
            if d == "seniority":
                rows_to_upsert = [
                    {
                        "use_title_key": use_title_key,
                        "source_key": source_key,
                        "value_normalized": fuzzy_result.normalized_val,
                        "method": "fuzzy",
                        "ref_key": fuzzy_result.ref_key,
                    }
                    for (use_title_key, source_key), fuzzy_result in fuzzy_resolved.items()
                ]
            else:
                rows_to_upsert = [
                    {
                        "key_normalized": k,
                        "value_normalized": fuzzy_result.normalized_val,
                        "method": "fuzzy",
                        "ref_key": fuzzy_result.ref_key,
                    }
                    for k, fuzzy_result in fuzzy_resolved.items()
                ]
            repo.upsert_map_rows(d, rows_to_upsert)

            # update current key - normalized value map
            map_key_to_value[d].update(
                {k: fuzzy_result.normalized_val for k, fuzzy_result in fuzzy_resolved.items()}
            )
            
            # update remaining unresolved key
            resolved_keys = set(fuzzy_resolved.keys())
            unresolved[d] = unresolved[d] - resolved_keys
            resolved_by_method["fuzzy"] += len(fuzzy_resolved)
    print_message("Normalization", "finished stage 2: fuzzy matching")
    
    # Stage 3: batch llm
    print_message("Normalization", "starting stage 3: llm normalization")
    for domain_i, d in enumerate(NormalizationConfig.DOMAINS.value):
        print_message("Normalization", f"starting domain {d}")
        if not unresolved[d]:
            continue
        
        # sort so related key can be together => more consistent result from llm
        keys_left = sorted(unresolved[d])
        
        batches = list(_chunks(keys_left, NormalizationConfig.BATCH_SIZE.value))
        for batch_i, batch in enumerate(batches):
            print_message("Normalization", f"domain {d} batch {batch_i+1}/{len(batches)}")
            rows_to_upsert: list[dict] = []

            if d == "seniority":
                raw_senior = [source_key for use_title_key, source_key in batch if not use_title_key]
                raw_title =  [source_key for use_title_key, source_key in batch if use_title_key]

                seniority_res = llm_normalizer.normalize_seniority(raw_senior, raw_title)
                if seniority_res.result != ScrapeResult.SUCCESSFUL:
                    print_message("error", seniority_res.error)
                    return _build_normalization_result(
                        posting_key_map=posting_key_map,
                        map_key_to_value=map_key_to_value,
                        unresolved=unresolved,
                        resolved_by_method=resolved_by_method,
                        error=seniority_res.error
                    )
                if not seniority_res.content:
                    continue

                s1_labels, s2_labels = seniority_res.content
                    
                rows_to_upsert = []

                rows_to_upsert.extend(
                    {
                        "use_title_key": False,
                        "source_key": source_key,
                        "value_normalized": label,
                        "method": "llm",
                        "ref_key": None,
                    }
                    for source_key, label in zip(raw_senior, s1_labels)
                )
                rows_to_upsert.extend(
                    {
                        "use_title_key": True,
                        "source_key": source_key,
                        "value_normalized": label,
                        "method": "llm",
                        "ref_key": None,
                    }
                    for source_key, label in zip(raw_title, s2_labels)
                )
            else:
                llm_res = llm_normalizer.normalize_batch(d, batch)
                if llm_res.result != ScrapeResult.SUCCESSFUL:
                    print_message("error", llm_res.error)
                    return _build_normalization_result(
                        posting_key_map=posting_key_map,
                        map_key_to_value=map_key_to_value,
                        unresolved=unresolved,
                        resolved_by_method=resolved_by_method,
                        error=llm_res.error
                    )
                if not llm_res.content:
                    continue

                rows_to_upsert = [
                    {
                        "key_normalized": key,
                        "value_normalized": value,
                        "method": "llm",
                        "ref_key": None,
                    }
                    for key, value in zip(batch, llm_res.content)
                ]

            if batch_i<len(batches)-1:
                sleep(NormalizationConfig.LLM_INTERVAL.value)
            
            if not rows_to_upsert:
                continue

            repo.upsert_map_rows(d, rows_to_upsert)
            if d == "seniority":
                for r in rows_to_upsert:
                    map_key_to_value[d][(r["use_title_key"], r["source_key"])] = r["value_normalized"]
            else:
                for r in rows_to_upsert:
                    map_key_to_value[d][r["key_normalized"]] = r["value_normalized"]
            resolved_by_method["llm"] += len(rows_to_upsert)

            if d == "seniority":
                resolved_keys = set(batch)
                unresolved[d] = unresolved[d] - resolved_keys
            else:
                resolved_keys = {r["key_normalized"] for r in rows_to_upsert}
                unresolved[d] = unresolved[d] - resolved_keys
                
        if domain_i<len(NormalizationConfig.DOMAINS.value)-1:
            sleep(NormalizationConfig.LLM_INTERVAL.value)
    print_message("Normalization", "finished stage 3: llm normalization")

    print_message("Normalization", "finish pipeline")
    return _build_normalization_result(
        posting_key_map=posting_key_map,
        map_key_to_value=map_key_to_value,
        unresolved=unresolved,
        resolved_by_method=resolved_by_method,
    )
