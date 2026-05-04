from groq import Groq, RateLimitError
from time import sleep
from linkedin_tool.schema import Result, ScrapeResult
from linkedin_tool.setting import NormalizationConfig, Setting

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
1. The input list is separated ONLY by semicolons (`;`).
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
   **City, [2-letter state abbreviation]**  
   Example: `San Francisco, CA`
3. If the input is a valid US state, output:  
   **State Name, United States**  
   Example: `West Virginia, United States`
4. If the location is outside the United States, output:  
   **City, Country**  
   Example: `Paris, France`
5. If the input does not contain a real or recognizable location, output:  
   **Unknown**
6. Ensure the number of outputs exactly matches the number of input items.
7. Preserve input order.
8. Do not deduplicate.

---

## Output Rules
1. Output ONLY a semicolon-separated list of normalized locations.
2. Use `;` as the delimiter.
3. Do not add spaces before or after semicolons.
4. Do not include a trailing semicolon.
5. Do not include any extra text, explanations, or formatting.

---

## Few-shot Examples

**Input:**  
New York;NYC;New York City;Manhattan NY;10001 New York  

**Output:**  
New York, NY;New York, NY;New York, NY;New York, NY;New York, NY  

---

**Input:**  
London;London UK;London England;Greater London  

**Output:**  
London, United Kingdom;London, United Kingdom;London, United Kingdom;London, United Kingdom  

---

**Input:**  
Toronto;Toronto ON;Toronto Ontario;Toronto Canada  

**Output:**  
Toronto, Canada;Toronto, Canada;Toronto, Canada;Toronto, Canada  

---

**Input:**  
Location, WV  

**Output:**  
Unknown  

---

**Input:**  
Location, WV;location wv;Remote;Multiple Locations;TBD;N/A  

**Output:**  
Unknown;Unknown;Unknown;Unknown;Unknown;Unknown  

---

**Input:**  
Charleston, WV;Morgantown WV;Buckhannon, West Virginia  

**Output:**  
Charleston, WV;Morgantown, WV;Buckhannon, WV  

---

**Input:**  
{locations}  

**Output:**
""",
    "title": 
"""
## Role
You are a job title normalization engine.

## Task
Normalize each input job title into exactly one official SOC Detailed Occupation title.

---

## Input Parsing Rules
1. The input list is separated ONLY by semicolons (`;`).
2. Commas are part of a single job title and must NOT be treated as separators.
3. Return exactly one output for each semicolon-separated input item.
4. If there is no semicolon, treat the entire input as ONE job title.
5. If a single item contains multiple roles, select the first recognizable valid occupation.

---

## Normalization Rules
1. Map each title to the closest **official SOC Detailed Occupation name (plural form)**.
2. Output MUST match standard SOC naming exactly (no paraphrasing or variants).
3. Consolidate equivalent roles into the same SOC title (e.g., "Software Engineer" → "Software Developers").
4. Remove seniority indicators (e.g., Senior, Junior, Lead, Principal, Staff, Intern, I, II, III, VP, Director), **unless they define a distinct SOC occupation** (e.g., "Marketing Managers" must remain distinct).
5. Expand common abbreviations (e.g., "RN" → "Registered Nurses").
6. Remove non-title content:
   - Locations
   - Company names
   - Departments
   - Employment types (e.g., contract, remote)
   - Job IDs, requisition numbers, or codes
   - Special characters or noise
7. For ambiguous or broad titles (e.g., "Analyst", "Consultant"):
   - Choose the closest widely recognized SOC occupation if reasonable
   - Otherwise output: **Unknown**
8. If no valid SOC occupation can be confidently determined, output: **Unknown**
9. Treat non-job-title inputs (e.g., recruiting messages, generic phrases, calls to action) as **Unknown**.

---

## Format Rules
1. Output exactly one SOC title per input.
2. Ensure outputs are in plural SOC format (e.g., "Data Scientists", "Marketing Managers").
3. Preserve input order.
4. Do not deduplicate.

---

## Output Rules
1. Output ONLY a semicolon-separated list.
2. Use `;` as the delimiter.
3. Do not add spaces before or after semicolons.
4. Do not include a trailing semicolon.
5. Do not include explanations or extra text.

---

## Few-shot Examples

**Input:**  
Accountant, Finance Department  

**Output:**  
Accountants and Auditors  

---

**Input:**  
Software Developer;Software Engineer;Sr. Software Engineer;Junior Software Dev;Backend Engineer  

**Output:**  
Software Developers;Software Developers;Software Developers;Software Developers;Software Developers  

---

**Input:**  
Data Scientist;Sr Data Scientist;Machine Learning Scientist;Applied Scientist - ML  

**Output:**  
Data Scientists;Data Scientists;Data Scientists;Data Scientists  

---

**Input:**  
Registered Nurse;RN;Staff Nurse;ICU Nurse - Boston  

**Output:**  
Registered Nurses;Registered Nurses;Registered Nurses;Registered Nurses  

---

