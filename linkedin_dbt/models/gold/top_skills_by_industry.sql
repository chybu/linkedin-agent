{{ config(materialized='view', schema='gold') }}

with skill_demand as (
    select
        coalesce(nullif(trim(f.industry), ''), 'Unknown') as industry,
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
    group by
        coalesce(nullif(trim(f.industry), ''), 'Unknown'),
        ds.skill_name
),

ranked as (
    select
        industry,
        skill_name,
        job_posting_count,
        company_count,
        title_count,
        location_count,
        dense_rank() over (
            partition by industry
            order by job_posting_count desc, skill_name
        ) as skill_rank
    from skill_demand
)

select
    industry,
    skill_rank,
    skill_name,
    job_posting_count,
    company_count,
    title_count,
    location_count
from ranked
where skill_rank <= 20
order by
    industry,
    skill_rank,
    skill_name
