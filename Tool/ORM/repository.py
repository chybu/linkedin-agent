from sqlalchemy.orm import Session

from ORM.models import JobModel


def insert_job(session: Session, job_data: dict) -> JobModel:
    job = session.get(JobModel, job_data["job_id"])

    if job is None:
        job = JobModel(**job_data)
        session.add(job)
        session.commit()
        return 1
    else:
        return 0