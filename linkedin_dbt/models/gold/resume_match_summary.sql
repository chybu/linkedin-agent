with scores as (
    select
        resume_job_semantic_score_id,
        resume_parse_id,
        job_posting_raw_id,
        semantic_score,
        cleared_count,
        total_requirement_count,
        scored_at
    from {{ source('silver', 'fact_resume_job_semantic_scores') }}
),

jobs as (
    select
        job_posting_raw_id,
        title_normalized,
        company_name,
        location,
        seniority,
        source_url
    from {{ ref('fact_job_postings') }}
)

select
    s.resume_job_semantic_score_id,
    s.resume_parse_id,
    s.job_posting_raw_id,
    j.title_normalized,
    j.company_name,
    j.location,
    j.seniority,
    j.source_url,
    s.semantic_score,
    s.cleared_count,
    s.total_requirement_count,
    round(
        s.cleared_count::numeric
        / nullif(s.total_requirement_count, 0)
        * 100,
        2
    ) as cleared_requirement_pct,
    s.scored_at
from scores s
left join jobs j
    on s.job_posting_raw_id = j.job_posting_raw_id
