{{ config(
    materialized='incremental',
    unique_key=['scrape_run_id', 'job_posting_raw_id']
) }}

-- cannot use view because this table will be reused multiple times=> view requires rebuild it in every time

with ready as (
    select
        scrape_run_id,
        job_posting_raw_id
        -- ref to the dbt model, not actual table
    from {{ source('bronze', 'staging_ready_job_postings') }}
),

raw as (
    select
        r.scrape_run_id,
        r.job_posting_raw_id,
        r.job_id,
        r.title_raw,
        r.location_raw,
        r.company_raw,
        r.source_url,
        r.scraped_at,
        r.seniority_level_raw,
        r.employment_type_raw,
        r.job_function_raw,
        r.industry_raw,
        r.description_raw,

        -- normalized keys used to join normalization maps
        -- needed to match the same cleaning strategy in keys.py
        regexp_replace(lower(trim(coalesce(r.title_raw, ''))), '\s+', ' ', 'g') as title_key_norm,
        regexp_replace(lower(trim(coalesce(r.location_raw, ''))), '\s+', ' ', 'g') as location_key_norm,
        regexp_replace(lower(trim(coalesce(r.seniority_level_raw, ''))), '\s+', ' ', 'g') as seniority_key_norm
    from bronze.job_postings_raw r
    inner join ready rd
        on r.scrape_run_id = rd.scrape_run_id
       and r.job_posting_raw_id = rd.job_posting_raw_id
),

title_map as (
    select
        key_normalized,
        value_normalized as title_normalized
    from bronze.title_normalization_map
),

location_map as (
    select
        key_normalized,
        value_normalized as location_normalized
    from bronze.location_normalization_map
),

seniority_map as (
    select
        use_title_key,
        source_key,
        value_normalized as seniority_normalized
    from bronze.seniority_normalization_map
)

select
    raw.scrape_run_id,
    raw.job_posting_raw_id,
    raw.job_id,

    raw.title_raw,
    raw.company_raw,
    raw.location_raw,
    raw.source_url,
    raw.scraped_at,

    raw.seniority_level_raw,
    raw.employment_type_raw,
    raw.job_function_raw,
    raw.industry_raw,
    raw.description_raw,

    tm.title_normalized,
    lm.location_normalized,
    sm.seniority_normalized

from raw
left join title_map tm
    on raw.title_key_norm = tm.key_normalized
left join location_map lm
    on raw.location_key_norm = lm.key_normalized
left join seniority_map sm
    on (
        raw.seniority_key_norm = 'not applicable'
        and sm.use_title_key = true
        and sm.source_key = raw.title_key_norm
    )
    or (
        raw.seniority_key_norm <> 'not applicable'
        and sm.use_title_key = false
        and sm.source_key = raw.seniority_key_norm
    )
