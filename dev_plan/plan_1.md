# Plan 1

## Goal For Today

Get one end-to-end pipeline working:

- scraper writes raw data to `bronze`
- dbt transforms raw data into `silver`
- cleaned jobs, companies, and locations are visible in Postgres

## Checklist

1. Create the warehouse schemas.
- `bronze`
- `silver`
- optionally `gold` now, even if unused today

2. Create the bronze tables first.
- `bronze.scrape_runs`
- `bronze.job_search_cards_raw`
- `bronze.job_postings_raw`

3. Create the silver target tables or dbt models.
- `silver.companies`
- `silver.locations`
- `silver.job_postings`

4. Update the scraper and database code so it only writes to bronze.
- create one row in `bronze.scrape_runs` at the start of each run
- write search card rows to `bronze.job_search_cards_raw`
- write detailed posting rows to `bronze.job_postings_raw`
- update scrape run status and counts when the run finishes

5. Build dbt models for silver.
- staging model for raw job postings
- company model
- location model
- cleaned job postings model

6. Put cleaning logic in dbt instead of scraper code.
- normalize company names
- normalize locations
- derive `role_family`
- keep `seniority_level_raw`
- derive `seniority_level_normalized` only if there is a reliable rule

7. Run one real scrape and validate the full path.
- bronze tables receive rows
- silver tables populate correctly
- one job maps to one cleaned company and one cleaned location
- `role_family` looks correct for a sample of jobs

## Important Rule

The scraper should only write to bronze.

Do not have scraper code write directly to:

- `silver.companies`
- `silver.locations`
- `silver.job_postings`

Let dbt own the move from bronze to silver.

## Suggested Work Order

1. Write the DDL for bronze and silver.
2. Update the Python write path to bronze.
3. Add dbt models for silver.
4. Run one end-to-end test.
5. Fix any normalization issues found during validation.

## Good Stopping Point

Today is successful if:

- a scrape creates a row in `bronze.scrape_runs`
- raw search cards and job postings land in bronze
- dbt builds cleaned rows in `silver.job_postings`
- company, location, and `role_family` look usable
