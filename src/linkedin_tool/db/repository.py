from sqlalchemy.orm import Session
from sqlalchemy import select
from datetime import datetime, UTC

from linkedin_tool.schema import JobSearchRequest, ScrapeResult
from linkedin_tool.db.model import ScrapeRunModel, JobSearchCardRawModel, JobPostingRawModel

class BronzeRepository:
    def __init__(self, session: Session):
        self.session = session

    def create_scrape_run(self, request: JobSearchRequest) -> ScrapeRunModel:
        now_utc = datetime.now(UTC)
        scrape_run = ScrapeRunModel(
            keywords=request.keywords or None,
            geo_id=request.geo_id.value if request.geo_id else None,
            start_index=request.start,
            time_range=request.time_range.value if request.time_range else None,
            workplace_type=request.workplace.value if request.workplace else None,
            experience_level=request.experience.value if request.experience else None,
            job_type=request.job_type.value if request.job_type else None,
            sort_by=request.sort_by.value if request.sort_by else None,
            status=ScrapeResult.RUNNING.value,
            started_at=now_utc,
        )
        self.session.add(scrape_run)
        self.session.commit()
        self.session.refresh(scrape_run)
        return scrape_run

    def insert_search_cards(self, scrape_run_id: int, cards: list[dict]) -> int:
        if not cards:
            return 0

        rows = []
        for card in cards:
            rows.append(
                JobSearchCardRawModel(
                    scrape_run_id=scrape_run_id,
                    job_id=int(card["job_id"]) if card.get("job_id") else None,
                    title_raw=card.get("title"),
                    company_raw=card.get("company"),
                    location_raw=card.get("location"),
                    source_url=card.get("source_url"),
                )
            )

        self.session.add_all(rows)
        self.session.commit()
        return len(rows)

    def insert_job_posting_raw(
        self,
        scrape_run_id: int,
        search_card: dict,
        job_detail: dict,
    ) -> int:
        
        criteria = job_detail.get("criteria", {}) or {}
        row = JobPostingRawModel(
            scrape_run_id=scrape_run_id,
            job_id=int(search_card["job_id"]),
            source_url=search_card.get("source_url"),
            title_raw=search_card.get("title"),
            company_raw=search_card.get("company"),
            location_raw=search_card.get("location"),
            posted_raw=job_detail.get("posted"),
            applicants_raw=job_detail.get("applicants"),
            seniority_level_raw=criteria.get("Seniority level"),
            employment_type_raw=criteria.get("Employment type"),
            job_function_raw=criteria.get("Job function"),
            industry_raw=criteria.get("Industries"),
            description_raw=job_detail.get("sections"),
        )

        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return row.job_posting_raw_id

    def finish_scrape_run(
        self,
        scrape_run: ScrapeRunModel,
        status: ScrapeResult,
        jobs_seen_count: int,
        jobs_inserted_count: int,
        error_message: str | None = None,
    ) -> None:
        if scrape_run is None:
            raise ValueError(f"scrape_run cannot be None")

        scrape_run.status = status.value
        scrape_run.jobs_seen_count = jobs_seen_count
        scrape_run.jobs_inserted_count = jobs_inserted_count
        scrape_run.error_message = error_message
        scrape_run.finished_at = datetime.now(UTC)

        self.session.commit()
        
    def get_existing_job_ids(self, job_ids: list[int]) -> set[int]:
        if not job_ids:
            return set()

        stmt = select(JobPostingRawModel.job_id).where(
            JobPostingRawModel.job_id.in_(job_ids)
        )
        return set(self.session.scalars(stmt).all())
