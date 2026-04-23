# from linkedin_tool.service import ScrapeService
# from linkedin_tool.schema import JobSearchRequest, ScrapeResult, ScrapeRuntime, Result
# from linkedin_tool.setting import Setting
# from linkedin_tool.db.repository import JobRepository
# from linkedin_tool.log import print_message
# from collections import deque
# from time import sleep

# class RequestManager:
#     def __init__(self, request_queue: deque[JobSearchRequest] | None = None):
#         self.request_queue =  request_queue if request_queue is not None else deque()
#         self.service = ScrapeService()
#         self.runtime = ScrapeRuntime()
        
#     def add(self, request:JobSearchRequest):
#         self.request_queue.append(request)

#     def get_new_from_db(self, repo:JobRepository):

#         job_searchs = []

#         while self.request_queue:

#             request = self.request_queue[0]

#             job_search_res = self.service.get_job_search(request, self.runtime)
#             if job_search_res.result == ScrapeResult.SUCCESSFUL:
#                 job_searchs.extend(job_search_res.content)
#                 self.request_queue.popleft()
#             elif job_search_res.result == ScrapeResult.FAILED:
#                 # the job search can have invalid start index (>=1000) causing bad request => failed => skip this request
#                 self.request_queue.popleft()
#             else:
#                 # hit block limit => converge early with content is successful job search before hitting the wall
#                 job_search_res.content = job_searchs # reuse the job search res
#                 return job_search_res
            
#             if self.request_queue:
#                 sleep(self.service._get_jitter_time())
        
#         print_message(ScrapeResult.SUCCESSFUL.value, f"finished job search with {len(job_searchs)} results")
        
#         new_id_map = repo.get_new_job_id_map(self._get_job_ids(job_searchs))
#         content = []
#         for i, (is_new, job_search) in enumerate(zip(new_id_map, job_searchs)):
#             if not is_new: continue
            
#             job_post_res = self.service.get_job_post(job_search["job_id"], self.runtime)
#             if job_post_res.result == ScrapeResult.SUCCESSFUL:
#                 job_detail = job_post_res.content
#                 content.append({
#                     "job_id": job_search["job_id"],
#                     "title": job_search["title"],
#                     "company": job_search["company"],
#                     "location": job_search["location"],
#                     "posted": job_detail["posted"] if "posted" in job_detail else None,
#                     "seniority_level": job_detail["criteria"]["Seniority level"] if "Seniority level" in job_detail["criteria"] else None,
#                     "employment_type": job_detail["criteria"]["Employment type"] if "Employment type" in job_detail["criteria"] else None,
#                     "job_function": job_detail["criteria"]["Job function"] if "Job function" in job_detail["criteria"] else None,
#                     "industry": job_detail["criteria"]["Industries"] if "Industries" in job_detail["criteria"] else None,
#                     "applicants": job_detail["applicants"] if "applicants" in job_detail else None,
#                     "description": job_detail["sections"] if "sections" in job_detail else None,
#                     "source_url": job_search["source_url"]
#                 })
#             else:
#                 job_post_res.content = content # reuse job post result
#                 return job_post_res
            
#             if i<len(job_searchs)-1:
#                 sleep(self.service._get_jitter_time())
        
#         print_message(ScrapeResult.SUCCESSFUL.value, f"finished job post with {len(content)} new jobs from {len(job_searchs)} job searchs")
              
#         return Result(
#             result=ScrapeResult.SUCCESSFUL,
#             content=content
#         )
                
#     def run(self):
#         content = []
#         while self.request_queue:
            
#             request = self.request_queue[0]
            
#             if request.start>=Setting.MAX_START_INDEX.value:
#                 self.request_queue.popleft()
#                 continue
                        
#             scrape_res = self.service.get_job(request, self.runtime)
            
#             if scrape_res.result == ScrapeResult.SUCCESSFUL:
#                 content.extend(scrape_res.content)
#                 self.request_queue.popleft()
#             else:
#                 return Result(
#                     result=scrape_res.result,
#                     content=content,
#                     error=scrape_res.error
#                 )
            
#             # sleep between each job search
#             if self.request_queue:
#                 sleep(self.service._get_jitter_time())
            
#         return Result(
#             result=ScrapeResult.SUCCESSFUL,
#             content=content
#         )
    
#     @staticmethod
#     def _get_job_ids(job_search_list: list[dict]):
#         ids = []
#         for job_search in job_search_list:
#             ids.append(int(job_search["job_id"]))
#         return ids
    
from collections import deque
from time import sleep

from linkedin_tool.db.repository import BronzeRepository
from linkedin_tool.db.model import ScrapeRunModel
from linkedin_tool.log import print_message
from linkedin_tool.schema import JobSearchRequest, ScrapeResult, ScrapeRuntime, Result
from linkedin_tool.service import ScrapeService
from linkedin_tool.setting import Setting

