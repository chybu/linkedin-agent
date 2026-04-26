from sqlalchemy.orm import Session
from sqlalchemy import bindparam, text

MAP_TABLE_BY_DOMAIN = {
    "title": "bronze.title_normalization_map",
    "location": "bronze.location_normalization_map",
    "seniority": "bronze.seniority_normalization_map",
}

staging_job_posting_table = 'silver.stg_job_postings_raw'
raw_job_posting_table = 'bronze.job_postings_raw'

class NormalizationRepository:
    def __init__(self, session: Session):
        self.session = session
        
    def fetch_candidate_raw_postings(self, scrape_run_ids: list[int]) -> list[dict]:
        """
        1. fetch raw job posting tables in bronze having given scrape run ids
        2. only return normalized job posting (not in silver)
        """
        
        if not scrape_run_ids:
            return []
        
        silver_exists = self._silver_job_postings_exists()
        
        if silver_exists:
            stmt = (
                text(
                    f"""
                    select
                        r.job_posting_raw_id,
                        r.title_raw,
                        r.location_raw,
                        r.seniority_level_raw
                    from {raw_job_posting_table} r
                    where r.scrape_run_id in :run_ids
                    and not exists (
                        select 1
                        from {staging_job_posting_table} s
                        where s.job_posting_raw_id = r.job_posting_raw_id
                    )
                    """
                ).bindparams(bindparam("run_ids", expanding=True))
            )
        
        else:
            stmt = (
                text(
                    f"""
                    select
                        r.job_posting_raw_id,
                        r.title_raw,
                        r.location_raw,
                        r.seniority_level_raw
                    from {raw_job_posting_table} r
                    where r.scrape_run_id in :run_ids
                    """
                ).bindparams(bindparam("run_ids", expanding=True))
            )
        
        rows = self.session.execute(stmt, {"run_ids": scrape_run_ids}).mappings().all()
        
        return [dict(row) for row in rows]
    
    def fetch_map_keys(self, domain: str) -> set[str]:
        table = MAP_TABLE_BY_DOMAIN[domain]
        rows = self.session.execute(text(f"select key_normalized from {table}")).scalars().all()
        return {r for r in rows if r}
    
    def fetch_map_values(self, domain: str) -> set[str]:
        table = MAP_TABLE_BY_DOMAIN[domain]
        rows = self.session.execute(text(f"select value_normalized from {table}")).scalars().all()
        return {r for r in rows if r}
    
    def upsert_map_rows(self, domain: str, rows: list[dict]) -> None:
        """
        update existing key or insert new key
        """
        
        if not rows:
            return

        table = MAP_TABLE_BY_DOMAIN[domain]
        stmt = text(
            f"""
            insert into {table} (
                key_normalized,
                value_normalized,
                method,
                ref_id,
                updated_at
            )
            values (
                :key_normalized,
                :value_normalized,
                :method,
                :ref_id,
                now()
            )
            on conflict (key_normalized) do update set
                value_normalized = excluded.value_normalized,
                method = excluded.method,
                ref_id = excluded.ref_id,
                updated_at = now()
            """
        )

        self.session.execute(stmt, rows)
        self.session.commit()
    
    def _silver_staging_job_postings_exists(self) -> bool:
        # to_regclass('schema.table'): This is a PostgreSQL function that looks up a table by name.
        # If the table exists, it returns the table's internal ID (OID).
        # If the table does not exist, it returns NULL (unlike other methods that might throw an error).
        
        exists = self.session.execute(
            text("SELECT to_regclass(:table_path) IS NOT NULL"),
            {"table_path": staging_job_posting_table}
        ).scalar_one()
        
        return exists