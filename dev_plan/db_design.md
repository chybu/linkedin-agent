# Database Design

This document describes the target Postgres warehouse design for the LinkedIn agent project.

The database follows a medallion structure:

- `bronze`: raw ingestion tables
- `silver`: cleaned and normalized tables
- `gold`: scoring and analytics tables

The goal is to keep raw source data separate from cleaned entities, and keep scoring outputs separate from both.

## Design Principles

- Keep raw and cleaned data separate.
- Keep one row per skill instead of storing skills as comma-separated text.
- Preserve source payloads in `jsonb` where extraction logic may change over time.
- Use `silver` for stable, app-ready entities.
- Use `gold` for deterministic outputs that can be recomputed.
- Keep role family and normalized seniority as plain columns in `silver.job_postings` for MVP instead of separate dimension tables.

## Schema Overview

### Bronze

- `bronze.scrape_runs`
- `bronze.job_search_cards_raw`
- `bronze.job_postings_raw`
- `bronze.resume_uploads_raw`
- `bronze.resume_parse_runs`
- `bronze.resume_profiles_raw`
- `bronze.resume_skills_raw`

### Silver

- `silver.companies`
- `silver.locations`
- `silver.skill_dim`
- `silver.job_postings`
- `silver.job_skills`
- `silver.candidate_profiles`
- `silver.candidate_skills`

### Gold

- `gold.job_market_skill_demand`
- `gold.resume_job_match_features`
- `gold.resume_job_rankings`
- `gold.resume_market_alignment`

## Bronze Tables

### `bronze.scrape_runs`

Purpose:
- One row per scraper execution
- Tracks request parameters and scrape status

Columns:
- `scrape_run_id bigserial primary key`
- `source text not null default 'linkedin'`
- `keywords text`
- `geo_id text`
- `start_index integer`
- `time_range text`
- `workplace_type text`
- `experience_level text`
- `job_type text`
- `sort_by text`
- `status text not null`
- `started_at timestamptz not null default now()`
- `finished_at timestamptz`
- `error_message text`
- `jobs_seen_count integer`
- `jobs_inserted_count integer`

Example:

```json
{
  "scrape_run_id": 101,
  "source": "linkedin",
  "keywords": "data engineer",
  "geo_id": "103644278",
  "start_index": 0,
  "time_range": "r604800",
  "workplace_type": "2",
  "experience_level": "3",
  "job_type": "F",
  "sort_by": "DD",
  "status": "successful",
  "started_at": "2026-04-22T08:15:00Z",
  "finished_at": "2026-04-22T08:18:12Z",
  "error_message": null,
  "jobs_seen_count": 25,
  "jobs_inserted_count": 12
}
```

### `bronze.job_search_cards_raw`

Purpose:
- Stores raw job cards from LinkedIn search results
- Keeps the search-page version of title, company, and location

Columns:
- `search_card_raw_id bigserial primary key`
- `scrape_run_id bigint not null references bronze.scrape_runs(scrape_run_id)`
- `job_id bigint`
- `title_raw text`
- `company_raw text`
- `location_raw text`
- `source_url text`
- `scraped_at timestamptz not null default now()`

Example:

```json
{
  "search_card_raw_id": 9001,
  "scrape_run_id": 101,
  "job_id": 4213370011,
  "title_raw": "Data Engineer",
  "company_raw": "Acme Analytics",
  "location_raw": "New York, NY",
  "source_url": "https://www.linkedin.com/jobs/view/data-engineer-4213370011?position=1&pageNum=0",
  "scraped_at": "2026-04-22T08:15:21Z"
}
```

### `bronze.job_postings_raw`

Purpose:
- Stores raw detailed job posting data
- Preserves the original scrape result before normalization

Columns:
- `job_posting_raw_id bigserial primary key`
- `scrape_run_id bigint not null references bronze.scrape_runs(scrape_run_id)`
- `job_id bigint not null`
- `source_url text`
- `title_raw text`
- `company_raw text`
- `location_raw text`
- `posted_raw text`
- `applicants_raw text`
- `seniority_level_raw text`
- `employment_type_raw text`
- `job_function_raw text`
- `industry_raw text`
- `description_raw text`
- `scraped_at timestamptz not null default now()`

Example:

