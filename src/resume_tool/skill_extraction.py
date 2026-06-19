from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session
from time import sleep

from linkedin_tool.schema import Result, ScrapeResult
from config import NormalizationConfig
from log import print_announcement, print_message
from resume_tool.llm import GroqResumeExtractor

RAW_RESUME_PARSES_TABLE = "bronze.raw_resume_parses"
DIM_SKILLS_TABLE = "silver.dim_skills"
BRIDGE_RESUME_PARSE_SKILLS_TABLE = "silver.bridge_resume_parse_skills"


def _normalize_skill_key(skill: str) -> str:
    return " ".join((skill or "").strip().lower().split())


def _fetch_resume_markdown(session: Session, resume_parse_id: int) -> str:
    """Return stored resume markdown for a parse id, or fail if the parse is missing."""
    stmt = text(
        f"""
        select resume_md
        from {RAW_RESUME_PARSES_TABLE}
        where resume_parse_id = :resume_parse_id
        """
    )

    resume_md = session.execute(
        stmt,
        {"resume_parse_id": resume_parse_id},
    ).scalar_one_or_none()

    if not resume_md:
        raise RuntimeError(
            "missing resume markdown for "
            f"resume_parse_id={resume_parse_id}"
        )

    return resume_md


def _resume_skills_already_exist(session: Session, resume_parse_id: int) -> bool:
    """Check whether resume skill extraction has already populated the bridge table."""
    stmt = text(
        f"""
        select exists (
            select 1
            from {BRIDGE_RESUME_PARSE_SKILLS_TABLE}
            where resume_parse_id = :resume_parse_id
        )
        """
    )

    return bool(
        session.execute(
            stmt,
            {"resume_parse_id": resume_parse_id},
        ).scalar_one()
    )


def _upsert_skill_dim(session: Session, skills: list[str]) -> None:
    """Insert normalized skill names into the shared skill dimension."""
    rows = [
        {"skill_name": skill}
        for skill in skills
        if _normalize_skill_key(skill)
    ]
    if not rows:
        return

    stmt = text(
        f"""
        insert into {DIM_SKILLS_TABLE} (
            skill_name
        )
        values (
            :skill_name
        )
        on conflict (skill_name) do nothing
        """
    )

    session.execute(stmt, rows)


def _fetch_skill_ids(session: Session, skills: list[str]) -> dict[str, int]:
    """Fetch skill ids keyed by normalized skill name."""
    skill_names = sorted({
        _normalize_skill_key(skill)
        for skill in skills
        if _normalize_skill_key(skill)
    })
    if not skill_names:
        return {}

    stmt = (
        text(
            f"""
            select
                skill_id,
                skill_name
            from {DIM_SKILLS_TABLE}
            where skill_name in :skill_names
            """
        ).bindparams(bindparam("skill_names", expanding=True))
    )

    rows = session.execute(
        stmt,
        {"skill_names": skill_names},
    ).all()

    return {skill_name: skill_id for skill_id, skill_name in rows}


def _upsert_resume_parse_skills(session: Session, rows: list[dict]) -> None:
    """Insert resume-to-skill bridge rows, ignoring duplicate links."""
    if not rows:
        return

    stmt = text(
        f"""
        insert into {BRIDGE_RESUME_PARSE_SKILLS_TABLE} (
            resume_parse_id,
            skill_id
        )
        values (
            :resume_parse_id,
            :skill_id
        )
        on conflict (resume_parse_id, skill_id) do nothing
        """
    )

    session.execute(stmt, rows)


def extract_skills_for_resume_parse(
    session: Session,
    resume_parse_id: int,
    resume_extractor: GroqResumeExtractor,
) -> Result[list[dict]]:
    """
    Extract and cache skills for an already parsed resume.

    This is a preparation step, not a scorer. It skips when resume skills already
    exist, requires `bronze.raw_resume_parses.resume_md` to be present, writes
    any new skills into `silver.dim_skills`, and links them through
    `silver.bridge_resume_parse_skills`.
    """
    try:
        print_announcement(
            "resume skill extraction",
            f"resume_parse_id={resume_parse_id}",
        )

        if _resume_skills_already_exist(session, resume_parse_id):
            session.commit()
            print_message("resume skill extraction", "finish")
            return Result(
                result=ScrapeResult.SUCCESSFUL,
                content=[],
            )

        resume_md = _fetch_resume_markdown(
            session=session,
            resume_parse_id=resume_parse_id,
        )
        skill_res = resume_extractor.extract_skills_from_resume(resume_md)
        if skill_res.result != ScrapeResult.SUCCESSFUL:
            session.rollback()
            print_message("resume skill extraction", "failed")
            return Result(
                result=ScrapeResult.FAILED,
                content=None,
                error=skill_res.error,
            )

        seen_skill_names: set[str] = set()
        skill_names: list[str] = []
        for skill in skill_res.content or []:
            skill_name = _normalize_skill_key(skill)
            if not skill_name or skill_name in seen_skill_names:
                continue
            seen_skill_names.add(skill_name)
            skill_names.append(skill_name)

        if not skill_names:
            session.commit()
            print_message("resume skill extraction", "finish")
            return Result(
                result=ScrapeResult.SUCCESSFUL,
                content=[],
            )

        _upsert_skill_dim(session, skill_names)
        skill_id_by_name = _fetch_skill_ids(session, skill_names)

        rows_to_upsert: list[dict] = []
        for skill_name in skill_names:
            skill_id = skill_id_by_name.get(skill_name)
            if skill_id is None:
                continue

            rows_to_upsert.append(
                {
                    "resume_parse_id": resume_parse_id,
                    "skill_id": skill_id,
                }
            )

        _upsert_resume_parse_skills(session, rows_to_upsert)
        session.commit()
        print_message("resume skill extraction", "finish")

        return Result(
            result=ScrapeResult.SUCCESSFUL,
            content=rows_to_upsert,
        )

    except Exception as e:
        session.rollback()
        print_message("resume skill extraction", "failed")
        return Result(
            result=ScrapeResult.FAILED,
            content=None,
            error=str(e),
        )
