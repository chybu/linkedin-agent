import urllib.parse as url_parser

from requests import Session
from linkedin_tool.schema import JobSearchRequest, GeoId

class LinkedinClient:
    def __init__(self, session:Session | None = None):
        self.session = session or Session()

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
            "accept": "*/*",
            "accept-language": "en-US,en;q=0.5",
            "user-agent": "Mozilla/5.0",
        }
        
        session = self.session
        
        response = session.get(search_url, headers=headers, timeout=30)
        response.raise_for_status()
        return response.text
    
    def fetch_job_post(self, jobId:str):
    
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