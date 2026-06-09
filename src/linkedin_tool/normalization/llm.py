import json
from time import sleep
from typing import TypeVar

from groq import RateLimitError
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_groq import ChatGroq
from pydantic import BaseModel, Field

from linkedin_tool.schema import Result, ScrapeResult
from config import NormalizationConfig, Setting
from log import print_message

StructuredOutput = TypeVar("StructuredOutput", bound=BaseModel)


class NormalizedValues(BaseModel):
    values: list[str] = Field(
        description="One normalized output value for each input item, preserving input order."
    )


class SkillValues(BaseModel):
    skills: list[str] = Field(description="Normalized job skills.")


class CleanedDescriptionValues(BaseModel):
    items: list[str] = Field(description="Retained role-relevant job description items.")


_ALLOWED_SENIORITY = {
    "intern",
    "junior",
    "mid",
    "senior",
    "lead",
    "executive",
    "not_applicable",
    "unknown",
}

_PROMPTS = {
    "location": 
"""
## Role
You are a geographic data normalization engine.

## Task
Normalize every input location into exactly one standardized location.

---

## Input Parsing Rules
1. The input list is separated ONLY by semicolons (;).
2. Commas are part of a single location value and must NOT be treated as item separators.
3. Return exactly one output for each semicolon-separated input item.
4. If there is no semicolon, treat the entire input as ONE location.
5. If an input item contains multiple locations, select the first recognizable valid city.

---

## Normalization Rules
1. Normalize casing, spelling variations, and common abbreviations (e.g., "NYC" → "New York, NY", "LA" → "Los Angeles, CA").
2. Remove zip codes, postal codes, street addresses, building names, floor numbers, suite numbers, and office names.
3. Remove non-essential administrative divisions for non-US locations (state, province, region, county, district).
4. If only a city is provided, infer the most commonly recognized location.
5. For ambiguous city names, select the most globally recognized city unless additional context is provided.
6. If multiple cities or locations appear within a single item, use the first valid city.
7. Treat placeholder or non-location terms (e.g., "location", "remote", "hybrid", "global", "anywhere", "various", "multiple locations", "TBD", "N/A", "not specified") as invalid.

---

## Format Rules
1. For every input, output exactly one normalized location.
2. If the location is in the United States, output:
   City, [2-letter state abbreviation]
   Example: San Francisco, CA
3. If the input is a valid US state, output:
   State Name, United States
   Example: West Virginia, United States
4. If the location is outside the United States, output:
   City, Country
   Example: Paris, France
5. If the input does not contain a real or recognizable location, output:
   Unknown
6. Ensure the number of outputs exactly matches the number of input items.
7. Preserve input order.
8. Do not deduplicate.

---

## Structured Output Rules
Return a JSON object that matches the provided schema.

- The number of normalized locations must exactly match the number of input items.
- Preserve input order.
- Do not include explanations.
- Do not include reasoning.
- Do not omit entries.
- Every input item must produce exactly one normalized location.

---

## Few-shot Examples

Input:
New York;NYC;New York City;Manhattan NY;10001 New York

Output:
{"values":["New York, NY","New York, NY","New York, NY","New York, NY","New York, NY"]}

---

Input:
London;London UK;London England;Greater London

Output:
{"values":["London, United Kingdom","London, United Kingdom","London, United Kingdom","London, United Kingdom"]}

---

Input:
Toronto;Toronto ON;Toronto Ontario;Toronto Canada

Output:
{"values":["Toronto, Canada","Toronto, Canada","Toronto, Canada","Toronto, Canada"]}

---

Input:
Location, WV

Output:
{"values":["Unknown"]}

---

Input:
Location, WV;location wv;Remote;Multiple Locations;TBD;N/A

Output:
{"values":["Unknown","Unknown","Unknown","Unknown","Unknown","Unknown"]}

---

Input:
Charleston, WV;Morgantown WV;Buckhannon, West Virginia

Output:
{"values":["Charleston, WV","Morgantown, WV","Buckhannon, WV"]}

---

Input:
{locations}
""",
    "title": 
"""
## Role
You are a job title normalization engine.

## Task
Normalize each input job title into exactly one official SOC Detailed Occupation title.

---

## Input Parsing Rules
1. The input list is separated ONLY by semicolons (;).
2. Commas are part of a single job title and must NOT be treated as separators.
3. Return exactly one output for each semicolon-separated input item.
4. If there is no semicolon, treat the entire input as ONE job title.
5. If a single item contains multiple roles, select the first recognizable valid occupation.

---

## Normalization Rules
1. Map each title to the closest official SOC Detailed Occupation name (plural form).
2. Output MUST match standard SOC naming exactly (no paraphrasing, synonyms, variants, or invented occupation names).
3. Consolidate equivalent roles into the same SOC title (e.g., "Software Engineer" → "Software Developers").
4. Remove seniority indicators (e.g., Senior, Junior, Lead, Principal, Staff, Intern, I, II, III, VP, Director), unless they define a distinct SOC occupation (e.g., "Marketing Managers" must remain distinct).
5. Expand common abbreviations (e.g., "RN" → "Registered Nurses").
6. Remove non-title content:
   - Locations
   - Company names
   - Departments
   - Employment types (e.g., contract, remote)
   - Job IDs, requisition numbers, or codes
   - Special characters or noise
7. For ambiguous or broad titles (e.g., "Analyst", "Consultant"):
   - Choose the closest widely recognized SOC occupation if reasonable.
   - Otherwise output: Unknown.
8. If no valid SOC occupation can be confidently determined, output: Unknown.
9. Treat non-job-title inputs (e.g., recruiting messages, generic phrases, calls to action) as Unknown.
10. Only use official SOC Detailed Occupation titles.
11. Do not invent occupation names.
12. If no official SOC Detailed Occupation can be confidently matched, output: Unknown.
13. When uncertain between multiple SOC occupations, prefer Unknown over guessing.

---

## Format Rules
1. Output exactly one SOC title per input.
2. Ensure outputs are in plural SOC format (e.g., "Data Scientists", "Marketing Managers").
3. Preserve input order.
4. Do not deduplicate.

---

## Structured Output Rules
Return a JSON object matching the provided schema.

Requirements:
1. Return exactly one normalized SOC occupation for each input item.
2. Preserve input order.
3. Do not deduplicate.
4. Do not omit entries.
5. Do not include explanations, reasoning, confidence scores, or additional fields.
6. Every output value must be either:
   - an official SOC Detailed Occupation title (plural form), or
   - "Unknown".

---

## Few-shot Examples

Input:
Accountant, Finance Department

Output:
{"values":[
  "Accountants and Auditors"
]}

---

Input:
Software Developer;Software Engineer;Sr. Software Engineer;Junior Software Dev;Backend Engineer

Output:
{"values":[
  "Software Developers",
  "Software Developers",
  "Software Developers",
  "Software Developers",
  "Software Developers"
]}

---

Input:
Data Scientist;Sr Data Scientist;Machine Learning Scientist;Applied Scientist - ML

Output:
{"values":[
  "Data Scientists",
  "Data Scientists",
  "Data Scientists",
  "Data Scientists"
]}

---

Input:
Registered Nurse;RN;Staff Nurse;ICU Nurse - Boston

Output:
{"values":[
  "Registered Nurses",
  "Registered Nurses",
  "Registered Nurses",
  "Registered Nurses"
]}

---

Input:
Accountant;Staff Accountant;Senior Accountant;Accounting Analyst

Output:
{"values":[
  "Accountants and Auditors",
  "Accountants and Auditors",
  "Accountants and Auditors",
  "Accountants and Auditors"
]}

---

Input:
HR Specialist;Human Resources Specialist;People Operations Specialist;Talent Specialist

Output:
{"values":[
  "Human Resources Specialists",
  "Human Resources Specialists",
  "Human Resources Specialists",
  "Human Resources Specialists"
]}

---

Input:
Marketing Manager;Growth Marketing Manager;Digital Marketing Manager;Sr. Marketing Manager

Output:
{"values":[
  "Marketing Managers",
  "Marketing Managers",
  "Marketing Managers",
  "Marketing Managers"
]}

---

## Fallback Examples (Invalid Titles)

Input:
Don't See A Career Match? Submit Your Resume for Future Opportunities!

Output:
{"values":[
  "Unknown"
]}

---

Input:
Looking for New Opportunities;Open to Work;Actively Seeking Roles

Output:
{"values":[
  "Unknown",
  "Unknown",
  "Unknown"
]}

---

Input:
Various Roles;Multiple Positions;TBD

Output:
{"values":[
  "Unknown",
  "Unknown",
  "Unknown"
]}

---

Input:
{job_titles}
""",
    "seniority_raw": 
"""
## Role
You are a seniority normalization engine.

## Task
Normalize each input into exactly one of the following seniority levels:

intern;junior;mid;senior;lead;executive;unknown

---

## Input Parsing Rules
1. The input list is separated ONLY by semicolons (;).
2. Commas are part of a single value and must NOT be treated as separators.
3. Return exactly one output for each semicolon-separated input item.
4. If there is no semicolon, treat the entire input as ONE value.
5. If multiple seniority indicators appear in one item, select the highest seniority level.

---

## Seniority Definitions

- intern: internships, trainees, students
- junior: entry-level, associate, early career
- mid: mid-level, intermediate, level II
- senior: senior-level, experienced individual contributor, level III+
- lead: lead, team lead, staff, principal, manager-level below director
- executive: director and above (director, VP, head, C-level, founder, owner)

---

## Normalization Rules

1. Normalize casing, punctuation, and formatting (e.g., "Sr.", "Sr", "SENIOR" → "senior").
2. Expand common abbreviations (e.g., "Sr" → senior, "Jr" → junior, "VP" → executive).
3. Ignore non-seniority content such as:
   - job titles
   - locations
   - departments
   - employment types (e.g., remote, contract)
   - job levels (e.g., L1–L10) unless clearly mappable
4. If multiple indicators exist, choose the highest level using this priority:

   executive > lead > senior > mid > junior > intern

5. If no clear seniority signal exists, output: unknown.
6. Treat vague or non-seniority phrases (e.g., "open", "various", "not specified", "TBD") as unknown.
7. Output values must be exactly one of:

   - intern
   - junior
   - mid
   - senior
   - lead
   - executive
   - unknown

8. Never invent additional levels.
9. When uncertain, output unknown.

---

## Format Rules

1. Output exactly one seniority level per input.
2. Preserve input order.
3. Do not deduplicate.
4. Ensure the number of outputs exactly matches the number of inputs.

---

## Structured Output Rules

Return a JSON object matching the provided schema.

Requirements:

1. Return exactly one normalized seniority level for each input item.
2. Preserve input order.
3. Do not deduplicate.
4. Do not omit entries.
5. Do not include explanations, reasoning, confidence scores, or additional fields.
6. Every output value must be one of:

   - intern
   - junior
   - mid
   - senior
   - lead
   - executive
   - unknown

---

## Few-shot Examples

Input:
Mid, Senior level

Output:
{"values":[
  "senior"
]}

---

Input:
Entry level

Output:
{"values":[
  "junior"
]}

---

Input:
Internship;Intern;Trainee;Student

Output:
{"values":[
  "intern",
  "intern",
  "intern",
  "intern"
]}

---

Input:
Entry level;Entry-Level;Junior;Associate;Early Career

Output:
{"values":[
  "junior",
  "junior",
  "junior",
  "junior",
  "junior"
]}

---

Input:
Mid-Senior level;Mid Level;Intermediate;Level II

Output:
{"values":[
  "senior",
  "mid",
  "mid",
  "mid"
]}

---

Input:
Senior level;Senior;Experienced;Level III

Output:
{"values":[
  "senior",
  "senior",
  "senior",
  "senior"
]}

---

Input:
Lead;Team Lead;Manager;Principal;Staff

Output:
{"values":[
  "lead",
  "lead",
  "lead",
  "lead",
  "lead"
]}

---

Input:
Director;Executive;VP;Vice President;C-Level;Founder;Owner

Output:
{"values":[
  "executive",
  "executive",
  "executive",
  "executive",
  "executive",
  "executive",
  "executive"
]}

---

Input:
No level specified;Open role;TBD

Output:
{"values":[
  "unknown",
  "unknown",
  "unknown"
]}

---

Input:
{seniority_values}
""",
    "seniority_title": 
"""
## Role
You are a job seniority classification engine.

## Task
Normalize each input job title into exactly one of the following seniority levels:

intern;junior;mid;senior;lead;executive;not_applicable;unknown

---

## Input Parsing Rules
1. The input list is separated ONLY by semicolons (;).
2. Commas are part of a single value and must NOT be treated as separators.
3. Return exactly one output for each semicolon-separated input item.
4. If there is no semicolon, treat the entire input as ONE value.
5. If multiple seniority indicators appear, resolve using the priority rules below.

---

## Seniority Definitions
- intern: internships, trainees, students
- junior: entry-level, associate, early-career roles, or explicitly 0–2 years
- mid: mid-level, intermediate, or explicitly 3–5 years
- senior: senior-level or explicitly 6+ years
- lead: lead, team lead, staff, principal, manager-level below director
- executive: director and above (director, head, VP, C-level, founder)
- not_applicable: valid job title with no seniority signal
- unknown: not a valid job title or cannot be classified

---

## Normalization Rules
1. Use ONLY the job title text.
2. Normalize casing, punctuation, and formatting.
3. Ignore non-seniority content:
   - locations
   - company names
   - employment types (e.g., remote, contract)
   - general descriptors (e.g., full-time)
4. Extract years of experience ONLY if explicitly stated (e.g., "2 years", "3+ yrs", "5-7 years").
5. Map years of experience strictly:
   - 0–2 → junior
   - 3–5 → mid
   - 6+ → senior
6. Do NOT infer experience if not explicitly stated.
7. Output values must be exactly one of:
   - intern
   - junior
   - mid
   - senior
   - lead
   - executive
   - not_applicable
   - unknown

---

## Priority Rules (Deterministic)
1. If explicit seniority keywords exist, they OVERRIDE years of experience.
2. If multiple seniority keywords exist, choose the highest using this order:

   executive > lead > senior > mid > junior > intern

3. If both keyword and years exist and conflict, use the keyword.
4. If multiple numeric ranges exist, use the highest implied level.
5. If no seniority signal exists but the title is a valid occupation → not_applicable.
6. If the input is vague, promotional, or not a real job title → unknown.
7. When uncertain between not_applicable and unknown:
   - Use not_applicable if the input is a recognizable job title.
   - Use unknown if the input is not clearly a job title.

---

## Validity Rules
1. Treat recognizable occupations (e.g., "Engineer", "Nurse", "Driver") as valid.
2. Treat vague phrases (e.g., "Open Role", "Various Positions", "Looking for Opportunities") as unknown.

---

## Format Rules
1. Output exactly one seniority level per input.
2. Ensure exactly one output per input.
3. Preserve order.
4. Do not deduplicate.

---

## Structured Output Rules
Return a JSON object matching the provided schema.

Requirements:
1. Return exactly one normalized seniority level for each input item.
2. Preserve input order.
3. Do not deduplicate.
4. Do not omit entries.
5. Do not include explanations, reasoning, confidence scores, or additional fields.
6. Every output value must be exactly one of:
   - intern
   - junior
   - mid
   - senior
   - lead
   - executive
   - not_applicable
   - unknown

---

## Few-shot Examples

Input:
Python Developer, Full Time (2 years experience)

Output:
{"values":[
  "junior"
]}

---

Input:
Senior Software Engineer, Backend

Output:
{"values":[
  "senior"
]}

---

Input:
Python Developer Full Time (2 years experience);Data Analyst 1 yr exp;Software Engineer 0-1 years

Output:
{"values":[
  "junior",
  "junior",
  "junior"
]}

---

Input:
Backend Developer (3 years experience);Product Manager 4 yrs;Business Analyst 5 years

Output:
{"values":[
  "mid",
  "mid",
  "mid"
]}

---

Input:
Data Scientist 6+ years;Software Engineer with 7 years experience;Financial Analyst 10 yrs

Output:
{"values":[
  "senior",
  "senior",
  "senior"
]}

---

Input:
Mid-Level Software Engineer;Intermediate Analyst;Software Engineer II

Output:
{"values":[
  "mid",
  "mid",
  "mid"
]}

---

Input:
Software Engineer;Product Manager;Business Analyst;Draftsman (civil/architect)

Output:
{"values":[
  "not_applicable",
  "not_applicable",
  "not_applicable",
  "not_applicable"
]}

---

Input:
Draftsman (3 years experience);Civil Draftsman 2 yrs;Architectural Draftsman 6+ years

Output:
{"values":[
  "mid",
  "junior",
  "senior"
]}

---

Input:
Senior Software Engineer (2 years experience)

Output:
{"values":[
  "senior"
]}

---

Input:
Lead/Senior Engineer

Output:
{"values":[
  "lead"
]}

---

Input:
Director of Engineering;VP of Product;Chief Technology Officer

Output:
{"values":[
  "executive",
  "executive",
  "executive"
]}

---

Input:
Software Engineer Intern;Marketing Intern

Output:
{"values":[
  "intern",
  "intern"
]}

---

Input:
Floorhand;Driver;Warehouse Worker;Operator;Cashier;Word Processor

Output:
{"values":[
  "not_applicable",
  "not_applicable",
  "not_applicable",
  "not_applicable",
  "not_applicable",
  "not_applicable"
]}

---

Input:
Open to Work;Looking for Opportunities;Various Roles

Output:
{"values":[
  "unknown",
  "unknown",
  "unknown"
]}

---

Input:
{job_titles}
""",
    "skill":
"""
## Role
You are a job skills extraction engine.

## Task
Extract the most critical skills from the job description.

---

## Selection Criteria
Include only skills that are:
- explicitly required or strongly emphasized
- essential to performing the core responsibilities of the role
- frequently mentioned or clearly central to the job

---

## Extraction Rules
1. Extract up to 10 skills.
2. Extract fewer than 10 skills if fewer are appropriate.
3. Do NOT include low-value or generic skills unless strongly emphasized.
4. Prioritize:
   - technical skills
   - tools, technologies, frameworks
   - domain-specific expertise
5. Include soft skills ONLY if clearly emphasized multiple times or critical to the role.
6. Do not extract company names, locations, benefits, employment types, or generic responsibilities as skills.
7. If no meaningful skills can be extracted, return an empty list.

---

## Normalization Rules
1. Consolidate similar skills into a single canonical form:
   - "Python programming" → "Python"
   - "AWS cloud" → "AWS"
2. Prefer widely recognized standard names:
   - "Amazon Web Services" → "AWS"
   - "Microsoft Excel" → "Excel"
3. Avoid redundancy or overlap:
   - Do NOT include both "SQL" and "Databases" unless clearly distinct in context.
4. Do not duplicate skills.
5. Use concise skill names, not full sentences.

---

## Structured Output Rules
Return a JSON object matching the provided schema.

Requirements:
1. Return a JSON object with a `skills` field containing the extracted skills.
2. Return at most 10 skills.
3. Do not include duplicate or overlapping skills.
4. Do not include explanations, reasoning, confidence scores, or additional fields.
5. If no skills are found, return an empty `skills` list.

---

## Example

Job Description:
We are looking for a Data Scientist with strong Python, SQL, AWS, data analysis, and TensorFlow experience.

Output:
{"skills":[
  "Python",
  "SQL",
  "AWS",
  "Data Analysis",
  "TensorFlow"
]}

---

## Job Description
{job_description}
""",
    "description":
"""
## Role

You are a senior job description cleanup assistant.

You specialize in removing non-role-specific content from job descriptions while preserving the original job-relevant wording, formatting, and meaning.

---

## Task

Review the raw job description and retain only content that is directly relevant to performing the role.

Remove all non-role-specific content.

---

## Keep Only

Retain content that directly describes:

- Job title
- Core responsibilities
- Day-to-day duties
- Required qualifications
- Preferred qualifications that are job-related
- Required years of experience
- Technical skills
- Programming languages
- Tools
- Frameworks
- Platforms
- Software
- Technologies
- Certifications
- Candidate expectations directly tied to job performance

---

## Remove

Remove any sentence, bullet point, heading, paragraph, clause, or section containing:

### Company Information
- Company introductions
- About Us sections
- Company history
- Founder stories
- Funding announcements
- Investor information
- Customer lists
- Customer logos

### Mission & Culture
- Mission statements
- Vision statements
- Values
- Culture descriptions
- Team descriptions
- Generic workplace statements

### Recruiting & Logistics
- Application instructions
- Recruiting process details
- Interview process details
- Start date information
- Program logistics
- Hiring timelines

### Benefits & Compensation
- Salary information
- Compensation information
- Equity information
- Benefits
- Perks
- Wellness programs
- Career growth promises

### Location & Work Arrangement
Remove all:
- Remote
- Hybrid
- Onsite
- In-person
- Relocation
- Visa sponsorship
- Office location information

### Marketing & Promotional Content
- Motivational language
- Recruiting slogans
- Hype statements
- Generic company marketing

---

## Preservation Rules

1. Preserve original wording whenever possible.
2. Preserve original capitalization whenever possible.
3. Preserve original technical terminology.
4. Preserve original tool names.
5. Preserve original technology names.
6. Do not paraphrase.
7. Do not summarize.
8. Do not infer missing information.
9. Do not rewrite requirements.
10. Do not merge unrelated requirements.
11. If a sentence contains both relevant and irrelevant content:
    - Remove only the irrelevant portion when possible.
    - Otherwise remove the entire sentence.

---

## Splitting Rules

1. Each retained item should represent a single responsibility, qualification, skill, requirement, tool, technology, or candidate expectation.
2. Split compound bullets only when meaning is preserved.
3. If splitting would lose context, keep the original item intact.

---

## Structured Output Rules

Return a JSON object matching the provided schema.

Requirements:

1. Return only retained role-relevant items.
2. Preserve original wording as much as possible.
3. Do not include removed content.
4. Do not include explanations.
5. Do not include summaries.
6. Do not include reasoning.
7. Do not include headings.
8. Do not include section titles.
9. Do not include empty items.
10. Preserve the original order whenever possible.

---

## Example

Input:

About Us

We are a fast-growing startup backed by top investors.

Responsibilities

Build backend services using Python and AWS.

Requirements

3+ years of software engineering experience.

Benefits

Competitive salary and equity.

Output:

{"items":[
  "Build backend services using Python and AWS.",
  "3+ years of software engineering experience."
]}

---

## Job Description

{job_description}
"""
}

