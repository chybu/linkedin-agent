from linkedin_tool.manager import RequestManager
from linkedin_tool.schema import JobSearchRequest, GeoId, SortBy
from time import time

start, end = 0, 11
JOB_PER_START = 10

valid_ct = 0
consecutive_zero_ct = 0

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
            geo_id=GeoId.WEST_VIRGINIA,
            start=request_start,
            sort_by=SortBy.MOST_RECENT
        )
        
        batch.append(request)
    
    batches.append(batch)

for batch in batches:
    for request in batch:
        manager.add(request)
    
    jobs = manager.run()
    if len(jobs)==0:
        consecutive_zero_ct+=1
    else:
        consecutive_zero_ct = 0