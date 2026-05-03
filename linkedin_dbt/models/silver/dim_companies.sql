{{ config(
    materialized='incremental',
    unique_key='company_id'
) }}

with base as (
    select distinct
        company_raw as company_name
    from {{ ref('stg_job_postings') }}
    where nullif(regexp_replace(trim(coalesce(company_raw, '')), '\s+', ' ', 'g'), '') is not null
),

new_rows as (
    select
        company_name,
        row_number() over (order by company_name) as rn
    from base
    {% if is_incremental() %}
    where not exists (
        select 1
        from {{ this }} d
        where d.company_name = base.company_name
    )
    {% endif %}
),

max_id as (
    {% if is_incremental() %}
    select coalesce(max(company_id), 0) as max_company_id
    from {{ this }}
    {% else %}
    select 0 as max_company_id
    {% endif %}
)

select
    (select max_company_id from max_id) + rn as company_id,
    company_name
from new_rows