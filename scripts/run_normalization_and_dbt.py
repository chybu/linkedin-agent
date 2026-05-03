import json
import os
import subprocess

from sqlalchemy import text

from linkedin_tool.db.base import SessionLocal
from linkedin_tool.log import print_message
from linkedin_tool.normalization.extract_skill import extract_skills_for_job_postings
from linkedin_tool.normalization.llm import GroqLLMNormalizer
from linkedin_tool.normalization.pipeline import run_normalization_pipeline
from linkedin_tool.normalization.repository import NormalizationRepository
from linkedin_tool.schema import ScrapeResult
from linkedin_tool.setting import NormalizationConfig


def chunks(items: list[int], size: int):
    for i in range(0, len(items), size):
        yield items[i : i + size]

def fetch_scrape_ids_to_process(session) -> list[int]:
    rows = session.execute(
        text(
            """
            select sr.scrape_run_id
            from bronze.scrape_runs sr
            where sr.status = 'successful'
              and exists (
                  select 1
                  from bronze.job_postings_raw r
                  where r.scrape_run_id = sr.scrape_run_id
              )
              and not exists (
                  select 1
                  from bronze.normalization_process_runs npr
                  where npr.status = 'successful'
                    and sr.scrape_run_id = any(npr.scrape_run_ids)
              )
            order by sr.scrape_run_id
            """
        )
    ).scalars().all()

    return list(rows)

def create_process_run(session, scrape_ids: list[int]) -> int:
    process_run_id = session.execute(
        text(
            """
            insert into bronze.normalization_process_runs (
                scrape_run_ids,
                status,
                stage,
                error
            )
            values (
                :scrape_run_ids,
                'running',
                'normalization',
                null
            )
            returning normalization_process_run_id
            """
        ),
        {"scrape_run_ids": scrape_ids},
    ).scalar_one()

    session.commit()
    return process_run_id

def update_process_run(
    session,
    process_run_id: int,
    stage: str,
    status: str = "running",
    error: str | None = None,
) -> None:
    session.execute(
        text(
            """
            update bronze.normalization_process_runs
            set
                stage = :stage,
                status = :status,
                error = :error,
                finished_at = case
                    when :status in ('successful', 'failed') then now()
                    else finished_at
                end
            where normalization_process_run_id = :process_run_id
            """
        ),
        {
            "process_run_id": process_run_id,
            "stage": stage,
            "status": status,
            "error": error,
        },
    )
    session.commit()

def run_dbt_for_ready_ids(ready_ids: list[int]) -> None:
    if ready_ids:
        vars_payload = json.dumps({"ready_job_posting_raw_ids": ready_ids})

        env_bronze = os.environ.copy()
        env_bronze["DBT_SCHEMA"] = "bronze"

        subprocess.run(
            [
                "dbt",
                "run",
                "--project-dir",
                "linkedin_dbt",
                "--select",
                "staging_ready_job_postings",
                "--vars",
                vars_payload,
            ],
            check=True,
            env=env_bronze,
        )
    else:
        print_message("warning", "No ready_job_posting_raw_ids")

    env_silver = os.environ.copy()
    env_silver["DBT_SCHEMA"] = "silver"

    subprocess.run(
        [
            "dbt",
            "run",
            "--project-dir",
            "linkedin_dbt",
            "--select",
            "stg_job_postings dim_companies dim_locations dim_titles fact_job_postings",
        ],
        check=True,
        env=env_silver,
    )

def process_scrape_batch(scrape_ids: list[int]) -> bool:
    process_run_id: int | None = None
    current_stage = "normalization"

    try:
        with SessionLocal() as session:
            process_run_id = create_process_run(session, scrape_ids)

        with SessionLocal() as session:
            repo = NormalizationRepository(session)
            llm_normalizer = GroqLLMNormalizer()
            normalization_res = run_normalization_pipeline(
                repo=repo,
                scrape_run_ids=scrape_ids,
                llm_normalizer=llm_normalizer,
            )

        if normalization_res.result != ScrapeResult.SUCCESSFUL:
            error = normalization_res.error or "normalization failed"
            with SessionLocal() as session:
                update_process_run(
                    session=session,
                    process_run_id=process_run_id,
                    stage="normalization",
                    status="failed",
                    error=error,
                )
            print_message("error", error)
            return False

        ready_ids = normalization_res.ready_job_posting_raw_ids

        current_stage = "dbt"
        with SessionLocal() as session:
            update_process_run(
                session=session,
                process_run_id=process_run_id,
                stage="dbt",
            )

        run_dbt_for_ready_ids(ready_ids)

        current_stage = "skill_extraction"
        with SessionLocal() as session:
            update_process_run(
                session=session,
                process_run_id=process_run_id,
                stage="skill_extraction",
            )

        if ready_ids:
            with SessionLocal() as session:
                skill_res = extract_skills_for_job_postings(
                    session=session,
                    job_posting_raw_ids=ready_ids,
                    llm_normalizer=GroqLLMNormalizer(),
                )

            if skill_res.result != ScrapeResult.SUCCESSFUL:
                error = skill_res.error or "skill extraction failed"
                with SessionLocal() as session:
                    update_process_run(
                        session=session,
                        process_run_id=process_run_id,
                        stage="skill_extraction",
                        status="failed",
                        error=error,
                    )
                print_message("error", error)
                return False

        with SessionLocal() as session:
            update_process_run(
                session=session,
                process_run_id=process_run_id,
                stage="skill_extraction",
                status="successful",
                error=None,
            )

        print_message("normalization_process_run_id", str(process_run_id))
        print_message("status", "successful")
        return True

    except subprocess.CalledProcessError as e:
        error = f"dbt failed with exit code {e.returncode}"
        if process_run_id is not None:
            with SessionLocal() as session:
                update_process_run(
                    session=session,
                    process_run_id=process_run_id,
                    stage="dbt",
                    status="failed",
                    error=error,
                )
        print_message("error", error)
        return False

    except Exception as e:
        error = str(e)
        if process_run_id is not None:
            with SessionLocal() as session:
                update_process_run(
                    session=session,
                    process_run_id=process_run_id,
                    stage=current_stage,
                    status="failed",
                    error=error,
                )
        print_message("error", error)
        return False

with SessionLocal() as session:
    scrape_ids_to_process = fetch_scrape_ids_to_process(session)

if not scrape_ids_to_process:
    print_message("normalization", "No scrape runs to process")
    raise SystemExit(0)

batch_size = NormalizationConfig.BATCH_SIZE.value

for scrape_ids in chunks(scrape_ids_to_process, batch_size):
    print_message("scrape_ids", str(scrape_ids))

    batch_success = process_scrape_batch(scrape_ids)
    if not batch_success:
        print_message("normalization", "Stopping because current batch failed")
        raise SystemExit(1)
