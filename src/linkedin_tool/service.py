from linkedin_tool.client import LinkedinClient
from linkedin_tool.parser import LinkedinParser
from linkedin_tool.schema import JobSearchRequest, ScrapeRuntime, ScrapeResult
from linkedin_tool.setting import Setting
from time import sleep
from random import uniform
from requests import HTTPError, RequestException
from linkedin_tool.log import print_message

class ScrapeService:
    def __init__(self, client:LinkedinClient | None = None, parser:LinkedinParser | None = None):
        self.client = client if client is not None else LinkedinClient()
        self.parser = parser if parser is not None else LinkedinParser()
        
    def get_job(self, request:JobSearchRequest, runtime:ScrapeRuntime):
        
        result_map = {
            "result": None,
            "content": [],
            "error": None
        }
        
        # get job search data
        for retry in range(Setting.MAX_RETRIES.value+1):
            self._reset_session(runtime)
            self._request_sleep(runtime, retry)
            
            job_search_map = self._get_job_search(request, runtime)
            
            # default sleep no matter what except when it is the last retry and still not succeed
            if not(
                job_search_map["result"] != ScrapeResult.SUCCESSFUL
                and retry == Setting.MAX_RETRIES.value
            ):
                sleep(self._get_jitter_time())

            if (
                job_search_map["result"] == ScrapeResult.SUCCESSFUL
                or job_search_map["result"] == ScrapeResult.FAILED
            ):
                break
        
        # early return when cannot get the job search page
        if job_search_map["result"] != ScrapeResult.SUCCESSFUL:
            result_map["result"] = job_search_map["result"]
            result_map["error"] = job_search_map["error"]
            return result_map
        
        # get job posting. Converge when after all retries, the request is still getting blocked => next job card will also be blocked => converge early when max retry is reached
        for job_card_i, job_card in enumerate(job_search_map["content"]):
            job_id = job_card["job_id"]
        
            for retry in range(Setting.MAX_RETRIES.value+1):
                self._reset_session(runtime)
                self._request_sleep(runtime, retry)
                
                job_post_map = self._get_job_post(job_id, runtime)
                
                # default sleep no matter what except when it is the last retry and still not succeed or when it is the last job in the job search and it succeeds
                if not(
                    (
                        job_post_map["result"] != ScrapeResult.SUCCESSFUL
                        and retry == Setting.MAX_RETRIES.value
                    )
                    or (
                        job_post_map["result"] == ScrapeResult.SUCCESSFUL
                        and job_card_i == len(job_search_map["content"])-1
                    )
                ):
                    sleep(self._get_jitter_time())
                
                if job_post_map["result"] == ScrapeResult.SUCCESSFUL:
                    break
                
            if job_post_map["result"] == ScrapeResult.SUCCESSFUL:
                job_detail = job_post_map["content"]
                result_map["content"].append({
                    "job_id": job_id,
                    "title": job_card["title"],
                    "company": job_card["company"],
                    "location": job_card["location"],
                    "posted": job_detail["posted"] if "posted" in job_detail else None,
                    "seniority_level": job_detail["criteria"]["Seniority level"] if "Seniority level" in job_detail["criteria"] else None,
                    "employment_type": job_detail["criteria"]["Employment type"] if "Employment type" in job_detail["criteria"] else None,
                    "job_function": job_detail["criteria"]["Job function"] if "Job function" in job_detail["criteria"] else None,
                    "industry": job_detail["criteria"]["Industries"] if "Industries" in job_detail["criteria"] else None,
                    "applicants": job_detail["applicants"] if "applicants" in job_detail else None,
                    "description": job_detail["sections"] if "sections" in job_detail else None,
                    "source_url": job_card["source_url"]
                })                
            else:
                result_map["error"] = job_post_map["error"]
                result_map["result"] = ScrapeResult.FAILED
                return result_map
                
        result_map["result"] = ScrapeResult.SUCCESSFUL
        return result_map
            
            
    def _get_job_search(self, request:JobSearchRequest, runtime:ScrapeRuntime):
        result_map = {
            "result": None,
            "content": None,
            "error": None
        }
        
        try:
            job_search_html = self.client.fetch_job_search(request)
            
            runtime.requests_since_sleep+=Setting.JOB_SEARCH_WEIGHT.value
            runtime.requests_since_session_reset+=Setting.JOB_SEARCH_WEIGHT.value
            
            result_map["content"] = self.parser.parse_job_search_page(job_search_html)
            result_map["result"] = ScrapeResult.SUCCESSFUL
            
            print_message(result_map["result"].value, f"job search at start index {request.start}")

        except HTTPError as e:
            result_map["error"] = str(e)
            status_code = e.response.status_code
            if status_code in (429, 403, 500, 502, 503, 504):
                result_map["result"] = ScrapeResult.RETRY
            else:
                result_map["result"] = ScrapeResult.FAILED
                
            print_message(result_map["result"].value, f"job search at start index {request.start} because {result_map['error']}")
            
        except RequestException as e:
            result_map["error"] = str(e)
            result_map["result"] = ScrapeResult.FAILED
            
            print_message(result_map["result"].value, f"job search at start index {request.start} because {result_map['error']}")
            
        return result_map
        
    
    def _get_job_post(self, job_id:str, runtime:ScrapeRuntime):
        result_map = {
            "result": None,
            "content": None,
            "error": None
        }
        
        try:
            job_post_html = self.client.fetch_job_post(job_id)
            runtime.requests_since_session_reset += Setting.JOB_POST_WEIGHT.value
            runtime.requests_since_sleep += Setting.JOB_POST_WEIGHT.value
            
            result_map["content"] = self.parser.parse_job_post_page(job_post_html)
            result_map["result"] = ScrapeResult.SUCCESSFUL
            
            print_message(result_map["result"].value, f"job post for job {result_map['content']['title']}")
            
        except HTTPError as e:
            result_map["error"] = str(e)
            result_map["result"] = ScrapeResult.RETRY
            
            print_message(result_map["result"].value, f"job post for job id {job_id} because {result_map['error']}")
            
        return result_map
    
        
    # reset session only after calling more than a number of requests no matter succeed or not. Always change session when blocked can make the server thinks "Aggressive Burn-and-Churn." 
    def _reset_session(self, runtime:ScrapeRuntime):
        # print("reset", runtime.requests_since_session_reset)
        if runtime.requests_since_session_reset >= Setting.JOB_SEARCH_SESSION_LIMIT.value:
            print_message("Reset Session")
            self.client.reset_session()
            runtime.requests_since_session_reset = 0
    
    # sleep only after calling more than a number of requests no matter succeed or not. Or sleep when the previous retry has blocked request
    def _request_sleep(self, runtime:ScrapeRuntime, retry:int):
        # print("sleep", runtime.requests_since_sleep)
        if (
            runtime.requests_since_sleep >= Setting.JOB_SEARCH_REQUEST_LIMIT.value 
            or retry>0
        ):
            sleep_time = self._get_sleep_time(retry)
            print_message("Request Sleep", f"sleep for {sleep_time} seconds")
            sleep(sleep_time)
            runtime.requests_since_sleep = 0
    
    
    @staticmethod
    def _get_sleep_time(retry:int = 0):
        extra_retry_time = Setting.FAIL_RETRY_PENALTY.value * retry
        base_time = uniform(Setting.MIN_JOB_SEARCH_SLEEP.value, Setting.MAX_JOB_SEARCH_SLEEP.value)
        total = base_time + extra_retry_time
        return total
    
    @staticmethod
    def _get_jitter_time(min_second:int=2, max_second:int=10):
        return uniform(min_second, max_second)