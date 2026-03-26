from ORM.db import Base, engine, SessionLocal
from ORM.repository import insert_job

Base.metadata.create_all(bind=engine)

parsed_job = { 
    "job_id": 4377558186,
    "title": "BI & Analytics Developer",
    "company": "First Community Bank",
    "location": "Clarksburg, WV",
    "posted": "4 weeks ago",
    "seniority_level": "Not Applicable",
    "employment_type": "Full-time",
    "job_function": "Information Technology",
    "industry": "Banking",
    "applicants": "37 applicants",
    "description": "At First Community Bank, we are committed...",
    "source_url": "https://www.linkedin.com/jobs/view/bi-analytics-developer-at-first-community-bank-4377558186",
}

with SessionLocal() as session:
    job = insert_job(session, parsed_job)