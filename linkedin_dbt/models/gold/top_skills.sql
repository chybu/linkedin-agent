{{ config(materialized='view', schema='gold') }}

select
    ds.skill_name,
    count(*) as job_posting_count,
    count(distinct f.company_id) as company_count,
    count(distinct f.title_id) as title_count,
    count(distinct f.location_id) as location_count
from {{ ref('fact_job_postings') }} f
inner join silver.job_posting_skills jps
    on f.job_posting_raw_id = jps.job_posting_raw_id
inner join silver.dim_skills ds
    on jps.skill_id = ds.skill_id
group by ds.skill_name
order by job_posting_count desc
