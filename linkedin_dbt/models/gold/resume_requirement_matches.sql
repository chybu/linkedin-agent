with matches as (
    select
        resume_job_semantic_score_id,
        requirement_index,
        jd_requirement,
        resume_bullet_point,
        similarity_score,
        is_satisfied
    from {{ source('silver', 'fact_resume_job_semantic_requirement_matches') }}
),

scores as (
    select
        resume_job_semantic_score_id,
        resume_parse_id,
        job_posting_raw_id,
        semantic_score,
        scored_at
    from {{ source('silver', 'fact_resume_job_semantic_scores') }}
),

jobs as (
    select
        job_posting_raw_id,
        title_normalized,
        company,
        source_url
    from {{ ref('fact_job_postings') }}
)

select
    m.resume_job_semantic_score_id,
    s.resume_parse_id,
    s.job_posting_raw_id,
    j.title_normalized,
    j.company,
    j.source_url,
    s.semantic_score,
    s.scored_at,
    m.requirement_index,
    m.jd_requirement,
    m.resume_bullet_point,
    m.similarity_score,
    m.is_satisfied,
    case
        when m.is_satisfied then 'satisfied'
        else 'missing'
    end as requirement_status
from matches m
inner join scores s
    on m.resume_job_semantic_score_id = s.resume_job_semantic_score_id
left join jobs j
    on s.job_posting_raw_id = j.job_posting_raw_id
