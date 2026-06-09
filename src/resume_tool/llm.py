import json
from time import sleep
from typing import TypeVar

from groq import RateLimitError
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_groq import ChatGroq
from pydantic import BaseModel, Field

from linkedin_tool.schema import Result, ScrapeResult
from config import NormalizationConfig, Setting

StructuredOutput = TypeVar("StructuredOutput", bound=BaseModel)


class ResumeEvidenceValues(BaseModel):
    items: list[str] = Field(description="Extracted resume evidence items.")


class ResumeSkillValues(BaseModel):
    skills: list[str] = Field(description="Extracted normalized resume skills.")


_RESUME_EVIDENCE_PROMPT = """
## Role

You are a resume evidence extraction assistant.

## Task

Extract only evidence from work experience and project sections.

Relevant sections may include:

- Experience
- Work Experience
- Professional Experience
- Employment
- Projects
- Project Experience
- Selected Projects
- Similar experience-related sections
- Similar project-related sections

---

## Extraction Rules

1. Extract only original resume content describing:
   - responsibilities
   - actions performed
   - technologies used
   - tools used
   - deliverables
   - project work
   - achievements
   - outcomes
   - measurable results

2. Exclude:
   - education
   - skills sections
   - certifications
   - awards
   - honors
   - summary
   - objective
   - profile
   - contact information
   - languages
   - interests
   - references
   - publications
   - volunteer activities unless they contain project-like work evidence

3. Preserve original wording whenever possible.

4. Do not:
   - rewrite
   - summarize
   - paraphrase
   - normalize
   - infer
   - combine multiple bullets

5. If a bullet contains multiple sentences:
   - split only when each sentence remains understandable on its own
   - otherwise preserve the original bullet

6. Do not deduplicate.

7. Preserve evidence order as it appears in the resume whenever possible.

---

## Evidence Definition

Valid evidence includes statements describing:

- work performed
- projects completed
- responsibilities owned
- systems built
- analyses performed
- research conducted
- products developed
- processes improved
- stakeholders managed
- measurable outcomes
- technologies applied

Examples:

Valid:
- Developed REST APIs using FastAPI.
- Led a team of 5 analysts.
- Built dashboards in Tableau.
- Increased conversion rate by 12%.

Invalid:
- Bachelor of Science in Computer Science.
- Skills: Python, SQL, AWS.
- Certified Scrum Master.
- GPA: 3.9/4.0.

---

## Structured Output Rules

Return a JSON object matching the provided schema.

Requirements:

1. Return a JSON object with an `items` field containing extracted evidence items.
2. Preserve original wording whenever possible.
3. Preserve original order whenever possible.
4. Do not include explanations.
5. Do not include reasoning.
6. Do not include headings.
7. Do not include section names.
8. Do not include empty items.
9. Do not deduplicate.
10. If no valid evidence exists, return {"items": []}.

Example output:

{
  "items": [
    "Developed REST APIs using FastAPI.",
    "Built dashboards in Tableau.",
    "Increased conversion rate by 12%."
  ]
}

---

## Input

The resume will be provided by the user as a JSON object with a `resume_text` field.
"""

_RESUME_SKILL_PROMPT = """
## Role

You are a resume skills extraction engine.

## Task

Extract the most relevant skills from the full resume.

---

## Selection Criteria

Include only skills that are:

- explicitly listed in skills, tools, technologies, certifications, experience, or project sections
- clearly demonstrated through actions, responsibilities, deliverables, or results
- useful for matching the candidate to job requirements
- likely to represent genuine capability rather than incidental exposure

---

## Evidence Rules

A skill is valid if it is supported by at least one of:

1. A dedicated skills section
2. Experience bullets
3. Project descriptions
4. Certifications
5. Technical tool usage
6. Measurable work performed using that skill

Skills appearing in a dedicated skills section are valid even if not repeated elsewhere.

Do not infer skills that are not explicitly supported by the resume.

---

## Extraction Rules

1. Extract up to 10 skills.
2. Extract fewer than 10 skills if fewer are strongly supported.
3. Prioritize:

   - technical skills
   - software tools
   - technologies
   - platforms
   - frameworks
   - analytical methods
   - business or functional expertise
   - professional capabilities demonstrated through execution

4. Include soft skills ONLY when strongly evidenced through:

   - leadership
   - stakeholder management
   - ownership
   - communication
   - negotiation
   - measurable achievements

5. Prefer skills demonstrated through experience over skills mentioned only once.

---

## Resume Guidelines

Examples:

- "Built dashboards in Tableau and SQL"
  → Tableau
  → SQL
  → Data Visualization

- "Led a team of 10 volunteers"
  → Team Leadership

- "Conducted market research and customer interviews"
  → Market Research
  → Customer Research

- "Negotiated partnerships with corporate sponsors"
  → Negotiation
  → Partnership Development

- "Managed cross-functional stakeholders across marketing and operations"
  → Stakeholder Management
  → Cross-functional Collaboration

Do not extract skills that appear only in job titles unless supported by:
- responsibilities
- achievements
- projects
- certifications
- a dedicated skills section

---

## Normalization Rules

1. Consolidate similar skills into a single canonical form:

   - Python programming → Python
   - Data analytics → Data Analysis
   - Business development → Business Development

2. Prefer widely recognized standard names:

   - Amazon Web Services → AWS
   - Microsoft Excel → Excel

3. Avoid redundancy or overlap:

   - Do NOT include both SQL and Databases unless clearly distinct.
   - Do NOT include both Leadership and Team Leadership; use the more specific term.
   - Do NOT include both Data Analysis and Analytics; use a single canonical form.

4. Prefer specific skills over broad categories:

   - Financial Modeling instead of Finance
   - Market Research instead of Research
   - Stakeholder Management instead of Communication

5. Use concise canonical skill names.

---

## Ranking Rules

When more than 10 valid skills exist:

Prioritize skills that are:

1. Most frequently supported
2. Most central to the candidate's work
3. Most likely to be useful for job matching
4. Most specialized and differentiating

---

## Structured Output Rules

Return a JSON object matching the provided schema.

Requirements:

1. Return a JSON object with a `skills` field containing extracted skills.
2. Return at most 10 skills.
3. Do not include duplicates.
4. Do not include overlapping skills.
5. Do not include explanations.
6. Do not include reasoning.
7. Do not include confidence scores.
8. Use canonical skill names whenever possible.
9. If no skills can be extracted, return {"skills": []}.

Example output:

{
  "skills": [
    "Python",
    "SQL",
    "AWS",
    "Data Analysis",
    "Stakeholder Management"
  ]
}

---

## Input

The resume will be provided by the user as a JSON object with a `resume_text` field.
"""

