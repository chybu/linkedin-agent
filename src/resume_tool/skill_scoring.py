from difflib import SequenceMatcher

from sqlalchemy import text
from sqlalchemy.orm import Session

from config import ResumeConfig
from linkedin_tool.schema import Result, ScrapeResult
from log import print_announcement, print_message
from resume_tool.schema import ResumeJobSkillScoreResult

DIM_SKILLS_TABLE = "silver.dim_skills"
BRIDGE_JOB_POSTING_SKILLS_TABLE = "silver.bridge_job_posting_skills"
BRIDGE_RESUME_PARSE_SKILLS_TABLE = "silver.bridge_resume_parse_skills"
RESUME_JOB_SKILL_SCORES_TABLE = "silver.fact_resume_job_skill_scores"
RESUME_JOB_SKILL_MATCHES_TABLE = "silver.fact_resume_job_skill_matches"


def _token_sort(skill: str) -> str:
    normalized = " ".join((skill or "").strip().lower().split())
    return " ".join(sorted(normalized.split()))


def _fuzzy_score(left: str, right: str) -> float:
    """Return a token-order-insensitive similarity score between two skill names."""
    return SequenceMatcher(None, _token_sort(left), _token_sort(right)).ratio()


def _best_resume_skill_match(
    job_skill_name: str,
    resume_skills: list[dict],
) -> tuple[dict | None, float]:
    """Find the highest-scoring resume skill candidate for a required job skill."""
    best_skill = None
    best_score = 0.0

    for resume_skill in resume_skills:
        score = _fuzzy_score(job_skill_name, resume_skill["skill_name"])
        if score > best_score:
            best_score = score
            best_skill = resume_skill

    return best_skill, best_score


def fetch_resume_skills(session: Session, resume_parse_id: int) -> list[dict]:
    """Return normalized skills already extracted for a resume parse."""
    stmt = text(
        f"""
        select
            s.skill_id,
            s.skill_name
        from {BRIDGE_RESUME_PARSE_SKILLS_TABLE} rps
        inner join {DIM_SKILLS_TABLE} s
            on rps.skill_id = s.skill_id
        where rps.resume_parse_id = :resume_parse_id
        order by s.skill_name
        """
    )

    rows = session.execute(
        stmt,
        {"resume_parse_id": resume_parse_id},
    ).mappings().all()

    return [dict(row) for row in rows]


def fetch_job_skills(session: Session, job_posting_raw_id: int) -> list[dict]:
    """Return normalized skills already extracted for a job posting."""
    stmt = text(
        f"""
        select
            s.skill_id,
            s.skill_name
        from {BRIDGE_JOB_POSTING_SKILLS_TABLE} jps
        inner join {DIM_SKILLS_TABLE} s
            on jps.skill_id = s.skill_id
        where jps.job_posting_raw_id = :job_posting_raw_id
        order by s.skill_name
        """
    )

    rows = session.execute(
        stmt,
        {"job_posting_raw_id": job_posting_raw_id},
    ).mappings().all()

    return [dict(row) for row in rows]


def fetch_existing_resume_job_skill_score(
    session: Session,
    resume_parse_id: int,
    job_posting_raw_id: int,
    fuzzy_threshold: float,
) -> ResumeJobSkillScoreResult | None:
    """Return a cached skill score for the same resume, job, and threshold."""
    stmt = text(
        f"""
        select
            resume_job_skill_score_id,
            resume_parse_id,
            job_posting_raw_id,
            skill_match_score,
            matched_skill_count,
            total_job_skill_count,
            missing_skill_count
        from {RESUME_JOB_SKILL_SCORES_TABLE}
        where resume_parse_id = :resume_parse_id
          and job_posting_raw_id = :job_posting_raw_id
          and fuzzy_threshold = :fuzzy_threshold
        """
    )

    row = session.execute(
        stmt,
        {
            "resume_parse_id": resume_parse_id,
            "job_posting_raw_id": job_posting_raw_id,
            "fuzzy_threshold": fuzzy_threshold,
        },
    ).mappings().one_or_none()

    if row is None:
        return None

    return ResumeJobSkillScoreResult(
        resume_job_skill_score_id=row["resume_job_skill_score_id"],
        resume_parse_id=row["resume_parse_id"],
        job_posting_raw_id=row["job_posting_raw_id"],
        skill_match_score=float(row["skill_match_score"]),
        matched_skill_count=row["matched_skill_count"],
        total_job_skill_count=row["total_job_skill_count"],
        missing_skill_count=row["missing_skill_count"],
    )


