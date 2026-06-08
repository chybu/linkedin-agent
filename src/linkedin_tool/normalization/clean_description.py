from time import sleep

from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from log import print_message
from linkedin_tool.normalization.llm import GroqLLMNormalizer
from linkedin_tool.schema import Result, ScrapeResult
from config import NormalizationConfig


RAW_JOB_POSTINGS_TABLE = "bronze.raw_job_postings"
JOB_DESCRIPTION_CLEANING_TABLE = "bronze.map_job_description_cleaning"


def _chunks(items: list[dict], size: int):
    for i in range(0, len(items), size):
        yield items[i : i + size]


def _fetch_uncleaned_descriptions(
    session: Session,
    job_posting_raw_ids: list[int],
) -> list[dict]:
    if not job_posting_raw_ids:
        return []

    stmt = (
        text(
            f"""
            select
                r.job_posting_raw_id,
                r.description_raw
            from {RAW_JOB_POSTINGS_TABLE} r
            where r.job_posting_raw_id in :job_posting_raw_ids
              and nullif(trim(coalesce(r.description_raw, '')), '') is not null
              and not exists (
                  select 1
                  from {JOB_DESCRIPTION_CLEANING_TABLE} c
                  where c.job_posting_raw_id = r.job_posting_raw_id
              )
            order by r.job_posting_raw_id
            """
        ).bindparams(bindparam("job_posting_raw_ids", expanding=True))
    )

    rows = session.execute(
        stmt,
        {"job_posting_raw_ids": job_posting_raw_ids},
    ).mappings().all()

    return [dict(row) for row in rows]


def _upsert_cleaned_descriptions(session: Session, rows: list[dict]) -> None:
    if not rows:
        return

    stmt = text(
        f"""
        insert into {JOB_DESCRIPTION_CLEANING_TABLE} (
            job_posting_raw_id,
            description_raw,
            description_cleaned
        )
        values (
            :job_posting_raw_id,
            :description_raw,
            :description_cleaned
        )
        on conflict (job_posting_raw_id) do update set
            description_raw = excluded.description_raw,
            description_cleaned = excluded.description_cleaned
        """
    )

    session.execute(stmt, rows)


def clean_descriptions_for_job_postings(
    session: Session,
    job_posting_raw_ids: list[int],
    llm_normalizer: GroqLLMNormalizer,
) -> Result[list[dict]]:
    print_message("Description cleaning", "start pipeline")

    rows = _fetch_uncleaned_descriptions(session, job_posting_raw_ids)
    if not rows:
        print_message("Description cleaning", "no uncleaned descriptions")
        return Result(
            result=ScrapeResult.SUCCESSFUL,
            content=[],
        )

    cleaned_rows: list[dict] = []
    batches = list(_chunks(rows, NormalizationConfig.BATCH_SIZE.value))

    for batch_i, batch in enumerate(batches):
        print_message("Description cleaning", f"batch {batch_i + 1}/{len(batches)}")

        rows_to_upsert: list[dict] = []

        for row_i, row in enumerate(batch):
            job_posting_raw_id = row["job_posting_raw_id"]
            description_raw = row["description_raw"]

            clean_res = llm_normalizer.clean_description(description_raw)

            if clean_res.result != ScrapeResult.SUCCESSFUL:
                print_message("error", clean_res.error or "description cleaning failed")
                return Result(
                    result=ScrapeResult.FAILED,
                    content=cleaned_rows,
                    error=(
                        "description cleaning failed for "
                        f"job_posting_raw_id={job_posting_raw_id}: {clean_res.error}"
                    ),
                )

            description_cleaned = clean_res.content or ""

            rows_to_upsert.append(
                {
                    "job_posting_raw_id": job_posting_raw_id,
                    "description_raw": description_raw,
                    "description_cleaned": description_cleaned,
                }
            )

            if row_i < len(batch) - 1:
                sleep(NormalizationConfig.LLM_INTERVAL.value)

        _upsert_cleaned_descriptions(session, rows_to_upsert)
        session.commit()
        cleaned_rows.extend(rows_to_upsert)

        if batch_i < len(batches) - 1:
            sleep(NormalizationConfig.LLM_INTERVAL.value)

    print_message("Description cleaning", "finish pipeline")
    return Result(
        result=ScrapeResult.SUCCESSFUL,
        content=cleaned_rows,
    )