import json
import os
import subprocess
from pathlib import Path
from time import sleep
from threading import Thread

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field
from sqlalchemy import bindparam, text

from config import AgentConfig, NormalizationConfig, ResumeConfig
from linkedin_tool.schema import ExperienceLevel
from linkedin_tool.db.base import SessionLocal
from linkedin_tool.db.repository import BronzeRepository
from linkedin_tool.manager import RequestManager
from linkedin_tool.normalization.clean_description import clean_descriptions_for_job_postings
from linkedin_tool.normalization.extract_skill import extract_skills_for_job_postings
from linkedin_tool.normalization.llm import GroqLLMNormalizer
from linkedin_tool.normalization.pipeline import run_normalization_pipeline
from linkedin_tool.normalization.repository import NormalizationRepository
from linkedin_tool.schema import JobSearchRequest, ScrapeResult, Result
from resume_tool.complete_scoring import (
    compute_complete_score,
    fetch_existing_resume_job_complete_score,
    insert_resume_job_complete_score,
)
from resume_tool.schema import ResumeJobCompleteScoreResult
from resume_tool.semantic_scoring import score_resume_semantic_against_job_evidence
from resume_tool.skill_extraction import extract_skills_for_resume_parse 
from resume_tool.skill_scoring import score_resume_skills_against_job
from resume_tool.llm import GroqResumeExtractor

from agent_server.helper.chat_memory import (
    fetch_compared_job_posting_raw_ids,
    get_active_chat_config,
    insert_chat_job_comparison,
    update_config_next_start_index,
    get_missing_config_fields,
)
from agent_server.helper.llm_rotation import run_with_groq_key_rotation
from agent_server.helper.grading_runs import (
    ResumeGradingRunPhase,
    ResumeGradingRunStatus,
    fail_resume_grading_run,
    cancel_resume_grading_run,
    finish_resume_grading_run,
    update_resume_grading_run_phase,
    update_resume_grading_run_progress,
    create_resume_grading_run,
    get_running_resume_grading_run,
    get_resume_grading_run,
    get_latest_resume_grading_run_for_chat_config,
    is_resume_grading_cancel_requested,
    request_resume_grading_cancel,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
DBT_PROJECT_DIR = REPO_ROOT / "linkedin_dbt"
DBT_PROFILES_DIR = DBT_PROJECT_DIR / ".dbt"


class StartResumeGradingResponse(BaseModel):
    grading_run_id: int = Field(
        description="Id of the resume grading run. Use this id to check progress."
    )
    status: str = Field(
        description="Current lifecycle status of the run."
    )
    phase: str = Field(
        description="Current processing phase of the run."
    )
    message: str = Field(
        description="Short user-facing message explaining what happened."
    )


class GradeResumeResponse(BaseModel):
    stopped_reason: str
    processed_job_count: int
    valid_matched_job_count: int
    new_comparison_count: int


class ResumeGradingStatusResponse(BaseModel):
    status: str = Field(
        description="Current lifecycle status of the run: running, completed, failed, or cancelled."
    )
    phase: str = Field(
        description=(
            "Current processing phase of the run, such as linkedin_scraping, "
            "job_normalization, dbt_processing, description_cleaning, "
            "job_skill_extraction, or resume_scoring."
        )
    )
    processed_job_count: int = Field(
        description="Total number of ready processed jobs produced so far."
    )
    valid_matched_job_count: int = Field(
        description="Total number of processed jobs that matched the target job title and seniority."
    )
    new_comparison_count: int = Field(
        description="Total number of new resume-to-job comparisons inserted so far."
    )
    cancel_requested: bool = Field(
        description="True if the user has requested cancellation for this grading run."
    )
    next_start_index: int | None = Field(
        default=None,
        description="Next LinkedIn search offset that the grading run will try."
    )
    stopped_reason: str | None = Field(
        default=None,
        description="Normal reason the run stopped, if it has completed."
    )
    error_message: str | None = Field(
        default=None,
        description="Error message if the run failed."
    )


class CancelResumeGradingResponse(BaseModel):
    status: str = Field(
        description="Current lifecycle status of the grading run after the cancel request."
    )
    phase: str = Field(
        description="Current processing phase where the grading run is stopping or stopped."
    )
    cancel_requested: bool = Field(
        description="True if cancellation has been requested for a running grading run."
    )
    message: str = Field(
        description="Short user-facing message explaining the cancellation result."
    )


def _set_grading_phase(
    grading_run_id: int,
    phase: ResumeGradingRunPhase,
) -> None:
    with SessionLocal() as session:
        update_resume_grading_run_phase(
            session=session,
            grading_run_id=grading_run_id,
            phase=phase,
        )
        session.commit()


def _update_grading_progress(
    grading_run_id: int,
    processed_job_count: int,
    valid_matched_job_count: int,
    new_comparison_count: int,
    next_start_index: int,
) -> None:
    with SessionLocal() as session:
        update_resume_grading_run_progress(
            session=session,
            grading_run_id=grading_run_id,
            processed_job_count=processed_job_count,
            valid_matched_job_count=valid_matched_job_count,
            new_comparison_count=new_comparison_count,
            next_start_index=next_start_index,
        )
        session.commit()


def _is_grading_cancel_requested(grading_run_id: int) -> bool:
    with SessionLocal() as session:
        return is_resume_grading_cancel_requested(
            session=session,
            grading_run_id=grading_run_id,
        )


def _seniority_mapper(seniority:str) -> ExperienceLevel:
    map = {
        "intern": ExperienceLevel.INTERN,
        "junior": ExperienceLevel.JUNIOR,
        "mid": ExperienceLevel.MID,
        "senior": ExperienceLevel.SENIOR,
        "lead": ExperienceLevel.LEAD,
        "executive": ExperienceLevel.EXECUTIVE,
        "not_applicable": None
    }
    return map[seniority]


def _run_dbt_for_ready_ids(ready_ids: list[int]) -> None:
    if ready_ids:
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
                json.dumps({"ready_job_posting_raw_ids": ready_ids}),
            ],
            check=True,
            env=env_bronze,
        )

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