def insert_resume_job_skill_score(
    session: Session,
    resume_parse_id: int,
    job_posting_raw_id: int,
    skill_match_score: float,
    matched_skill_count: int,
    total_job_skill_count: int,
    missing_skill_count: int,
    fuzzy_threshold: float,
) -> int:
    """Insert the skill-match summary row and return its generated id."""
    stmt = text(
        f"""
        insert into {RESUME_JOB_SKILL_SCORES_TABLE} (
            resume_parse_id,
            job_posting_raw_id,
            skill_match_score,
            matched_skill_count,
            total_job_skill_count,
            missing_skill_count,
            fuzzy_threshold
        )
        values (
            :resume_parse_id,
            :job_posting_raw_id,
            :skill_match_score,
            :matched_skill_count,
            :total_job_skill_count,
            :missing_skill_count,
            :fuzzy_threshold
        )
        returning resume_job_skill_score_id
        """
    )

    return session.execute(
        stmt,
        {
            "resume_parse_id": resume_parse_id,
            "job_posting_raw_id": job_posting_raw_id,
            "skill_match_score": skill_match_score,
            "matched_skill_count": matched_skill_count,
            "total_job_skill_count": total_job_skill_count,
            "missing_skill_count": missing_skill_count,
            "fuzzy_threshold": fuzzy_threshold,
        },
    ).scalar_one()


def insert_resume_job_skill_matches(
    session: Session,
    matches: list[dict],
) -> None:
    """Insert per-job-skill match details for a skill score."""
    if not matches:
        return

    stmt = text(
        f"""
        insert into {RESUME_JOB_SKILL_MATCHES_TABLE} (
            resume_job_skill_score_id,
            job_skill_id,
            job_skill_name,
            matched_resume_skill_id,
            matched_resume_skill_name,
            fuzzy_score,
            is_matched
        )
        values (
            :resume_job_skill_score_id,
            :job_skill_id,
            :job_skill_name,
            :matched_resume_skill_id,
            :matched_resume_skill_name,
            :fuzzy_score,
            :is_matched
        )
        """
    )

    session.execute(stmt, matches)


