{{ config(materialized='view', schema='gold') }}

select
    title_normalized,
    location,
    seniority,
    employment_type,
    industry,
    count(*) as job_posting_count,
    count(distinct company_id) as company_count,
    min(scraped_at) as first_seen_at,
    max(scraped_at) as last_seen_at
from {{ ref('fact_job_postings') }}
group by
    title_normalized,
    location,
    seniority,
    employment_type,
    industry
