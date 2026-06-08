from sqlalchemy import text
from sqlalchemy.orm import Session

from config import ResumeConfig
from linkedin_tool.schema import Result, ScrapeResult
from log import print_announcement, print_message
from resume_tool.extraction import extract_and_store_resume_evidence
from resume_tool.llm import GroqResumeExtractor
from resume_tool.schema import ResumeJobCompleteScoreResult
from resume_tool.semantic_scoring import score_resume_semantic_against_job_evidence
from resume_tool.skill_extraction import extract_skills_for_resume_parse
from resume_tool.skill_scoring import score_resume_skills_against_job

RESUME_JOB_COMPLETE_SCORES_TABLE = "silver.fact_resume_job_complete_scores"


def compute_complete_score(
    semantic_score: float,
    skill_match_score: float,
    semantic_weight: float,
    skill_weight: float,
) -> float:
    """Compute a weighted score from semantic and skill-match scores."""
    weight_total = semantic_weight + skill_weight
    if weight_total <= 0:
        raise ValueError("semantic_weight + skill_weight must be greater than 0")

    return round(
        (
            semantic_score * semantic_weight
            + skill_match_score * skill_weight
        )
        / weight_total,
        2,
    )


def fetch_existing_resume_job_complete_score(
    session: Session,
    resume_job_semantic_score_id: int,
    resume_job_skill_score_id: int,
) -> ResumeJobCompleteScoreResult | None:
    """Return an existing complete score for the same semantic and skill scores."""
    stmt = text(
        f"""
        select
            resume_job_semantic_score_id,
            resume_job_skill_score_id,
            resume_parse_id,
            job_posting_raw_id,
            semantic_score,
            skill_match_score,
            complete_score,
            semantic_weight,
            skill_weight
        from {RESUME_JOB_COMPLETE_SCORES_TABLE}
        where resume_job_semantic_score_id = :resume_job_semantic_score_id
          and resume_job_skill_score_id = :resume_job_skill_score_id
        """
    )

    row = session.execute(
        stmt,
        {
            "resume_job_semantic_score_id": resume_job_semantic_score_id,
            "resume_job_skill_score_id": resume_job_skill_score_id,
        },
    ).mappings().one_or_none()

    if row is None:
        return None

    return ResumeJobCompleteScoreResult(
        resume_job_semantic_score_id=row["resume_job_semantic_score_id"],
        resume_job_skill_score_id=row["resume_job_skill_score_id"],
        resume_parse_id=row["resume_parse_id"],
        job_posting_raw_id=row["job_posting_raw_id"],
        semantic_score=float(row["semantic_score"]),
        skill_match_score=float(row["skill_match_score"]),
        complete_score=float(row["complete_score"]),
        semantic_weight=float(row["semantic_weight"]),
        skill_weight=float(row["skill_weight"]),
    )


def insert_resume_job_complete_score(
    session: Session,
    result: ResumeJobCompleteScoreResult,
) -> None:
    """Insert the complete score keyed by semantic score id and skill score id."""
    stmt = text(
        f"""
        insert into {RESUME_JOB_COMPLETE_SCORES_TABLE} (
            resume_job_semantic_score_id,
            resume_job_skill_score_id,
            resume_parse_id,
            job_posting_raw_id,
            semantic_score,
            skill_match_score,
            complete_score,
            semantic_weight,
            skill_weight
        )
        values (
            :resume_job_semantic_score_id,
            :resume_job_skill_score_id,
            :resume_parse_id,
            :job_posting_raw_id,
            :semantic_score,
            :skill_match_score,
            :complete_score,
            :semantic_weight,
            :skill_weight
        )
        on conflict (resume_job_semantic_score_id, resume_job_skill_score_id)
        do nothing
        """
    )

    session.execute(
        stmt,
        {
            "resume_job_semantic_score_id": result.resume_job_semantic_score_id,
            "resume_job_skill_score_id": result.resume_job_skill_score_id,
            "resume_parse_id": result.resume_parse_id,
            "job_posting_raw_id": result.job_posting_raw_id,
            "semantic_score": result.semantic_score,
            "skill_match_score": result.skill_match_score,
            "complete_score": result.complete_score,
            "semantic_weight": result.semantic_weight,
            "skill_weight": result.skill_weight,
        },
    )