def _fetch_valid_matched_jobs(
    session,
    ready_ids: list[int],
    job_title: str,
    seniority: str,
) -> list[int]:
    if not ready_ids:
        return []

    stmt = (
        text(
            """
            select distinct job_posting_raw_id
            from silver.fact_job_postings
            where job_posting_raw_id in :ready_ids
              and title_normalized = :job_title
              and seniority = :seniority
            order by job_posting_raw_id
            """
        ).bindparams(bindparam("ready_ids", expanding=True))
    )

    return list(
        session.execute(
            stmt,
            {
                "ready_ids": ready_ids,
                "job_title": job_title,
                "seniority": seniority,
            },
        ).scalars().all()
    )


def _fetch_resume_bullets(session, resume_parse_id: int) -> list[str]:
    evidence = session.execute(
        text(
            """
            select extracted_experience_project_bullets
            from bronze.raw_resume_parses
            where resume_parse_id = :resume_parse_id
            """
        ),
        {"resume_parse_id": resume_parse_id},
    ).scalar_one()

    return [
        " ".join(line.strip().split())
        for line in evidence.splitlines()
        if line.strip()
    ]


def _score_from_resume_parse_id(
    session,
    resume_parse_id: int,
    resume_bullets: list[str],
    job_posting_raw_id: int,
):
    semantic_res = score_resume_semantic_against_job_evidence(
        session=session,
        resume_parse_id=resume_parse_id,
        resume_bullets=resume_bullets,
        job_posting_raw_id=job_posting_raw_id,
    )
    if semantic_res.result != ScrapeResult.SUCCESSFUL or semantic_res.content is None:
        return semantic_res

    skill_extract_res = run_with_groq_key_rotation(
        phase="resume skill extraction",
        call=lambda api_key: extract_skills_for_resume_parse(
            session=session,
            resume_parse_id=resume_parse_id,
            resume_extractor=GroqResumeExtractor(api_key=api_key),
        ),
    )
    if skill_extract_res.result != ScrapeResult.SUCCESSFUL:
        return skill_extract_res
    if skill_extract_res.content:
        sleep(NormalizationConfig.LLM_INTERVAL.value)

    skill_res = score_resume_skills_against_job(
        session=session,
        resume_parse_id=resume_parse_id,
        job_posting_raw_id=job_posting_raw_id,
    )
    if skill_res.result != ScrapeResult.SUCCESSFUL or skill_res.content is None:
        return skill_res

    semantic_score = semantic_res.content
    skill_score = skill_res.content

    existing = fetch_existing_resume_job_complete_score(
        session=session,
        resume_job_semantic_score_id=semantic_score.resume_job_semantic_score_id,
        resume_job_skill_score_id=skill_score.resume_job_skill_score_id,
    )
    if existing is not None:
        return Result(
            result=ScrapeResult.SUCCESSFUL,
            content=existing,
        )

    semantic_weight = float(ResumeConfig.COMPLETE_SCORE_SEMANTIC_WEIGHT.value)
    skill_weight = float(ResumeConfig.COMPLETE_SCORE_SKILL_WEIGHT.value)

    complete = ResumeJobCompleteScoreResult(
        resume_job_semantic_score_id=semantic_score.resume_job_semantic_score_id,
        resume_job_skill_score_id=skill_score.resume_job_skill_score_id,
        resume_parse_id=resume_parse_id,
        job_posting_raw_id=job_posting_raw_id,
        semantic_score=semantic_score.semantic_score,
        skill_match_score=skill_score.skill_match_score,
        complete_score=compute_complete_score(
            semantic_score.semantic_score,
            skill_score.skill_match_score,
            semantic_weight,
            skill_weight,
        ),
        semantic_weight=semantic_weight,
        skill_weight=skill_weight,
    )

    insert_resume_job_complete_score(session=session, result=complete)
    session.commit()

    return Result(
        result=ScrapeResult.SUCCESSFUL,
        content=complete,
    )


