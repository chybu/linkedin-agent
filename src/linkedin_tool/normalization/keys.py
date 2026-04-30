import re

def clean_key(value: str | None) -> str:
    """
    trimmed and colapse extra space in the key
    """
    
    if value is None:
        return ""
    
    value = value.strip().lower()
    value = re.sub(r"\s+", " ", value)
    return value


def build_posting_key_map(rows: list[dict[str, object]]) -> dict[int, dict[str, str]]:
    """
    build a dictionary with job_posting_raw_id as the key
    and cleaned(trim, collapse space) title, location, seniortiy as value
    """
    
    result: dict[int, dict[str, str]] = {}

    for row in rows:
        raw_id = int(row["job_posting_raw_id"])
        
        cleaned_title = clean_key(row.get("title_raw"))
        if not cleaned_title: continue
        
        cleaned_location = clean_key(row.get("location_raw"))
        if not cleaned_location: continue
        
        cleaned_seniority = clean_key(row.get("seniority_level_raw"))
        if not cleaned_seniority: continue
        
        result[raw_id] = {
            "title": cleaned_title,
            "location": cleaned_location,
            "seniority": cleaned_seniority,
        }

    return result
