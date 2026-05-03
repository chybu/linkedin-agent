from linkedin_tool.client import LinkedinClient
from linkedin_tool.parser import LinkedinParser
from linkedin_tool.schema import JobSearchRequest, ScrapeRuntime, ScrapeResult, Result
from linkedin_tool.setting import Setting
from time import sleep
from random import uniform
from requests import HTTPError, RequestException
from linkedin_tool.log import print_message

class ScrapeService:
    def __init__(self, client:LinkedinClient | None = None, parser:LinkedinParser | None = None):
        self.client = client if client is not None else LinkedinClient()
        self.parser = parser if parser is not None else LinkedinParser()

    def get_job_search(self, request:JobSearchRequest, runtime:ScrapeRuntime):
        for retry in range(Setting.MAX_RETRIES.value+1):
            self._reset_session(runtime)
            self._request_sleep(runtime, retry)

            job_search_res = self._get_job_search(request, runtime)

            if (
                job_search_res.result == ScrapeResult.SUCCESSFUL
                or job_search_res.result == ScrapeResult.FAILED
            ):
                break

        return job_search_res
    
    def get_job_post(self, job_id:str, runtime:ScrapeRuntime):
        for retry in range(Setting.MAX_RETRIES.value+1):
            self._reset_session(runtime)
            self._request_sleep(runtime, retry)
                
            job_post_res = self._get_job_post(job_id, runtime)
            
            if (
                job_post_res.result == ScrapeResult.SUCCESSFUL
                or job_post_res.result == ScrapeResult.FAILED
            ):
                break

        return job_post_res
                     
    def _get_job_search(self, request:JobSearchRequest, runtime:ScrapeRuntime):
        
        try:
            job_search_html = self.client.fetch_job_search(request)
            
            runtime.requests_since_sleep+=Setting.JOB_SEARCH_WEIGHT.value
            runtime.requests_since_session_reset+=Setting.JOB_SEARCH_WEIGHT.value

            res = Result(
                result=ScrapeResult.SUCCESSFUL,
                content= self.parser.parse_job_search_page(job_search_html)
            )
            
            print_message(res.result.value, f"job search at start index {request.start}")

        except HTTPError as e:
            status_code = e.response.status_code
            if status_code ==404:
                res = Result(ScrapeResult.FAILED)
            else:
                # in (429, 403, 500, 502, 503, 504)
                res = Result(ScrapeResult.RETRY)
            res.error = str(e)
                
            print_message(res.result.value, f"job search at start index {request.start} because {res.error}")
            
        except RequestException as e:
            res = Result(result=ScrapeResult.FAILED, error=str(e))               
            print_message(res.result.value, f"job search at start index {request.start} because {res.error}")
            
        return res
        
    def _get_job_post(self, job_id:str, runtime:ScrapeRuntime):
        
        try:
            job_post_html = self.client.fetch_job_post(job_id)
            runtime.requests_since_session_reset += Setting.JOB_POST_WEIGHT.value
            runtime.requests_since_sleep += Setting.JOB_POST_WEIGHT.value

            res = Result(
                result=ScrapeResult.SUCCESSFUL,
                content= self.parser.parse_job_post_page(job_post_html)
            )
            
            print_message(res.result.value, f"job post for job {res.content['title']}")

        except HTTPError as e:
            status_code = e.response.status_code
            if status_code == 404:
                res = Result(ScrapeResult.FAILED)
            else:
                # in (429, 403, 500, 502, 503, 504)
                res = Result(ScrapeResult.RETRY)
            res.error = str(e)
            print_message(res.result.value, f"job post for job id {job_id} because {res.error}")
            
        except RequestException as e:
            res = Result(result=ScrapeResult.FAILED, error=str(e))   
            print_message(res.result.value, f"job post for job id {job_id} because {res.error}")
            
        return res
       
    # reset session only after calling more than a number of requests no matter succeed or not. Always change session when blocked can make the server thinks "Aggressive Burn-and-Churn." 
    def _reset_session(self, runtime:ScrapeRuntime):
        # print("reset", runtime.requests_since_session_reset)
        if runtime.requests_since_session_reset >= Setting.SESSION_LIMIT.value:
            print_message("Reset Session")
            self.client.reset_session()
            runtime.requests_since_session_reset = 0
    
    # sleep only after calling more than a number of requests no matter succeed or not. Or sleep when the previous retry has blocked request
    def _request_sleep(self, runtime:ScrapeRuntime, retry:int):
        # print("sleep", runtime.requests_since_sleep)
        if (
            runtime.requests_since_sleep >= Setting.REQUEST_LIMIT.value 
            or retry>0
        ):
            sleep_time = self._get_sleep_time(retry)
            print_message("Request Sleep", f"sleep for {sleep_time} seconds")
            sleep(sleep_time)
            runtime.requests_since_sleep = 0
     
    @staticmethod
    def _get_sleep_time(retry:int = 0):
        extra_retry_time = Setting.FAIL_RETRY_PENALTY.value * retry
        base_time = uniform(Setting.MIN_LONG_SLEEP.value, Setting.MAX_LONG_SLEEP.value)
        total = base_time + extra_retry_time
        return total
    
    @staticmethod
    def _get_jitter_time(min_second:int=Setting.MIN_SHORT_SLEEP.value, max_second:int=Setting.MAX_SHORT_SLEEP.value):
        return uniform(min_second, max_second)