from dataclasses import dataclass

@dataclass(frozen=True)
class ResumeEvidenceResult:
    resume_parse_id: int
    resume_file_name: str
    resume_md: str
    resume_evidence: str
    resume_bullets: list[str]

@dataclass(frozen=True)
class MatchResult:
    jd_sentence: str
    resume_sentence: str | None
    score: float

@dataclass(frozen=True)
class ResumeJobSemanticScoreResult:
    resume_job_semantic_score_id: int
    resume_parse_id: int
    job_posting_raw_id: int
    semantic_score: float
    cleared_count: int
    total_requirement_count: int

@dataclass(frozen=True)
class ResumeJobSkillScoreResult:
    resume_job_skill_score_id: int
    resume_parse_id: int
    job_posting_raw_id: int
    skill_match_score: float
    matched_skill_count: int
    total_job_skill_count: int
    missing_skill_count: int

@dataclass(frozen=True)
class ResumeJobCompleteScoreResult:
    resume_job_semantic_score_id: int
    resume_job_skill_score_id: int
    resume_parse_id: int
    job_posting_raw_id: int
    semantic_score: float
    skill_match_score: float
    complete_score: float
    semantic_weight: float
    skill_weight: float