```json
{
  "job_posting_raw_id": 5001,
  "scrape_run_id": 101,
  "job_id": 4213370011,
  "source_url": "https://www.linkedin.com/jobs/view/data-engineer-4213370011?position=1&pageNum=0",
  "title_raw": "Data Engineer",
  "company_raw": "Acme Analytics",
  "location_raw": "New York, NY",
  "posted_raw": "3 days ago",
  "applicants_raw": "47 applicants",
  "seniority_level_raw": "Associate",
  "employment_type_raw": "Full-time",
  "job_function_raw": "Engineering",
  "industry_raw": "Technology, Information and Internet",
  "description_raw": "We are looking for a Data Engineer with Python, SQL, Airflow, and dbt experience..",
  "scraped_at": "2026-04-22T08:16:04Z"
}
```

### `bronze.resume_uploads_raw`

Purpose:
- Stores the raw uploaded resume text or file reference
- Preserves the original candidate submission

Columns:
- `resume_upload_id bigserial primary key`
- `candidate_external_id text`
- `file_name text`
- `mime_type text`
- `source_text text`
- `storage_path text`
- `uploaded_at timestamptz not null default now()`

Example:

```json
{
  "resume_upload_id": 3001,
  "candidate_external_id": "cand_001",
  "file_name": "alice_nguyen_resume.pdf",
  "mime_type": "application/pdf",
  "source_text": "Alice Nguyen\nSenior Data Analyst...\nSkills: SQL, Python, Tableau, dbt...",
  "storage_path": "uploads/2026/04/alice_nguyen_resume.pdf",
  "uploaded_at": "2026-04-22T09:00:00Z"
}
```

### `bronze.resume_parse_runs`

Purpose:
- Tracks each resume parsing attempt
- Stores parser metadata and raw parser output

Columns:
- `resume_parse_run_id bigserial primary key`
- `resume_upload_id bigint not null references bronze.resume_uploads_raw(resume_upload_id)`
- `parser_name text not null`
- `parser_version text`
- `status text not null`
- `started_at timestamptz not null default now()`
- `finished_at timestamptz`
- `error_message text`
- `raw_output jsonb`

Example:

```json
{
  "resume_parse_run_id": 7001,
  "resume_upload_id": 3001,
  "parser_name": "resume_parser_v1",
  "parser_version": "1.0.0",
  "status": "successful",
  "started_at": "2026-04-22T09:01:00Z",
  "finished_at": "2026-04-22T09:01:03Z",
  "error_message": null,
  "raw_output": {
    "name": "Alice Nguyen",
    "skills": ["SQL", "Python", "dbt", "Tableau"],
    "location": "Brooklyn, New York, United States"
  }
}
```

### `bronze.resume_profiles_raw`

Purpose:
- Stores raw structured profile information extracted from a resume
- Keeps the parser output before standardization

Columns:
- `resume_profile_raw_id bigserial primary key`
- `resume_parse_run_id bigint not null references bronze.resume_parse_runs(resume_parse_run_id)`
- `candidate_name_raw text`
- `headline_raw text`
- `summary_raw text`
- `location_raw text`
- `years_experience_raw text`
- `titles_payload jsonb`
- `education_payload jsonb`
- `experience_payload jsonb`
- `raw_payload jsonb`
- `created_at timestamptz not null default now()`

Example:

```json
{
  "resume_profile_raw_id": 8101,
  "resume_parse_run_id": 7001,
  "candidate_name_raw": "Alice Nguyen",
  "headline_raw": "Senior Data Analyst",
  "summary_raw": "Analytics professional with 5+ years building dashboards and data pipelines.",
  "location_raw": "Brooklyn, New York, United States",
  "years_experience_raw": "5+ years",
  "titles_payload": ["Senior Data Analyst", "Data Analyst"],
  "education_payload": [
    {
      "school": "NYU",
      "degree": "B.S. Computer Science"
    }
  ],
  "experience_payload": [
    {
      "company": "Acme Retail",
      "title": "Senior Data Analyst"
    }
  ],
  "raw_payload": {
    "parser_notes": "confidence high"
  },
  "created_at": "2026-04-22T09:01:04Z"
}
```

### `bronze.resume_skills_raw`

Purpose:
- Stores raw skill strings extracted from the resume
- Preserves parser confidence and source section

Columns:
- `resume_skill_raw_id bigserial primary key`
- `resume_parse_run_id bigint not null references bronze.resume_parse_runs(resume_parse_run_id)`
- `skill_raw text not null`
- `source_section text`
- `confidence numeric(5,4)`
- `created_at timestamptz not null default now()`

Example:

```json
{
  "resume_skill_raw_id": 9101,
  "resume_parse_run_id": 7001,
  "skill_raw": "PostgreSQL",
  "source_section": "Skills",
  "confidence": 0.9800,
  "created_at": "2026-04-22T09:01:05Z"
}
```

## Silver Tables

### `silver.companies`

