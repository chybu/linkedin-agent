from sqlalchemy import text
from sqlalchemy.orm import Session


def fetch_resume_grading_results(
    session: Session,
    chat_config_id: int,
    limit: int = 10,
) -> list[dict]:
    rows = session.execute(
        text(
            """
            select
                cc.chat_comparison_id,
                c.job_posting_raw_id,
                j.title,
                j.company,
                j.location,
                j.source_url,
                c.complete_score,
                c.semantic_score,
                c.skill_match_score
            from app.chat_job_comparisons cc
            inner join silver.fact_resume_job_complete_scores c
                on c.resume_job_semantic_score_id = cc.resume_job_semantic_score_id
               and c.resume_job_skill_score_id = cc.resume_job_skill_score_id
            inner join silver.fact_job_postings j
                on j.job_posting_raw_id = c.job_posting_raw_id
            where cc.chat_config_id = :chat_config_id
            order by cc.created_at desc, c.complete_score desc
            limit :limit
            """
        ),
        {
            "chat_config_id": chat_config_id,
            "limit": limit,
        },
    ).mappings().all()

    return [dict(row) for row in rows]


def fetch_chat_comparison_details(
    session: Session,
    chat_comparison_id: int,
) -> dict | None:
    row = session.execute(
        text(
            """
            select
                cc.chat_comparison_id,
                cc.chat_config_id,
                c.resume_job_semantic_score_id,
                c.resume_job_skill_score_id,
                c.job_posting_raw_id,
                j.title,
                j.company,
                j.location,
                j.source_url,
                c.complete_score,
                c.semantic_score,
                c.skill_match_score
            from app.chat_job_comparisons cc
            inner join silver.fact_resume_job_complete_scores c
                on c.resume_job_semantic_score_id = cc.resume_job_semantic_score_id
               and c.resume_job_skill_score_id = cc.resume_job_skill_score_id
            inner join silver.fact_job_postings j
                on j.job_posting_raw_id = c.job_posting_raw_id
            where cc.chat_comparison_id = :chat_comparison_id
            """
        ),
        {"chat_comparison_id": chat_comparison_id},
    ).mappings().one_or_none()

    return dict(row) if row is not None else None
