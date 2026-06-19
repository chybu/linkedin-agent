import argparse

from config import NormalizationConfig
from linkedin_tool.db.base import SessionLocal
from linkedin_tool.schema import ScrapeResult
from resume_tool.llm import GroqResumeExtractor
from resume_tool.semantic_scoring import (
    fetch_resume_job_semantic_score_details,
    score_resume_semantic_against_job,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Test resume semantic scoring against one cleaned job description."
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
    parser.add_argument(
        "--show-matches",
        type=int,
        default=10,
        help="Number of requirement match rows to print. Defaults to 10.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    api_key = NormalizationConfig.GROQ_API_KEYS.value[args.api_key_index]
    resume_extractor = GroqResumeExtractor(api_key=api_key)

    with SessionLocal() as session:
        result = score_resume_semantic_against_job(
            session=session,
            resume_file_path=args.resume_path,
            job_posting_raw_id=args.job_posting_raw_id,
            resume_extractor=resume_extractor,
        )

        if result.result != ScrapeResult.SUCCESSFUL:
            raise RuntimeError(result.error or "semantic scoring failed")

        score = result.content
        if score is None:
            raise RuntimeError("semantic scoring returned no content")

        print(f"resume_job_semantic_score_id={score.resume_job_semantic_score_id}")
        print(f"resume_parse_id={score.resume_parse_id}")
        print(f"job_posting_raw_id={score.job_posting_raw_id}")
        print(f"semantic_score={score.semantic_score}")
        print(f"cleared_count={score.cleared_count}")
        print(f"total_requirement_count={score.total_requirement_count}")

        details = fetch_resume_job_semantic_score_details(
            session=session,
            resume_job_semantic_score_id=score.resume_job_semantic_score_id,
        )
        if details is None:
            return

        print("\nMatches:")
        for match in details["matches"][: args.show_matches]:
            print(f"- requirement_index={match['requirement_index']}")
            print(f"  satisfied={match['is_satisfied']}")
            print(f"  similarity_score={match['similarity_score']}")
            print(f"  jd_requirement={match['jd_requirement']}")
            print(f"  resume_bullet_point={match['resume_bullet_point']}")


if __name__ == "__main__":
    # python scripts/test_semantic_scoring.py "/path/to/resume.pdf" 123
    main()