def _start_grading_thread(
    grading_run_id: int,
    config: dict,
) -> None:
    thread = Thread(
        target=_run_resume_grading_job_safely,
        kwargs={
            "grading_run_id": grading_run_id,
            "config": config,
        },
        daemon=True,
    )
    thread.start()


def _run_resume_grading_job_safely(
    grading_run_id: int,
    config: dict,
) -> None:
    try:
        run_resume_grading_job(
            grading_run_id=grading_run_id,
            config=config,
        )
    except Exception as exc:
        with SessionLocal() as session:
            fail_resume_grading_run(
                session=session,
                grading_run_id=grading_run_id,
                error_message=f"unexpected_error: {exc}",
            )
            session.commit()


def _fetch_existing_ready_ids_by_job_ids(
    session,
    job_ids: list[int],
) -> list[int]:
    if not job_ids:
        return []

    stmt = (
        text(
            """
            select distinct f.job_posting_raw_id
            from silver.fact_job_postings f
            inner join bronze.raw_job_postings r
                on r.job_posting_raw_id = f.job_posting_raw_id
            where r.job_id in :job_ids
            order by f.job_posting_raw_id
            """
        ).bindparams(bindparam("job_ids", expanding=True))
    )

    return list(
        session.execute(
            stmt,
            {"job_ids": job_ids},
        ).scalars().all()
    )


