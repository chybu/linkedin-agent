from sqlalchemy import text
from sqlalchemy.orm import Session


REQUIRED_CONFIG_FIELDS = ("resume_parse_id", "job_title", "seniority")


def ensure_chat(session: Session, chat_id: int | None) -> int:
    """
    check the given chat_id is valid
    """
    if chat_id is not None:
        result = session.execute(
            text(
                """
                update app.chat_sessions
                set updated_at = now()
                where chat_id = :chat_id
                """
            ),
            {"chat_id": chat_id},
        )
        if result.rowcount == 0:
            raise ValueError(f"chat_id does not exist: {chat_id}")
        return chat_id

    return session.execute(
        text(
            """
            insert into app.chat_sessions default values
            returning chat_id
            """
        )
    ).scalar_one()


def get_active_chat_config(session: Session, chat_id: int) -> dict | None:
    row = session.execute(
        text(
            """
            select
                chat_config_id,
                chat_id,
                seniority,
                job_title,
                resume_parse_id,
                is_active,
                next_start_index
            from app.chat_search_configs
            where chat_id = :chat_id
              and is_active = true
            order by updated_at desc, chat_config_id desc
            limit 1
            """
        ),
        {"chat_id": chat_id},
    ).mappings().one_or_none()

    return dict(row) if row is not None else None


def create_draft_chat_config(session: Session, chat_id: int) -> dict:
    chat_config_id = session.execute(
        text(
            """
            insert into app.chat_search_configs (
                chat_id,
                is_active,
                next_start_index
            )
            values (
                :chat_id,
                true,
                0
            )
            returning chat_config_id
            """
        ),
        {"chat_id": chat_id},
    ).scalar_one()

    row = session.execute(
        text(
            """
            select
                chat_config_id,
                chat_id,
                seniority,
                job_title,
                resume_parse_id,
                is_active,
                next_start_index
            from app.chat_search_configs
            where chat_config_id = :chat_config_id
            """
        ),
        {"chat_config_id": chat_config_id},
    ).mappings().one()

    return dict(row)


def initialize_chat_config(session: Session, chat_id: int | None) -> tuple[int, dict]:
    chat_id = ensure_chat(session, chat_id)
    config = get_active_chat_config(session, chat_id)

    if config is None:
        config = create_draft_chat_config(session, chat_id)

    return chat_id, config


def get_missing_config_fields(config: dict) -> list[str]:
    return [field for field in REQUIRED_CONFIG_FIELDS if config.get(field) in (None, "")]


def update_config_job_title(
    session: Session,
    chat_id: int,
    normalized_job_title: str,
) -> dict:
    config = get_active_chat_config(session, chat_id)

    if config is None:
        raise ValueError(
            f"No active resume grading config found for chat_id={chat_id}. "
            "Call initialize_resume_grading_chat first."
        )
    
    missing_fields = get_missing_config_fields(config)

    if "job_title" not in missing_fields:
        raise ValueError(
            "The active chat config already has a job title."
        )

    row = session.execute(
        text(
            """
            update app.chat_search_configs
            set
                job_title = :job_title,
                updated_at = now()
            where chat_config_id = :chat_config_id
            returning
                seniority,
                job_title,
                resume_parse_id
            """
        ),
        {
            "chat_config_id": config["chat_config_id"],
            "job_title": normalized_job_title,
        },
    ).mappings().one()

    return dict(row)


def update_config_resume(
    session: Session,
    chat_id: int,
    resume_parse_id: int,
) -> dict:
    config = get_active_chat_config(session, chat_id)

    if config is None:
        raise ValueError(
            f"No active resume grading config found for chat_id={chat_id}. "
            "Call initialize_resume_grading_chat first."
        )
    
    missing_fields = get_missing_config_fields(config)

    if "resume_parse_id" not in missing_fields:
        raise ValueError(
            "The active chat config already has a resume"
        )

    row = session.execute(
        text(
            """
            update app.chat_search_configs
            set
                resume_parse_id = :resume_parse_id,
                updated_at = now()
            where chat_config_id = :chat_config_id
            returning
                seniority,
                job_title,
                resume_parse_id
            """
        ),
        {
            "chat_config_id": config["chat_config_id"],
            "resume_parse_id": resume_parse_id,
        },
    ).mappings().one()

    return dict(row)


