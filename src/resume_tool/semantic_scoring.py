from sqlalchemy import text
from sqlalchemy.orm import Session

from linkedin_tool.schema import Result, ScrapeResult
from log import print_announcement, print_message
from resume_tool.extraction import extract_and_store_resume_evidence
from resume_tool.llm import GroqResumeExtractor
from resume_tool.semantic_similarity_calculator import (
    match_jd_sentences_to_resume,
    parse_bullet_text,
)
from resume_tool.schema import MatchResult, ResumeJobSemanticScoreResult
from config import ResumeConfig

JOB_DESCRIPTION_CLEANING_TABLE = "bronze.map_job_description_cleaning"
RESUME_JOB_SEMANTIC_SCORES_TABLE = "silver.fact_resume_job_semantic_scores"
RESUME_JOB_SEMANTIC_REQUIREMENT_MATCHES_TABLE = "silver.fact_resume_job_semantic_requirement_matches"


def _match_credit(match: MatchResult) -> float:
    """
    Normalize similarity score
    """
    if match.resume_sentence is None:
        return 0.0

    if match.score >= 0.70:
        # full credit
        return 1.0
    if match.score >= 0.60:
        # partial credit
        return 0.7
    if match.score >= 0.50:
        # weak credit
        return 0.4
    
    # no credit
    return 0.0


def _compute_semantic_score(matches: list[MatchResult]) -> tuple[float, int, int]:
    """
    compute the final score of the resume and the job description. 
    Return final score, number of satisfied requirements, and number of total requirements
    """
    total_requirement_count = len(matches)
    if total_requirement_count == 0:
        return 0.0, 0, 0

    total_credit = 0.0
    cleared_count = 0

    for match in matches:
        credit = _match_credit(match)
        total_credit += credit

        if credit > 0:
            cleared_count += 1

    semantic_score = round((total_credit / total_requirement_count) * 100, 2)
    return semantic_score, cleared_count, total_requirement_count


def fetch_cleaned_jd(
    session: Session,
    job_posting_raw_id: int,
) -> str:
    stmt = text(
        f"""
        select description_cleaned
        from {JOB_DESCRIPTION_CLEANING_TABLE}
        where job_posting_raw_id = :job_posting_raw_id
        """
    )

    cleaned_jd = session.execute(
        stmt,
        {"job_posting_raw_id": job_posting_raw_id},
    ).scalar_one_or_none()

    if not cleaned_jd:
        raise RuntimeError(
            "missing cleaned job description for "
            f"job_posting_raw_id={job_posting_raw_id}"
        )

    return cleaned_jd


def insert_resume_job_semantic_score(
    session: Session,
    resume_parse_id: int,
    job_posting_raw_id: int,
    semantic_score: float,
    embedding_model: str,
    cleared_count: int,
    total_requirement_count: int,
) -> int:
    stmt = text(
        f"""
        insert into {RESUME_JOB_SEMANTIC_SCORES_TABLE} (
            resume_parse_id,
            job_posting_raw_id,
            semantic_score,
            embedding_model,
            cleared_count,
            total_requirement_count
        )
        values (
            :resume_parse_id,
            :job_posting_raw_id,
            :semantic_score,
            :embedding_model,
            :cleared_count,
            :total_requirement_count
        )
        returning resume_job_semantic_score_id
        """
    )

    return session.execute(
        stmt,
        {
            "resume_parse_id": resume_parse_id,
            "job_posting_raw_id": job_posting_raw_id,
            "semantic_score": semantic_score,
            "embedding_model": embedding_model,
            "cleared_count": cleared_count,
            "total_requirement_count": total_requirement_count,
        },
    ).scalar_one()


def insert_semantic_requirement_matches(
    session: Session,
    resume_job_semantic_score_id: int,
    matches: list[MatchResult],
) -> None:
    if not matches:
        return

    rows = [
        {
            "resume_job_semantic_score_id": resume_job_semantic_score_id,
            "requirement_index": i,
            "jd_requirement": match.jd_sentence,
            "resume_bullet_point": match.resume_sentence,
            "similarity_score": match.score,
            "is_satisfied": _match_credit(match) > 0,
        }
        for i, match in enumerate(matches)
    ]

    stmt = text(
        f"""
        insert into {RESUME_JOB_SEMANTIC_REQUIREMENT_MATCHES_TABLE} (
            resume_job_semantic_score_id,
            requirement_index,
            jd_requirement,
            resume_bullet_point,
            similarity_score,
            is_satisfied
        )
        values (
            :resume_job_semantic_score_id,
            :requirement_index,
            :jd_requirement,
            :resume_bullet_point,
            :similarity_score,
            :is_satisfied
        )
        """
    )

    session.execute(stmt, rows)


