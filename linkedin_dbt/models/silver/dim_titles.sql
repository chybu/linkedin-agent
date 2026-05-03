{{ config(
    materialized='incremental',
    unique_key='title_id'
) }}

with base as (
    select distinct
        title_normalized as title_name
    from {{ ref('stg_job_postings') }}
    where nullif(trim(coalesce(title_normalized, '')), '') is not null
      and lower(trim(title_normalized)) <> 'unknown'
),

new_rows as (
    select
        title_name,
        row_number() over (order by title_name) as rn
    from base
    {% if is_incremental() %}
    where not exists (
        select 1
        from {{ this }} d
        where d.title_name = base.title_name
    )
    {% endif %}
),

max_id as (
    {% if is_incremental() %}
    select coalesce(max(title_id), 0) as max_title_id
    from {{ this }}
    {% else %}
    select 0 as max_title_id
    {% endif %}
)

select
    (select max_title_id from max_id) + rn as title_id,
    title_name
from new_rows