def run_resume_grading_job(
    grading_run_id: int,
    config: dict,
) -> GradeResumeResponse:
    chat_config_id = config["chat_config_id"]
    resume_parse_id = config["resume_parse_id"]
    job_title = config["job_title"]
    seniority = config["seniority"]
    mapped_seniority = _seniority_mapper(seniority)
    next_start_index = config["next_start_index"]

    with SessionLocal() as session:
        resume_bullets = _fetch_resume_bullets(session, resume_parse_id)
        compared_job_ids = fetch_compared_job_posting_raw_ids(session, chat_config_id)

    processed_job_count = 0
    valid_matched_job_count = 0
    new_comparison_count = 0
    empty_valid_batches = 0
    stopped_reason = "min_job_reached. Enough jobs to compare. Can move to next phase"

    while new_comparison_count < AgentConfig.MIN_JOB.value:
        if _is_grading_cancel_requested(grading_run_id):
            stopped_reason = "cancel_requested"
            break

        _set_grading_phase(
            grading_run_id,
            ResumeGradingRunPhase.LINKEDIN_SCRAPING,
        )

        manager = RequestManager()
        manager.add(
            JobSearchRequest(
                keywords=job_title,
                start=next_start_index,
                experience=mapped_seniority,
            )
        )

        with SessionLocal() as session:
            ingest_res = manager.ingest_jobs(BronzeRepository(session))

        next_start_index += AgentConfig.LINKEDIN_START_INDEX_STEP.value

        if ingest_res.result != ScrapeResult.SUCCESSFUL:
            stopped_reason = f"linkedin_scrape_failed: {ingest_res.error}"
            break

        if _is_grading_cancel_requested(grading_run_id):
            stopped_reason = "cancel_requested"
            break

        scrape_run_ids = list(ingest_res.content["scrape_run_map"].keys())

        _set_grading_phase(
            grading_run_id,
            ResumeGradingRunPhase.JOB_NORMALIZATION,
        )

        with SessionLocal() as session:
            normalization_res = run_with_groq_key_rotation(
                phase="job normalization",
                call=lambda api_key: run_normalization_pipeline(
                    repo=NormalizationRepository(session),
                    scrape_run_ids=scrape_run_ids,
                    llm_normalizer=GroqLLMNormalizer(api_key=api_key),
                ),
            )

        if normalization_res.result != ScrapeResult.SUCCESSFUL:
            stopped_reason = f"normalization_processing_failed: {normalization_res.error}"
            break

        if _is_grading_cancel_requested(grading_run_id):
            stopped_reason = "cancel_requested"
            break

        llm_count = normalization_res.summary.resolved_by_method.get("llm", 0)
        if llm_count > 0:
            sleep(NormalizationConfig.LLM_INTERVAL.value)

        new_ready_ids = normalization_res.ready_job_posting_raw_ids
        existing_job_ids = ingest_res.content.get("existing_job_ids", [])

        with SessionLocal() as session:
            existing_ready_ids = _fetch_existing_ready_ids_by_job_ids(
                session=session,
                job_ids=existing_job_ids,
            )

        ready_ids = list(dict.fromkeys([*new_ready_ids, *existing_ready_ids]))
        processed_job_count += len(ready_ids)

        if _is_grading_cancel_requested(grading_run_id):
            stopped_reason = "cancel_requested"
            break

        _set_grading_phase(
            grading_run_id,
            ResumeGradingRunPhase.DBT_PROCESSING,
        )

        try:
            _run_dbt_for_ready_ids(ready_ids)
        except subprocess.CalledProcessError as exc:
            stopped_reason = f"dbt_processing_failed: dbt exited {exc.returncode}"
            break

        if _is_grading_cancel_requested(grading_run_id):
            stopped_reason = "cancel_requested"
            break

        _set_grading_phase(
            grading_run_id,
            ResumeGradingRunPhase.DESCRIPTION_CLEANING,
        )

        with SessionLocal() as session:
            clean_res = run_with_groq_key_rotation(
                phase="job description cleaning",
                call=lambda api_key: clean_descriptions_for_job_postings(
                    session,
                    ready_ids,
                    GroqLLMNormalizer(api_key=api_key),
                ),
            )

            if clean_res.result != ScrapeResult.SUCCESSFUL:
                stopped_reason = f"clean_description_processing_failed: {clean_res.error}"
                break

            if _is_grading_cancel_requested(grading_run_id):
                stopped_reason = "cancel_requested"
                break

            if clean_res.content:
                sleep(NormalizationConfig.LLM_INTERVAL.value)

            _set_grading_phase(
                grading_run_id,
                ResumeGradingRunPhase.JOB_SKILL_EXTRACTION,
            )

            skill_res = run_with_groq_key_rotation(
                phase="job skill extraction",
                call=lambda api_key: extract_skills_for_job_postings(
                    session,
                    ready_ids,
                    GroqLLMNormalizer(api_key=api_key),
                ),
            )

            if skill_res.result != ScrapeResult.SUCCESSFUL:
                stopped_reason = f"extract_processing_failed: {skill_res.error}"
                break

            if _is_grading_cancel_requested(grading_run_id):
                stopped_reason = "cancel_requested"
                break

            if skill_res.content:
                sleep(NormalizationConfig.LLM_INTERVAL.value)

            valid_job_ids = _fetch_valid_matched_jobs(
                session=session,
                ready_ids=ready_ids,
                job_title=job_title,
                seniority=seniority,
            )

        valid_matched_job_count += len(valid_job_ids)

        if not valid_job_ids:
            empty_valid_batches += 1

            _update_grading_progress(
                grading_run_id=grading_run_id,
                processed_job_count=processed_job_count,
                valid_matched_job_count=valid_matched_job_count,
                new_comparison_count=new_comparison_count,
                next_start_index=next_start_index,
            )

            if empty_valid_batches > AgentConfig.MAX_EMPTY_VALID_BATCHES.value:
                stopped_reason = "too_many_empty_valid_batches"
                break

            continue

        empty_valid_batches = 0

        _set_grading_phase(
            grading_run_id,
            ResumeGradingRunPhase.RESUME_SCORING,
        )

        for job_posting_raw_id in valid_job_ids:
            if _is_grading_cancel_requested(grading_run_id):
                stopped_reason = "cancel_requested"
                break

            if job_posting_raw_id in compared_job_ids:
                continue

            with SessionLocal() as session:
                score_res = _score_from_resume_parse_id(
                    session=session,
                    resume_parse_id=resume_parse_id,
                    resume_bullets=resume_bullets,
                    job_posting_raw_id=job_posting_raw_id,
                )

                if score_res.result != ScrapeResult.SUCCESSFUL or score_res.content is None:
                    stopped_reason = f"scoring_failed: {score_res.error}"
                    break

                inserted = insert_chat_job_comparison(
                    session=session,
                    chat_config_id=chat_config_id,
                    resume_job_semantic_score_id=score_res.content.resume_job_semantic_score_id,
                    resume_job_skill_score_id=score_res.content.resume_job_skill_score_id,
                )
                session.commit()

            compared_job_ids.add(job_posting_raw_id)

            if inserted:
                new_comparison_count += 1

            _update_grading_progress(
                grading_run_id=grading_run_id,
                processed_job_count=processed_job_count,
                valid_matched_job_count=valid_matched_job_count,
                new_comparison_count=new_comparison_count,
                next_start_index=next_start_index,
            )

            if new_comparison_count >= AgentConfig.MIN_JOB.value:
                break

        if stopped_reason.startswith("scoring_failed") or stopped_reason == "cancel_requested":
            break

    with SessionLocal() as session:
        update_config_next_start_index(session, chat_config_id, next_start_index)

        if stopped_reason == "cancel_requested":
            cancel_resume_grading_run(
                session=session,
                grading_run_id=grading_run_id,
            )
        elif (
            stopped_reason.startswith("linkedin_scrape_failed")
            or stopped_reason.startswith("normalization_processing_failed")
            or stopped_reason.startswith("dbt_processing_failed")
            or stopped_reason.startswith("clean_description_processing_failed")
            or stopped_reason.startswith("extract_processing_failed")
            or stopped_reason.startswith("scoring_failed")
        ):
            fail_resume_grading_run(
                session=session,
                grading_run_id=grading_run_id,
                error_message=stopped_reason,
            )
        else:
            finish_resume_grading_run(
                session=session,
                grading_run_id=grading_run_id,
                stopped_reason=stopped_reason,
            )

        session.commit()

    return GradeResumeResponse(
        stopped_reason=stopped_reason,
        processed_job_count=processed_job_count,
        valid_matched_job_count=valid_matched_job_count,
        new_comparison_count=new_comparison_count,
    )