Purpose:
- Deduplicated company dimension
- Standardized company names for joins and analytics

Columns:
- `company_id bigserial primary key`
- `company_name text not null`
- `company_name_normalized text not null`
- `created_at timestamptz not null default now()`

Example:

```json
{
  "company_id": 201,
  "company_name": "Acme Analytics",
  "company_name_normalized": "acme analytics",
  "created_at": "2026-04-22T08:20:00Z"
}
```

### `silver.locations`

Purpose:
- Standardized location dimension
- Supports filtering and location-fit scoring

Columns:
- `location_id bigserial primary key`
- `location_raw text`
- `location_normalized text not null`
- `city text`
- `state_region text`
- `country text`
- `is_remote boolean`
- `created_at timestamptz not null default now()`

Example:

```json
{
  "location_id": 301,
  "location_raw": "New York, NY",
  "location_normalized": "new york, ny, united states",
  "city": "New York",
  "state_region": "NY",
  "country": "United States",
  "is_remote": false,
  "created_at": "2026-04-22T08:20:30Z"
}
```

### `silver.skill_dim`

Purpose:
- Canonical skill dimension
- Maps fuzzy or variant spellings into one normalized skill

Columns:
- `skill_id bigserial primary key`
- `canonical_skill text not null`
- `normalized_skill text not null`
- `skill_category text`
- `created_at timestamptz not null default now()`

Example:

```json
{
  "skill_id": 401,
  "canonical_skill": "PostgreSQL",
  "normalized_skill": "postgresql",
  "skill_category": "database",
  "created_at": "2026-04-22T08:21:00Z"
}
```

### `silver.job_postings`

Purpose:
- One cleaned current row per job posting
- The main job entity used by scoring and analytics
- Keeps the original title for display, plus a simplified role bucket for grouping

Columns:
- `job_id bigint primary key`
- `job_posting_raw_id bigint not null references bronze.job_postings_raw(job_posting_raw_id)`
- `company_id bigint references silver.companies(company_id)`
- `location_id bigint references silver.locations(location_id)`
- `title text not null`
- `role_family text not null`
- `company_name text`
- `location_name text`
- `posted_at date`
- `seniority_level_raw text`
- `seniority_level_normalized text`
- `employment_type text`
- `job_function text`
- `industry text`
- `applicant_count integer`
- `description text`
- `source_url text`
- `created_at timestamptz not null default now()`

Example:

```json
{
  "job_id": 4213370011,
  "job_posting_raw_id": 5001,
  "company_id": 201,
  "location_id": 301,
  "title": "Data Engineer",
  "role_family": "data engineer",
  "company_name": "Acme Analytics",
  "location_name": "New York, NY",
  "posted_at": "2026-04-19",
  "seniority_level_raw": "Associate",
  "seniority_level_normalized": "mid",
  "employment_type": "Full-time",
  "job_function": "Engineering",
  "industry": "Technology, Information and Internet",
  "applicant_count": 47,
  "description": "We are looking for a Data Engineer with Python, SQL, Airflow, and dbt experience...",
  "source_url": "https://www.linkedin.com/jobs/view/data-engineer-4213370011?position=1&pageNum=0",
  "created_at": "2026-04-22T08:20:45Z",
}
```

### `silver.job_skills`

Purpose:
- One row per extracted job skill
- Links raw skill text to canonicalized skills

Columns:
- `job_skill_id bigserial primary key`
- `job_id bigint not null references silver.job_postings(job_id)`
- `skill_id bigint references silver.skill_dim(skill_id)`
- `skill_raw text not null`
- `normalized_skill text not null`
- `match_weight numeric(6,3)`
- `is_required boolean`
- `extraction_method text`
- `created_at timestamptz not null default now()`

Example:

```json
{
  "job_skill_id": 6001,
  "job_id": 4213370011,
  "skill_id": 401,
  "skill_raw": "Postgres",
  "normalized_skill": "postgresql",
  "match_weight": 0.900,
  "is_required": true,
  "extraction_method": "llm_plus_rules",
  "created_at": "2026-04-22T08:22:00Z"
}
```

### `silver.candidate_profiles`

Purpose:
- One cleaned current row per candidate resume
- Main candidate entity used by scoring

Columns:
- `candidate_id bigserial primary key`
- `resume_upload_id bigint not null references bronze.resume_uploads_raw(resume_upload_id)`
- `latest_resume_parse_run_id bigint not null references bronze.resume_parse_runs(resume_parse_run_id)`
- `candidate_external_id text`
- `candidate_name text`
- `headline text`
- `summary text`
- `location_id bigint references silver.locations(location_id)`
- `years_experience numeric(5,2)`
- `current_title text`
- `current_role_family text`
- `created_at timestamptz not null default now()`
- `updated_at timestamptz not null default now()`

