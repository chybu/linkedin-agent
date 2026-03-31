from linkedin_tool.manager import RequestManager
from linkedin_tool.schema import JobSearchRequest, GeoId, SortBy
from linkedin_tool.db.base import SessionLocal
from linkedin_tool.db.repository import JobRepository
from linkedin_tool.log import print_message

start, end = 0, 50
JOB_PER_START = 10

valid_ct = 0

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
            geo_id=GeoId.CALIFORNIA,
            start=request_start,
            sort_by=SortBy.MOST_RECENT
        )
        
        batch.append(request)
    
    batches.append(batch)

total_new_job_ct = 0
with SessionLocal() as session:
    repo = JobRepository(session)
    
    for batch in batches:
        
        new_job_ct = 0
        
        for request in batch:
            manager.add(request)
        
        res = manager.run()
        jobs = res.content
        for job in jobs:
            if repo.insert_if_not_exists(job):
                new_job_ct+=1
                
        print_message("NEW JOB", f"Find {new_job_ct} new jobs")
        
        total_new_job_ct+=new_job_ct

print_message("TOTAL NEW JOB", f"Find {total_new_job_ct} new jobs")