{{ config(materialized='view', schema='gold') }}

select
    location,
    count(*) as job_posting_count,
    count(distinct company_id) as company_count,
    count(distinct title_id) as title_count
from {{ ref('fact_job_postings') }}
group by location
order by job_posting_count desc