# 6-Week Execution Plan

This execution plan translates [design_document.md](design_document.md) into a practical 6-week build roadmap for the MVP.

The goal is to ship a working system that:

- scrapes LinkedIn job data
- stores data in a medallion-style warehouse
- parses uploaded resumes
- computes resume-to-market fit with deterministic scoring
- uses an AI agent to explain the results

## MVP Scope

To keep the project achievable in 6 weeks, the MVP should stay narrow:

- target one role family first, such as `data engineer`
- target one geography first, such as `United States`
- support one primary resume input path first
- return four main outputs:
  - top matching jobs
  - market alignment score
  - missing skills
  - improvement recommendations

## Week 1: Foundation and Database Layout

### Goal

Prepare the repository and database for the target architecture.

### Deliverables

- create database schemas: `bronze`, `silver`, `gold`, `app`, `ops`
- add raw bronze tables for job search runs, job cards, and job posts
- add `app.resume_upload`
- add `ops.pipeline_run`
- keep the current `jobs` table temporarily for compatibility

### Tasks

1. Update `infra/postgresql_init` to create the new schemas.
2. Add SQL init files for bronze, app, and ops tables.
3. Review existing SQLAlchemy models and plan which should remain as legacy compatibility models.
4. Decide and document the initial target role family and geography.
5. Confirm a local setup flow using the existing `docker-compose.yml`.

### Success Criteria

- Postgres starts with all required schemas and tables.
- Existing scraper code still runs without being broken.
- New schemas are visible in Adminer or SQL queries.

## Week 2: Bronze Ingestion

### Goal

Move ingestion from the single legacy `jobs` table into the bronze layer.

### Deliverables

- scraper writes search request metadata into `bronze.linkedin_job_search_run`
- scraper writes raw search-card data into `bronze.linkedin_job_card_raw`
- scraper writes raw job-post data into `bronze.linkedin_job_post_raw`
- basic scrape logging tied to run metadata

### Tasks

1. Refactor the repository layer to insert into bronze raw tables.
2. Preserve raw values instead of cleaning them during ingestion.
3. Store scrape timestamps and source URLs.
4. Add row counts and statuses to `ops.pipeline_run`.
5. Add or improve parser tests using files in `test/fixture`.

### Success Criteria

- One scrape produces bronze records across all raw tables.
- The system preserves historical observations instead of overwriting everything.
- You can inspect raw cards and raw job posts directly in SQL.

## Week 3: dbt Setup and Silver Models

### Goal

Build the first transformation layer from raw data to cleaned data.

### Deliverables

- initialize a `dbt` project for Postgres
- define sources for bronze and app schemas
- create silver models for cleaned jobs
- create silver models for extracted and normalized job skills
- add basic dbt tests

### Tasks

1. Create a `dbt/` project structure.
2. Add source YAML files for bronze job tables and app resume tables.
3. Build staging models:
   - `stg_linkedin_job_card_raw`
   - `stg_linkedin_job_post_raw`
4. Build intermediate and silver models:
   - `int_latest_job_posting`
   - `silver.job_posting`
   - `silver.job_skill`
5. Implement fuzzy-matching-based skill normalization.
6. Store:
   - raw skill text
   - `skill_normalized`
   - `confidence`
   - `match_method`
7. Add dbt tests for uniqueness, null checks, and relationships.

### Success Criteria

- `dbt run` succeeds locally.
- You have one latest-record job model in silver.
- Extracted job skills are queryable and reasonably normalized.

## Week 4: Resume Ingestion and Resume-to-Job Feature Set

### Goal

Add resume handling and create the structured comparison layer.

### Deliverables

- raw resume stored in `app.resume_upload`
- parsed resume profile in `silver.resume_profile`
- parsed resume skills in `silver.resume_skill`
- first resume-to-job feature set

### Tasks

1. Add a resume input path:
   - plain text first, PDF later if needed
