from linkedin_tool.manager import RequestManager
from linkedin_tool.schema import JobSearchRequest, GeoId, SortBy, ScrapeResult
from linkedin_tool.db.base import SessionLocal
from linkedin_tool.db.repository import JobRepository
from linkedin_tool.log import print_message

start, end = 0, 1000
JOB_PER_START = 10
max_no_new = 2

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
    repo = JobRepository(session)
    
    for batch in batches:
        
        new_job_ct = 0
        
        for request in batch:
            manager.add(request)
        
        res = manager.get_new_from_db(repo)
        
        if res.result!=ScrapeResult.SUCCESSFUL:
            print_message("Stop early", f"failed because {res.error}")
            break
        
        jobs = res.content
        for job in jobs:
            if repo.insert_if_not_exists(job):
                new_job_ct+=1
                
        print_message("NEW JOB", f"Find {new_job_ct} new jobs")
        if new_job_ct==0:
            no_new_ct+=1
        else:
            no_new_ct=0
        if no_new_ct==max_no_new:
            print_message("Stop Early")
            break
        
        total_new_job_ct+=new_job_ct

print_message("TOTAL NEW JOB", f"Find {total_new_job_ct} new jobs")