**Input:**  
Accountant;Staff Accountant;Senior Accountant;Accounting Analyst  

**Output:**  
Accountants and Auditors;Accountants and Auditors;Accountants and Auditors;Accountants and Auditors  

---

**Input:**  
HR Specialist;Human Resources Specialist;People Operations Specialist;Talent Specialist  

**Output:**  
Human Resources Specialists;Human Resources Specialists;Human Resources Specialists;Human Resources Specialists  

---

**Input:**  
Marketing Manager;Growth Marketing Manager;Digital Marketing Manager;Sr. Marketing Manager  

**Output:**  
Marketing Managers;Marketing Managers;Marketing Managers;Marketing Managers  

---

## Fallback Examples (Invalid Titles)

**Input:**  
Don't See A Career Match? Submit Your Resume for Future Opportunities!  

**Output:**  
Unknown  

---

**Input:**  
Looking for New Opportunities;Open to Work;Actively Seeking Roles  

**Output:**  
Unknown;Unknown;Unknown  

---

**Input:**  
Various Roles;Multiple Positions;TBD  

**Output:**  
Unknown;Unknown;Unknown  

---

**Input:**  
{job_titles}  

**Output:**
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
1. The input list is separated ONLY by semicolons (`;`).
2. Commas are part of a single value and must NOT be treated as separators.
3. Return exactly one output for each semicolon-separated input item.
4. If there is no semicolon, treat the entire input as ONE value.
5. If multiple seniority indicators appear in one item, select the **highest seniority level**.

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
   **executive > lead > senior > mid > junior > intern**
5. If no clear seniority signal exists, output: **unknown**
6. Treat vague or non-seniority phrases (e.g., "open", "various", "not specified", "TBD") as **unknown**

---

## Output Rules
1. Output ONLY a semicolon-separated list.
2. Use `;` as the delimiter.
3. Do not add spaces before or after semicolons.
4. Do not include a trailing semicolon.
5. Do not include explanations or extra text.
6. Ensure the number of outputs exactly matches the number of inputs.
7. Preserve input order.
8. Do not deduplicate.

---

## Few-shot Examples

**Input:**  
Mid, Senior level  

**Output:**  
senior  

---

**Input:**  
Entry level  

**Output:**  
junior  

---

**Input:**  
Internship;Intern;Trainee;Student  

**Output:**  
intern;intern;intern;intern  

---

**Input:**  
Entry level;Entry-Level;Junior;Associate;Early Career  

**Output:**  
junior;junior;junior;junior;junior  

---

**Input:**  
Mid-Senior level;Mid Level;Intermediate;Level II  

**Output:**  
senior;mid;mid;mid  

---

**Input:**  
Senior level;Senior;Experienced;Level III  

**Output:**  
senior;senior;senior;senior  

---

**Input:**  
Lead;Team Lead;Manager;Principal;Staff  

**Output:**  
lead;lead;lead;lead;lead  

---

**Input:**  
Director;Executive;VP;Vice President;C-Level;Founder;Owner  

**Output:**  
executive;executive;executive;executive;executive;executive;executive  

---

**Input:**  
No level specified;Open role;TBD  

**Output:**  
unknown;unknown;unknown  

---

**Input:**  
{seniority_values}  

**Output:**
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
1. The input list is separated ONLY by semicolons (`;`).
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

---

## Priority Rules (Deterministic)
1. If explicit seniority keywords exist, they OVERRIDE years of experience.
2. If multiple seniority keywords exist, choose the highest using this order:  
   **executive > lead > senior > mid > junior > intern**
3. If both keyword and years exist and conflict, use the keyword.
4. If multiple numeric ranges exist, use the highest implied level.
5. If no seniority signal exists but the title is a valid occupation → **not_applicable**
6. If the input is vague, promotional, or not a real job title → **unknown**

---

## Validity Rules
1. Treat recognizable occupations (e.g., "Engineer", "Nurse", "Driver") as valid.
2. Treat vague phrases (e.g., "Open Role", "Various Positions", "Looking for Opportunities") as **unknown**.

---

## Output Rules
1. Output ONLY a semicolon-separated list.
2. Use `;` as delimiter.
3. Do not include spaces before or after semicolons.
4. No trailing semicolon.
5. No explanations.
6. Ensure exactly one output per input.
7. Preserve order.
8. Do not deduplicate.

---

## Few-shot Examples

**Input:**  
Python Developer, Full Time (2 years experience)  

**Output:**  
junior  

---

**Input:**  
Senior Software Engineer, Backend  

**Output:**  
senior  

---

**Input:**  
Python Developer Full Time (2 years experience);Data Analyst 1 yr exp;Software Engineer 0-1 years  

**Output:**  
junior;junior;junior  

---

**Input:**  
Backend Developer (3 years experience);Product Manager 4 yrs;Business Analyst 5 years  

**Output:**  
mid;mid;mid  

---

**Input:**  
Data Scientist 6+ years;Software Engineer with 7 years experience;Financial Analyst 10 yrs  

