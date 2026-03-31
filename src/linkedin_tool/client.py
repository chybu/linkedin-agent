import urllib.parse as url_parser
import time

from requests import Session
from linkedin_tool.schema import JobSearchRequest, GeoId
from linkedin_tool.setting import Setting

class LinkedinClient:
            
    def __init__(self):
        self.reset_session()
        
    def reset_session(self):
        new_session = Session()
        new_session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Connection": "keep-alive"
        })
        
        # Warm up by hitting the main page first to get fresh JSESSIONID and bcookie naturally
        new_session.get("https://www.linkedin.com", timeout=Setting.REQUEST_TIMEOUT.value)
        
        self.session = new_session

    @staticmethod
    def _get_job_search_url(request:JobSearchRequest) -> str:
        map = {}
        base_url = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"

        map["keywords"] = request.keywords

        if request.geo_id is None:
            map["geoId"] = GeoId.UNITED_STATE.value
        else:
            map["geoId"] = request.geo_id.value
        
        if request.time_range is not None:
            map["f_TPR"] = request.time_range.value

        if request.workplace is not None:
            map["f_WT"] = request.workplace.value

        if request.experience is not None:
            map["f_E"] = request.experience.value

        if request.job_type is not None:
            map["f_JT"] = request.job_type.value

        if request.sort_by is not None:
            map["sortBy"] = request.sort_by.value

        map["start"] = request.start
         
        query_string = url_parser.urlencode(map)

        return f"{base_url}?{query_string}"
     
    def fetch_job_search(self, request:JobSearchRequest):
        
        search_url = self._get_job_search_url(request)

        headers = {
            "authority": "www.linkedin.com",
            "accept-language": "en-US,en;q=0.9",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
            "referer": "https://www.linkedin.com",
            "sec-ch-ua": '"Chromium";v="146", "Not(A:Brand";v="24", "Google Chrome";v="146"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "x-restli-protocol-version": "2.0.0" # Critical: Tells the API you are a "real" frontend component
        }        
        session = self.session
        
        response = session.get(search_url, headers=headers, timeout=Setting.REQUEST_TIMEOUT.value)
        response.raise_for_status()
        return response.text
    
    def fetch_job_post(self, jobId:str):
    
        url = (
            "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/"
            f"{jobId}"
        )
        
        headers = {
            "authority": "www.linkedin.com",
            "accept-language": "en-US,en;q=0.9",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
            "referer": "https://www.linkedin.com",
            "sec-ch-ua": '"Chromium";v="146", "Not(A:Brand";v="24", "Google Chrome";v="146"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "document", 
            "sec-fetch-mode": "navigate",
            "sec-fetch-site": "same-origin",
            "upgrade-insecure-requests": "1"
        }
        
        session = self.session

        res = session.get(url, headers=headers, timeout=Setting.REQUEST_TIMEOUT.value)
        # filename = f"debug_429_{int(time.time())}.txt"
        # with open(filename, "w", encoding="utf-8") as f:
        #     f.write(f"--- STATUS CODE ---\n{res.status_code}\n\n")
        #     f.write("--- HEADERS ---\n")
        #     for k, v in res.headers.items():
        #         f.write(f"{k}: {v}\n")
        #     f.write("\n--- BODY ---\n")
        #     f.write(res.text)
            
        res.raise_for_status()
        return res.text