Example:

```json
{
  "candidate_id": 1001,
  "resume_upload_id": 3001,
  "latest_resume_parse_run_id": 7001,
  "candidate_external_id": "cand_001",
  "candidate_name": "Alice Nguyen",
  "headline": "Senior Data Analyst",
  "summary": "Analytics professional with 5+ years building dashboards and pipelines.",
  "location_id": 301,
  "years_experience": 5.00,
  "current_title": "Senior Data Analyst",
  "current_role_family": "data analyst",
  "created_at": "2026-04-22T09:02:00Z",
  "updated_at": "2026-04-22T09:02:00Z"
}
```

### `silver.candidate_skills`

Purpose:
- One row per candidate skill
- Used to compare resume skills to job skills

Columns:
- `candidate_skill_id bigserial primary key`
- `candidate_id bigint not null references silver.candidate_profiles(candidate_id)`
- `skill_id bigint references silver.skill_dim(skill_id)`
- `skill_raw text not null`
- `normalized_skill text not null`
- `evidence_text text`
- `confidence numeric(5,4)`
- `created_at timestamptz not null default now()`

Example:

```json
{
  "candidate_skill_id": 11001,
  "candidate_id": 1001,
  "skill_id": 401,
  "skill_raw": "PostgreSQL",
  "normalized_skill": "postgresql",
  "evidence_text": "Skills: SQL, PostgreSQL, Python, dbt",
  "confidence": 0.9800,
  "created_at": "2026-04-22T09:02:10Z"
}
```

## Gold Tables

### `gold.job_market_skill_demand`

Purpose:
- Aggregated market demand for skills by role and location
- Used for alignment summaries and trend reporting

Columns:
- `role_family text not null`
- `location_scope text not null`
- `skill_id bigint references silver.skill_dim(skill_id)`
- `normalized_skill text not null`
- `job_count integer not null`
- `skill_mention_count integer not null`
- `demand_rank integer`
- `window_start date not null`
- `window_end date not null`
- `created_at timestamptz not null default now()`

Example:

```json
{
  "role_family": "data engineer",
  "location_scope": "united states",
  "skill_id": 401,
  "normalized_skill": "postgresql",
  "job_count": 120,
  "skill_mention_count": 74,
  "demand_rank": 5,
  "window_start": "2026-04-01",
  "window_end": "2026-04-22",
  "created_at": "2026-04-22T10:00:00Z"
}
```

### `gold.resume_job_match_features`

Purpose:
- Deterministic feature table for resume-to-job scoring
- The scoring engine should be built from this table

Columns:
- `candidate_id bigint not null references silver.candidate_profiles(candidate_id)`
- `job_id bigint not null references silver.job_postings(job_id)`
- `matched_skill_count integer not null`
- `missing_skill_count integer not null`
- `matched_skill_ratio numeric(6,4)`
- `title_similarity_score numeric(6,4)`
- `seniority_fit_score numeric(6,4)`
- `location_fit_score numeric(6,4)`
- `experience_fit_score numeric(6,4)`
- `market_demand_score numeric(6,4)`
- `overall_score numeric(6,4)`
- `computed_at timestamptz not null default now()`

Example:

```json
{
  "candidate_id": 1001,
  "job_id": 4213370011,
  "matched_skill_count": 4,
  "missing_skill_count": 2,
  "matched_skill_ratio": 0.6667,
  "title_similarity_score": 0.7200,
  "seniority_fit_score": 0.8500,
  "location_fit_score": 1.0000,
  "experience_fit_score": 0.9000,
  "market_demand_score": 0.7800,
  "overall_score": 0.8125,
  "computed_at": "2026-04-22T10:10:00Z"
}
```

### `gold.resume_job_rankings`

Purpose:
- Final ranked jobs for a candidate
- Main result table for user-facing recommendations

Columns:
- `candidate_id bigint not null references silver.candidate_profiles(candidate_id)`
- `job_id bigint not null references silver.job_postings(job_id)`
- `rank_position integer not null`
- `overall_score numeric(6,4) not null`
- `matched_skills text[]`
- `missing_skills text[]`
- `top_reasons jsonb`
- `computed_at timestamptz not null default now()`

Example:

