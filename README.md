# LinkedIn Job Agent

LinkedIn Job Agent is an evidence-based intelligence system for the hiring market.

The product idea is simple: most resume matching tools ask an LLM to read a resume and a job description, then return a polished opinion. That is easy to demo, but hard to trust, hard to audit, and hard to scale.

This project takes the opposite path. It treats job matching as a data problem first. It collects real job postings, preserves raw evidence, normalizes the market into structured tables, extracts resume evidence, computes repeatable scores, and stores every comparison. The LLM is not the judge. The LLM is a worker inside the pipeline, helping with extraction, cleanup, and normalization.

MCP is the communication layer. It lets a chat client or agent operate the system, but the value of the project is the underlying evidence engine: the warehouse, the scoring rules, the persisted comparisons, and the ability to explain every recommendation.

## Demo

See the evidence-based resume grading workflow in action:

[Watch demo video](demo.mp4)

## What This Project Does

- Builds a private job-market dataset from LinkedIn guest job search and posting pages.
- Stores the raw market evidence in Postgres before any interpretation happens.
- Normalizes titles, locations, seniority levels, companies, and skills into warehouse-ready entities.
- Uses dbt to move data through bronze, silver, and gold analytical layers.
- Extracts resume evidence and skills from candidate resumes.
- Scores resumes against real job postings using requirement coverage and skill coverage.
- Saves ranking results, matched requirements, missing requirements, matched skills, and missing skills.
- Exposes the whole workflow through MCP tools so an agent can drive the system conversationally.
- Tracks grading progress, cancellation requests, and comparison history.

## Why This Is Different

The market is full of thin AI wrappers that perform resume analysis by sending two blobs of text to a model. They can sound convincing, but they usually cannot answer the most important question: "What evidence produced this recommendation?"

LinkedIn Job Agent is built around evidence:

- Every job starts as a raw stored record.
- Every resume parse is stored as extracted evidence.
- Every normalized title, seniority level, location, and skill becomes reusable data.
- Every semantic requirement match is saved with the job requirement, resume evidence, and similarity score.
- Every skill match is saved with the job skill, resume skill, fuzzy score, and match result.
- Every final grade is reproducible from persisted intermediate scores.

That makes the system useful for more than one-off resume feedback. It can become a job-market intelligence layer, a resume targeting engine, a candidate-fit analyzer, or the foundation for a recruiting product that needs traceability instead of vibes.

## Grading Strategy

The grading strategy is designed to answer a more serious question than "does the LLM like this resume?" It asks: "Which job requirements are supported by evidence in the resume, and which required skills are actually present?"

### 1. Requirement Evidence Score

The system starts with a cleaned job description and splits it into individual requirements. It also extracts resume bullet evidence from the candidate resume.

Each job requirement is embedded and compared against the resume evidence using the configured Ollama embedding model. For every requirement, the system stores:

- the job requirement
- the best matching resume bullet, if a strong enough match exists
- the similarity score
- whether the requirement is considered satisfied

Credit is assigned by similarity threshold:

- `>= 0.70`: full credit
- `>= 0.60`: partial credit
- `>= 0.50`: weak credit
- below `0.50`: no credit

The semantic score is the total requirement credit divided by the number of job requirements, scaled to `0-100`. This rewards resumes that show concrete evidence for the work the job actually asks for.

### 2. Skill Match Score

The system separately extracts normalized skills from both the job posting and the resume. Each job skill is compared with the resume skills using token-normalized fuzzy matching.

A skill counts as matched only when it reaches the configured fuzzy threshold. The skill score is:

```text
matched job skills / total job skills * 100
```

This creates a second score focused on explicit skill coverage. It also produces an explainable list of matched and missing skills.

### 3. Complete Score

The final score combines the two signals:

```text
complete_score =
  semantic_score * semantic_weight
  + skill_match_score * skill_weight
```

The default weighting favors evidence over keyword overlap:

```text
semantic weight = 70%
skill weight    = 30%
```

That means a resume is rewarded more for proving it can satisfy the job responsibilities, while still getting credit for explicit skills.

### 4. Explainable Output

The final result is not just a rank or a percentage. The system can explain why a job matched by showing:

- matched job requirements
- missing job requirements
- matched skills
- missing skills
- per-requirement similarity scores
- per-skill fuzzy match scores

This is the core product thesis: the chat experience is convenient, but the durable asset is the evidence graph behind the recommendation.

