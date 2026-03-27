from Entity.fetcher import Fetcher
from Entity.parser import Parser

class Scraper:
    def __init__(self, fetcher:Fetcher | None = None, parser:Parser | None = None):
        self.fetcher = fetcher or Fetcher()
        self.parser = parser or Parser(self.fetcher)
        
    def scrape_jobs(self, start:int):
        job_search_html = self.fetcher.fetch_job_search(start)
        jobs = self.parser.parse_job_search_page(job_search_html)
        return jobs