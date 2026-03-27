from linkedin_tool.client import LinkedinClient
from linkedin_tool.parser import LinkedinParser
from linkedin_tool.schema import JobSearchRequest

class ScrapeService:
    def __init__(self, client:LinkedinClient, parser:LinkedinParser):
        self.client = client
        self.parser = parser

    def get_job(self, request:JobSearchRequest):
        job_search_html = self.client.fetch_job_search(request)
        jobs = self.parser.parse_job_search_page(job_search_html)
        for job in jobs:
            job_id = job["job_id"]
            job_post_html = self.client.fetch_job_post()