async def start_resume_grading(chat_id: int) -> StartResumeGradingResponse:
    """
    Start a resume grading run in the background.

    Use this tool only after the resume grading chat has a parsed resume,
    target job title, and target seniority.

    This tool does not return final job matches. It creates or reuses a running
    grading run, starts background processing, and returns a grading_run_id
    immediately.

    The assistant should give the grading_run_id to the user and use
    get_resume_grading_status to check progress later.

    If a grading run is already running for the active chat config, this tool
    returns the existing grading_run_id instead of starting a duplicate run.
    """
    
    
    with SessionLocal() as session:
        config = get_active_chat_config(session, chat_id)

        if config is None:
            raise ValueError(
                f"No active resume grading config found for chat_id={chat_id}. "
                "Call initialize_resume_grading_chat first."
            )

        missing = get_missing_config_fields(config)
        if missing:
            raise ValueError(
                f"setup incomplete: missing {', '.join(missing)}"
            )

        running_run = get_running_resume_grading_run(
            session=session,
            chat_config_id=config["chat_config_id"],
        )

        if running_run is not None:
            return StartResumeGradingResponse(
                grading_run_id=running_run["grading_run_id"],
                status=running_run["status"],
                phase=running_run["phase"],
                message="Resume grading is already running. Use this id to check progress.",
            )

        grading_run_id = create_resume_grading_run(
            session=session,
            chat_id=chat_id,
        )
        session.commit()

    config = dict(config)
    _start_grading_thread(
        grading_run_id=grading_run_id,
        config=config,
    )

    return StartResumeGradingResponse(
        grading_run_id=grading_run_id,
        status=ResumeGradingRunStatus.RUNNING.value,
        phase=ResumeGradingRunPhase.LINKEDIN_SCRAPING.value,
        message="Resume grading started. Use this id to check progress.",
    )


