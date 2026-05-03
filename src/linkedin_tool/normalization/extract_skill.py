from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from linkedin_tool.log import print_message
from linkedin_tool.normalization.llm import GroqLLMNormalizer
from linkedin_tool.schema import Result, ScrapeResult
from linkedin_tool.setting import NormalizationConfig
from time import sleep


FACT_JOB_POSTINGS_TABLE = "silver.fact_job_postings"
DIM_SKILLS_TABLE = "silver.dim_skills"
JOB_POSTING_SKILL_TABLE = "silver.job_posting_skills"

def _chunks(items: list[dict], size: int):
    for i in range(0, len(items), size):
        yield items[i : i + size]

def _normalize_skill_key(skill: str) -> str:
    return " ".join((skill or "").strip().lower().split())

def _fetch_unprocessed_descriptions(
    session: Session,
    job_posting_raw_ids: list[int],
) -> list[dict]:
    if not job_posting_raw_ids:
        return []

    stmt = (
        text(
            f"""
            select
                f.job_posting_raw_id,
                f.description
            from {FACT_JOB_POSTINGS_TABLE} f
            where f.job_posting_raw_id in :job_posting_raw_ids
              and nullif(trim(coalesce(f.description, '')), '') is not null
              and not exists (
                  select 1
                  from {JOB_POSTING_SKILL_TABLE} js
                  where js.job_posting_raw_id = f.job_posting_raw_id
              )
            order by f.job_posting_raw_id
            """
        ).bindparams(bindparam("job_posting_raw_ids", expanding=True))
    )

    rows = session.execute(
        stmt,
        {"job_posting_raw_ids": job_posting_raw_ids},
    ).mappings().all()

    return [dict(row) for row in rows]

def _upsert_skill_dim(session: Session, skills: list[str]) -> None:
    rows = [
        {
            "skill_name": skill,
        }
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
    skill_names = sorted({_normalize_skill_key(skill) for skill in skills if _normalize_skill_key(skill)})
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

def _upsert_job_posting_skills(session: Session, rows_to_upsert: list[dict]) -> None:
    if not rows_to_upsert:
        return

    stmt = text(
        f"""
        insert into {JOB_POSTING_SKILL_TABLE} (
            job_posting_raw_id,
            skill_id
        )
        values (
            :job_posting_raw_id,
            :skill_id
        )
        on conflict (job_posting_raw_id, skill_id) do nothing
        """
    )

    session.execute(stmt, rows_to_upsert)

def extract_skills_for_job_postings(
    session: Session,
    job_posting_raw_ids: list[int],
    llm_normalizer: GroqLLMNormalizer,
) -> Result[list[dict]]:
    print_message("Skill extraction", "start pipeline")

    rows = _fetch_unprocessed_descriptions(session, job_posting_raw_ids)
    if not rows:
        print_message("Skill extraction", "no unprocessed descriptions")
        return Result(
            result=ScrapeResult.SUCCESSFUL,
            content=[],
        )

    inserted_rows: list[dict] = []
    batches = list(_chunks(rows, NormalizationConfig.BATCH_SIZE.value))
    for batch_i, batch in enumerate(batches):
        print_message("Skill extraction", f"batch {batch_i + 1}/{len(batches)}")

        extracted_rows: list[dict] = []
        skill_names: list[str] = []

        for row_i, row in enumerate(batch):
            job_posting_raw_id = row["job_posting_raw_id"]
            skill_res = llm_normalizer.extract_skills_from_description(row["description"])
            if skill_res.result != ScrapeResult.SUCCESSFUL:
                print_message("error", skill_res.error or "skill extraction failed")
                return Result(
                    result=ScrapeResult.FAILED,
                    content=inserted_rows,
                    error=f"skill extraction failed for job_posting_raw_id={job_posting_raw_id}: {skill_res.error}",
                )

            for skill in skill_res.content or []:
                skill_name = _normalize_skill_key(skill)
                if not skill_name:
                    continue

                skill_names.append(skill_name)
                extracted_rows.append(
                    {
                        "job_posting_raw_id": job_posting_raw_id,
                        "skill_name": skill_name,
                    }
                )

            if row_i < len(batch) - 1:
                sleep(NormalizationConfig.LLM_INTERVAL.value)

        if not extracted_rows:
            continue

        _upsert_skill_dim(session, skill_names)
        skill_id_by_name = _fetch_skill_ids(session, skill_names)

        rows_to_upsert: list[dict] = []
        for row in extracted_rows:
            skill_id = skill_id_by_name.get(row["skill_name"])
            if skill_id is None:
                continue

            rows_to_upsert.append(
                {
                    "job_posting_raw_id": row["job_posting_raw_id"],
                    "skill_id": skill_id,
                }
            )

        _upsert_job_posting_skills(session, rows_to_upsert)
        session.commit()
        inserted_rows.extend(rows_to_upsert)

        if batch_i < len(batches) - 1:
            sleep(NormalizationConfig.LLM_INTERVAL.value)

    print_message("Skill extraction", "finish pipeline")
    return Result(
        result=ScrapeResult.SUCCESSFUL,
        content=inserted_rows,
    )