class GroqResumeExtractor:
    def __init__(self, api_key: str):
        self.model = NormalizationConfig.LLM.value
        self.max_completion_tokens = NormalizationConfig.MAX_TOKEN.value
        self.llm = ChatGroq(
            groq_api_key=api_key,
            model=self.model,
            temperature=0,
            max_tokens=self.max_completion_tokens,
        )

    def extract_evidence(self, resume_text: str) -> Result[list[str]]:
        resume_text = (resume_text or "").strip()
        if not resume_text:
            return Result(
                result=ScrapeResult.SUCCESSFUL,
                content=[],
            )

        last_error: Exception | None = None

        for retry in range(Setting.MAX_RETRIES.value + 1):
            try:
                if retry > 0:
                    sleep(Setting.FAIL_RETRY_PENALTY.value * retry)

                user_payload = self._resume_payload(resume_text)
                response = self._call_structured(
                    _RESUME_EVIDENCE_PROMPT,
                    user_payload,
                    ResumeEvidenceValues,
                )
                items = [item.strip() for item in response.items if item.strip()]

                return Result(
                    result=ScrapeResult.SUCCESSFUL,
                    content=items,
                )

            except RateLimitError as e:
                last_error = e
                continue
            except Exception as e:
                last_error = e
                break

        return Result(
            result=ScrapeResult.FAILED,
            content=None,
            error=str(last_error),
        )

    def extract_skills_from_resume(self, resume_text: str) -> Result[list[str]]:
        resume_text = (resume_text or "").strip()
        if not resume_text:
            return Result(
                result=ScrapeResult.SUCCESSFUL,
                content=[],
            )

        last_error: Exception | None = None

        for retry in range(Setting.MAX_RETRIES.value + 1):
            try:
                if retry > 0:
                    sleep(Setting.FAIL_RETRY_PENALTY.value * retry)

                user_payload = self._resume_payload(resume_text)
                response = self._call_structured(
                    _RESUME_SKILL_PROMPT,
                    user_payload,
                    ResumeSkillValues,
                )
                parsed = response.skills

                seen: set[str] = set()
                deduped_skills: list[str] = []
                for skill in parsed:
                    skill = " ".join(skill.strip().split())
                    if not skill:
                        continue
                    skill_key = skill.lower()
                    if skill_key in seen:
                        continue
                    seen.add(skill_key)
                    deduped_skills.append(skill)

                if len(deduped_skills) > 10:
                    deduped_skills = deduped_skills[:10]

                return Result(
                    result=ScrapeResult.SUCCESSFUL,
                    content=deduped_skills,
                )

            except RateLimitError as e:
                last_error = e
                continue
            except Exception as e:
                last_error = e
                break

        return Result(
            result=ScrapeResult.FAILED,
            content=None,
            error=str(last_error),
        )

    def _call_structured(
        self,
        system_prompt: str,
        user_payload: str,
        output_schema: type[StructuredOutput],
    ) -> StructuredOutput:
        structured_llm = self.llm.with_structured_output(output_schema)
        return structured_llm.invoke(
            [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_payload),
            ]
        )

    @staticmethod
    def _resume_payload(resume_text: str) -> str:
        return json.dumps({"resume_text": resume_text}, ensure_ascii=False)
