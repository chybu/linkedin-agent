from linkedin_tool.service import ScrapeService
from linkedin_tool.schema import JobSearchRequest, ScrapeResult, ScrapeRuntime
from linkedin_tool.setting import Setting
from collections import deque

class RequestManager:
    def __init__(self, request_queue: deque[JobSearchRequest] | None = None, service: ScrapeService | None = None):
        self.request_queue =  request_queue if request_queue is not None else deque()
        self.service = service if service is not None else ScrapeService()
        
    def add(self, request:JobSearchRequest):
        self.request_queue.append(request)
        
    def run(self):
        results = []
        runtime = ScrapeRuntime()
        while self.request_queue:
            
            request = self.request_queue[0]
            
            if request.start>=Setting.MAX_START_INDEX.value:
                self.request_queue.popleft()
                continue
                        
            jobs = self.service.get_job(request, runtime)
            
            if jobs["result"] == ScrapeResult.SUCCESSFUL:
                results.extend(jobs["content"])
                self.request_queue.popleft()
            else:
                break
            
        return results