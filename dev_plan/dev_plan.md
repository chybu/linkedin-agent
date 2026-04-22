# LinkedIn Agent

```
github.com/chybu/linkedin-agent
```
This project is an AI job-market agent that combines a LinkedIn scraper, a
warehouse-style data pipeline, and an LLM-based interface. A user uploads a
resume, the system compares it against current job-market data, and the agent
returns top matching jobs, an alignment score, missing skills, and improvement
suggestions.

The core design idea is simple: the LLM is the interface, not the hidden scoring
engine. The system first turns resumes and job posts into structured data, com-
putes match signals with SQL and Python, and then uses the LLM to explain
the results in natural language. That makes the output more explainable, more
consistent, and easier to debug than a pure prompt-based matcher.

## System Design Pattern

The project follows a layered design:

- scraper layer: collects raw LinkedIn job data
- medallion data layer: organizes data intobronze,silver, andgold
- transformation layer: usesdbtto clean, model, and test data
- scoring layer: computes deterministic resume-to-job match features
- agent layer: usesMCPandLangChainto call tools and explain results

At a high level:

```
LinkedIn scraper -> bronze -> silver -> gold -> scoring engine -> AI agent
^
|
resume parsing
```
This pattern keeps responsibilities clear:

- ingestion is separate from analytics
- raw data is separate from cleaned data
- scoring is separate from explanation
- the LLM sits on top of trusted structured outputs

## What Is Stored in Bronze, Silver, and Gold

The medallion pattern is the backbone of the system.

```
Bronze
Bronze stores raw or near-raw source data.
Examples:
```
- raw LinkedIn job cards from search pages


- raw job posting details
- scrape run metadata
- raw uploaded resume text
Bronze is useful because it preserves the original source data before cleanup or
interpretation.

```
Silver
```
```
Silver stores cleaned, standardized, and partially structured data.
Examples:
```
- cleaned job postings
- parsed resume profiles
- extracted resume skills
- extracted job skills
- normalized fields like titles, locations, or skills
Silver is where messy text becomes usable for analysis and matching.

```
Gold
```
```
Gold stores analytics-ready and product-ready outputs.
Examples:
```
- skill demand by role or location
- role demand summaries
- resume-to-job match features
- ranked job matches
- final market alignment summaries
Gold is what the scoring engine, dashboards, and agent should use.

## Typical Workflow

The normal end-to-end flow looks like this:

```
1.A user uploads a resume.
2.The system stores the raw resume and parses skills, experience, titles, and
preferences.
3.The scraper collects recent LinkedIn jobs for a target role or market.
4.Raw job data lands inbronze.
5.dbttransforms the raw data into cleanedsilvermodels and analytics-
readygoldmodels.
6.The scoring engine compares the resume against relevant jobs using struc-
tured features such as skills, title similarity, seniority, and location.
7.The AI agent calls the scoring and market-analysis tools, then explains
the results in natural language.
```

The final output should answer questions like:

- Which jobs fit this resume best?
- How aligned is this resume with the current market?
- Which skills are missing most often?
- What should the candidate improve next?

## Why This Design

This architecture is designed to solve a few common problems in AI + data
products.

**1. Raw text is too messy for reliable matching**
Raw resumes and job descriptions are inconsistent, so the same skill, title, or
location can appear in many different forms. The data needs to be cleaned and
normalized before later steps like joining resume skills to job skills, grouping
similar roles, calculating demand trends, and computing reliable match scores.
**2. LLM-only matching is hard to trust**
If an LLM is asked to judge resume fit directly from raw text, the result can
be inconsistent and hard to explain. Deterministic scoring makes the result
auditable.
**3. Analytics and agent behavior should share the same data founda-
tion**

The same structured models should support:

- user-facing recommendations
- skill-gap analysis
- role-demand reporting
- future dashboards or APIs
**4. The project should be realistic and extensible**

```
Using Postgres,dbt, medallion schemas, and a tool-calling agent makes the
system look and behave like a real analytics engineering plus AI application,
not just a demo script.
```
## Main Components

- src/linkedin_tool/: current scraper, parser, retry logic, and database
    write path
- Postgres: local warehouse
- dbt: transformation, testing, and lineage layer
- resume parser: converts uploaded CVs into structured candidate data


- scoring engine: computes match scores from structured features
- MCP + LangChain agent: orchestrates tools and explains results

## Matching Philosophy

The system should not simply ask an LLM, “Does this resume match this job?”
Instead, it should:
1.extract structured fields from the resume and jobs
2.compare them using code and SQL
3.compute a score
4.let the LLM explain the score

That means the AI response is grounded in evidence such as:

- matched skills
- missing skills
- title overlap
- seniority fit
- location fit
- market demand signals

## MVP Scope

The first good version of this project should stay narrow:

- one role family, such asdata engineer
- one geography, such asUnited Statesor one city
- one warehouse, using local Postgres
- core outputs:
    **-** top matching jobs
    **-** market alignment score
    **-** missing skills
    **-** improvement recommendations

## Current Direction

The current repository already has a working scraper and Postgres setup. The
next major steps are:
1.add medallion schemas and raw bronze tables
2.adddbtmodels for silver and gold
3.add resume ingestion and parsing
4.implement deterministic scoring
5.add the MCP/LangChain agent layer


