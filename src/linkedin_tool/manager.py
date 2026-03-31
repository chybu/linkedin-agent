from linkedin_tool.service import ScrapeService
from linkedin_tool.schema import JobSearchRequest, ScrapeResult, ScrapeRuntime, Result
from linkedin_tool.setting import Setting
from collections import deque
from time import sleep
from sqlalchemy.orm import Session as DbSession

class RequestManager:
    def __init__(self, request_queue: deque[JobSearchRequest] | None = None):
        self.request_queue =  request_queue if request_queue is not None else deque()
        self.service = ScrapeService()
        self.runtime = ScrapeRuntime()
        
    def add(self, request:JobSearchRequest):
        self.request_queue.append(request)

    """
    get_new_job_for_db(list of request, db session)
    1. iterate through all request to get the job ids of each start index
    2. store all the id result of job search inside a set
    3. delete the object that already stored in the db
    4. get the job details of the new one (in batch, size 10 job postings)
    5. save the result and then continue until all job finish. if being blocked => converge
    """
    def run_new_from_db(self, db_session:DbSession):

        job_searchs = []

        while self.request_queue:

            request = self.request_queue[0]

            job_searchs.append(
                self.service.get_job_search(request, self.runtime)
            )
        
        
    def run(self):
        content = []
        while self.request_queue:
            
            request = self.request_queue[0]
            
            if request.start>=Setting.MAX_START_INDEX.value:
                self.request_queue.popleft()
                continue
                        
            scrape_res = self.service.get_job(request, self.runtime)
            
            if scrape_res.result == ScrapeResult.SUCCESSFUL:
                content.extend(scrape_res.content)
                self.request_queue.popleft()
            else:
                return Result(
                    result=scrape_res.result,
                    content=content,
                    error=scrape_res.error
                )
            
            # sleep between each job search
            if self.request_queue:
                sleep(self.service._get_jitter_time())
            
        return Result(
            result=ScrapeResult.SUCCESSFUL,
            content=content
        )