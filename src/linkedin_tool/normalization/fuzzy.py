from difflib import SequenceMatcher
from linkedin_tool.schema import FuzzyResult

def _token_sort(s: str) -> str:
    return " ".join(sorted(s.split()))


def _score(a: str, b: str) -> float:
    return SequenceMatcher(None, _token_sort(a), _token_sort(b)).ratio()


def _best_match(query: str, candidates: set[str]) -> tuple[str | None, float]:
    best_val = None
    best_score = -1.0

    for cand in candidates:
        s = _score(query, cand)
        if s > best_score:
            best_score = s
            best_val = cand

    return best_val, best_score

def resolve_with_fuzzy_simple(
    unresolved_keys: set[str],
    known_key_to_value: dict[str, str],
    threshold_value: float,
    threshold_key: float,
) -> dict[str, FuzzyResult]:
    if not unresolved_keys:
        return {}

    resolved: dict[str, FuzzyResult] = {}
    value_candidates = set(known_key_to_value.values())
    raw_key_candidates = set(known_key_to_value.keys())

    for key in unresolved_keys:
        if not key:
            continue
        
        # Stage 1: match raw key to known canonical values
        best_val, best_score = _best_match(key, value_candidates)
        if best_val is not None and best_score >= threshold_value:
            resolved[key] = FuzzyResult(key, best_val)
            continue

        # Stage 2: match raw key to known map keys and inherit mapped value
        best_raw_key, best_score = _best_match(key, raw_key_candidates)
        if best_raw_key is not None and best_score >= threshold_key:
            inherited_value = known_key_to_value[best_raw_key]
            resolved[key] = FuzzyResult(key, inherited_value, best_raw_key)

    return resolved

def resolve_with_fuzzy_seniority(
    unresolved_keys: set[tuple[bool, str]],
    known_key_to_value: dict[tuple[bool, str], str],
    threshold_value: float,
    threshold_key: float,
) -> dict[tuple[bool, str], FuzzyResult]:
    if not unresolved_keys:
        return {}

    resolved: dict[tuple[bool, str], FuzzyResult] = {}
    # Candidate key pools split by source type
    value_candidates_by_type = {
        False: set(),
        True: set()
    }
    source_candidate_by_type = {
        False: set(),
        True: set()
    }
    for (use_title_key, source_key), value in known_key_to_value.items():            
        value_candidates_by_type[use_title_key].add(value)
        
        source_candidate_by_type[use_title_key].add(source_key)

    for key in unresolved_keys:
        use_title_key, source_key = key

        # Stage 1: compare against value candidates of same source type.
        stage1_candidates = value_candidates_by_type[use_title_key]
        if stage1_candidates:
            best_val, best_score = _best_match(source_key, stage1_candidates)
            if best_val is not None and best_score >= threshold_value:
                resolved[key] = FuzzyResult(str(key), best_val)
                continue

        # Stage 2: fuzzy against existing source keys of the same type.
        raw_key_candidates = source_candidate_by_type[use_title_key]

        best_raw_key_text, best_score = _best_match(source_key, raw_key_candidates)
        if best_raw_key_text is not None and best_score >= threshold_key:
            matched_key = (use_title_key, best_raw_key_text)
            inherited_value = known_key_to_value[matched_key]
            resolved[key] = FuzzyResult(str(key), inherited_value, best_raw_key_text)

    return resolved