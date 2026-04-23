from sqlalchemy import BigInteger, ForeignKey, Integer, Text, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime

from linkedin_tool.db.base import Base

class ScrapeRunModel(Base):
    __tablename__ = "scrape_runs"
    __table_args__ = {"schema": "bronze"}

    scrape_run_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    keywords: Mapped[str | None] = mapped_column(Text, nullable=True)
    geo_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    start_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    time_range: Mapped[str | None] = mapped_column(Text, nullable=True)
    workplace_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    experience_level: Mapped[str | None] = mapped_column(Text, nullable=True)
    job_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    jobs_seen_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    jobs_inserted_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

class JobSearchCardRawModel(Base):
    __tablename__ = "job_search_cards_raw"
    __table_args__ = {"schema": "bronze"}

    search_card_raw_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    scrape_run_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("bronze.scrape_runs.scrape_run_id"),
        nullable=False,
    )
    job_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    title_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    company_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    location_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    scraped_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    
class JobPostingRawModel(Base):
    __tablename__ = "job_postings_raw"
    __table_args__ = {"schema": "bronze"}

    job_posting_raw_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    scrape_run_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("bronze.scrape_runs.scrape_run_id"),
        nullable=False,
    )
    job_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    title_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    company_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    location_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    posted_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    applicants_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    seniority_level_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    employment_type_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    job_function_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    industry_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    description_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    scraped_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )