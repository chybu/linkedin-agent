from enum import StrEnum

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

from linkedin_tool.db.base import SessionLocal

from agent_server.helper.chat_memory import update_config_seniority, get_missing_config_fields


class Seniority(StrEnum):
    INTERN = "intern"
    JUNIOR = "junior"
    MID = "mid"
    SENIOR = "senior"
    LEAD = "lead"
    EXECUTIVE = "executive"
    NOT_APPLICABLE = "not_applicable"


class SeniorityResponse(BaseModel):
    seniority: Seniority = Field(
        description=(
            "Target seniority saved to the active chat config. "
            "Tell the user their target seniority was set to this value."
        )
    )
    resume_ready: bool = Field(
        description=(
            "True when the active chat config already has a parsed resume. "
            "If false, ask the user for their resume PDF path and call set_target_resume."
        )
    )
    job_title_ready: bool = Field(
        description=(
            "True when the active chat config already has a normalized target job title. "
            "If false, ask the user what job title they want to target and call set_target_job_title."
        )
    )
    missing_fields: list[str] = Field(
        description=(
            "User-facing setup fields still required before resume grading can start. "
            "If empty, all required setup fields are present."
        )
    )


async def set_target_seniority(
    chat_id: int,
    seniority: Seniority,
) -> SeniorityResponse:
    """
    Set the user's target job seniority.

    If seniority is missing, ask the user to choose exactly one option.

    Present the choices as:

    1. Intern
    2. Junior
    3. Mid-level
    4. Senior
    5. Lead
    6. Executive
    7. Not Applicable

    Tell the user they can reply with either the number or the name
    (e.g. "3" or "Mid-level").

    Once the user chooses, map the selection to the corresponding enum value:

    1 -> intern
    2 -> junior
    3 -> mid
    4 -> senior
    5 -> lead
    6 -> executive
    7 -> not_applicable

    Do not call this tool until the user has made a selection.
    """
    

    with SessionLocal() as session:
        config = update_config_seniority(
            session=session,
            chat_id=chat_id,
            seniority=seniority.value,
        )
        missing_fields = get_missing_config_fields(config)
        session.commit()

    return SeniorityResponse(
        seniority=seniority,
        resume_ready=config.get("resume_parse_id") is not None,
        job_title_ready=bool((config.get("job_title") or "").strip()),
        missing_fields=missing_fields,
        ready_to_grade=not missing_fields,
    )


def register(mcp: FastMCP) -> None:
    mcp.tool()(set_target_seniority)
