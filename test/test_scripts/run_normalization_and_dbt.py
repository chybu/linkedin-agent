import json, os, subprocess
from collections import deque
from pathlib import Path
from sqlalchemy import bindparam, text

from linkedin_tool.db.base import SessionLocal
from log import print_message, print_announcement
from linkedin_tool.normalization.extract_skill import extract_skills_for_job_postings
from linkedin_tool.normalization.llm import GroqLLMNormalizer
from linkedin_tool.normalization.pipeline import run_normalization_pipeline
from linkedin_tool.normalization.repository import NormalizationRepository
from linkedin_tool.normalization.clean_description import clean_descriptions_for_job_postings
from linkedin_tool.schema import ScrapeResult, Result
from config import NormalizationConfig
from linkedin_tool.schema import ScrapeResult, Result, ProcessStage

REPO_ROOT = Path(__file__).resolve().parents[1]
DBT_PROJECT_DIR = REPO_ROOT / "linkedin_dbt"
DBT_PROFILES_DIR = DBT_PROJECT_DIR / ".dbt"

def chunks(items: list[int], size: int):
    for i in range(0, len(items), size):
        yield items[i : i + size]

def fetch_scrape_ids_to_process(session) -> list[int]:
    rows = session.execute(
        text(
            """
            select sr.scrape_run_id
            from bronze.run_scrapes sr
            where sr.status = 'successful'
              and exists (
                  select 1
                  from bronze.raw_job_postings r
                  where r.scrape_run_id = sr.scrape_run_id
              )
              and not exists (
                  select 1
                  from bronze.run_normalization_processes npr
                  where npr.status = 'successful'
                    and sr.scrape_run_id = any(npr.scrape_run_ids)
              )
            order by sr.scrape_run_id
            """
        )
    ).scalars().all()

    return list(rows)

def fetch_unextracted_ready_job_posting_raw_ids(
    session,
    scrape_ids: list[int],
) -> list[int]:
    if not scrape_ids:
        return []

    stmt = (
        text(
            """
            select distinct r.job_posting_raw_id
            from bronze.raw_job_postings r
            inner join bronze.ctl_ready_job_postings sr
                on sr.scrape_run_id = r.scrape_run_id
               and sr.job_posting_raw_id = r.job_posting_raw_id
            where r.scrape_run_id in :scrape_ids
              and not exists (
                  select 1
                  from silver.bridge_job_posting_skills js
                  where js.job_posting_raw_id = r.job_posting_raw_id
              )
            order by r.job_posting_raw_id
            """
        ).bindparams(bindparam("scrape_ids", expanding=True))
    )

    rows = session.execute(stmt, {"scrape_ids": scrape_ids}).scalars().all()
    return list(rows)

def create_process_run(session, scrape_ids: list[int]) -> int:
    process_run_id = session.execute(
        text(
            """
            insert into bronze.run_normalization_processes (
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
    stage: ProcessStage,
    status: ScrapeResult = ScrapeResult.RUNNING,
    error: str | None = None,
) -> None:
    session.execute(
        text(
            """
            update bronze.run_normalization_processes
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
            "stage": stage.value,
            "status": status.value,
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
                str(DBT_PROJECT_DIR),
                "--profiles-dir",
                str(DBT_PROFILES_DIR),
                "--select",
                "ctl_ready_job_postings",
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
            str(DBT_PROJECT_DIR),
            "--profiles-dir",
            str(DBT_PROFILES_DIR),
            "--select",
            "stg_job_postings dim_companies dim_locations dim_titles fact_job_postings",
        ],
        check=True,
        env=env_silver,
    )

