from dataclasses import dataclass, field
from enum import Enum
from linkedin_tool.setting import NormalizationConfig
from typing import Generic, TypeVar

T = TypeVar("T")

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
    RUNNING = "running"

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
    requests_since_sleep: int = 0
    requests_since_session_reset: int = 0

@dataclass
class Result(Generic[T]):    
    result: ScrapeResult
    content: T | None = None
    error: str | None = None
    
@dataclass
class NormalizationSummary:
    total_candidates: int = 0
    ready_count: int = 0
    unresolved_by_domain: dict[str, int] = field(default_factory=dict)
    resolved_by_method: dict[str, int] = field(
        default_factory=lambda: {
            method:0 for method in NormalizationConfig.METHODS.value
        }
    )

@dataclass
class NormalizationResult:
    ready_job_posting_raw_ids: list[int] = field(default_factory=list)
    summary: NormalizationSummary = field(default_factory=NormalizationSummary)
    
@dataclass
class FuzzyResult:
    raw_key:str
    normalized_val:str
    ref_key:str = None