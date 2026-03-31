from dataclasses import dataclass, field
from enum import Enum
from linkedin_tool.setting import Setting

class TimePostedRange(Enum):
    """f_TPR parameter values (in seconds)"""
    PAST_24H = "r86400"
    PAST_WEEK = "r604800"
    PAST_MONTH = "r2592000"

class WorkplaceType(Enum):
    """f_WT parameter values"""
    ON_SITE = "1"
    REMOTE = "2"
    HYBRID = "3"

class ExperienceLevel(Enum):
    """f_E parameter values"""
    INTERN = "1"
    ENTRY_LEVEL = "2"
    ASSOCIATE = "3"
    MID_SENIOR = "4"
    DIRECTOR = "5"
    EXECUTIVE = "6"

class JobType(Enum):
    """f_JT parameter values"""
    FULL_TIME = "F"
    PART_TIME = "P"
    CONTRACT = "C"
    TEMPORARY = "T"
    INTERNSHIP = "I"

class SortBy(Enum):
    """sortBy parameter values"""
    MOST_RECENT = "DD"
    MOST_RELEVANT = "R"

class GeoId(Enum):
    UNITED_STATE = "103644278"
    WEST_VIRGINIA = "106420769"
    VIETNAM = "104195383"
    CALIFORNIA = "102095887"
    
class ScrapeResult(Enum):
    SUCCESSFUL = "successful"
    FAILED = "failed"
    RETRY = "retry"

@dataclass(frozen=True, slots=True)
class JobSearchRequest:
    geo_id: GeoId | None = None
    keywords: str = ""
    start: int = 0

    # filters
    time_range: TimePostedRange | None = None
    workplace: WorkplaceType | None = None
    experience: ExperienceLevel | None = None
    job_type: JobType | None = None
    sort_by: SortBy| None = None
    
@dataclass
class ScrapeRuntime:
    total_requests: int = 0
    requests_since_sleep: int = 0
    requests_since_session_reset: int = 0