import argparse

from config import NormalizationConfig
from linkedin_tool.db.base import SessionLocal
from linkedin_tool.schema import ScrapeResult
from resume_tool.llm import GroqResumeExtractor
from resume_tool.skill_extraction import extract_skills_for_resume_parse
from resume_tool.skill_scoring import (
    fetch_resume_job_skill_score_details,
    score_resume_skills_against_job,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Test resume skill extraction and skill scoring against one job."
    )
    parser.add_argument(
        "resume_parse_id",
        type=int,
        help="bronze.raw_resume_parses.resume_parse_id to score.",
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
        default=20,
        help="Number of skill match rows to print. Defaults to 20.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    api_key = NormalizationConfig.GROQ_API_KEYS.value[args.api_key_index]
    resume_extractor = GroqResumeExtractor(api_key=api_key)

    with SessionLocal() as session:
        extract_res = extract_skills_for_resume_parse(
            session=session,
            resume_parse_id=args.resume_parse_id,
            resume_extractor=resume_extractor,
        )
        if extract_res.result != ScrapeResult.SUCCESSFUL:
            raise RuntimeError(extract_res.error or "resume skill extraction failed")

        score_res = score_resume_skills_against_job(
            session=session,
            resume_parse_id=args.resume_parse_id,
            job_posting_raw_id=args.job_posting_raw_id,
        )
        if score_res.result != ScrapeResult.SUCCESSFUL:
            raise RuntimeError(score_res.error or "skill scoring failed")

        score = score_res.content
        if score is None:
            raise RuntimeError("skill scoring returned no content")

        print(f"resume_job_skill_score_id={score.resume_job_skill_score_id}")
        print(f"resume_parse_id={score.resume_parse_id}")
        print(f"job_posting_raw_id={score.job_posting_raw_id}")
        print(f"skill_match_score={score.skill_match_score}")
        print(f"matched_skill_count={score.matched_skill_count}")
        print(f"total_job_skill_count={score.total_job_skill_count}")
        print(f"missing_skill_count={score.missing_skill_count}")

        details = fetch_resume_job_skill_score_details(
            session=session,
            resume_job_skill_score_id=score.resume_job_skill_score_id,
        )
        if details is None:
            return

        print("\nSkill matches:")
        for match in details["matches"][: args.show_matches]:
            print(f"- job_skill={match['job_skill_name']}")
            print(f"  matched={match['is_matched']}")
            print(f"  fuzzy_score={match['fuzzy_score']}")
            print(f"  resume_skill={match['matched_resume_skill_name']}")


if __name__ == "__main__":
    # python scripts/test_skill_scoring.py 1 123
    main()
