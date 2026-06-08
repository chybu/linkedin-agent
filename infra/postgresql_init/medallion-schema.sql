CREATE SCHEMA IF NOT EXISTS bronze;
CREATE SCHEMA IF NOT EXISTS silver;
CREATE SCHEMA IF NOT EXISTS gold;

CREATE TABLE IF NOT EXISTS bronze.run_scrapes (
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

CREATE TABLE IF NOT EXISTS bronze.raw_job_search_cards (
    search_card_raw_id BIGSERIAL PRIMARY KEY,
    scrape_run_id BIGINT NOT NULL REFERENCES bronze.run_scrapes(scrape_run_id),
    job_id BIGINT,
    title_raw TEXT,
    company_raw TEXT,
    location_raw TEXT,
    source_url TEXT,
    scraped_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS bronze.raw_job_postings (
    job_posting_raw_id BIGSERIAL PRIMARY KEY,
    scrape_run_id BIGINT NOT NULL REFERENCES bronze.run_scrapes(scrape_run_id),
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

CREATE TABLE IF NOT EXISTS bronze.map_job_description_cleaning (
    job_posting_raw_id BIGINT PRIMARY KEY,
    description_raw TEXT,
    description_cleaned TEXT NOT NULL,

    FOREIGN KEY (job_posting_raw_id)
        REFERENCES bronze.raw_job_postings(job_posting_raw_id)
);

CREATE TABLE IF NOT EXISTS bronze.map_normalized_job_titles (
    key_normalized TEXT PRIMARY KEY,
    value_normalized TEXT NOT NULL,
    method TEXT NOT NULL CHECK (method IN ('llm', 'fuzzy')),
    ref_key TEXT REFERENCES bronze.map_normalized_job_titles(key_normalized),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS bronze.map_normalized_locations (
    key_normalized TEXT PRIMARY KEY,
    value_normalized TEXT NOT NULL,
    method TEXT NOT NULL CHECK (method IN ('llm', 'fuzzy')),
    ref_key TEXT REFERENCES bronze.map_normalized_locations(key_normalized),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS bronze.map_normalized_seniority_levels (
    use_title_key BOOLEAN NOT NULL DEFAULT FALSE,
    source_key TEXT NOT NULL,
    value_normalized TEXT NOT NULL,
    method TEXT NOT NULL CHECK (method IN ('llm', 'fuzzy')),
    ref_key TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (use_title_key, source_key)
);

CREATE TABLE IF NOT EXISTS bronze.ctl_ready_job_postings (
    scrape_run_id BIGINT NOT NULL,
    job_posting_raw_id BIGINT NOT NULL,
    ready_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (scrape_run_id, job_posting_raw_id),
    FOREIGN KEY (scrape_run_id)
        REFERENCES bronze.run_scrapes(scrape_run_id),
    FOREIGN KEY (job_posting_raw_id)
        REFERENCES bronze.raw_job_postings(job_posting_raw_id)
);

CREATE TABLE IF NOT EXISTS bronze.run_normalization_processes (
    normalization_process_run_id BIGSERIAL PRIMARY KEY,

    scrape_run_ids BIGINT[] NOT NULL,

    status TEXT NOT NULL CHECK (
        -- use ScrapeResult enum
        status IN ('running', 'successful', 'failed')
    ),

    stage TEXT NOT NULL CHECK (
        -- have an enum ProcessStage class in schema.py
        stage IN (
            'normalization',
            'dbt',
            'description_cleaning',
            'skill_extraction'
        )
    ),

    error TEXT,

    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS bronze.raw_resume_parses (
    resume_parse_id BIGSERIAL PRIMARY KEY,
    resume_file_name TEXT NOT NULL,
    resume_md TEXT NOT NULL,
    extracted_experience_project_bullets TEXT NOT NULL,
    extracted_evidence_hash TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS silver.dim_skills (
    skill_id BIGSERIAL PRIMARY KEY,
    skill_name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS silver.bridge_job_posting_skills (
    job_posting_raw_id BIGINT NOT NULL,
    skill_id BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    PRIMARY KEY (job_posting_raw_id, skill_id),

    FOREIGN KEY (job_posting_raw_id)
        REFERENCES bronze.raw_job_postings(job_posting_raw_id),

    FOREIGN KEY (skill_id)
        REFERENCES silver.dim_skills(skill_id)
);

CREATE TABLE IF NOT EXISTS silver.bridge_resume_parse_skills (
    resume_parse_id BIGINT NOT NULL,
    skill_id BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    PRIMARY KEY (resume_parse_id, skill_id),

    FOREIGN KEY (resume_parse_id)
        REFERENCES bronze.raw_resume_parses(resume_parse_id),

    FOREIGN KEY (skill_id)
        REFERENCES silver.dim_skills(skill_id)
);

CREATE TABLE IF NOT EXISTS silver.fact_resume_job_semantic_scores (
    resume_job_semantic_score_id BIGSERIAL PRIMARY KEY,
    resume_parse_id BIGINT NOT NULL,
    job_posting_raw_id BIGINT NOT NULL,
    semantic_score NUMERIC(5, 2) NOT NULL,
    embedding_model TEXT NOT NULL,
    cleared_count INTEGER NOT NULL,
    total_requirement_count INTEGER NOT NULL,
    scored_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_resume_job_semantic_scores_resume_job_model
        UNIQUE (resume_parse_id, job_posting_raw_id, embedding_model),

    FOREIGN KEY (resume_parse_id)
        REFERENCES bronze.raw_resume_parses(resume_parse_id),

    FOREIGN KEY (job_posting_raw_id)
        REFERENCES bronze.raw_job_postings(job_posting_raw_id)
);

CREATE TABLE IF NOT EXISTS silver.fact_resume_job_semantic_requirement_matches (
    resume_job_semantic_score_id BIGINT NOT NULL,
    requirement_index INTEGER NOT NULL,
    jd_requirement TEXT NOT NULL,
    resume_bullet_point TEXT,
    similarity_score NUMERIC(8, 6) NOT NULL,
    is_satisfied BOOLEAN NOT NULL,

    PRIMARY KEY (resume_job_semantic_score_id, requirement_index),

    FOREIGN KEY (resume_job_semantic_score_id)
        REFERENCES silver.fact_resume_job_semantic_scores(resume_job_semantic_score_id)
);

CREATE TABLE IF NOT EXISTS silver.fact_resume_job_skill_scores (
    resume_job_skill_score_id BIGSERIAL PRIMARY KEY,
    resume_parse_id BIGINT NOT NULL,
    job_posting_raw_id BIGINT NOT NULL,
    skill_match_score NUMERIC(5, 2) NOT NULL,
    matched_skill_count INTEGER NOT NULL,
    total_job_skill_count INTEGER NOT NULL,
    missing_skill_count INTEGER NOT NULL,
    fuzzy_threshold NUMERIC(4, 2) NOT NULL,
    scored_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_resume_job_skill_scores_resume_job_threshold
        UNIQUE (resume_parse_id, job_posting_raw_id, fuzzy_threshold),

    FOREIGN KEY (resume_parse_id)
        REFERENCES bronze.raw_resume_parses(resume_parse_id),

    FOREIGN KEY (job_posting_raw_id)
        REFERENCES bronze.raw_job_postings(job_posting_raw_id)
);

CREATE TABLE IF NOT EXISTS silver.fact_resume_job_skill_matches (
    resume_job_skill_score_id BIGINT NOT NULL,
    job_skill_id BIGINT NOT NULL,
    job_skill_name TEXT NOT NULL,
    matched_resume_skill_id BIGINT,
    matched_resume_skill_name TEXT,
    fuzzy_score NUMERIC(8, 6) NOT NULL,
    is_matched BOOLEAN NOT NULL,

    PRIMARY KEY (resume_job_skill_score_id, job_skill_id),

    FOREIGN KEY (resume_job_skill_score_id)
        REFERENCES silver.fact_resume_job_skill_scores(resume_job_skill_score_id),

    FOREIGN KEY (job_skill_id)
        REFERENCES silver.dim_skills(skill_id),

    FOREIGN KEY (matched_resume_skill_id)
        REFERENCES silver.dim_skills(skill_id)
);

CREATE TABLE IF NOT EXISTS silver.fact_resume_job_complete_scores (
    resume_job_semantic_score_id BIGINT NOT NULL,
    resume_job_skill_score_id BIGINT NOT NULL,
    resume_parse_id BIGINT NOT NULL,
    job_posting_raw_id BIGINT NOT NULL,
    semantic_score NUMERIC(5, 2) NOT NULL,
    skill_match_score NUMERIC(5, 2) NOT NULL,
    complete_score NUMERIC(5, 2) NOT NULL,
    semantic_weight NUMERIC(6, 4) NOT NULL,
    skill_weight NUMERIC(6, 4) NOT NULL,
    scored_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    PRIMARY KEY (resume_job_semantic_score_id, resume_job_skill_score_id),

    FOREIGN KEY (resume_job_semantic_score_id)
        REFERENCES silver.fact_resume_job_semantic_scores(resume_job_semantic_score_id),

    FOREIGN KEY (resume_job_skill_score_id)
        REFERENCES silver.fact_resume_job_skill_scores(resume_job_skill_score_id),

    FOREIGN KEY (resume_parse_id)
        REFERENCES bronze.raw_resume_parses(resume_parse_id),

    FOREIGN KEY (job_posting_raw_id)
        REFERENCES bronze.raw_job_postings(job_posting_raw_id)
);