## Medallion Data Model

The project uses a medallion-style data model with three schemas: `bronze`, `silver`, and `gold`. Each layer has a different job, so the system can separate raw evidence, cleaned entities, and investor-ready product views.

### Bronze: Raw and Operational Data

The `bronze` layer keeps data close to how it arrived from LinkedIn or the resume parser. It includes raw job search cards, raw job postings, scrape run metadata, resume parses, and process tracking tables.

This layer also stores control and mapping tables used by the normalization pipeline:

- `bronze.raw_job_search_cards` stores job cards from LinkedIn search results.
- `bronze.raw_job_postings` stores the full raw job posting details.
- `bronze.run_scrapes` tracks each scrape request and whether it succeeded.
- `bronze.raw_resume_parses` stores parsed resume text and extracted evidence.
- `bronze.map_normalized_job_titles`, `bronze.map_normalized_locations`, and `bronze.map_normalized_seniority_levels` store normalized values produced by fuzzy matching or LLM cleanup.
- `bronze.ctl_ready_job_postings` marks job postings that are ready to move into dbt processing.

In short, bronze is the source-of-truth layer. It preserves the original inputs and records how far each item has moved through the pipeline. This is where trust begins.

### Silver: Cleaned and Modeled Data

The `silver` layer turns raw data into reusable analytical tables. The main dbt staging model, `stg_job_postings`, joins raw postings with the normalization maps from bronze. From there, dbt builds dimensions and facts such as:

- `silver.dim_titles`
- `silver.dim_companies`
- `silver.dim_locations`
- `silver.fact_job_postings`

The resume scoring pipeline also writes silver tables for skills and match results:

- `silver.dim_skills`
- `silver.bridge_job_posting_skills`
- `silver.bridge_resume_parse_skills`
- `silver.fact_resume_job_semantic_scores`
- `silver.fact_resume_job_skill_scores`
- `silver.fact_resume_job_complete_scores`

This is the layer used for reliable joins, scoring, filtering, and downstream analysis. It turns scraped pages and parsed resumes into a structured matching substrate.

### Gold: Analysis-Ready Views

The `gold` layer is built for direct reporting and product-facing summaries. These models are views on top of silver tables, shaped around commercial questions the product needs to answer:

- Which companies are hiring the most?
- Which locations have the most demand?
- Which skills appear most often by role or industry?
- How well does a resume match a job?
- Which job requirements are satisfied or missing?

Examples include:

- `gold.company_hiring_demand`
- `gold.location_demand`
- `gold.top_skills`
- `gold.top_skills_by_industry`
- `gold.resume_match_summary`
- `gold.resume_requirement_matches`
- `gold.resume_missing_requirements`

The overall flow is:

```text
LinkedIn and resume inputs
        ↓
bronze: raw records, run history, normalization maps
        ↓
silver: cleaned dimensions, facts, skills, and resume/job scores
        ↓
gold: reporting views and resume match summaries
```

## Tech Stack

- **Python**: core application logic, scraping, parsing, scoring, and MCP tools.
- **MCP / FastMCP**: communication layer that exposes the evidence engine as chat/agent tools.
- **PostgreSQL**: application database and warehouse storage.
- **dbt**: bronze, silver, and gold data transformations.
- **Docker Compose**: local Postgres and Adminer services.
- **Groq**: LLM-assisted extraction, cleanup, and normalization inside the larger pipeline.
- **Ollama**: local embedding model for resume/job semantic scoring.
- **BeautifulSoup + requests**: LinkedIn HTML fetching and parsing.
- **Pydantic**: request and response schemas.

## Requirements

- Python 3.11 or newer
- Docker Desktop or Docker Engine
- Ollama
- A Groq API key

## Installation

### 1. Clone the repository

```bash
git clone <repo-url>
cd linkedin-agent
```

### 2. Create and activate a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install Python dependencies

```bash
python -m pip install --upgrade pip
python -m pip install -e .
```

### 4. Add your Groq API keys

Create a `.secrets.toml` file in the project root:

```toml
groq_api_keys = [
  "your-groq-api-key"
]
```

You can include more than one key. The resume grading pipeline can rotate through them if one key hits a rate limit.

### 5. Start the local services

The simplest way to start everything is with the included script:

```bash
bash test/test_scripts/startup.sh
```

It starts:

- Postgres on `localhost:5432`
- Adminer on `http://localhost:8080`
- Ollama on `http://localhost:11434`
- The Ollama embedding model configured in `ResumeConfig.EMBED_MODEL`