class RequestManager:
    def __init__(self, request_queue: deque[JobSearchRequest] | None = None):
        self.request_queue = request_queue if request_queue is not None else deque()
        self.service = ScrapeService()
        self.runtime = ScrapeRuntime()

    def add(self, request: JobSearchRequest):
        self.request_queue.append(request)

    def ingest_jobs(self, repo: BronzeRepository):
        """
        1. fetch all the job search
        2. extract the job ids
        3. filter out the job ids that are already exist
        4. fetch the new job posts
        """
        
        collected_cards: list[dict] = []
        scrape_run_map: dict[int, ScrapeRunModel] = {}
        job_ids: list[int] = []
        
        while self.request_queue:
            request = self.request_queue[0]
            
            if request.start >= Setting.MAX_START_INDEX.value:
                self.request_queue.popleft()
                continue
            
            scrape_run = repo.create_scrape_run(request)
            scrape_run_id = scrape_run.scrape_run_id
            
            scrape_run_map[scrape_run_id] = scrape_run
            
            job_search_res = self.service.get_job_search(request, self.runtime)

            if job_search_res.result == ScrapeResult.SUCCESSFUL:
                cards: list[dict] = job_search_res.content
                repo.insert_search_cards(scrape_run_id, cards)
                
                scrape_run.jobs_seen_count = len(cards)
                
                for card in cards:
                    job_id = card["job_id"]
                    
                    if not job_id: continue
                    
                    job_ids.append(int(job_id))
                    collected_cards.append(
                        {
                            "scrape_run_id": scrape_run_id,
                            "job_search": card,
                        }
                    )
                
                self.request_queue.popleft()
                
            elif job_search_res.result == ScrapeResult.FAILED:
                repo.finish_scrape_run(
                    scrape_run,
                    status=ScrapeResult.FAILED,
                    jobs_seen_count=0,
                    jobs_inserted_count=0,
                    error_message=job_search_res.error
                )
                self.request_queue.popleft()
                
            else:
                # hitting hard blocked. Set the all run to failed.
                for run in scrape_run_map.values():
                    
                    if run.status != ScrapeResult.RUNNING.value:continue
                    
                    repo.finish_scrape_run(
                        run,
                        status=ScrapeResult.FAILED,
                        jobs_seen_count= run.jobs_seen_count or 0,
                        jobs_inserted_count=0,
                        error_message=job_search_res.error
                    )
                return Result(
                    ScrapeResult.FAILED,
                    scrape_run_map,
                    job_search_res.error
                )
                    
            if self.request_queue:
                sleep(self.service._get_jitter_time())
                
        print_message(
            ScrapeResult.SUCCESSFUL.value,
            f"finished job search with {len(collected_cards)} results",
        )
        
        existing_job_ids = repo.get_existing_job_ids(job_ids)
        new_job_ct = 0
        
        # the api will return bad request instead of 0 job cards => catch with failed
        # so, there won't be cases where collected_card is empty with valid runs
        
        # finish run when move to new job card of another run
        prev_run: ScrapeRunModel = None
        for i, item in enumerate(collected_cards):
            scrape_run_id = item["scrape_run_id"]
            
            if prev_run and scrape_run_id!=prev_run.scrape_run_id:
                repo.finish_scrape_run(
                    prev_run,
                    ScrapeResult.SUCCESSFUL,
                    prev_run.jobs_seen_count,
                    jobs_inserted_count = prev_run.jobs_inserted_count or 0
                )
            
                scrape_run = scrape_run_map[scrape_run_id]
                prev_run = scrape_run
                
            elif prev_run and scrape_run_id==prev_run.scrape_run_id:
                scrape_run = prev_run
                
            else:
                scrape_run = scrape_run_map[scrape_run_id]
                prev_run = scrape_run
                
            job_search = item["job_search"]
            
            job_id = job_search["job_id"]
            if int(job_id) in existing_job_ids:
                
                if i == len(collected_cards) - 1:
                    repo.finish_scrape_run(
                        scrape_run,
                        ScrapeResult.SUCCESSFUL,
                        scrape_run.jobs_seen_count,
                        jobs_inserted_count=scrape_run.jobs_inserted_count or 0
                    )
                    
                continue
            
            job_post_res = self.service.get_job_post(job_id, self.runtime)
            
            if job_post_res.result == ScrapeResult.SUCCESSFUL:
                repo.insert_job_posting_raw(
                    scrape_run_id=scrape_run_id,
                    search_card=job_search,
                    job_detail=job_post_res.content,
                )
                scrape_run.jobs_inserted_count = scrape_run.jobs_inserted_count+1 if scrape_run.jobs_inserted_count else 1
                new_job_ct+=1
                
            # get_job_post may return Failed or Retry Error. 
            # However, with the job id get from the job search earlier, the job id should be valid. 
            # So, when it fails to get the job post with a valid id, then it's because it hits a hard block
            # or a network problem occured
            # => getting later job id would likely fail
            # => stop early
            else:
                # hitting hard blocked. Set the all unsuccessful runs to failed.
                for run in scrape_run_map.values():
                    if run.status!=ScrapeResult.RUNNING.value: continue
                    
                    repo.finish_scrape_run(
                        run,
                        status=ScrapeResult.FAILED,
                        jobs_seen_count= run.jobs_seen_count,
                        jobs_inserted_count=run.jobs_inserted_count or 0,
                        error_message=job_post_res.error
                    )
                    
                return Result(
                    ScrapeResult.FAILED,
                    scrape_run_map,
                    job_post_res.error
                )

            if i < len(collected_cards) - 1:
                sleep(self.service._get_jitter_time())
            else:
                # finish the last run
                repo.finish_scrape_run(
                    scrape_run,
                    ScrapeResult.SUCCESSFUL,
                    scrape_run.jobs_seen_count,
                    scrape_run.jobs_inserted_count
                )
                
        print_message(
            ScrapeResult.SUCCESSFUL.value,
            f"finished job post with {new_job_ct} new jobs from {len(collected_cards)} job searchs",
        )
        
        return Result(
            ScrapeResult.SUCCESSFUL,
            scrape_run_map
        )