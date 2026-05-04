from enum import Enum

class Setting(Enum):
    REQUEST_TIMEOUT = 30 # seconds
    MIN_LONG_SLEEP = 120 # seconds
    MAX_LONG_SLEEP = 300 # seconds
    MIN_SHORT_SLEEP = 1 # seconds
    MAX_SHORT_SLEEP = 4 # seconds

    FAIL_RETRY_PENALTY = 60 * 5 # seconds
    MAX_RETRIES = 1 # times
    JOB_SEARCH_WEIGHT = 1 # requests
    JOB_POST_WEIGHT = 1 # requests
    REQUEST_LIMIT = 3300 # should be more than max_retries * (job_search_weight + 10 * job_post_weight)
    SESSION_LIMIT = 3300 # should be more than max_retries * (job_search_weight + 10 * job_post_weight)
    MAX_START_INDEX = 1000
    DATABASE_URL = "postgresql+psycopg://user:password@localhost:5432/jobsdb"

class NormalizationConfig(Enum):
    BATCH_SIZE = 3
    FUZZY_VAL_THRESH = 0.90
    FUZZY_KEY_THRESH = 0.94
    DOMAINS = ("title", "location", "seniority")
    METHODS = ("map", "fuzzy", "llm")
    LLM = "meta-llama/llama-4-scout-17b-16e-instruct"
    GROQ_API_KEYS = [
        "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",
        "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",
        "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",
        "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",
        "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"
    ]
    MAX_TOKEN = 8192
    LLM_INTERVAL = 5 # seconds
    EXTRACT_UNEXTRACTED_READY_JOBS = True