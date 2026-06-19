from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

from linkedin_tool.db.base import SessionLocal
from agent_server.helper.chat_memory import (
    create_replacement_chat_config,
    get_missing_config_fields,
)


class ReplacementConfigResponse(BaseModel):
    missing_fields: list[str] = Field(
        description=(
            "Setup fields still required before resume grading can start. "
            "Ask the user for these fields next."
        )
    )
    ready_to_grade: bool = Field(
        description="True when the new active config has all required setup fields."
    )
    message: str = Field(
        description="Short user-facing message explaining what to do next."
    )


async def start_new_resume_grading_config(
    chat_id: int,
    copy_resume: bool,
    copy_job_title: bool,
    copy_seniority: bool,
) -> ReplacementConfigResponse:
    """
    Create a new active resume grading config for an existing chat.

    Use this when the user wants to change their resume, target job title, or
    seniority after a config already exists.

    Set copy_resume, copy_job_title, and copy_seniority to true only for fields
    the user wants to keep from the previous active config. Set them to false
    for fields the user wants to replace.

    After calling this tool, ask the user for any fields listed in missing_fields.
    """
    with SessionLocal() as session:
        config = create_replacement_chat_config(
            session=session,
            chat_id=chat_id,
            copy_resume=copy_resume,
            copy_job_title=copy_job_title,
            copy_seniority=copy_seniority,
        )
        missing_fields = get_missing_config_fields(config)
        session.commit()

    message = (
        "New resume grading config is ready. You can start resume grading."
        if not missing_fields
        else f"New resume grading config created. Ask the user for: {', '.join(missing_fields)}."
    )

    return ReplacementConfigResponse(
        missing_fields=missing_fields,
        ready_to_grade=not missing_fields,
        message=message,
    )


def register(mcp: FastMCP) -> None:
    mcp.tool()(start_new_resume_grading_config)