from sqlalchemy.orm import Session
from sqlalchemy import bindparam, text

MAP_TABLE_BY_DOMAIN = {
    "title": "bronze.title_normalization_map",
    "location": "bronze.location_normalization_map",
    "seniority": "bronze.seniority_normalization_map",
}

staging_ready_job_postings_table = 'bronze.staging_ready_job_postings'
raw_job_posting_table = 'bronze.job_postings_raw'

class NormalizationRepository:
    def __init__(self, session: Session):
        self.session = session
        
    def fetch_candidate_raw_postings(self, scrape_run_ids: list[int]) -> list[dict]:
        """
        1. fetch raw job posting tables in bronze having given scrape run ids
        2. only return normalized job posting that's not normalized
        """
        
        if not scrape_run_ids:
            return []
        
        staging_ready_exists = self._staging_ready_job_postings_exists()
        
        if staging_ready_exists:
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
                        from {staging_ready_job_postings_table} s
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
    
    def fetch_simple_map_key_to_value(self, domain: str) -> dict[str, str]:
        """
        For title/location:
            key_normalized -> value_normalized
        """
        
        table = MAP_TABLE_BY_DOMAIN[domain]
        rows = self.session.execute(
            text(f"select key_normalized, value_normalized from {table}")
        ).all()
        return {k: v for k, v in rows}

    def fetch_seniority_map_key_to_value(self) -> dict[tuple[bool, str], str]:
        """
        For seniority:
            (use_title_key, source_key) -> value_normalized
        """
        table = MAP_TABLE_BY_DOMAIN["seniority"]
        rows = self.session.execute(
            text(
                f"""
                select
                    use_title_key,
                    source_key,
                    value_normalized
                from {table}
                """
            )
        ).all()

        return {
            (bool(use_title_key), source_key): value
            for use_title_key, source_key, value in rows
        }

    def fetch_map_key_to_value(self, domain: str):
        if domain == "seniority":
            return self.fetch_seniority_map_key_to_value()
        else: 
            return self.fetch_simple_map_key_to_value(domain)
    
    def upsert_map_rows(self, domain: str, rows: list[dict]) -> None:
        """
        update existing key or insert new key to normalization table.
        insert content includes: key_normalized, value_normalized, method, ref_key
        """
        
        if not rows:
            return

        table = MAP_TABLE_BY_DOMAIN[domain]
        if domain == "seniority":
            stmt = text(
                f"""
                insert into {table} (
                    use_title_key,
                    source_key,
                    value_normalized,
                    method,
                    ref_key,
                    updated_at
                )
                values (
                    :use_title_key,
                    :source_key,
                    :value_normalized,
                    :method,
                    :ref_key,
                    now()
                )
                on conflict (use_title_key, source_key) do update set
                    value_normalized = excluded.value_normalized,
                    method = excluded.method,
                    ref_key = excluded.ref_key,
                    updated_at = now()
                """
            )
        else:
            stmt = text(
                f"""
                insert into {table} (
                    key_normalized,
                    value_normalized,
                    method,
                    ref_key,
                    updated_at
                )
                values (
                    :key_normalized,
                    :value_normalized,
                    :method,
                    :ref_key,
                    now()
                )
                on conflict (key_normalized) do update set
                    value_normalized = excluded.value_normalized,
                    method = excluded.method,
                    ref_key = excluded.ref_key,
                    updated_at = now()
                """
            )

        self.session.execute(stmt, rows)
        self.session.commit()
    
    def _staging_ready_job_postings_exists(self) -> bool:
        # to_regclass('schema.table'): This is a PostgreSQL function that looks up a table by name.
        # If the table exists, it returns the table's internal ID (OID).
        # If the table does not exist, it returns NULL (unlike other methods that might throw an error).
        
        exists = self.session.execute(
            text("SELECT to_regclass(:table_path) IS NOT NULL"),
            {"table_path": staging_ready_job_postings_table}
        ).scalar_one()
        
        return exists
