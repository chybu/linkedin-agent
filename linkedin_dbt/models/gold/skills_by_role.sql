{{ config(materialized='view', schema='gold') }}

select
    f.title_normalized,
    f.seniority,
    ds.skill_name,
    count(*) as job_posting_count,
    count(distinct f.company_id) as company_count
from {{ ref('fact_job_postings') }} f
inner join silver.job_posting_skills jps
    on f.job_posting_raw_id = jps.job_posting_raw_id
inner join silver.dim_skills ds
    on jps.skill_id = ds.skill_id
group by
    f.title_normalized,
    f.seniority,
    ds.skill_name
