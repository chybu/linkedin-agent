from dataclasses import dataclass, field
from Entity.scraper import Scraper
from queue import PriorityQueue
from time import time, sleep
from requests.exceptions import HTTPError, RequestException

@dataclass(order=True)
class Task:
    next_run_at: float
    start: int = field(compare=False)
    retries: int = field(default=0, compare=False)
    last_error: str = field(default="", compare=False)

class Manager:
    MAX_RETRIES = 3
    def __init__(self, scraper:Scraper | None = None):
        self.scraper = scraper or Scraper()
        self.queue = PriorityQueue()
        self.failed = []
        
    def scrape(self, start):
        
        error = None
        jobs = None
        
        try:
            jobs = self.scraper.scrape_jobs(start)
            status = "success"
        except HTTPError as e:
            error = str(e)
            status_code = e.response.status_code
            if status_code in (429, 403, 500, 502, 503, 504):
                status = "retry"
            else:
                status = "fail"
        except RequestException as e:
            error = str(e)
            status = "retry"
                
        return status, jobs, error
    
    @staticmethod
    def backoff(retries:int):
        return 5 ** retries
        
    def run(self):
        results = []
        
        while not self.queue.empty():
            task = self.queue.get()
            
            now = time()
            if task.next_run_at>now:
                print(f"Waiting--- at index {task.start} after ({task.retries}) retries for {task.next_run_at-now}s")
                sleep(task.next_run_at-now)
            
            status, jobs, error = self.scrape(task.start)
            
            if status=="success":
                print(f"Successful at index {task.start} after ({task.retries}) retries")
                results.extend(jobs)
                continue
            
            task.last_error = error
            if status=="retry" and task.retries<self.MAX_RETRIES:
                print(f"Retry----- at index {task.start} after ({task.retries}) retries because {error}")
                task.retries+=1
                task.next_run_at+=self.backoff(task.retries)
                self.queue.put(task)                    
            else:
                print(f"\nFailed---- at index {task.start} after ({task.retries}) retries because {error}\n")
                self.failed.append(task)
        
        return results
    
    def generate_task(self, start:int, end:int):
        for i in range(start, end+1, 10):
            task = Task(
                next_run_at=time(),
                start=i
            )
            self.queue.put(task)