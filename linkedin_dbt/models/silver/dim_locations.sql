{{ config(
    materialized='incremental',
    unique_key='location_id'
) }}

with base as (
    select distinct
        location_normalized as location_name
    from {{ ref('stg_job_postings') }}
    where nullif(trim(coalesce(location_normalized, '')), '') is not null
        and lower(trim(location_normalized)) <> 'unknown'
),

new_rows as (
    select
        location_name,
        row_number() over (order by location_name) as rn
    from base
    {% if is_incremental() %}
    where not exists (
        select 1
        from {{ this }} d
        where d.location_name = base.location_name
    )
    {% endif %}
),

max_id as (
    {% if is_incremental() %}
    select coalesce(max(location_id), 0) as max_location_id
    from {{ this }}
    {% else %}
    select 0 as max_location_id
    {% endif %}
)

select
    (select max_location_id from max_id) + rn as location_id,
    location_name
from new_rows
