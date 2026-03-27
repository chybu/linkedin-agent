from enum import Enum

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