def process_scrape_batch(scrape_ids: list[int], api_key:str) -> Result:
    process_run_id: int | None = None
    current_stage = ProcessStage.NORMALIZATION
    groq_normalizer =  GroqLLMNormalizer(api_key=api_key)

    try:
        with SessionLocal() as session:
            process_run_id = create_process_run(session, scrape_ids)

        with SessionLocal() as session:
            repo = NormalizationRepository(session)
            normalization_res = run_normalization_pipeline(
                repo=repo,
                scrape_run_ids=scrape_ids,
                llm_normalizer=groq_normalizer,
            )

        if normalization_res.result != ScrapeResult.SUCCESSFUL:
            error = normalization_res.error or "normalization failed"
            with SessionLocal() as session:
                update_process_run(
                    session=session,
                    process_run_id=process_run_id,
                    stage=ProcessStage.NORMALIZATION,
                    status=ScrapeResult.FAILED,
                    error=error,
                )
                
            return Result(
                ScrapeResult.FAILED,
                content=None,
                error=normalization_res.error
            )

        ready_ids = normalization_res.ready_job_posting_raw_ids

        if NormalizationConfig.EXTRACT_UNEXTRACTED_READY_JOBS.value:
            with SessionLocal() as session:
                unextracted_ready_ids = fetch_unextracted_ready_job_posting_raw_ids(
                    session=session,
                    scrape_ids=scrape_ids,
                )

            ready_ids = sorted(set(ready_ids) | set(unextracted_ready_ids))


        current_stage = ProcessStage.DBT
        with SessionLocal() as session:
            update_process_run(
                session=session,
                process_run_id=process_run_id,
                stage=ProcessStage.DBT,
            )

        run_dbt_for_ready_ids(ready_ids)

        if ready_ids:

            current_stage = ProcessStage.DESCRIPTION_CLEANING
            with SessionLocal() as session:
                update_process_run(
                    session=session,
                    process_run_id=process_run_id,
                    stage=ProcessStage.DESCRIPTION_CLEANING,
                )

            with SessionLocal() as session:
                clean_res = clean_descriptions_for_job_postings(
                    session=session,
                    job_posting_raw_ids=ready_ids,
                    llm_normalizer=groq_normalizer,
                )
            if clean_res.result != ScrapeResult.SUCCESSFUL:
                error = clean_res.error
                update_process_run(
                    session=session,
                    process_run_id=process_run_id,
                    stage=ProcessStage.DESCRIPTION_CLEANING,
                    status=ScrapeResult.FAILED,
                    error=error,
                )
                return Result(
                    ScrapeResult.FAILED,
                    content = None,
                    error = clean_res.error
                )
            
            current_stage = ProcessStage.SKILL_EXTRACTION
            with SessionLocal() as session:
                update_process_run(
                    session=session,
                    process_run_id=process_run_id,
                    stage=ProcessStage.SKILL_EXTRACTION
                ) 
                
            with SessionLocal() as session:
                skill_res = extract_skills_for_job_postings(
                    session=session,
                    job_posting_raw_ids=ready_ids,
                    llm_normalizer=groq_normalizer,
                )
            if skill_res.result != ScrapeResult.SUCCESSFUL:
                error = skill_res.error or "skill extraction failed"
                with SessionLocal() as session:
                    update_process_run(
                        session=session,
                        process_run_id=process_run_id,
                        stage=ProcessStage.SKILL_EXTRACTION,
                        status=ScrapeResult.FAILED,
                        error=error,
                    )
                return Result(
                    ScrapeResult.FAILED,
                    content = None,
                    error = skill_res.error
                )

        with SessionLocal() as session:
            update_process_run(
                session=session,
                process_run_id=process_run_id,
                stage=ProcessStage.SKILL_EXTRACTION,
                status=ScrapeResult.SUCCESSFUL,
                error=None,
            )

        return Result(
            ScrapeResult.SUCCESSFUL
        )

    except subprocess.CalledProcessError as e:
        error = f"dbt failed with exit code {e.returncode}"
        if process_run_id is not None:
            with SessionLocal() as session:
                update_process_run(
                    session=session,
                    process_run_id=process_run_id,
                    stage=ProcessStage.DBT,
                    status=ScrapeResult.FAILED,
                    error=error,
                )
        return Result(
            ScrapeResult.FAILED,
            content=None,
            error=error
        )

    except Exception as e:
        error = str(e)
        if process_run_id is not None:
            with SessionLocal() as session:
                update_process_run(
                    session=session,
                    process_run_id=process_run_id,
                    stage=current_stage,
                    status=ScrapeResult.FAILED,
                    error=error,
                )
        return Result(
            ScrapeResult.FAILED,
            content=None,
            error=error
        )


with SessionLocal() as session:
    scrape_ids_to_process = fetch_scrape_ids_to_process(session)

if not scrape_ids_to_process:
    print_message("normalization", "No scrape runs to process")
    raise SystemExit(0)

scrape_batch_queue = deque(
    chunks(scrape_ids_to_process, NormalizationConfig.BATCH_SIZE.value)
)

for api_key in NormalizationConfig.GROQ_API_KEYS.value:
        
    while scrape_batch_queue:
        
        scrape_ids = scrape_batch_queue[0]
        print_message("scrape_ids", str(scrape_ids))

        batch_result = process_scrape_batch(scrape_ids, api_key)
        if batch_result.result!=ScrapeResult.SUCCESSFUL:
            print_message("error", batch_result.error)
            if "Rate limit reached" in batch_result.error:
                print_message("switching api key")
                break
            else:
                raise SystemExit(1)
        else:
            scrape_batch_queue.popleft()
            
            if not scrape_batch_queue:
                print_announcement("finish normalization and extraction pipeline")
                raise SystemExit(0)

print_message("error", "all Groq API keys failed")
raise SystemExit(1)
