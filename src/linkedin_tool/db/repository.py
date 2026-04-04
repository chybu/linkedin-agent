from sqlalchemy.orm import Session
from sqlalchemy import select
from linkedin_tool.db.model import JobModel

class JobRepository:
    def __init__(self, session: Session):
        self.session = session

    def insert_if_not_exists(self, job_data: dict) -> bool:
        job = self.session.get(JobModel, int(job_data["job_id"]))

        if job is None:
            job = JobModel(**job_data)
            self.session.add(job)
            self.session.commit()
            return True

        return False
    
    def get_new_job_id_map(self, scraped_ids: list[int]):
        
        if not scraped_ids: return []
        
        stmt = select(JobModel.job_id).where(JobModel.job_id.in_(scraped_ids))
        existing_ids = set(self.session.scalars(stmt).all())
        
        new_id_map = []
        for id in scraped_ids:
            new_id_map.append(not(id in existing_ids))
        
        return new_id_map