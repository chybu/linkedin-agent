from time import sleep

from groq import Groq, RateLimitError

from linkedin_tool.schema import Result, ScrapeResult
from config import NormalizationConfig, Setting


_RESUME_EVIDENCE_PROMPT = """
You are a resume evidence extraction assistant.

Extract only evidence from work experience and project sections, including headings such as:

* Experience
* Work Experience
* Professional Experience
* Employment
* Projects
* Project Experience
* Selected Projects
* Similar experience- or project-related sections

Rules:

* Extract only original sentences or bullet points describing responsibilities, actions, technologies, deliverables, achievements, or project work.
* Exclude education, skills, certifications, awards, summary/objective, contact information, and other non-experience content.
* Preserve the original wording as much as possible.
* Do not rewrite, summarize, paraphrase, normalize, infer, or combine content.
* If a bullet contains multiple sentences, split it only when each sentence remains understandable on its own. Otherwise keep the original bullet intact.
* Do not deduplicate.

Output:

* Return bullet points only.
* One bullet per line.
* No headings, labels, numbering, JSON, tables, explanations, or additional text.
* If no relevant experience or project evidence exists, return nothing.

Resume:
"""

_RESUME_SKILL_PROMPT = """
## Role

You are a resume skills extraction engine.

## Task

Extract the most relevant skills from the full resume.

---

## Selection Criteria

Include only skills that are:

* explicitly listed in skills, tools, technologies, certifications, experience, or project sections
* clearly demonstrated through actions, responsibilities, deliverables, or results
* useful for matching the candidate to job requirements
* likely to represent genuine capability rather than incidental exposure

---

## Extraction Rules

1. Extract up to 10 skills (fewer if appropriate).
2. Do NOT infer skills without evidence from the resume.
3. Prioritize:

   * technical skills
   * tools, technologies, platforms
   * analytical methods
   * business, functional, or domain expertise
   * professional capabilities demonstrated through execution
4. Include soft skills ONLY when strongly evidenced through leadership, stakeholder management, ownership, communication, or measurable achievements.
5. Skills from a dedicated skills section are valid even when not repeated in experience bullets.

---

## Resume Guidelines

Examples:

* "Built dashboards in Tableau and SQL" → Tableau;SQL;Data Visualization
* "Led a team of 10 volunteers" → Team Leadership
* "Conducted market research and customer interviews" → Market Research;Customer Research
* "Negotiated partnerships with corporate sponsors" → Negotiation;Partnership Development
* "Managed cross-functional stakeholders across marketing and operations" → Stakeholder Management;Cross-functional Collaboration

Do NOT extract skills that appear only in job titles unless supported by responsibilities, achievements, or a dedicated skills section.

---

## Normalization Rules

1. Consolidate similar skills into a single canonical form:

   * "Python programming" → "Python"
   * "Data analytics" → "Data Analysis"
   * "Business development" → "Business Development"
2. Prefer widely recognized standard names:

   * "Amazon Web Services" → "AWS"
   * "Microsoft Excel" → "Excel"
3. Avoid redundancy or overlap:

   * Do NOT include both "SQL" and "Databases" unless clearly distinct.
   * Do NOT include both "Leadership" and "Team Leadership"; use the more specific term.
4. Prefer specific skills over broad categories:

   * "Financial Modeling" instead of "Finance"
   * "Market Research" instead of "Research"

---

## Output Rules

1. Return ONLY a semicolon-separated list.
2. Use `;` as delimiter.
3. Do not add spaces before or after semicolons.
4. Do not include explanations or extra text.
5. Do not include duplicate or overlapping skills.

---

## Example Output

Business Development;Negotiation;Stakeholder Management;Market Research;Project Management;Excel;SQL;Data Analysis;Team Leadership;Presentation Skills

---

## Resume

[RESUME]

Extract and return the skills now.
"""

class GroqResumeExtractor:
    def __init__(self, api_key: str):
        self.client = Groq(api_key=api_key)
        self.model = NormalizationConfig.LLM.value
        self.max_completion_tokens = NormalizationConfig.MAX_TOKEN.value

    def extract_evidence(self, resume_text: str) -> Result[str]:
        resume_text = (resume_text or "").strip()
        if not resume_text:
            return Result(
                result=ScrapeResult.SUCCESSFUL,
                content=None,
            )

        last_error: Exception | None = None

        for retry in range(Setting.MAX_RETRIES.value + 1):
            try:
                if retry > 0:
                    sleep(Setting.FAIL_RETRY_PENALTY.value * retry)

                content = self._call(_RESUME_EVIDENCE_PROMPT, resume_text)

                return Result(
                    result=ScrapeResult.SUCCESSFUL,
                    content=content,
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

                content = self._call(_RESUME_SKILL_PROMPT, resume_text)
                parsed = self._parse_semicolon(content)

                seen: set[str] = set()
                deduped_skills: list[str] = []
                for skill in parsed:
                    skill_key = skill.lower()
                    if skill_key in seen:
                        continue
                    seen.add(skill_key)
                    deduped_skills.append(skill)

                if len(deduped_skills) > 20:
                    deduped_skills = deduped_skills[:20]

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

    def _call(self, system_prompt: str, user_payload: str) -> str:
        completion = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_payload},
            ],
            temperature=0,
            max_completion_tokens=self.max_completion_tokens,
            top_p=1,
            stream=False,
            stop=None,
        )
        return (completion.choices[0].message.content or "").strip()

    def _parse_semicolon(self, content: str) -> list[str]:
        return [
            " ".join(item.strip().split())
            for item in (content or "").split(";")
            if item.strip()
        ]
