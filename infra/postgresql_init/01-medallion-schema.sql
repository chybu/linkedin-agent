CREATE SCHEMA IF NOT EXISTS bronze;
CREATE SCHEMA IF NOT EXISTS silver;
CREATE SCHEMA IF NOT EXISTS gold;

CREATE TABLE IF NOT EXISTS bronze.scrape_runs (
    scrape_run_id BIGSERIAL PRIMARY KEY,
    keywords TEXT,
    geo_id TEXT,
    start_index INTEGER,
    time_range TEXT,
    workplace_type TEXT,
    experience_level TEXT,
    job_type TEXT,
    sort_by TEXT,
    status TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ,
    error_message TEXT,
    jobs_seen_count INTEGER,
    jobs_inserted_count INTEGER
);

CREATE TABLE IF NOT EXISTS bronze.job_search_cards_raw (
    search_card_raw_id BIGSERIAL PRIMARY KEY,
    scrape_run_id BIGINT NOT NULL REFERENCES bronze.scrape_runs(scrape_run_id),
    job_id BIGINT,
    title_raw TEXT,
    company_raw TEXT,
    location_raw TEXT,
    source_url TEXT,
    scraped_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS bronze.job_postings_raw (
    job_posting_raw_id BIGSERIAL PRIMARY KEY,
    scrape_run_id BIGINT NOT NULL REFERENCES bronze.scrape_runs(scrape_run_id),
    job_id BIGINT NOT NULL,
    source_url TEXT,
    title_raw TEXT,
    company_raw TEXT,
    location_raw TEXT,
    posted_raw TEXT,
    applicants_raw TEXT,
    seniority_level_raw TEXT,
    employment_type_raw TEXT,
    job_function_raw TEXT,
    industry_raw TEXT,
    description_raw TEXT,
    criteria_payload JSONB,
    raw_payload JSONB,
    scraped_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS bronze.title_normalization_map (
    key_normalized TEXT PRIMARY KEY,
    value_normalized TEXT NOT NULL,
    method TEXT NOT NULL CHECK (method IN ('llm', 'fuzzy')),
    ref_key TEXT REFERENCES bronze.title_normalization_map(key_normalized),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS bronze.location_normalization_map (
    key_normalized TEXT PRIMARY KEY,
    value_normalized TEXT NOT NULL,
    method TEXT NOT NULL CHECK (method IN ('llm', 'fuzzy')),
    ref_key TEXT REFERENCES bronze.location_normalization_map(key_normalized),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS bronze.seniority_normalization_map (
    use_title_key BOOLEAN NOT NULL DEFAULT FALSE,
    source_key TEXT NOT NULL,
    value_normalized TEXT NOT NULL,
    method TEXT NOT NULL CHECK (method IN ('llm', 'fuzzy')),
    ref_key TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (use_title_key, source_key)
);

-- CREATE TABLE IF NOT EXISTS silver.companies (
--     company_id BIGSERIAL PRIMARY KEY,
--     company_name TEXT NOT NULL,
--     company_name_normalized TEXT NOT NULL,
--     created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
-- );

-- CREATE TABLE IF NOT EXISTS silver.locations (
--     location_id BIGSERIAL PRIMARY KEY,
--     location_raw TEXT,
--     location_normalized TEXT NOT NULL,
--     city TEXT,
--     state_region TEXT,
--     country TEXT,
--     is_remote BOOLEAN,
--     created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
-- );

-- CREATE TABLE IF NOT EXISTS silver.job_postings (
--     job_id BIGINT PRIMARY KEY,
--     job_posting_raw_id BIGINT NOT NULL REFERENCES bronze.job_postings_raw(job_posting_raw_id),
--     company_id BIGINT REFERENCES silver.companies(company_id),
--     location_id BIGINT REFERENCES silver.locations(location_id),
--     title TEXT NOT NULL,
--     role_family TEXT NOT NULL,
--     company_name TEXT,
--     location_name TEXT,
--     posted_at DATE,
--     seniority_level_raw TEXT,
--     seniority_level_normalized TEXT,
--     employment_type TEXT,
--     job_function TEXT,
--     industry TEXT,
--     applicant_count INTEGER,
--     description TEXT,
--     source_url TEXT,
--     created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
-- );