def score_resume_complete_against_job(
    session: Session,
    resume_file_path: str,
    job_posting_raw_id: int,
    resume_extractor: GroqResumeExtractor,
) -> Result[ResumeJobCompleteScoreResult]:
    """
    Run the full resume-to-job scoring pipeline and persist the complete score.

    The pipeline extracts/stores resume evidence, computes or reuses semantic
    scoring, extracts or reuses resume skills, computes or reuses skill scoring,
    then stores the weighted complete score.
    """
    try:
        print_announcement(
            "complete scoring",
            f"resume={resume_file_path} job_posting_raw_id={job_posting_raw_id}",
        )

        resume_res = extract_and_store_resume_evidence(
            session=session,
            resume_file_path=resume_file_path,
            resume_extractor=resume_extractor,
        )
        if resume_res.result != ScrapeResult.SUCCESSFUL or resume_res.content is None:
            print_message("complete scoring", "failed")
            return Result(
                result=ScrapeResult.FAILED,
                content=None,
                error=resume_res.error or "resume extraction failed",
            )
        resume_data = resume_res.content

        semantic_res = score_resume_semantic_against_job_evidence(
            session=session,
            resume_parse_id=resume_data.resume_parse_id,
            resume_bullets=resume_data.resume_bullets,
            job_posting_raw_id=job_posting_raw_id,
        )
        if semantic_res.result != ScrapeResult.SUCCESSFUL or semantic_res.content is None:
            print_message("complete scoring", "failed")
            return Result(
                result=ScrapeResult.FAILED,
                content=None,
                error=semantic_res.error or "semantic scoring failed",
            )
        semantic_score = semantic_res.content

        skill_extract_res = extract_skills_for_resume_parse(
            session=session,
            resume_parse_id=resume_data.resume_parse_id,
            resume_extractor=resume_extractor,
        )
        if skill_extract_res.result != ScrapeResult.SUCCESSFUL:
            print_message("complete scoring", "failed")
            return Result(
                result=ScrapeResult.FAILED,
                content=None,
                error=skill_extract_res.error or "resume skill extraction failed",
            )

        skill_res = score_resume_skills_against_job(
            session=session,
            resume_parse_id=resume_data.resume_parse_id,
            job_posting_raw_id=job_posting_raw_id,
        )
        if skill_res.result != ScrapeResult.SUCCESSFUL or skill_res.content is None:
            print_message("complete scoring", "failed")
            return Result(
                result=ScrapeResult.FAILED,
                content=None,
                error=skill_res.error or "skill scoring failed",
            )
        skill_score = skill_res.content

        existing_score = fetch_existing_resume_job_complete_score(
            session=session,
            resume_job_semantic_score_id=semantic_score.resume_job_semantic_score_id,
            resume_job_skill_score_id=skill_score.resume_job_skill_score_id,
        )
        if existing_score is not None:
            session.commit()
            print_message("complete scoring", "finish")
            return Result(
                result=ScrapeResult.SUCCESSFUL,
                content=existing_score,
            )

        semantic_weight = float(ResumeConfig.COMPLETE_SCORE_SEMANTIC_WEIGHT.value)
        skill_weight = float(ResumeConfig.COMPLETE_SCORE_SKILL_WEIGHT.value)
        complete_score = compute_complete_score(
            semantic_score=semantic_score.semantic_score,
            skill_match_score=skill_score.skill_match_score,
            semantic_weight=semantic_weight,
            skill_weight=skill_weight,
        )

        result = ResumeJobCompleteScoreResult(
            resume_job_semantic_score_id=semantic_score.resume_job_semantic_score_id,
            resume_job_skill_score_id=skill_score.resume_job_skill_score_id,
            resume_parse_id=resume_data.resume_parse_id,
            job_posting_raw_id=job_posting_raw_id,
            semantic_score=semantic_score.semantic_score,
            skill_match_score=skill_score.skill_match_score,
            complete_score=complete_score,
            semantic_weight=semantic_weight,
            skill_weight=skill_weight,
        )

        insert_resume_job_complete_score(
            session=session,
            result=result,
        )
        session.commit()
        print_message("complete scoring", "finish")

        return Result(
            result=ScrapeResult.SUCCESSFUL,
            content=result,
        )

    except Exception as e:
        session.rollback()
        print_message("complete scoring", "failed")
        return Result(
            result=ScrapeResult.FAILED,
            content=None,
            error=str(e),
        )