**Output:**  
senior;senior;senior  

---

**Input:**  
Mid-Level Software Engineer;Intermediate Analyst;Software Engineer II  

**Output:**  
mid;mid;mid  

---

**Input:**  
Software Engineer;Product Manager;Business Analyst;Draftsman (civil/architect)  

**Output:**  
not_applicable;not_applicable;not_applicable;not_applicable  

---

**Input:**  
Draftsman (3 years experience);Civil Draftsman 2 yrs;Architectural Draftsman 6+ years  

**Output:**  
mid;junior;senior  

---

**Input:**  
Senior Software Engineer (2 years experience)  

**Output:**  
senior  

---

**Input:**  
Lead/Senior Engineer  

**Output:**  
lead  

---

**Input:**  
Director of Engineering;VP of Product;Chief Technology Officer  

**Output:**  
executive;executive;executive  

---

**Input:**  
Software Engineer Intern;Marketing Intern  

**Output:**  
intern;intern  

---

**Input:**  
Floorhand;Driver;Warehouse Worker;Operator;Cashier;Word Processor  

**Output:**  
not_applicable;not_applicable;not_applicable;not_applicable;not_applicable;not_applicable  

---

**Input:**  
Open to Work;Looking for Opportunities;Various Roles  

**Output:**  
unknown;unknown;unknown  

---

**Input:**  
{job_titles}  

**Output:**
""",
    "description":
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
1. Extract up to 10 skills (fewer if appropriate).
2. Do NOT include low-value or generic skills unless strongly emphasized.
3. Prioritize:
   - technical skills
   - tools, technologies, frameworks
   - domain-specific expertise
4. Include soft skills ONLY if clearly emphasized multiple times or critical to the role.

---

## Normalization Rules
1. Consolidate similar skills into a single canonical form:
   - "Python programming" → "Python"
   - "AWS cloud" → "AWS"
2. Prefer widely recognized standard names:
   - "Amazon Web Services" → "AWS"
   - "Microsoft Excel" → "Excel"
3. Avoid redundancy or overlap:
   - Do NOT include both "SQL" and "Databases" unless clearly distinct in context

---

## Output Rules
1. Return ONLY a semicolon-separated list.
2. Use `;` as delimiter.
3. Do not add spaces before or after semicolons.
4. Do not include explanations or extra text.
5. Do not include duplicate or overlapping skills.

---

## Example Output
Python;SQL;AWS;Data Analysis;TensorFlow

---

## Job Description
[JOB DESCRIPTION]

Extract and return the skills now.
"""
}

class GroqLLMNormalizer:
    def __init__(self, api_key:str):
        self.client = Groq(api_key=api_key)
        self.model = NormalizationConfig.LLM.value
        self.max_completion_tokens = NormalizationConfig.MAX_TOKEN.value

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

        user_payload = ";".join(inputs)
        last_error: Exception | None = None

        for retry in range(Setting.MAX_RETRIES.value + 1):
            try:
                if retry > 0:
                    sleep_seconds = Setting.FAIL_RETRY_PENALTY.value * retry
                    sleep(sleep_seconds)
                
                # sometime model can give invalid output. Maybe try again
                for llm_retry in range(Setting.MAX_RETRIES.value+1):
                    content = self._call(_PROMPTS[domain], user_payload)
                    parsed = self._parse_semicolon(content)
                    if len(parsed) != len(inputs) and llm_retry<Setting.MAX_RETRIES.value:
                        sleep(NormalizationConfig.LLM_INTERVAL.value)
                        user_payload = \
f"""
The previous output had {len(parsed)} items, but there are {len(inputs)} inputs.

Regenerate the FULL output.
Ensure the number of outputs EXACTLY matches the number of inputs.

Input:
{user_payload}
"""
                    else:
                        break

                if len(parsed) != len(inputs):
                    raise ValueError(
                        f"LLM parse size mismatch for domain={domain}: "
                        f"expected {len(inputs)}, got {len(parsed)}\n"
                        f"raw={inputs!r}\n"
                        f"raw_response={content!r}"
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

                content = self._call(_PROMPTS["description"], description)
                parsed = self._parse_semicolon(content)

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

    def _call(self, system_prompt: str, user_payload: str) -> str:
        completion = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_payload},
            ],
            # avoid random
            temperature=0,
            max_completion_tokens=self.max_completion_tokens,
            top_p=1,
            stream=False,
            stop=None
        )
        return (completion.choices[0].message.content or "").strip()

    @staticmethod
    def _parse_semicolon(text: str) -> list[str]:
        return [part.strip() for part in text.split(";") if part.strip() != ""]

    @staticmethod
    def _clean_text(value: str) -> str:
        return (value or "").replace("\n", " ").replace(";", ",").strip()

    @staticmethod
    def _clean_seniority(value: str) -> str:
        v = (value or "").strip().lower().replace(" ", "_")
        if v in _ALLOWED_SENIORITY:
            return v
        return "unknown"
