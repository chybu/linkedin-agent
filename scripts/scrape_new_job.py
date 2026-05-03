from linkedin_tool.manager import RequestManager
from linkedin_tool.schema import JobSearchRequest, GeoId, SortBy, ScrapeResult
from linkedin_tool.db.base import SessionLocal
from linkedin_tool.db.repository import BronzeRepository
from linkedin_tool.log import print_message, print_announcement

start, end = 0, 1000
max_no_new = 2

# DONT CHANGE
JOB_PER_START = 10

manager = RequestManager()
batches = []
batch_size = 10
step = JOB_PER_START*batch_size

for i in range(start, end, step):
    batch: list[JobSearchRequest] = []
    j = i + step
    for request_start in range(i, j, JOB_PER_START):
        
        if request_start>end: break
        
        request = JobSearchRequest(
            # keywords="data engineer intern",
            geo_id=GeoId.WEST_VIRGINIA,
            start=request_start,
            sort_by=SortBy.MOST_RECENT
        )
        
        batch.append(request)
    
    batches.append(batch)

total_new_job_ct = 0
no_new_ct = 0
with SessionLocal() as session:
    repo = BronzeRepository(session)
    
    for batch in batches:
        
        new_job_ct = 0
        
        for request in batch:
            manager.add(request)
        
        res = manager.ingest_jobs(repo)
        
        if res.result!=ScrapeResult.SUCCESSFUL:
            print_message("Stop early", f"failed because {res.error}")
            break
                        
        new_job_ct = res.content["new_job_ct"]
        if new_job_ct==0:
            no_new_ct+=1
        else:
            no_new_ct=0
        if no_new_ct==max_no_new:
            print_message("Stop Early", f"Cannot find any new jobs for {max_no_new} times")
            break
        
        total_new_job_ct+=new_job_ct

print_announcement("TOTAL NEW JOB", f"Find {total_new_job_ct} new jobs")