from linkedin_tool.db.base import SessionLocal
from linkedin_tool.log import print_message
from linkedin_tool.normalization.llm import GroqLLMNormalizer
from linkedin_tool.normalization.extract_skill import extract_skills_for_job_postings
from linkedin_tool.schema import ScrapeResult

job_posting_raw_ids = list(range(100))

with SessionLocal() as session:
    skill_res = extract_skills_for_job_postings(
        session=session,
        job_posting_raw_ids=job_posting_raw_ids,
        llm_normalizer=GroqLLMNormalizer(),
    )

if skill_res.result != ScrapeResult.SUCCESSFUL:
    print_message("error", skill_res.error or "skill extraction failed")
else:
    print_message("skill_rows_inserted", str(len(skill_res.content)))