2. Store raw resume content and metadata in `app.resume_upload`.
3. Build a resume parser that extracts:
   - skills
   - titles
   - years of experience estimate
   - target role if provided
   - target location if provided
4. Build silver resume models:
   - `silver.resume_profile`
   - `silver.resume_skill`
5. Build `int_resume_job_feature_set`.
6. Join resume skills with job skills and compute:
   - skill overlap
   - missing skills
   - title similarity
   - location fit

### Success Criteria

- A sample uploaded resume becomes structured silver data.
- You can compare one resume against many jobs in SQL.

## Week 5: Gold Models and Deterministic Scoring

### Goal

Produce the core product outputs from structured data.

### Deliverables

- gold dimensions and facts
- `gold.fct_resume_job_match`
- market demand marts
- final alignment score formula
- ranked top jobs per resume

### Tasks

1. Build dimension tables:
   - `dim_skill`
   - `dim_role`
   - `dim_location`
   - optionally `dim_company` and `dim_date`
2. Build fact tables:
   - `fct_job_posting`
   - `fct_job_skill`
   - `fct_resume_skill`
   - `fct_resume_job_match`
3. Build marts:
   - `mart_market_skill_demand`
   - `mart_role_demand`
   - `mart_resume_market_alignment`
4. Implement deterministic scoring using fields such as:
   - skill overlap
   - missing critical skills
   - title similarity
   - seniority fit
   - location fit
   - market demand score
5. Use window functions for:
   - latest record selection
   - top ranked jobs per resume
   - skill demand ranking by role/location

### Success Criteria

- The system can produce:
  - alignment score
  - top matching jobs
  - top missing skills
  - top role recommendations

## Week 6: Agent Layer, Demo Flow, and Project Polish

### Goal

Connect the structured data system to an AI agent and make the project demoable.

### Deliverables

- LangChain agent integrated with MCP-style tools
- tools for resume parsing, market summary, scoring, and recommendations
- repeatable demo flow
- polished documentation

### Tasks

1. Create a `career_agent` package or equivalent module.
2. Implement tools for:
   - `parse_resume`
   - `get_market_summary`
   - `score_resume_against_market`
   - `recommend_resume_improvements`
3. Make the agent call structured tools instead of inferring everything from raw text.
4. Ensure the final answer is based on stored scores and computed features.
5. Add a demo path:
   - CLI
   - simple API
   - or simple UI
6. Update `README.md` and keep `design_document.md` aligned with the implementation.

### Success Criteria

- A user can submit a resume and receive:
  - top jobs
  - alignment score
  - missing skills
  - recommendations
- The LLM explanation is grounded in structured results.

## Weekly Priority Order

If time becomes tight, protect work in this order:

1. bronze ingestion
2. silver models
3. resume parsing
4. deterministic scoring
5. gold marts
6. agent interface
7. extra polish

## Suggested End-of-Week Checkpoints

### End of Week 1

- schemas exist
- init SQL is stable
- local DB setup is repeatable

### End of Week 2

- scraper writes to bronze
- raw data is inspectable
- scrape run metadata exists

### End of Week 3

- dbt project runs
- silver jobs model exists
- normalized job skills exist

### End of Week 4

- resume upload path works
- parsed resume skills exist
- resume-to-job feature set exists

### End of Week 5

- final scores exist
- jobs can be ranked for a resume
- market demand marts exist

### End of Week 6

- end-to-end demo works
- agent explains structured results
- documentation is ready for portfolio use

## Final MVP Definition

At the end of 6 weeks, the MVP should be able to:

1. scrape recent jobs for one target market
2. store raw source data in bronze
3. transform jobs and resumes into silver
4. compute match and market outputs in gold
5. score a resume against current jobs
6. let an AI agent explain the result clearly

## Recommended Next Step After This Plan

After the MVP is stable, the next best improvements are:

- add orchestration scheduling
- improve fuzzy matching quality
- add more role families
- support richer resume parsing
- add dashboarding or a stronger UI
