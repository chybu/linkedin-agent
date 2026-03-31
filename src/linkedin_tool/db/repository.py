from sqlalchemy.orm import Session
from linkedin_tool.db.model import JobModel

class JobRepository:
    def __init__(self, session: Session):
        self.session = session

    def insert_if_not_exists(self, job_data: dict) -> bool:
        job = self.session.get(JobModel, job_data["job_id"])

        if job is None:
            job = JobModel(**job_data)
            self.session.add(job)
            self.session.commit()
            return True

        return False