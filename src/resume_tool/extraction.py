import hashlib
from pathlib import Path

from markitdown import MarkItDown
from sqlalchemy import text
from sqlalchemy.orm import Session

from linkedin_tool.schema import Result, ScrapeResult
from log import print_announcement, print_message
from resume_tool.llm import GroqResumeExtractor
from resume_tool.schema import ResumeEvidenceResult

RAW_RESUME_PARSES_TABLE = "bronze.raw_resume_parses"


def extract_resume_as_markdown(resume_file_path: str) -> str:
    md = MarkItDown()
    result = md.convert(resume_file_path)
    return result.text_content


def compute_resume_content_hash(cleaned_evidence: str) -> str:
    return hashlib.sha256(cleaned_evidence.encode("utf-8")).hexdigest()


def insert_resume_parse(
    session: Session,
    resume_file_name: str,
    resume_md: str,
    extracted_evidence: str,
    extracted_evidence_hash: str,
) -> int:
    stmt = text(
        f"""
        with inserted as (
            insert into {RAW_RESUME_PARSES_TABLE} (
                resume_file_name,
                resume_md,
                extracted_experience_project_bullets,
                extracted_evidence_hash
            )
            values (
                :resume_file_name,
                :resume_md,
                :extracted_experience_project_bullets,
                :extracted_evidence_hash
            )
            on conflict (extracted_evidence_hash) do nothing
            returning resume_parse_id
        )
        select resume_parse_id
        from inserted

        union all

        select resume_parse_id
        from {RAW_RESUME_PARSES_TABLE}
        where extracted_evidence_hash = :extracted_evidence_hash
          and not exists (select 1 from inserted)

        limit 1
        """
    )

    return session.execute(
        stmt,
        {
            "resume_file_name": resume_file_name,
            "resume_md": resume_md,
            "extracted_experience_project_bullets": extracted_evidence,
            "extracted_evidence_hash": extracted_evidence_hash,
        },
    ).scalar_one()


def extract_and_store_resume_evidence(
    session: Session,
    resume_file_path: str,
    resume_extractor: GroqResumeExtractor,
) -> Result[ResumeEvidenceResult]:
    resume_file_name = Path(resume_file_path).name
    print_announcement("resume extraction", f"resume={resume_file_name}")

    try:
        resume_md = extract_resume_as_markdown(resume_file_path)

        evidence_res = resume_extractor.extract_evidence(resume_md)

        if evidence_res.result != ScrapeResult.SUCCESSFUL:
            print_message("resume extraction", "failed")
            return Result(
                result=ScrapeResult.FAILED,
                content=None,
                error=evidence_res.error,
            )

        resume_bullets = [
            " ".join(item.strip().split())
            for item in (evidence_res.content or [])
            if item.strip()
        ]
        if not resume_bullets:
            print_message("resume extraction", "failed")
            return Result(
                result=ScrapeResult.FAILED,
                content=None,
                error="resume evidence extraction returned no parseable bullet points",
            )

        cleaned_resume_evidence = "\n".join(resume_bullets)
        resume_content_hash = compute_resume_content_hash(cleaned_resume_evidence)

        resume_parse_id = insert_resume_parse(
            session=session,
            resume_file_name=resume_file_name,
            resume_md=resume_md,
            extracted_evidence_hash=resume_content_hash,
            extracted_evidence=cleaned_resume_evidence,
        )

        print_message("resume extraction", "finish")
        return Result(
            result=ScrapeResult.SUCCESSFUL,
            content=ResumeEvidenceResult(
                resume_parse_id=resume_parse_id,
                resume_file_name=resume_file_name,
                resume_md=resume_md,
                resume_evidence=cleaned_resume_evidence,
                resume_bullets=resume_bullets,
            ),
        )

    except Exception as e:
        session.rollback()
        print_message("resume extraction", "failed")
        return Result(
            result=ScrapeResult.FAILED,
            content=None,
            error=str(e),
        )
