from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field
from time import sleep

from config import NormalizationConfig
from linkedin_tool.schema import ScrapeResult
from linkedin_tool.db.base import SessionLocal
from linkedin_tool.normalization.llm import GroqLLMNormalizer
from linkedin_tool.normalization.fuzzy import resolve_with_fuzzy_simple
from linkedin_tool.normalization.keys import clean_key
from linkedin_tool.normalization.repository import NormalizationRepository

from agent_server.helper.chat_memory import update_config_job_title, get_missing_config_fields
from agent_server.helper.llm_rotation import run_with_groq_key_rotation

class JobTitleResponse(BaseModel):
    raw_job_title: str = Field(
        description="Raw job title provided by the user."
    )
    normalized_job_title: str = Field(
        description=(
            "Normalized SOC job title used for database search. "
            "Tell the user their raw title was set to this normalized value."
        )
    )
    resume_ready: bool = Field(
        description=(
            "True when the active chat config already has a parsed resume. "
            "If false, ask the user for their resume PDF path and call set_target_resume."
        )
    )
    seniority_ready: bool = Field(
        description=(
            "True when the active chat config already has a target seniority. "
            "If false, ask the user to choose a seniority and call set_target_seniority."
        )
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

async def set_target_job_title(
    chat_id: int,
    job_title: str,
) -> JobTitleResponse:
    """
    Set the user's desired job title.

    If job_title is missing, ask the user what job title they want to target.

    Do not call this tool until the user has provided a desired job title.
    """

    cleaned_job_title = clean_key(job_title)

    if not cleaned_job_title:
        raise ValueError("job title is required")

    with SessionLocal() as session:
        repo = NormalizationRepository(session)
        title_map = repo.fetch_map_key_to_value("title")
        normalized_job_title: str | None = None

        # Stage 1: map lookup
        if cleaned_job_title in title_map:
            normalized_job_title = title_map[cleaned_job_title]
        else:
            # Stage 2: fuzzy match
            fuzzy_resolved = resolve_with_fuzzy_simple(
                unresolved_keys={cleaned_job_title},
                known_key_to_value=title_map,
                threshold_value=NormalizationConfig.FUZZY_VAL_THRESH.value,
                threshold_key=NormalizationConfig.FUZZY_KEY_THRESH.value,
            )

            if cleaned_job_title in fuzzy_resolved:
                fuzzy_result = fuzzy_resolved[cleaned_job_title]
                normalized_job_title = fuzzy_result.normalized_val
                repo.upsert_map_rows(
                    "title",
                    [
                        {
                            "key_normalized": cleaned_job_title,
                            "value_normalized": normalized_job_title,
                            "method": "fuzzy",
                            "ref_key": fuzzy_result.ref_key,
                        }
                    ],
                )
            else:
                # Stage 3: LLM fallback
                result = run_with_groq_key_rotation(
                    phase="job title normalization",
                    call=lambda api_key: GroqLLMNormalizer(api_key=api_key).normalize_batch(
                        "title",
                        [cleaned_job_title],
                    ),
                )

                if result.result != ScrapeResult.SUCCESSFUL or not result.content:
                    raise ValueError(result.error or "job title normalization failed")

                normalized_job_title = result.content[0]

                if normalized_job_title == "unknown":
                    raise ValueError(f"could not normalize job title: {cleaned_job_title}")

                repo.upsert_map_rows(
                    "title",
                    [
                        {
                            "key_normalized": cleaned_job_title,
                            "value_normalized": normalized_job_title,
                            "method": "llm",
                            "ref_key": None,
                        }
                    ],
                )
                sleep(NormalizationConfig.LLM_INTERVAL.value)

        config = update_config_job_title(session, chat_id, normalized_job_title)
        missing_fields = get_missing_config_fields(config)
        resume_ready = config.get("resume_parse_id") is not None
        seniority_ready = bool(config.get("seniority"))
        session.commit()

    return JobTitleResponse(
        raw_job_title=job_title,
        normalized_job_title=normalized_job_title,
        resume_ready=resume_ready,
        seniority_ready=seniority_ready,
        missing_fields=missing_fields,
        ready_to_grade=not missing_fields
    )

def register(mcp: FastMCP) -> None:
    mcp.tool()(set_target_job_title)