class GroqLLMNormalizer:
    def __init__(self, api_key:str):
        self.model = NormalizationConfig.LLM.value
        self.max_completion_tokens = NormalizationConfig.MAX_TOKEN.value
        self.llm = ChatGroq(
            groq_api_key=api_key,
            model=self.model,
            temperature=0,
            max_tokens=self.max_completion_tokens,
        )

    def normalize_batch(self, domain: str, values: list[str]) -> Result:
        if domain not in _PROMPTS:
            return Result(
                result=ScrapeResult.FAILED,
                content=None,
                error=f"unsupported domain: {domain}",
            )

        inputs = [self._clean_text(v) for v in values]
        if not inputs:
            return Result(
                result=ScrapeResult.SUCCESSFUL,
                content=[]
            )
        inputs.append("unknown")

        original_payload = json.dumps(inputs, ensure_ascii=False)
        user_payload = f"Input items JSON array:\n{original_payload}"
        last_error: Exception | None = None

        for retry in range(Setting.MAX_RETRIES.value + 1):
            try:
                if retry > 0:
                    sleep_seconds = Setting.FAIL_RETRY_PENALTY.value * retry
                    sleep(sleep_seconds)
                
                # Sometimes the model can give invalid output. Try again with a stricter repair prompt.
                for llm_retry in range(Setting.MAX_RETRIES.value+1):
                    response = self._call_structured(
                        _PROMPTS[domain],
                        user_payload,
                        NormalizedValues,
                    )
                    parsed = response.values
                    if len(parsed) != len(inputs) and llm_retry<Setting.MAX_RETRIES.value:
                        sleep(NormalizationConfig.LLM_INTERVAL.value)
                        user_payload = \
