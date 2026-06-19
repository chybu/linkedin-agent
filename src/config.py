from enum import Enum
from pathlib import Path
import tomllib

def get_api_keys() -> list[str]:
    ROOT_DIR = Path(__file__).resolve().parents[1]
    SECRETS_FILE = ROOT_DIR / ".secrets.toml"

    with SECRETS_FILE.open("rb") as f:
        secrets = tomllib.load(f)
    
    return secrets["groq_api_keys"]

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
    BATCH_SIZE = 10
    FUZZY_VAL_THRESH = 0.90
    FUZZY_KEY_THRESH = 0.94
    DOMAINS = ("title", "location", "seniority")
    METHODS = ("map", "fuzzy", "llm")
    LLM = "meta-llama/llama-4-scout-17b-16e-instruct"
    # LLM = "llama-3.3-70b-versatile"
    MAX_TOKEN = 8000 # MAX COMPLETETION TOKEN
    LLM_INTERVAL = 10 # seconds
    GROQ_API_KEYS = get_api_keys()

    EXTRACT_UNEXTRACTED_READY_JOBS = True

class ResumeConfig(Enum):
    EMBED_MODEL = "mxbai-embed-large"
    # minimum valid score for semantic scoring 
    MIN_MATCH_SCORE = 0.6
    SKILL_FUZZY_MATCH_THRESHOLD = 0.90
    COMPLETE_SCORE_SEMANTIC_WEIGHT = 0.70
    COMPLETE_SCORE_SKILL_WEIGHT = 0.30

class AgentConfig(Enum):
    MCP_SERVER_NAME = "LinkedIn Job Agent"
    MCP_SERVER_HOST = "0.0.0.0"
    MCP_SERVER_PORT = 8001
    MIN_JOB = 5
    LINKEDIN_START_INDEX_STEP = 10
    MAX_EMPTY_VALID_BATCHES = 1