from collections import deque
from time import sleep

from linkedin_tool.db.repository import BronzeRepository
from linkedin_tool.db.model import ScrapeRunModel
from linkedin_tool.log import print_message
from linkedin_tool.schema import JobSearchRequest, ScrapeResult, ScrapeRuntime, Result
from linkedin_tool.service import ScrapeService
from linkedin_tool.setting import Setting

class RequestManager:
    def __init__(self, request_queue: deque[JobSearchRequest] | None = None):
        self.request_queue = request_queue if request_queue is not None else deque()
        self.service = ScrapeService()
        self.runtime = ScrapeRuntime()

    def add(self, request: JobSearchRequest):
        self.request_queue.append(request)

    def _finish_run(
        self,
        repo: BronzeRepository,
        scrape_run: ScrapeRunModel,
        status: ScrapeResult,
        error_message: str | None = None,
    ) -> None:
        repo.finish_scrape_run(
            scrape_run=scrape_run,
            status=status,
            jobs_seen_count=scrape_run.jobs_seen_count or 0,
            jobs_inserted_count=scrape_run.jobs_inserted_count or 0,
            error_message=error_message,
        )

    def _fail_running_runs(
        self,
        repo: BronzeRepository,
        scrape_run_map: dict[int, ScrapeRunModel],
        error_message: str | None,
    ) -> None:
        for run in scrape_run_map.values():
            if run.status != ScrapeResult.RUNNING.value:
                continue
            self._finish_run(
                repo=repo,
                scrape_run=run,
                status=ScrapeResult.FAILED,
                error_message=error_message,
            )
            
    def _create_ingest_jobs_return_content(
        self,
        scrape_run_map: dict[int, ScrapeRunModel],
        new_job_ct: int
    ):
        return {
            "new_job_ct"  :new_job_ct,
            "scrape_run_map": scrape_run_map
        }
    

    def ingest_jobs(self, repo: BronzeRepository):
        """
        1. fetch all the job search
        2. extract the job ids
        3. filter out the job ids that are already exist
        4. fetch the new job posts
        """
        # cards of each job search
        collected_cards_by_run: dict[int, list[dict]] = {}
        # return result of this function
        scrape_run_map: dict[int, ScrapeRunModel] = {}
        # used to filter out existing jobs
        job_ids: list[int] = []
        
        while self.request_queue:
            request = self.request_queue[0]
            
            if request.start >= Setting.MAX_START_INDEX.value:
                self.request_queue.popleft()
                continue
            
            scrape_run = repo.create_scrape_run(request)
            scrape_run_id = scrape_run.scrape_run_id
            scrape_run_map[scrape_run_id] = scrape_run

            job_search_res = self.service.get_job_search(request, self.runtime)

            if job_search_res.result == ScrapeResult.SUCCESSFUL:
                cards: list[dict] = job_search_res.content
                repo.insert_search_cards(scrape_run_id, cards)
                scrape_run.jobs_seen_count = len(cards)
                collected_cards_by_run[scrape_run_id] = []

                for card in cards:
                    job_id = card["job_id"]

                    if not job_id:
                        continue

                    job_ids.append(int(job_id))
                    collected_cards_by_run[scrape_run_id].append(card)

                self.request_queue.popleft()

            elif job_search_res.result == ScrapeResult.FAILED:
                self._finish_run(
                    repo=repo,
                    scrape_run=scrape_run,
                    status=ScrapeResult.FAILED,
                    error_message=job_search_res.error
                )
                self.request_queue.popleft()

            else:
                # hitting hard blocked. Set all unfinished runs to failed.
                self._fail_running_runs(
                    repo=repo,
                    scrape_run_map=scrape_run_map,
                    error_message=job_search_res.error,
                )
                return Result(
                    ScrapeResult.FAILED,
                    self._create_ingest_jobs_return_content(scrape_run_map, new_job_ct=0),
                    job_search_res.error
                )
                    
            if self.request_queue:
                sleep(self.service._get_jitter_time())
                
        total_cards_count = sum(len(cards) for cards in collected_cards_by_run.values())
                
        print_message(
            ScrapeResult.SUCCESSFUL.value,
            f"finished job search with {total_cards_count} results",
        )

        existing_job_ids = repo.get_existing_job_ids(job_ids)
        new_job_ct = 0

        remaining_cards = total_cards_count

        for scrape_run_id in scrape_run_map.keys():
            scrape_run = scrape_run_map[scrape_run_id]
            cards = collected_cards_by_run.get(scrape_run_id, [])

            for job_search in cards:
                job_id = int(job_search["job_id"])

                if job_id not in existing_job_ids:
                    job_post_res = self.service.get_job_post(job_id, self.runtime)

                    if job_post_res.result == ScrapeResult.SUCCESSFUL:
                        repo.insert_job_posting_raw(
                            scrape_run_id=scrape_run_id,
                            search_card=job_search,
                            job_detail=job_post_res.content,
                        )
                        scrape_run.jobs_inserted_count = (
                            (scrape_run.jobs_inserted_count or 0) + 1
                        )
                        new_job_ct += 1
                    else:
                        # A valid job id from search failing here likely means a hard block
                        # or transient network issue, so stop early and fail unfinished runs.
                        self._fail_running_runs(
                            repo=repo,
                            scrape_run_map=scrape_run_map,
                            error_message=job_post_res.error,
                        )
                        return Result(
                            ScrapeResult.FAILED,
                            self._create_ingest_jobs_return_content(scrape_run_map, new_job_ct),
                            job_post_res.error
                        )

                remaining_cards -= 1
                if remaining_cards > 0:
                    sleep(self.service._get_jitter_time())

            self._finish_run(
                repo=repo,
                scrape_run=scrape_run,
                status=ScrapeResult.SUCCESSFUL,
            )
                
        print_message(
            ScrapeResult.SUCCESSFUL.value,
            f"finished job post with {new_job_ct} new jobs from {sum(len(cards) for cards in collected_cards_by_run.values())} job searchs",
        )
        
        return Result(
            ScrapeResult.SUCCESSFUL,
            self._create_ingest_jobs_return_content(scrape_run_map, new_job_ct)
        )