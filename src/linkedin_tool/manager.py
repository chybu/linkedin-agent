from linkedin_tool.service import ScrapeService
from linkedin_tool.schema import JobSearchRequest, ScrapeResult, ScrapeRuntime, Result
from linkedin_tool.setting import Setting
from linkedin_tool.db.repository import JobRepository
from linkedin_tool.log import print_message
from collections import deque
from time import sleep

class RequestManager:
    def __init__(self, request_queue: deque[JobSearchRequest] | None = None):
        self.request_queue =  request_queue if request_queue is not None else deque()
        self.service = ScrapeService()
        self.runtime = ScrapeRuntime()
        
    def add(self, request:JobSearchRequest):
        self.request_queue.append(request)

    def get_new_from_db(self, repo:JobRepository):

        job_searchs = []

        while self.request_queue:

            request = self.request_queue[0]

            job_search_res = self.service.get_job_search(request, self.runtime)
            if job_search_res.result == ScrapeResult.SUCCESSFUL:
                job_searchs.extend(job_search_res.content)
                self.request_queue.popleft()
            elif job_search_res.result == ScrapeResult.FAILED:
                # the job search can have invalid start index (>=1000) causing bad request => failed => skip this request
                self.request_queue.popleft()
            else:
                # hit block limit => converge early with content is successful job search before hitting the wall
                job_search_res.content = job_searchs # reuse the job search res
                return job_search_res
            
            if self.request_queue:
                sleep(self.service._get_jitter_time())
        
        print_message(ScrapeResult.SUCCESSFUL.value, f"finished job search with {len(job_searchs)} results")
        
        new_id_map = repo.get_new_job_id_map(self._get_job_ids(job_searchs))
        content = []
        for i, (is_new, job_search) in enumerate(zip(new_id_map, job_searchs)):
            if not is_new: continue
            
            job_post_res = self.service.get_job_post(job_search["job_id"], self.runtime)
            if job_post_res.result == ScrapeResult.SUCCESSFUL:
                job_detail = job_post_res.content
                content.append({
                    "job_id": job_search["job_id"],
                    "title": job_search["title"],
                    "company": job_search["company"],
                    "location": job_search["location"],
                    "posted": job_detail["posted"] if "posted" in job_detail else None,
                    "seniority_level": job_detail["criteria"]["Seniority level"] if "Seniority level" in job_detail["criteria"] else None,
                    "employment_type": job_detail["criteria"]["Employment type"] if "Employment type" in job_detail["criteria"] else None,
                    "job_function": job_detail["criteria"]["Job function"] if "Job function" in job_detail["criteria"] else None,
                    "industry": job_detail["criteria"]["Industries"] if "Industries" in job_detail["criteria"] else None,
                    "applicants": job_detail["applicants"] if "applicants" in job_detail else None,
                    "description": job_detail["sections"] if "sections" in job_detail else None,
                    "source_url": job_search["source_url"]
                })
            else:
                # get_job_post may return Failed or Retry Error. However, with the job id get from the job search earlier, the job id should be valid. So, when it fails to get the job post with a valid id, then it's because it hits a hard block or a network problem occured => getting later job id would likely fail => stop early
                job_post_res.content = content # reuse job post result
                return job_post_res
            
            if i<len(job_searchs)-1:
                sleep(self.service._get_jitter_time())
        
        print_message(ScrapeResult.SUCCESSFUL.value, f"finished job post with {len(content)} new jobs from {len(job_searchs)} job searchs")
              
        return Result(
            result=ScrapeResult.SUCCESSFUL,
            content=content
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
    
    @staticmethod
    def _get_job_ids(job_search_list: list[dict]):
        ids = []
        for job_search in job_search_list:
            ids.append(int(job_search["job_id"]))
        return ids