from requests import Session
from Entity.filter_enumerator import TimePostedRange, WorkplaceType, ExperienceLevel, JobType, SortBy

class Fetcher:
    def __init__(self, session:Session | None = None):
        self.session = session or Session()
        
    def fetch_job_search(
            self,
            geo_id: str, 
            keywords: str, 
            start: int = 0, 
            time_range: TimePostedRange = None, 
            workplace: WorkplaceType = None, 
            experience: ExperienceLevel = None, 
            job_type: JobType = None, 
            sort_by: SortBy = None
        ):
        
        url = (
            "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
            f"?keywords=&geoId=106420769&f_TPR=&start={start}"
        )

        headers = {
            "accept": "*/*",
            "accept-language": "en-US,en;q=0.5",
            "user-agent": "Mozilla/5.0",
        }
        
        session = self.session
        
        response = session.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        return response.text
    
    def fetch_job_posting(self, jobId:str):
    
        url = (
            "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/"
            f"{jobId}"
        )
        
        headers = {
            "accept": "*/*",
            "accept-language": "en-US,en;q=0.5",
            "user-agent": "Mozilla/5.0",
        }
        
        session = self.session

        res = session.get(url, headers=headers, timeout=30)
        res.raise_for_status()
        return res.text
    
    
    
    