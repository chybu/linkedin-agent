from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

from linkedin_tool.db.base import SessionLocal
from agent_server.helper.chat_memory import get_active_chat_config
from agent_server.helper.grading_results import (
    fetch_chat_comparison_details,
    fetch_resume_grading_results,
)
from resume_tool.semantic_scoring import fetch_resume_job_semantic_score_details
from resume_tool.skill_scoring import fetch_resume_job_skill_score_details

class ResumeGradingResultItem(BaseModel):
    chat_comparison_id: int = Field(
        description="Id of this saved resume-to-job comparison. Use this id to explain the match."
    )
    job_posting_raw_id: int = Field(
        description="Internal raw job posting id for the matched job."
    )
    title: str | None = Field(
        description="Raw job title shown on the matched job posting."
    )
    company: str | None = Field(
        description="Company name for the matched job."
    )
    location: str | None = Field(
        description="Job location for the matched job."
    )
    source_url: str | None = Field(
        description="Source URL for the matched job posting."
    )
    complete_score: float = Field(
        description="Overall resume-to-job match score."
    )
    semantic_score: float = Field(
        description="Score based on how well resume evidence satisfies job requirements."
    )
    skill_match_score: float = Field(
        description="Score based on how well resume skills match required job skills."
    )


class JobMatchInfo(BaseModel):
    title: str | None = Field(description="Raw job title shown on the job posting.")
    company: str | None = Field(description="Company name.")
    location: str | None = Field(description="Job location.")
    source_url: str | None = Field(description="Source URL for the job posting.")


class JobMatchScores(BaseModel):
    complete_score: float = Field(description="Overall resume-to-job match score.")
    semantic_score: float = Field(
        description="Score based on resume evidence matched to job requirements."
    )
    skill_match_score: float = Field(
        description="Score based on resume skills matched to required job skills."
    )


class RequirementMatchItem(BaseModel):
    job_requirement: str = Field(description="Requirement extracted from the job description.")
    resume_evidence: str | None = Field(
        default=None,
        description="Resume bullet or evidence matched to the job requirement, if any."
    )
    similarity_score: float = Field(
        description="Semantic similarity score between the job requirement and resume evidence."
    )


class SkillMatchItem(BaseModel):
    job_skill: str = Field(description="Skill required by the job.")
    resume_skill: str | None = Field(
        default=None,
        description="Resume skill matched to the job skill, if any."
    )
    fuzzy_score: float | None = Field(
        default=None,
        description="Fuzzy match score between the job skill and resume skill."
    )


class ResumeJobMatchExplanationResponse(BaseModel):
    chat_comparison_id: int = Field(
        description="Id of the saved resume-to-job comparison being explained."
    )
    job: JobMatchInfo = Field(description="Basic information about the matched job.")
    scores: JobMatchScores = Field(description="Overall, semantic, and skill match scores.")
    matched_requirements: list[RequirementMatchItem] = Field(
        description="Job requirements that the resume appears to satisfy."
    )
    missing_requirements: list[RequirementMatchItem] = Field(
        description="Job requirements that the resume does not clearly satisfy."
    )
    matched_skills: list[SkillMatchItem] = Field(
        description="Required job skills found in the resume."
    )
    missing_skills: list[SkillMatchItem] = Field(
        description="Required job skills not found in the resume."
    )


class ResumeGradingResultsResponse(BaseModel):
    results: list[ResumeGradingResultItem] = Field(
        description="Ranked resume-to-job comparison results for the active chat config."
    )


async def list_resume_grading_results(
    chat_id: int,
    limit: int = 10,
) -> ResumeGradingResultsResponse:
    """
    List ranked resume grading results for the active chat config.

    Use this after resume grading has completed or while results are available.
    This tool returns compact match summaries. Use explain_resume_job_match for
    detailed reasoning about one specific comparison.
    """
    with SessionLocal() as session:
        config = get_active_chat_config(session, chat_id)

        if config is None:
            raise ValueError(
                f"No active resume grading config found for chat_id={chat_id}. "
                "Call initialize_resume_grading_chat first."
            )

        rows = fetch_resume_grading_results(
            session=session,
            chat_config_id=config["chat_config_id"],
            limit=limit,
        )

    return ResumeGradingResultsResponse(
        results=[ResumeGradingResultItem(**row) for row in rows]
    )


async def explain_resume_job_match(
    chat_comparison_id: int,
) -> ResumeJobMatchExplanationResponse:
    """
    Explain one saved resume-to-job comparison.

    Use this when the user asks why a specific job matched, why it scored well
    or poorly, which requirements were covered, or which skills were missing.

    The input must be a chat_comparison_id from list_resume_grading_results.
    """
    with SessionLocal() as session:
        comparison = fetch_chat_comparison_details(
            session=session,
            chat_comparison_id=chat_comparison_id,
        )

        if comparison is None:
            raise ValueError(
                f"chat_comparison_id does not exist: {chat_comparison_id}"
            )

        semantic_details = fetch_resume_job_semantic_score_details(
            session=session,
            resume_job_semantic_score_id=comparison["resume_job_semantic_score_id"],
        )
        skill_details = fetch_resume_job_skill_score_details(
            session=session,
            resume_job_skill_score_id=comparison["resume_job_skill_score_id"],
        )

    semantic_matches = semantic_details["matches"] if semantic_details else []
    skill_matches = skill_details["matches"] if skill_details else []

    matched_requirements = [
        RequirementMatchItem(
            job_requirement=row["jd_requirement"],
            resume_evidence=row["resume_bullet_point"],
            similarity_score=float(row["similarity_score"]),
        )
        for row in semantic_matches
        if row["is_satisfied"]
    ]

    missing_requirements = [
        RequirementMatchItem(
            job_requirement=row["jd_requirement"],
            resume_evidence=row["resume_bullet_point"],
            similarity_score=float(row["similarity_score"]),
        )
        for row in semantic_matches
        if not row["is_satisfied"]
    ]

    matched_skills = [
        SkillMatchItem(
            job_skill=row["job_skill_name"],
            resume_skill=row["matched_resume_skill_name"],
            fuzzy_score=float(row["fuzzy_score"]) if row["fuzzy_score"] is not None else None,
        )
        for row in skill_matches
        if row["is_matched"]
    ]

    missing_skills = [
        SkillMatchItem(
            job_skill=row["job_skill_name"],
            resume_skill=row["matched_resume_skill_name"],
            fuzzy_score=float(row["fuzzy_score"]) if row["fuzzy_score"] is not None else None,
        )
        for row in skill_matches
        if not row["is_matched"]
    ]

    return ResumeJobMatchExplanationResponse(
        chat_comparison_id=chat_comparison_id,
        job=JobMatchInfo(
            title=comparison["title"],
            company=comparison["company"],
            location=comparison["location"],
            source_url=comparison["source_url"],
        ),
        scores=JobMatchScores(
            complete_score=float(comparison["complete_score"]),
            semantic_score=float(comparison["semantic_score"]),
            skill_match_score=float(comparison["skill_match_score"]),
        ),
        matched_requirements=matched_requirements,
        missing_requirements=missing_requirements,
        matched_skills=matched_skills,
        missing_skills=missing_skills,
    )


def register(mcp: FastMCP) -> None:
    mcp.tool()(list_resume_grading_results)
    mcp.tool()(explain_resume_job_match)