def score_resume_skills_against_job(
    session: Session,
    resume_parse_id: int,
    job_posting_raw_id: int,
) -> Result[ResumeJobSkillScoreResult]:
    """
    Score extracted resume skills against extracted job skills.

    This scorer assumes upstream skill extraction is complete. It returns an
    existing score for the same resume, job, and fuzzy threshold, but it will not
    extract missing inputs. Missing resume skills or job skills are treated as
    pipeline errors.
    """
    try:
        threshold = round(float(ResumeConfig.SKILL_FUZZY_MATCH_THRESHOLD.value), 2)
        print_announcement(
            "skill scoring",
            f"resume_parse_id={resume_parse_id} job_posting_raw_id={job_posting_raw_id}",
        )

        existing_score = fetch_existing_resume_job_skill_score(
            session=session,
            resume_parse_id=resume_parse_id,
            job_posting_raw_id=job_posting_raw_id,
            fuzzy_threshold=threshold,
        )
        if existing_score is not None:
            session.commit()
            print_message("skill scoring", "finish")
            return Result(
                result=ScrapeResult.SUCCESSFUL,
                content=existing_score,
            )

        resume_skills = fetch_resume_skills(
            session=session,
            resume_parse_id=resume_parse_id,
        )
        if not resume_skills:
            raise RuntimeError(
                "missing extracted resume skills for "
                f"resume_parse_id={resume_parse_id}"
            )

        job_skills = fetch_job_skills(
            session=session,
            job_posting_raw_id=job_posting_raw_id,
        )
        if not job_skills:
            raise RuntimeError(
                "missing extracted job skills for "
                f"job_posting_raw_id={job_posting_raw_id}"
            )

        detail_rows: list[dict] = []
        matched_skill_count = 0

        for job_skill in job_skills:
            best_resume_skill, fuzzy_score = _best_resume_skill_match(
                job_skill_name=job_skill["skill_name"],
                resume_skills=resume_skills,
            )
            is_matched = best_resume_skill is not None and fuzzy_score >= threshold
            if is_matched:
                matched_skill_count += 1

            detail_rows.append(
                {
                    "resume_job_skill_score_id": None,
                    "job_skill_id": job_skill["skill_id"],
                    "job_skill_name": job_skill["skill_name"],
                    "matched_resume_skill_id": (
                        best_resume_skill["skill_id"]
                        if is_matched and best_resume_skill is not None
                        else None
                    ),
                    "matched_resume_skill_name": (
                        best_resume_skill["skill_name"]
                        if is_matched and best_resume_skill is not None
                        else None
                    ),
                    "fuzzy_score": round(fuzzy_score, 6),
                    "is_matched": is_matched,
                }
            )

        total_job_skill_count = len(job_skills)
        missing_skill_count = total_job_skill_count - matched_skill_count
        skill_match_score = round(
            (matched_skill_count / total_job_skill_count) * 100,
            2,
        )

        resume_job_skill_score_id = insert_resume_job_skill_score(
            session=session,
            resume_parse_id=resume_parse_id,
            job_posting_raw_id=job_posting_raw_id,
            skill_match_score=skill_match_score,
            matched_skill_count=matched_skill_count,
            total_job_skill_count=total_job_skill_count,
            missing_skill_count=missing_skill_count,
            fuzzy_threshold=threshold,
        )

        for row in detail_rows:
            row["resume_job_skill_score_id"] = resume_job_skill_score_id

        insert_resume_job_skill_matches(
            session=session,
            matches=detail_rows,
        )
        session.commit()
        print_message("skill scoring", "finish")

        return Result(
            result=ScrapeResult.SUCCESSFUL,
            content=ResumeJobSkillScoreResult(
                resume_job_skill_score_id=resume_job_skill_score_id,
                resume_parse_id=resume_parse_id,
                job_posting_raw_id=job_posting_raw_id,
                skill_match_score=skill_match_score,
                matched_skill_count=matched_skill_count,
                total_job_skill_count=total_job_skill_count,
                missing_skill_count=missing_skill_count,
            ),
        )

    except Exception as e:
        session.rollback()
        print_message("skill scoring", "failed")
        return Result(
            result=ScrapeResult.FAILED,
            content=None,
            error=str(e),
        )


def fetch_resume_job_skill_score_details(
    session: Session,
    resume_job_skill_score_id: int,
) -> dict | None:
    """Return a skill score row with its per-skill match details."""
    score_stmt = text(
        f"""
        select
            resume_job_skill_score_id,
            resume_parse_id,
            job_posting_raw_id,
            skill_match_score,
            matched_skill_count,
            total_job_skill_count,
            missing_skill_count,
            fuzzy_threshold,
            scored_at
        from {RESUME_JOB_SKILL_SCORES_TABLE}
        where resume_job_skill_score_id = :resume_job_skill_score_id
        """
    )

    score_row = session.execute(
        score_stmt,
        {"resume_job_skill_score_id": resume_job_skill_score_id},
    ).mappings().one_or_none()

    if score_row is None:
        return None

    matches_stmt = text(
        f"""
        select
            job_skill_id,
            job_skill_name,
            matched_resume_skill_id,
            matched_resume_skill_name,
            fuzzy_score,
            is_matched
        from {RESUME_JOB_SKILL_MATCHES_TABLE}
        where resume_job_skill_score_id = :resume_job_skill_score_id
        order by is_matched desc, fuzzy_score desc, job_skill_name
        """
    )

    match_rows = session.execute(
        matches_stmt,
        {"resume_job_skill_score_id": resume_job_skill_score_id},
    ).mappings().all()

    return {
        "score": dict(score_row),
        "matches": [dict(row) for row in match_rows],
    }
