from linkedin_tool.normalization.repository import NormalizationRepository
from linkedin_tool.normalization.llm import GroqLLMNormalizer
from linkedin_tool.normalization.pipeline import run_normalization_pipeline
from linkedin_tool.db.base import SessionLocal

with SessionLocal() as session:
    repo = NormalizationRepository(session)
    llm_normalizer = GroqLLMNormalizer()
    scrape_ids = [10, 11, 12]
    res = run_normalization_pipeline(
        repo,
        scrape_ids,
        llm_normalizer
    )
    
    print(res)