async def get_resume_grading_status(
    chat_id: int,
) -> ResumeGradingStatusResponse:
    """
    Get the current status of the latest resume grading run for a chat.

    Use this tool after start_resume_grading has been called.

    This tool does not start new work. It finds the active chat config, reads
    the latest grading run for that config, and returns the current status,
    phase, progress counts, stopped reason, and error message.

    If the returned status is completed, call list_resume_grading_results with
    the same chat_id to show the user the ranked job matches.
    """
    with SessionLocal() as session:
        config = get_active_chat_config(session, chat_id)

        if config is None:
            raise ValueError(
                f"No active resume grading config found for chat_id={chat_id}. "
                "Call initialize_resume_grading_chat first."
            )

        run = get_latest_resume_grading_run_for_chat_config(
            session=session,
            chat_config_id=config["chat_config_id"],
        )

        if run is None:
            raise ValueError(
                f"No resume grading run found for chat_id={chat_id}. "
                "Call start_resume_grading first."
            )

    return ResumeGradingStatusResponse(
        status=run["status"],
        phase=run["phase"],
        processed_job_count=run["processed_job_count"],
        valid_matched_job_count=run["valid_matched_job_count"],
        new_comparison_count=run["new_comparison_count"],
        cancel_requested=run["cancel_requested"],
        next_start_index=run["next_start_index"],
        stopped_reason=run["stopped_reason"],
        error_message=run["error_message"],
    )


async def cancel_resume_grading(chat_id: int) -> CancelResumeGradingResponse:
    """
    Request graceful cancellation of the running resume grading run for a chat.

    Use this when the user says they want to stop, cancel, pause, or abandon
    the current resume grading process.

    This tool does not force-kill in-flight scraping, dbt, or LLM work. It marks
    the latest running grading run as cancel_requested. The background worker
    checks that flag between phases and stops at the next safe checkpoint.
    """
    with SessionLocal() as session:
        config = get_active_chat_config(session, chat_id)

        if config is None:
            raise ValueError(
                f"No active resume grading config found for chat_id={chat_id}. "
                "Call initialize_resume_grading_chat first."
            )

        running_run = get_running_resume_grading_run(
            session=session,
            chat_config_id=config["chat_config_id"],
        )

        if running_run is None:
            latest_run = get_latest_resume_grading_run_for_chat_config(
                session=session,
                chat_config_id=config["chat_config_id"],
            )

            if latest_run is None:
                raise ValueError(
                    f"No resume grading run found for chat_id={chat_id}. "
                    "Call start_resume_grading first."
                )

            return CancelResumeGradingResponse(
                status=latest_run["status"],
                phase=latest_run["phase"],
                cancel_requested=latest_run["cancel_requested"],
                message="No running resume grading run was found.",
            )

        request_resume_grading_cancel(
            session=session,
            grading_run_id=running_run["grading_run_id"],
        )
        session.commit()

    return CancelResumeGradingResponse(
        status=ResumeGradingRunStatus.RUNNING.value,
        phase=running_run["phase"],
        cancel_requested=True,
        message="Resume grading cancellation requested. It will stop at the next safe checkpoint.",
    )


def register(mcp: FastMCP) -> None:
    mcp.tool()(start_resume_grading)
    mcp.tool()(get_resume_grading_status)
    mcp.tool()(cancel_resume_grading)
