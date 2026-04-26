import re
from typing import Any


def normalize_key(value: str | None) -> str:
    if value is None:
        return ""
    value = value.strip().lower()
    value = re.sub(r"\s+", " ", value)
    return value


def build_posting_key_map(rows: list[dict[str, Any]]) -> dict[int, dict[str, str]]:
    result: dict[int, dict[str, str]] = {}

    for row in rows:
        raw_id = int(row["job_posting_raw_id"])
        result[raw_id] = {
            "title": normalize_key(row.get("title_raw")),
            "location": normalize_key(row.get("location_raw")),
            "seniority": normalize_key(row.get("seniority_level_raw")),
        }

    return result
