{{ config(
    materialized='incremental',
    unique_key=['scrape_run_id', 'job_posting_raw_id']
) }}

with base as (
    select
        s.scrape_run_id,
        s.job_posting_raw_id,
        s.job_id,

        s.title_raw as title,
        s.title_normalized,

        s.company_raw as company,
        s.location_normalized as location,

        s.seniority_normalized as seniority,
        s.employment_type_raw as employment_type,
        s.industry_raw as industry,

        s.description_raw as description,
        s.source_url,
        s.scraped_at
    from {{ ref('stg_job_postings') }} s
    where coalesce(s.title_normalized, '') <> 'unknown'
      and coalesce(s.location_normalized, '') <> 'unknown'
      and coalesce(s.seniority_normalized, '') <> 'unknown'
      and nullif(coalesce(s.title_normalized, ''), '') is not null
      and nullif(coalesce(s.location_normalized, ''), '') is not null
      and nullif(coalesce(s.seniority_normalized, ''), '') is not null
),

joined as (
    select
        b.scrape_run_id,
        b.job_posting_raw_id,
        b.job_id,

        dt.title_id,
        dc.company_id,
        dl.location_id,

        b.title,
        b.title_normalized,
        b.company,
        b.location,
        b.seniority,

        b.employment_type,
        b.industry,
        b.description,

        b.source_url,
        b.scraped_at
    from base b
    inner join {{ ref('dim_titles') }} dt
        on dt.title_name = b.title_normalized
    inner join {{ ref('dim_companies') }} dc
        on dc.company_name = b.company
    inner join {{ ref('dim_locations') }} dl
        on dl.location_name = b.location
)

select
    scrape_run_id,
    job_posting_raw_id,
    job_id,

    title_id,
    company_id,
    location_id,

    title,
    title_normalized,
    company,
    location,
    seniority,

    employment_type,
    industry,
    description,

    source_url,
    scraped_at
from joined

{% if is_incremental() %}
where not exists (
    select 1
    from {{ this }} f
    where f.scrape_run_id = joined.scrape_run_id
      and f.job_posting_raw_id = joined.job_posting_raw_id
)
{% endif %}