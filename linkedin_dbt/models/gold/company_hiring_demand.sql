{{ config(materialized='view', schema='gold') }}

select
    company,
    count(*) as job_posting_count,
    count(distinct title_id) as distinct_roles,
    count(distinct location_id) as distinct_locations,
    count(distinct seniority) as distinct_seniority_levels,
    min(scraped_at) as first_seen_at,
    max(scraped_at) as last_seen_at
from {{ ref('fact_job_postings') }}
group by company
order by job_posting_count desc
