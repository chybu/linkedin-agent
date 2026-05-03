BEGIN;

CREATE TEMP TABLE legacy_jobs_to_import AS
-- create batch number
SELECT
    j.*,
    ((row_number() OVER (
        ORDER BY coalesce(j.created_at, now()), j.job_id
    ) - 1) / 10)::int AS batch_no
FROM public.jobs j
WHERE j.job_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM bronze.job_postings_raw r
      WHERE r.job_id = j.job_id
  );

CREATE TEMP TABLE legacy_import_runs AS
-- create scrape runs table
WITH batches AS (
    SELECT
        batch_no,
        count(*) AS job_count,
        min(coalesce(created_at, now())) AS started_at,
        max(coalesce(created_at, now())) AS finished_at
    FROM legacy_jobs_to_import
    GROUP BY batch_no
),
inserted AS (
    INSERT INTO bronze.scrape_runs (
        keywords,
        status,
        started_at,
        finished_at,
        jobs_seen_count,
        jobs_inserted_count,
        start_index
    )
    SELECT
        '',
        'successful',
        started_at,
        finished_at,
        job_count,
        job_count,
        batch_no * 10
    FROM batches
    ORDER BY batch_no
    RETURNING scrape_run_id, start_index
)
SELECT
    scrape_run_id,
    start_index / 10 AS batch_no
FROM inserted;

-- legacy_import_runs is a table with scrape_run_id and corresponding batch_no
INSERT INTO bronze.job_postings_raw (
    scrape_run_id,
    job_id,
    source_url,
    title_raw,
    company_raw,
    location_raw,
    posted_raw,
    applicants_raw,
    seniority_level_raw,
    employment_type_raw,
    job_function_raw,
    industry_raw,
    description_raw,
    scraped_at
)
SELECT
    r.scrape_run_id,
    j.job_id,
    j.source_url,
    j.title,
    j.company,
    j.location,
    j.posted,
    j.applicants,
    j.seniority_level,
    j.employment_type,
    j.job_function,
    j.industry,
    j.description,
    coalesce(j.created_at, now())
FROM legacy_jobs_to_import j
JOIN legacy_import_runs r
    ON r.batch_no = j.batch_no;

COMMIT;