def score_resume_semantic_against_job_evidence(
    session: Session,
    resume_parse_id: int,
    resume_bullets: list[str],
    job_posting_raw_id: int,
) -> Result[ResumeJobSemanticScoreResult]:
    try:
        print_announcement(
            "semantic scoring",
            f"resume_parse_id={resume_parse_id} job_posting_raw_id={job_posting_raw_id}",
        )

        if not resume_bullets:
            print_message("semantic scoring", "failed")
            return Result(
                result=ScrapeResult.FAILED,
                content=None,
                error="resume_bullets must contain at least one bullet point",
            )

        embedding_model = ResumeConfig.EMBED_MODEL.value
        existing_score = fetch_existing_resume_job_semantic_score(
            session=session,
            resume_parse_id=resume_parse_id,
            job_posting_raw_id=job_posting_raw_id,
            embedding_model=embedding_model,
        )
        if existing_score is not None:
            session.commit()
            print_message("semantic scoring", "finish")
            return Result(
                result=ScrapeResult.SUCCESSFUL,
                content=existing_score,
            )

        cleaned_jd = fetch_cleaned_jd(
            session=session,
            job_posting_raw_id=job_posting_raw_id,
        )

        jd_requirements = parse_bullet_text(cleaned_jd)

        matches = match_jd_sentences_to_resume(
            jd_sentences=jd_requirements,
            resume_sentences=resume_bullets,
        )

        semantic_score, cleared_count, total_requirement_count = _compute_semantic_score(matches)

        resume_job_semantic_score_id = insert_resume_job_semantic_score(
            session=session,
            resume_parse_id=resume_parse_id,
            job_posting_raw_id=job_posting_raw_id,
            semantic_score=semantic_score,
            embedding_model=embedding_model,
            cleared_count=cleared_count,
            total_requirement_count=total_requirement_count,
        )

        insert_semantic_requirement_matches(
            session=session,
            resume_job_semantic_score_id=resume_job_semantic_score_id,
            matches=matches,
        )

        session.commit()
        print_message("semantic scoring", "finish")

        return Result(
            result=ScrapeResult.SUCCESSFUL,
            content=ResumeJobSemanticScoreResult(
                resume_job_semantic_score_id=resume_job_semantic_score_id,
                resume_parse_id=resume_parse_id,
                job_posting_raw_id=job_posting_raw_id,
                semantic_score=semantic_score,
                cleared_count=cleared_count,
                total_requirement_count=total_requirement_count,
            ),
        )

    except Exception as e:
        session.rollback()
        print_message("semantic scoring", "failed")
        return Result(
            result=ScrapeResult.FAILED,
            content=None,
            error=str(e),
        )


def score_resume_semantic_against_job(
    session: Session,
    resume_file_path: str,
    job_posting_raw_id: int,
    resume_extractor: GroqResumeExtractor,
) -> Result[ResumeJobSemanticScoreResult]:
    """Extract resume evidence, then score it semantically against a prepared job."""
    try:
        resume_res = extract_and_store_resume_evidence(
            session=session,
            resume_file_path=resume_file_path,
            resume_extractor=resume_extractor,
        )
        if resume_res.result != ScrapeResult.SUCCESSFUL or resume_res.content is None:
            return Result(
                result=ScrapeResult.FAILED,
                content=None,
                error=resume_res.error or "resume extraction failed",
            )

        return score_resume_semantic_against_job_evidence(
            session=session,
            resume_parse_id=resume_res.content.resume_parse_id,
            resume_bullets=resume_res.content.resume_bullets,
            job_posting_raw_id=job_posting_raw_id,
        )

    except Exception as e:
        session.rollback()
        print_message("semantic scoring", "failed")
        return Result(
            result=ScrapeResult.FAILED,
            content=None,
            error=str(e),
        )


def fetch_resume_job_semantic_score_details(
    session: Session,
    resume_job_semantic_score_id: int,
) -> dict | None:
    """Return a semantic score row with its per-requirement match details."""
    score_stmt = text(
        f"""
        select
            resume_job_semantic_score_id,
            resume_parse_id,
            job_posting_raw_id,
            semantic_score,
            cleared_count,
            total_requirement_count,
            scored_at
        from {RESUME_JOB_SEMANTIC_SCORES_TABLE}
        where resume_job_semantic_score_id = :resume_job_semantic_score_id
        """
    )

    score_row = session.execute(
        score_stmt,
        {"resume_job_semantic_score_id": resume_job_semantic_score_id},
    ).mappings().one_or_none()

    if score_row is None:
        return None

    matches_stmt = text(
        f"""
        select
            requirement_index,
            jd_requirement,
            resume_bullet_point,
            similarity_score,
            is_satisfied
        from {RESUME_JOB_SEMANTIC_REQUIREMENT_MATCHES_TABLE}
        where resume_job_semantic_score_id = :resume_job_semantic_score_id
        order by requirement_index
        """
    )

    match_rows = session.execute(
        matches_stmt,
        {"resume_job_semantic_score_id": resume_job_semantic_score_id},
    ).mappings().all()

    return {
        "score": dict(score_row),
        "matches": [dict(row) for row in match_rows],
    }


def fetch_existing_resume_job_semantic_score(
    session: Session,
    resume_parse_id: int,
    job_posting_raw_id: int,
    embedding_model: str,
) -> ResumeJobSemanticScoreResult | None:
    stmt = text(
        f"""
        select
            resume_job_semantic_score_id,
            resume_parse_id,
            job_posting_raw_id,
            semantic_score,
            cleared_count,
            total_requirement_count
        from {RESUME_JOB_SEMANTIC_SCORES_TABLE}
        where resume_parse_id = :resume_parse_id
          and job_posting_raw_id = :job_posting_raw_id
          and embedding_model = :embedding_model
        """
    )

    row = session.execute(
        stmt,
        {
            "resume_parse_id": resume_parse_id,
            "job_posting_raw_id": job_posting_raw_id,
            "embedding_model": embedding_model,
        },
    ).mappings().one_or_none()

    if row is None:
        return None

    return ResumeJobSemanticScoreResult(
        resume_job_semantic_score_id=row["resume_job_semantic_score_id"],
        resume_parse_id=row["resume_parse_id"],
        job_posting_raw_id=row["job_posting_raw_id"],
        semantic_score=float(row["semantic_score"]),
        cleared_count=row["cleared_count"],
        total_requirement_count=row["total_requirement_count"],
    )
