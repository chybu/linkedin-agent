from ORM.db import Base, engine, SessionLocal
from ORM.repository import insert_job
from Entity.fetcher import Fetcher
from Entity.parser import Parser
from Entity.scraper import Scraper
from Entity.manager import Manager
from requests import Session


fetcher  = Fetcher(Session())
parser = Parser(fetcher)
scraper = Scraper(fetcher=fetcher, parser=parser)
manager = Manager(scraper=scraper)

start, end = 2000, 3000
export_limit = 100
JOB_PER_START = 10
CONSECUTIVE_LIMIT = 3

Base.metadata.create_all(bind=engine)

valid_ct = 0
consecutive_zero_ct = 0

with SessionLocal() as session:
    for i in range(start, end, export_limit):
        j = i + (export_limit - JOB_PER_START)
        manager.generate_task(start=i, end=j)
        jobs = manager.run()
        for job in jobs:
            valid_ct+=insert_job(session, job)
        if len(jobs)==0:
            consecutive_zero_ct+=1
        if consecutive_zero_ct>=CONSECUTIVE_LIMIT:
            print(f"\nStop early at index {i} due to cannot find any jobs for multiple times\n")
            break
        
print(f"\nHave found {valid_ct} new job postings\n")