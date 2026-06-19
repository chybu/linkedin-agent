from pathlib import Path
from time import sleep

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

from config import NormalizationConfig
from linkedin_tool.db.base import SessionLocal
from linkedin_tool.schema import ScrapeResult
from resume_tool.extraction import extract_and_store_resume_evidence
from resume_tool.llm import GroqResumeExtractor

from agent_server.helper.chat_memory import update_config_resume, get_missing_config_fields
from agent_server.helper.llm_rotation import run_with_groq_key_rotation

class ResumeParseResponse(BaseModel):
    job_title_ready: bool = Field(
        description="True when the active chat config already has a normalized target job title. If false, ask the user what job title they want to target and call set_target_job_title."
    )
    seniority_ready: bool = Field(
        description="True when the active chat config already has a target seniority. If false, ask the user to choose a seniority and call set_target_seniority."
    )
    missing_fields: list[str] = Field(
        description="User-facing setup fields still required before resume grading can start. If empty, all required setup fields are present."
    )
    ready_to_grade: bool = Field(
        description="True when the active chat config has all required setup fields and the assistant can call grade_resume with the current chat_id."
    )


async def set_target_resume(
    chat_id: int,
    resume_file_path: str,
) -> ResumeParseResponse:
    """
    Set the user's resume PDF path, parse the resume, store it, and return the resume_parse_id.

    If resume_file_path is missing, ask the user to provide the local path to their resume PDF.

    The file must exist and must be a PDF.

    Do not call this tool until the user has provided a resume PDF path.
    """
    resume_path = Path(resume_file_path).expanduser()

    if not resume_path.exists():
        raise ValueError(f"resume file does not exist: {resume_path}")

    if not resume_path.is_file():
        raise ValueError(f"resume path is not a file: {resume_path}")

    if resume_path.suffix.lower() != ".pdf":
        raise ValueError(f"resume file must be a PDF: {resume_path}")

    with SessionLocal() as session:

        result = run_with_groq_key_rotation(
            phase="resume evidence extraction",
            call=lambda api_key: extract_and_store_resume_evidence(
                session=session,
                resume_file_path=str(resume_path),
                resume_extractor=GroqResumeExtractor(api_key=api_key),
            ),
        )

        if result.result != ScrapeResult.SUCCESSFUL or result.content is None:
            session.rollback()
            raise ValueError(result.error or "resume parsing failed")

        sleep(NormalizationConfig.LLM_INTERVAL.value)

        config = update_config_resume(
            session=session,
            chat_id=chat_id,
            resume_parse_id=result.content.resume_parse_id
        )

        missing_fields = get_missing_config_fields(config)

        session.commit()

    return ResumeParseResponse(
        job_title_ready=bool((config.get("job_title") or "").strip()),
        seniority_ready=bool((config.get("seniority") or "").strip()),
        missing_fields=missing_fields,
        ready_to_grade=not missing_fields,
    )


def register(mcp: FastMCP) -> None:
    mcp.tool()(set_target_resume)