```json
{
  "candidate_id": 1001,
  "job_id": 4213370011,
  "rank_position": 3,
  "overall_score": 0.8125,
  "matched_skills": ["sql", "python", "postgresql", "dbt"],
  "missing_skills": ["airflow", "snowflake"],
  "top_reasons": {
    "strengths": ["strong SQL overlap", "good title similarity", "same location"],
    "risks": ["missing Airflow", "missing Snowflake"]
  },
  "computed_at": "2026-04-22T10:11:00Z"
}
```

### `gold.resume_market_alignment`

Purpose:
- Candidate-level summary of market fit
- Best table for agent explanations and dashboards

Columns:
- `candidate_id bigint primary key references silver.candidate_profiles(candidate_id)`
- `target_role_family text`
- `target_location_scope text`
- `market_alignment_score numeric(6,4)`
- `top_missing_skills text[]`
- `top_strengths text[]`
- `improvement_priorities jsonb`
- `computed_at timestamptz not null default now()`

Example:

```json
{
  "candidate_id": 1001,
  "target_role_family": "data engineer",
  "target_location_scope": "united states",
  "market_alignment_score": 0.7400,
  "top_missing_skills": ["airflow", "spark", "snowflake"],
  "top_strengths": ["sql", "python", "postgresql"],
  "improvement_priorities": {
    "priority_1": "Build and document one Airflow pipeline project",
    "priority_2": "Add a cloud warehouse project using Snowflake or BigQuery"
  },
  "computed_at": "2026-04-22T10:12:00Z"
}
```

## Relationship Summary

Flow:

1. Scraper execution creates a row in `bronze.scrape_runs`.
2. Search results are stored in `bronze.job_search_cards_raw`.
3. Job detail pages are stored in `bronze.job_postings_raw`.
4. Resume uploads land in `bronze.resume_uploads_raw`.
5. Resume parsing metadata lands in `bronze.resume_parse_runs`.
6. Cleaned entities are built in `silver`.
7. Match features and rankings are built in `gold`.

Key relationships:

- `bronze.job_search_cards_raw.scrape_run_id -> bronze.scrape_runs.scrape_run_id`
- `bronze.job_postings_raw.scrape_run_id -> bronze.scrape_runs.scrape_run_id`
- `bronze.resume_parse_runs.resume_upload_id -> bronze.resume_uploads_raw.resume_upload_id`
- `bronze.resume_profiles_raw.resume_parse_run_id -> bronze.resume_parse_runs.resume_parse_run_id`
- `bronze.resume_skills_raw.resume_parse_run_id -> bronze.resume_parse_runs.resume_parse_run_id`
- `silver.job_postings.latest_job_posting_raw_id -> bronze.job_postings_raw.job_posting_raw_id`
- `silver.job_postings.company_id -> silver.companies.company_id`
- `silver.job_postings.location_id -> silver.locations.location_id`
- `silver.job_skills.job_id -> silver.job_postings.job_id`
- `silver.job_skills.skill_id -> silver.skill_dim.skill_id`
- `silver.candidate_profiles.resume_upload_id -> bronze.resume_uploads_raw.resume_upload_id`
- `silver.candidate_profiles.latest_resume_parse_run_id -> bronze.resume_parse_runs.resume_parse_run_id`
- `silver.candidate_profiles.location_id -> silver.locations.location_id`
- `silver.candidate_skills.candidate_id -> silver.candidate_profiles.candidate_id`
- `silver.candidate_skills.skill_id -> silver.skill_dim.skill_id`

## Recommended MVP Build Order

1. Create schemas `bronze`, `silver`, `gold`.
2. Build `bronze.scrape_runs`, `bronze.job_search_cards_raw`, and `bronze.job_postings_raw`.
3. Update the scraper to write raw job data into bronze.
4. Build `bronze.resume_uploads_raw` and `bronze.resume_parse_runs`.
5. Build `silver.skill_dim`, `silver.locations`, and `silver.companies`.
6. Build `silver.job_postings` and `silver.job_skills`.
7. Build `silver.candidate_profiles` and `silver.candidate_skills`.
8. Build `gold.resume_job_match_features`.
9. Build `gold.resume_job_rankings` and `gold.resume_market_alignment`.

## Smallest Practical MVP

If you want the smallest version that still supports matching, start with:

- `bronze.scrape_runs`
- `bronze.job_postings_raw`
- `bronze.resume_uploads_raw`
- `bronze.resume_parse_runs`
- `silver.skill_dim`
- `silver.job_postings`
- `silver.job_skills`
- `silver.candidate_profiles`
- `silver.candidate_skills`
- `gold.resume_job_match_features`
- `gold.resume_job_rankings`
- `gold.resume_market_alignment`

This gives you raw traceability, normalized job and candidate entities, and enough gold output to support ranking and explanation.
