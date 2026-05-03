{{ config(
    materialized='incremental',
    unique_key=['scrape_run_id', 'job_posting_raw_id']
) }}

{% set ready_ids = var('ready_job_posting_raw_ids', []) %}

with input_ids as (

    {% if ready_ids | length > 0 %}
    -- unnest: un-nest the value in the array into rows (each value is a row)
    select unnest(array[{{ ready_ids | join(',') }}]::bigint[]) as job_posting_raw_id
    {% else %}
    select null::bigint as job_posting_raw_id where false
    {% endif %}

),

mapped as (
    select distinct
        r.scrape_run_id,
        r.job_posting_raw_id,
        now() as ready_at
    from bronze.job_postings_raw r
    inner join input_ids i
        on r.job_posting_raw_id = i.job_posting_raw_id
)

select * from mapped
