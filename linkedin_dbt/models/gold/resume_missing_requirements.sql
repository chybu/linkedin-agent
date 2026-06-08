select
    resume_job_semantic_score_id,
    resume_parse_id,
    job_posting_raw_id,
    title_normalized,
    company_name,
    source_url,
    semantic_score,
    scored_at,
    requirement_index,
    jd_requirement,
    similarity_score
from {{ ref('resume_requirement_matches') }}
where not is_satisfied