f"""
The previous output had {len(parsed)} items, but there are {len(inputs)} inputs.

Regenerate the FULL output.
Ensure the number of outputs EXACTLY matches the number of inputs.
Return one output for each item in this JSON array, preserving order.

Input items JSON array:
{original_payload}
"""
                    else:
                        break

                if len(parsed) != len(inputs):
                    raise ValueError(
                        f"LLM parse size mismatch for domain={domain}: "
                        f"expected {len(inputs)}, got {len(parsed)}\n"
                        f"raw={inputs!r}"
                    )
                    
                parsed = parsed[:-1]

                if domain.startswith("seniority"):
                    parsed = [self._clean_seniority(x) for x in parsed]
                else:
                    parsed = [self._clean_text(x).lower() for x in parsed]
                    
                return Result(
                    result=ScrapeResult.SUCCESSFUL,
                    content=parsed
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
            error=str(last_error)
        )

    def normalize_seniority(
        self,
        raw_senior: list[str],
        raw_title: list[str],
    ) -> Result:
        stage1_labels: list[str] = []
        stage2_labels: list[str] = []

        # Stage 1: normalize explicit seniority values.
        if raw_senior:
            s1_res = self.normalize_batch("seniority_raw", raw_senior)
            if s1_res.result != ScrapeResult.SUCCESSFUL:
                return Result(
                    result=ScrapeResult.FAILED,
                    content=None,
                    error=f"seniority stage 1 failed: {s1_res.error}"
                )
            stage1_labels = [self._clean_seniority(v) for v in s1_res.content]

        # Stage 2: normalize title-derived seniority values.
        if raw_title:
            if raw_senior:
                sleep(5)
            s2_res = self.normalize_batch("seniority_title", raw_title)
            if s2_res.result != ScrapeResult.SUCCESSFUL:
                return Result(
                    result=ScrapeResult.FAILED,
                    content=None,
                    error=f"seniority stage 2 failed: {s2_res.error}"
                )
            stage2_labels = [self._clean_seniority(v) for v in s2_res.content]

        return Result(
            result=ScrapeResult.SUCCESSFUL,
            content=(stage1_labels, stage2_labels)
        )

    def extract_skills_from_description(self, description: str) -> Result:
        description = self._clean_text(description)
        if not description:
            return Result(
                result=ScrapeResult.SUCCESSFUL,
                content=[],
            )

        last_error: Exception | None = None

        for retry in range(Setting.MAX_RETRIES.value + 1):
            try:
                if retry > 0:
                    sleep_seconds = Setting.FAIL_RETRY_PENALTY.value * retry
                    sleep(sleep_seconds)

                response = self._call_structured(
                    _PROMPTS["skill"],
                    description,
                    SkillValues,
                )
                parsed = response.skills

                # Preserve order while removing duplicates case-insensitively.
                seen: set[str] = set()
                deduped_skills: list[str] = []
                for skill in parsed:
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

    def clean_description(self, description: str) -> Result[list[str]]:
        description = self._clean_text(description)
        if not description:
            return Result(
                result=ScrapeResult.SUCCESSFUL,
                content=[],
            )

        last_error: Exception | None = None

        for retry in range(Setting.MAX_RETRIES.value + 1):
            try:
                if retry > 0:
                    sleep_seconds = Setting.FAIL_RETRY_PENALTY.value * retry
                    sleep(sleep_seconds)

                response = self._call_structured(
                    _PROMPTS["description"],
                    description,
                    CleanedDescriptionValues,
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
    
    def _call_structured(
        self,
        system_prompt: str,
        user_payload: str,
        output_schema: type[StructuredOutput],
    ) -> StructuredOutput:
        print_message("llm", f"normalization model={self.model}")
        structured_llm = self.llm.with_structured_output(output_schema)
        return structured_llm.invoke(
            [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_payload),
            ]
        )

    @staticmethod
    def _clean_text(value: str) -> str:
        return (value or "").replace("\n", " ").replace(";", ",").strip()

    @staticmethod
    def _clean_seniority(value: str) -> str:
        v = (value or "").strip().lower().replace(" ", "_")
        if v in _ALLOWED_SENIORITY:
            return v
        return "unknown"