If you only need the database services, run:

```bash
docker compose up -d
```

### 6. Check the dbt connection

```bash
dbt debug --project-dir linkedin_dbt --profiles-dir linkedin_dbt/.dbt
```

Then run the dbt models:

```bash
dbt run --project-dir linkedin_dbt --profiles-dir linkedin_dbt/.dbt
```

## Running the MCP Server

Once the dependencies and local services are ready, start the MCP server:

```bash
python -m agent_server.server
```

The MCP server is defined in `src/agent_server/server.py`:

- host: `0.0.0.0`
- port: `8001`
- transport: `streamable-http`

Resume grading setup changes are handled by the config tool in `src/agent_server/tools/config.py`.

### MCP Resume Grading Flow

The MCP server is designed around a chat workflow. A `chat_id` identifies one user conversation, and each chat has one active resume grading config. The active config stores the three setup fields needed before grading can start:

- `resume_parse_id`: the parsed resume stored from a local PDF.
- `job_title`: the normalized target job title.
- `seniority`: the target seniority level.

Start by calling `initialize_resume_grading_chat`. If the user already has a `chat_id`, pass it in to continue the same workflow. If not, call it with `chat_id=None` to create a new chat. The response returns the `chat_id`, which fields are ready, which fields are missing, and whether the chat is ready to grade.

If setup is incomplete, fill the missing fields with these tools:

- `set_target_resume` parses and stores the user's resume PDF.
- `set_target_job_title` normalizes the target job title before saving it.
- `set_target_seniority` saves one of the supported seniority values: `intern`, `junior`, `mid`, `senior`, `lead`, `executive`, or `not_applicable`.

Once the response says `ready_to_grade=true`, call `start_resume_grading` with the same `chat_id`. This starts a background grading run and returns a `grading_run_id`. The run will scrape LinkedIn jobs, normalize new postings, run dbt models, extract skills, score the resume, and save job comparisons.

Use `get_resume_grading_status` with the `chat_id` to check progress. The status response includes the current phase, processed job count, matched job count, new comparison count, and any stop or error reason. If the user wants to stop the current run, call `cancel_resume_grading`; cancellation happens at the next safe checkpoint.

After results are available, use:

- `list_resume_grading_results` to show ranked job matches for the active config.
- `explain_resume_job_match` with a `chat_comparison_id` from the results list to show matched requirements, missing requirements, matched skills, and missing skills.

If the user wants to change their resume, target job title, or seniority after a config already exists, use `start_new_resume_grading_config`. This creates a new active config for the same `chat_id` and can copy fields from the previous config. For example, if the user wants to keep the same resume but target a different role, set `copy_resume=true`, `copy_job_title=false`, and `copy_seniority` depending on whether the seniority should stay the same.

The typical flow looks like this:

```text
initialize_resume_grading_chat
        ↓
set_target_resume / set_target_job_title / set_target_seniority
        ↓
start_resume_grading
        ↓
get_resume_grading_status
        ↓
list_resume_grading_results
        ↓
explain_resume_job_match
```

## Useful Commands

Run a sample LinkedIn scrape:

```bash
python test/test_scripts/scrape_new_job.py
```

Normalize successful scrape runs and process them with dbt:

```bash
python test/test_scripts/run_normalization_and_dbt.py
```

Stop local services:

```bash
bash test/test_scripts/shutdown.sh
```

## Database Access

Default local database connection:

- host: `localhost`
- port: `5432`
- database: `jobsdb`
- user: `user`
- password: `password`

Adminer runs at:

```text
http://localhost:8080
```

## Project Structure

```text
src/linkedin_tool/      LinkedIn scraping, parsing, persistence, and normalization
src/resume_tool/        Resume extraction, semantic scoring, skill scoring, and complete scoring
src/agent_server/       MCP server and resume-grading tools
linkedin_dbt/           dbt project for bronze, silver, and gold warehouse models
infra/postgresql_init/  Postgres initialization SQL
test/test_scripts/      Local scripts for startup, scraping, scoring, and pipeline runs
```

## Notes

- LinkedIn scraping can be rate-limited or blocked. Retry, delay, and session behavior are configured in `src/config.py`.
- The default database URL is defined in `Setting.DATABASE_URL`.
- The default embedding model is defined in `ResumeConfig.EMBED_MODEL`.
