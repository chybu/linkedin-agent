from difflib import SequenceMatcher


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


def resolve_with_fuzzy(
    unresolved_keys: set[str],
    candidate_values: set[str],          # from value_normalized
    known_key_to_value: dict[str, str],  # key_normalized -> value_normalized
    threshold_value: float,              # e.g. 0.90
    threshold_key: float,                # e.g. 0.94 (usually stricter)
) -> dict[str, str]:
    """
    Returns: new_key -> resolved normalized value
    Stage 1: match new key to candidate normalized values.
    Stage 2: if stage 1 fails, match new key to known raw keys, then inherit that key's normalized value.
    """
    if not unresolved_keys:
        return {}

    resolved: dict[str, str] = {}
    raw_key_candidates = {k for k in known_key_to_value.keys() if k}
    value_candidates = {v for v in candidate_values if v}

    for key in unresolved_keys:
        if not key:
            continue

        # Stage 1: match to canonical normalized values
        if value_candidates:
            best_val, best_score = _best_match(key, value_candidates)
            if best_val is not None and best_score >= threshold_value:
                resolved[key] = best_val
                continue

        # Stage 2: match to known raw keys, then inherit mapped normalized value
        if raw_key_candidates:
            best_raw_key, best_score = _best_match(key, raw_key_candidates)
            if best_raw_key is not None and best_score >= threshold_key:
                inherited_value = known_key_to_value.get(best_raw_key, "")
                if inherited_value:
                    resolved[key] = inherited_value

    return resolved
