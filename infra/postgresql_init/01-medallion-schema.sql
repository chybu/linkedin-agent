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

CREATE TABLE IF NOT EXISTS bronze.staging_ready_job_postings (
    scrape_run_id BIGINT NOT NULL,
    job_posting_raw_id BIGINT NOT NULL,
    ready_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (scrape_run_id, job_posting_raw_id),
    FOREIGN KEY (scrape_run_id)
        REFERENCES bronze.scrape_runs(scrape_run_id),
    FOREIGN KEY (job_posting_raw_id)
        REFERENCES bronze.job_postings_raw(job_posting_raw_id)
);

CREATE TABLE IF NOT EXISTS bronze.normalization_process_runs (
    normalization_process_run_id BIGSERIAL PRIMARY KEY,

    scrape_run_ids BIGINT[] NOT NULL,

    status TEXT NOT NULL CHECK (
        status IN ('running', 'successful', 'failed')
    ),

    stage TEXT NOT NULL CHECK (
        stage IN ('normalization', 'dbt', 'skill_extraction')
    ),

    error TEXT,

    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ
);


CREATE TABLE IF NOT EXISTS silver.dim_skills (
    skill_id BIGSERIAL PRIMARY KEY,
    skill_name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS silver.job_posting_skills (
    job_posting_raw_id BIGINT NOT NULL,
    skill_id BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    PRIMARY KEY (job_posting_raw_id, skill_id),

    FOREIGN KEY (job_posting_raw_id)
        REFERENCES bronze.job_postings_raw(job_posting_raw_id),

    FOREIGN KEY (skill_id)
        REFERENCES silver.dim_skills(skill_id)
);

