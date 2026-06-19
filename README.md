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

## MCP Resume Grading Flow

MCP is how an agent talks to the evidence engine. A `chat_id` identifies one user conversation, and each chat has one active resume grading config with three required setup fields:

- `resume_parse_id`: the parsed resume stored from a local PDF.
- `job_title`: the normalized target job title.
- `seniority`: the target seniority level.

The workflow is built for a guided chat experience:

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

Once the setup is complete, `start_resume_grading` launches a background run. That run scrapes LinkedIn jobs, normalizes new postings, runs dbt models, extracts skills, scores the resume, and saves the comparisons. The chat layer can then list ranked matches or explain a specific job through matched requirements, missing requirements, matched skills, and missing skills.

## Medallion Data Model

The warehouse uses a medallion model so the system can separate raw evidence from product-ready insight:

- **Bronze** preserves the original inputs: raw LinkedIn cards, raw job postings, scrape runs, resume parses, normalization maps, and readiness controls.
- **Silver** turns those inputs into reusable entities and facts: titles, companies, locations, job postings, skills, semantic scores, skill scores, and complete resume/job scores.
- **Gold** exposes the product-facing views: hiring demand, location demand, top skills, resume match summaries, matched requirements, and missing requirements.

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
