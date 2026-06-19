from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

from agent_server.helper.chat_memory import initialize_chat_config, get_missing_config_fields

from linkedin_tool.db.base import SessionLocal


class ChatInitResponse(BaseModel):
    chat_id: int = Field(
        description="Chat id for this resume grading workflow. Remember this chat id to call later tools. Give this to the user so they can continue later."
    )
    resume_ready: bool = Field(
        description="True when the active chat config already has a parsed resume. If false, ask the user for their resume PDF path and call set_target_resume."
    )
    job_title_ready: bool = Field(
        description="True when the active chat config already has a normalized target job title. If false, ask the user what job title they want to target and call set_target_job_title."
    )
    seniority_ready: bool = Field(
        description="True when the active chat config already has a target seniority. If false, ask the user to choose a seniority and call set_target_seniority."
    )
    missing_fields: list[str] = Field(
        description=(
            "User-facing setup fields still required before resume grading can start. "
            "If empty, all required setup fields are present."
        )
    )
    ready_to_grade: bool = Field(
        description=(
            "True when the active chat config has all required setup fields and the assistant "
            "can call grade_resume with the current chat_id. False means the assistant should "
            "ask the user for the fields listed in missing_fields first."
        )
    )


async def initialize_resume_grading_chat(
    chat_id: int | None = None,
) -> ChatInitResponse:
    """
    Initialize or resume a resume grading chat workflow.

    Use this tool only when the user wants to use the resume/job grading workflow,
    such as comparing their resume to jobs, uploading a resume for job matching,
    grading resume fit, or getting job recommendations.

    Before calling this tool:
    - Ask the user whether they already have a chat_id to continue.
    - If they provide a chat_id, pass it to this tool.
    - If they do not have one or want to start fresh, call this tool with chat_id=None.

    Do not call this tool for general conversation unrelated to resume/job grading.
    Do not create a new chat if the user says they want to continue an existing one
    but has not provided the chat_id yet; ask for the chat_id first.
    """
    with SessionLocal() as session:
        chat_id, config = initialize_chat_config(session=session, chat_id=chat_id)
        session.commit()
    
    resume_ready = config.get("resume_parse_id") is not None
    job_title_ready = bool(config.get("job_title"))
    seniority_ready = bool(config.get("seniority"))

    missing_fields = get_missing_config_fields(config)

    return ChatInitResponse(
        chat_id=chat_id,
        resume_ready=resume_ready,
        job_title_ready=job_title_ready,
        seniority_ready=seniority_ready,
        missing_fields=missing_fields,
        ready_to_grade=not missing_fields
    )


def register(mcp: FastMCP) -> None:
    mcp.tool()(initialize_resume_grading_chat)
