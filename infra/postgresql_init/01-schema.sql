CREATE TABLE IF NOT EXISTS jobs (
    job_id BIGINT PRIMARY KEY,
    title TEXT,
    company TEXT,
    location TEXT,
    posted TEXT,
    seniority_level TEXT,
    employment_type TEXT,
    job_function TEXT,
    industry TEXT,
    applicants TEXT,
    description TEXT,
    source_url TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);