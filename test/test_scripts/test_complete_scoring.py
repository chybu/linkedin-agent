import argparse

from config import NormalizationConfig
from linkedin_tool.db.base import SessionLocal
from linkedin_tool.schema import ScrapeResult
from resume_tool.complete_scoring import score_resume_complete_against_job
from resume_tool.llm import GroqResumeExtractor


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Test complete resume scoring against one job posting."
    )
    parser.add_argument(
        "resume_path",
        help="Path to the resume file to score.",
    )
    parser.add_argument(
        "job_posting_raw_id",
        type=int,
        help="bronze.raw_job_postings.job_posting_raw_id to score against.",
    )
    parser.add_argument(
        "--api-key-index",
        type=int,
        default=0,
        help="Index into configured Groq API keys. Defaults to 0.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    api_key = NormalizationConfig.GROQ_API_KEYS.value[args.api_key_index]
    resume_extractor = GroqResumeExtractor(api_key=api_key)

    with SessionLocal() as session:
        result = score_resume_complete_against_job(
            session=session,
            resume_file_path=args.resume_path,
            job_posting_raw_id=args.job_posting_raw_id,
            resume_extractor=resume_extractor,
        )

        if result.result != ScrapeResult.SUCCESSFUL:
            raise RuntimeError(result.error or "complete scoring failed")

        score = result.content
        if score is None:
            raise RuntimeError("complete scoring returned no content")

        print(f"resume_job_semantic_score_id={score.resume_job_semantic_score_id}")
        print(f"resume_job_skill_score_id={score.resume_job_skill_score_id}")
        print(f"resume_parse_id={score.resume_parse_id}")
        print(f"job_posting_raw_id={score.job_posting_raw_id}")
        print(f"semantic_score={score.semantic_score}")
        print(f"skill_match_score={score.skill_match_score}")
        print(f"complete_score={score.complete_score}")
        print(f"semantic_weight={score.semantic_weight}")
        print(f"skill_weight={score.skill_weight}")


if __name__ == "__main__":
    # python scripts/test_complete_scoring.py "/path/to/resume.pdf" 123
    main()
