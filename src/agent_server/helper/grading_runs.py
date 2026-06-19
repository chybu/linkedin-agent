from enum import StrEnum

from sqlalchemy import text
from sqlalchemy.orm import Session

from agent_server.helper.chat_memory import get_active_chat_config


class ResumeGradingRunStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ResumeGradingRunPhase(StrEnum):
    LINKEDIN_SCRAPING = "linkedin_scraping"
    JOB_NORMALIZATION = "job_normalization"
    DBT_PROCESSING = "dbt_processing"
    DESCRIPTION_CLEANING = "description_cleaning"
    JOB_SKILL_EXTRACTION = "job_skill_extraction"
    RESUME_SCORING = "resume_scoring"


def create_resume_grading_run(session: Session, chat_id: int) -> int:
    config = get_active_chat_config(session, chat_id)

    if config is None:
        raise ValueError(f"No active resume grading config found for chat_id={chat_id}")

    return session.execute(
        text(
            """
            insert into app.resume_grading_runs (
                chat_config_id,
                next_start_index
            )
            values (
                :chat_config_id,
                :next_start_index
            )
            returning grading_run_id
            """
        ),
        {
            "chat_config_id": config["chat_config_id"],
            "next_start_index": config["next_start_index"],
        },
    ).scalar_one()


def update_resume_grading_run_phase(
    session: Session,
    grading_run_id: int,
    phase: ResumeGradingRunPhase,
) -> None:
    session.execute(
        text(
            """
            update app.resume_grading_runs
            set
                phase = :phase,
                updated_at = now()
            where grading_run_id = :grading_run_id
            """
        ),
        {
            "grading_run_id": grading_run_id,
            "phase": phase.value,
        },
    )


def update_resume_grading_run_progress(
    session: Session,
    grading_run_id: int,
    processed_job_count: int,
    valid_matched_job_count: int,
    new_comparison_count: int,
    next_start_index: int,
) -> None:
    session.execute(
        text(
            """
            update app.resume_grading_runs
            set
                processed_job_count = :processed_job_count,
                valid_matched_job_count = :valid_matched_job_count,
                new_comparison_count = :new_comparison_count,
                next_start_index = :next_start_index,
                updated_at = now()
            where grading_run_id = :grading_run_id
            """
        ),
        {
            "grading_run_id": grading_run_id,
            "processed_job_count": processed_job_count,
            "valid_matched_job_count": valid_matched_job_count,
            "new_comparison_count": new_comparison_count,
            "next_start_index": next_start_index,
        },
    )


def finish_resume_grading_run(
    session: Session,
    grading_run_id: int,
    stopped_reason: str,
) -> None:
    session.execute(
        text(
            """
            update app.resume_grading_runs
            set
                status = :status,
                stopped_reason = :stopped_reason,
                finished_at = now(),
                updated_at = now()
            where grading_run_id = :grading_run_id
            """
        ),
        {
            "grading_run_id": grading_run_id,
            "status": ResumeGradingRunStatus.COMPLETED.value,
            "stopped_reason": stopped_reason,
        },
    )


def cancel_resume_grading_run(
    session: Session,
    grading_run_id: int,
) -> None:
    session.execute(
        text(
            """
            update app.resume_grading_runs
            set
                status = :status,
                stopped_reason = :stopped_reason,
                finished_at = now(),
                updated_at = now()
            where grading_run_id = :grading_run_id
            """
        ),
        {
            "grading_run_id": grading_run_id,
            "status": ResumeGradingRunStatus.CANCELLED.value,
            "stopped_reason": "cancel_requested",
        },
    )


def fail_resume_grading_run(
    session: Session,
    grading_run_id: int,
    error_message: str,
) -> None:
    session.execute(
        text(
            """
            update app.resume_grading_runs
            set
                status = :status,
                error_message = :error_message,
                finished_at = now(),
                updated_at = now()
            where grading_run_id = :grading_run_id
            """
        ),
        {
            "grading_run_id": grading_run_id,
            "status": ResumeGradingRunStatus.FAILED.value,
            "error_message": error_message,
        },
    )


def get_resume_grading_run(session: Session, grading_run_id: int) -> dict:
    row = session.execute(
        text(
            """
            select
                grading_run_id,
                chat_config_id,
                status,
                phase,
                processed_job_count,
                valid_matched_job_count,
                new_comparison_count,
                cancel_requested,
                next_start_index,
                stopped_reason,
                error_message,
                started_at,
                finished_at,
                created_at,
                updated_at
            from app.resume_grading_runs
            where grading_run_id = :grading_run_id
            """
        ),
        {"grading_run_id": grading_run_id},
    ).mappings().one_or_none()

    if row is None:
        raise ValueError(f"grading_run_id does not exist: {grading_run_id}")

    return dict(row)


def get_running_resume_grading_run(
    session: Session,
    chat_config_id: int,
) -> dict | None:
    row = session.execute(
        text(
            """
            select
                grading_run_id,
                chat_config_id,
                status,
                phase,
                processed_job_count,
                valid_matched_job_count,
                new_comparison_count,
                cancel_requested,
                next_start_index,
                stopped_reason,
                error_message,
                started_at,
                finished_at,
                created_at,
                updated_at
            from app.resume_grading_runs
            where chat_config_id = :chat_config_id
              and status = :status
            order by grading_run_id desc
            limit 1
            """
        ),
        {
            "chat_config_id": chat_config_id,
            "status": ResumeGradingRunStatus.RUNNING.value,
        },
    ).mappings().one_or_none()

    return dict(row) if row is not None else None


def get_latest_resume_grading_run_for_chat_config(
    session: Session,
    chat_config_id: int,
) -> dict | None:
    row = session.execute(
        text(
            """
            select
                grading_run_id,
                chat_config_id,
                status,
                phase,
                processed_job_count,
                valid_matched_job_count,
                new_comparison_count,
                cancel_requested,
                next_start_index,
                stopped_reason,
                error_message,
                started_at,
                finished_at,
                created_at,
                updated_at
            from app.resume_grading_runs
            where chat_config_id = :chat_config_id
            order by created_at desc, grading_run_id desc
            limit 1
            """
        ),
        {"chat_config_id": chat_config_id},
    ).mappings().one_or_none()

    return dict(row) if row is not None else None


def request_resume_grading_cancel(
    session: Session,
    grading_run_id: int,
) -> bool:
    result = session.execute(
        text(
            """
            update app.resume_grading_runs
            set
                cancel_requested = true,
                updated_at = now()
            where grading_run_id = :grading_run_id
              and status = :status
            """
        ),
        {
            "grading_run_id": grading_run_id,
            "status": ResumeGradingRunStatus.RUNNING.value,
        },
    )

    return result.rowcount > 0


def is_resume_grading_cancel_requested(
    session: Session,
    grading_run_id: int,
) -> bool:
    return bool(
        session.execute(
            text(
                """
                select cancel_requested
                from app.resume_grading_runs
                where grading_run_id = :grading_run_id
                """
            ),
            {"grading_run_id": grading_run_id},
        ).scalar_one_or_none()
    )