def update_config_seniority(
    session: Session,
    chat_id: int,
    seniority: str,
) -> dict:
    config = get_active_chat_config(session, chat_id)

    if config is None:
        raise ValueError(
            f"No active resume grading config found for chat_id={chat_id}. "
            "Call initialize_resume_grading_chat first."
        )

    missing_fields = get_missing_config_fields(config)

    if "seniority" not in missing_fields:
        raise ValueError(
            "The active chat config already has a seniority."
        )

    row = session.execute(
        text(
            """
            update app.chat_search_configs
            set
                seniority = :seniority,
                updated_at = now()
            where chat_config_id = :chat_config_id
            returning
                seniority,
                job_title,
                resume_parse_id
            """
        ),
        {
            "chat_config_id": config["chat_config_id"],
            "seniority": seniority,
        },
    ).mappings().one()

    return dict(row)


def fetch_compared_job_posting_raw_ids(
    session: Session,
    chat_config_id: int,
) -> set[int]:
    rows = session.execute(
        text(
            """
            select c.job_posting_raw_id
            from app.chat_job_comparisons cc
            inner join silver.fact_resume_job_complete_scores c
                on c.resume_job_semantic_score_id = cc.resume_job_semantic_score_id
               and c.resume_job_skill_score_id = cc.resume_job_skill_score_id
            where cc.chat_config_id = :chat_config_id
            """
        ),
        {"chat_config_id": chat_config_id},
    ).scalars().all()

    return set(rows)


def insert_chat_job_comparison(
    session: Session,
    chat_config_id: int,
    resume_job_semantic_score_id: int,
    resume_job_skill_score_id: int,
) -> bool:
    row = session.execute(
        text(
            """
            insert into app.chat_job_comparisons (
                chat_config_id,
                resume_job_semantic_score_id,
                resume_job_skill_score_id
            )
            values (
                :chat_config_id,
                :resume_job_semantic_score_id,
                :resume_job_skill_score_id
            )
            on conflict (
                chat_config_id,
                resume_job_semantic_score_id,
                resume_job_skill_score_id
            )
            do nothing
            returning chat_comparison_id
            """
        ),
        {
            "chat_config_id": chat_config_id,
            "resume_job_semantic_score_id": resume_job_semantic_score_id,
            "resume_job_skill_score_id": resume_job_skill_score_id,
        },
    ).scalar_one_or_none()

    return row is not None


def update_config_next_start_index(
    session: Session,
    chat_config_id: int,
    next_start_index: int,
) -> None:
    session.execute(
        text(
            """
            update app.chat_search_configs
            set
                next_start_index = :next_start_index,
                updated_at = now()
            where chat_config_id = :chat_config_id
            """
        ),
        {
            "chat_config_id": chat_config_id,
            "next_start_index": next_start_index,
        },
    )


def create_replacement_chat_config(
    session: Session,
    chat_id: int,
    copy_resume: bool,
    copy_job_title: bool,
    copy_seniority: bool,
) -> dict:
    old_config = get_active_chat_config(session, chat_id)

    if old_config is None:
        raise ValueError(
            f"No active resume grading config found for chat_id={chat_id}. "
            "Call initialize_resume_grading_chat first."
        )

    session.execute(
        text(
            """
            update app.chat_search_configs
            set
                is_active = false,
                updated_at = now()
            where chat_config_id = :chat_config_id
            """
        ),
        {"chat_config_id": old_config["chat_config_id"]},
    )

    row = session.execute(
        text(
            """
            insert into app.chat_search_configs (
                chat_id,
                seniority,
                job_title,
                resume_parse_id,
                is_active,
                next_start_index
            )
            values (
                :chat_id,
                :seniority,
                :job_title,
                :resume_parse_id,
                true,
                0
            )
            returning
                chat_config_id,
                chat_id,
                seniority,
                job_title,
                resume_parse_id,
                is_active,
                next_start_index
            """
        ),
        {
            "chat_id": chat_id,
            "seniority": old_config["seniority"] if copy_seniority else None,
            "job_title": old_config["job_title"] if copy_job_title else None,
            "resume_parse_id": old_config["resume_parse_id"] if copy_resume else None,
        },
    ).mappings().one()

    return dict(row)