CREATE SCHEMA IF NOT EXISTS app;

CREATE TABLE IF NOT EXISTS app.chat_sessions (
    chat_id BIGSERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS app.chat_search_configs (
    chat_config_id BIGSERIAL PRIMARY KEY,
    chat_id BIGINT NOT NULL REFERENCES app.chat_sessions(chat_id),
    seniority TEXT,
    job_title TEXT,
    resume_parse_id BIGINT REFERENCES bronze.raw_resume_parses(resume_parse_id),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    next_start_index INT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS app.chat_job_comparisons (
    chat_comparison_id BIGSERIAL PRIMARY KEY,
    chat_config_id BIGINT NOT NULL
        REFERENCES app.chat_search_configs(chat_config_id),

    resume_job_semantic_score_id BIGINT NOT NULL,
    resume_job_skill_score_id BIGINT NOT NULL,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (
        chat_config_id,
        resume_job_semantic_score_id,
        resume_job_skill_score_id
    ),

    FOREIGN KEY (
        resume_job_semantic_score_id,
        resume_job_skill_score_id
    )
    REFERENCES silver.fact_resume_job_complete_scores (
        resume_job_semantic_score_id,
        resume_job_skill_score_id
    )
);

CREATE TABLE IF NOT EXISTS app.resume_grading_runs (
    grading_run_id BIGSERIAL PRIMARY KEY,
    chat_config_id BIGINT NOT NULL
        REFERENCES app.chat_search_configs(chat_config_id),

    status TEXT NOT NULL DEFAULT 'running',
    phase TEXT NOT NULL DEFAULT 'linkedin_scraping',
    cancel_requested BOOLEAN NOT NULL DEFAULT FALSE,

    processed_job_count INT NOT NULL DEFAULT 0,
    valid_matched_job_count INT NOT NULL DEFAULT 0,
    new_comparison_count INT NOT NULL DEFAULT 0,

    next_start_index INT,
    stopped_reason TEXT,
    error_message TEXT,

    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
