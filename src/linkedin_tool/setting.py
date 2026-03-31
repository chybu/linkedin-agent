from enum import Enum

class Setting(Enum):
    REQUEST_TIMEOUT = 30 # seconds
    MIN_JOB_SEARCH_SLEEP = 120 # seconds
    MAX_JOB_SEARCH_SLEEP = 300 # seconds
    FAIL_RETRY_PENALTY = 60 # seconds
    MAX_RETRIES = 3 # times
    JOB_SEARCH_WEIGHT = 1 # requests
    JOB_POST_WEIGHT = 1 # requests
    JOB_SEARCH_REQUEST_LIMIT = 33 # should be more than max_retries * (job_search_weight + 10 * job_post_weight)
    JOB_SEARCH_SESSION_LIMIT = 33 # should be more than max_retries * (job_search_weight + 10 * job_post_weight)
    MAX_START_INDEX = 1000
