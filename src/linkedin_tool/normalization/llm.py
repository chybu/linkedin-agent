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
Role: You are a geographic data normalization engine.

Task:
Normalize every input location into exactly one standardized location.

Input Parsing Rules:
1. The input list is separated ONLY by semicolons (;).
2. Commas are part of a single location value and must NOT be treated as item separators.
3. Return exactly one output for each semicolon-separated input item.
4. If there is no semicolon, treat the entire input as ONE location.

Format Rules:
1. For every input, output exactly one normalized location.
2. If the location is in the United States, output:
   City, [2-letter state abbreviation]
   Example: San Francisco, CA
3. If the location is outside the United States, output:
   City, Country
   Example: Paris, France
4. For non-US locations, remove state, province, region, county, district, and administrative-area names.
5. Remove zip codes, postal codes, street addresses, building names, floor numbers, suite numbers, and office names.
6. If only a valid city is provided, infer the most commonly recognized location.
7. If the input does not contain a real city or valid recognizable location, output: Unknown
8. Do NOT treat placeholder words like "location", "remote", "various", "multiple locations", "TBD", "N/A", or "not specified" as city names.
9. Preserve input order.
10. Do not deduplicate.

Output Rules:
1. Output ONLY a semicolon-separated list of normalized locations.
2. Use ";" as the delimiter.
3. Do not add spaces before or after semicolons.
4. No trailing semicolon.
5. No preamble, no reasoning, no extra text.

Few-shot examples:

Input:
New York;NYC;New York City;Manhattan NY;10001 New York

Output:
New York, NY;New York, NY;New York, NY;New York, NY;New York, NY

Input:
London;London UK;London England;Greater London

Output:
London, United Kingdom;London, United Kingdom;London, United Kingdom;London, United Kingdom

Input:
Toronto;Toronto ON;Toronto Ontario;Toronto Canada

Output:
Toronto, Canada;Toronto, Canada;Toronto, Canada;Toronto, Canada

Input:
Location, WV

Output:
Unknown

Input:
Location, WV;location wv;Remote;Multiple Locations;TBD;N/A

Output:
Unknown;Unknown;Unknown;Unknown;Unknown;Unknown

Input:
Charleston, WV;Morgantown WV;Buckhannon, West Virginia

Output:
Charleston, WV;Morgantown, WV;Buckhannon, WV

Input:
{locations}

Output:
""",
    "title": 
"""
You are a data cleaning assistant. Your task is to normalize job titles.

Goal:
Map every input job title to the most relevant official SOC Detailed Occupation name.

Input Parsing Rules:
1. The input list is separated ONLY by semicolons (;).
2. Commas are part of a single job title value and must NOT be treated as item separators.
3. Return exactly one output for each semicolon-separated input item.
4. If there is no semicolon, treat the entire input as ONE job title.

Few-shot examples:

Input:
Accountant, Finance Department

Output:
Accountants and Auditors

Input:
Don’t See A Career Match? Submit Your Resume for Future Opportunities!

Output:
Unknown

Rules:
1. Consolidate equivalent titles into the exact same standardized SOC title.
2. Remove seniority indicators such as Senior, Junior, Lead, Principal, Staff, Entry-Level, Intern, I, II, III, Manager, Director, VP, Head, etc., unless they change the occupation itself.
3. Expand common abbreviations.
4. Remove location tags, company names, departments, and employment-type labels.
5. Do NOT deduplicate. Return one normalized output for every input title, in the same order.
6. If the input is NOT a valid job title (e.g., recruiting messages, calls to action, vague phrases, or cannot be mapped to a real occupation), output: Unknown

Output Rules:
1. Output ONLY a semicolon-separated list.
2. Use ";" as the delimiter, NOT commas.
3. Do not add spaces before or after semicolons.
4. No trailing semicolon.
5. No explanation.

Few-shot examples:

Input:
Software Developer;Software Engineer;Sr. Software Engineer;Junior Software Dev;Backend Engineer

Output:
Software Developers;Software Developers;Software Developers;Software Developers;Software Developers

Input:
Data Scientist;Sr Data Scientist;Machine Learning Scientist;Applied Scientist - ML

Output:
Data Scientists;Data Scientists;Data Scientists;Data Scientists

Input:
Registered Nurse;RN;Staff Nurse;ICU Nurse - Boston

Output:
Registered Nurses;Registered Nurses;Registered Nurses;Registered Nurses

Input:
Accountant;Staff Accountant;Senior Accountant;Accounting Analyst

Output:
Accountants and Auditors;Accountants and Auditors;Accountants and Auditors;Accountants and Auditors

Input:
HR Specialist;Human Resources Specialist;People Operations Specialist;Talent Specialist

Output:
Human Resources Specialists;Human Resources Specialists;Human Resources Specialists;Human Resources Specialists

Input:
Marketing Manager;Growth Marketing Manager;Digital Marketing Manager;Sr. Marketing Manager

Output:
Marketing Managers;Marketing Managers;Marketing Managers;Marketing Managers

# Fallback examples (invalid titles)

Input:
Don’t See A Career Match? Submit Your Resume for Future Opportunities!

Output:
Unknown

Input:
Looking for New Opportunities;Open to Work;Actively Seeking Roles

Output:
Unknown;Unknown;Unknown

Input:
Various Roles;Multiple Positions;TBD

Output:
Unknown;Unknown;Unknown

Input:
{job_titles}

Output:
""",
    "seniority_raw": 
"""
Role: You are a data cleaning assistant for seniority normalization.

Task:
Normalize each input seniority value into one of the following EXACT seniority levels:
intern;junior;mid;senior;lead;executive;unknown

Input Parsing Rules:
1. The input list is separated ONLY by semicolons (;).
2. Commas are part of a single seniority value and must NOT be treated as item separators.
3. Return exactly one output for each semicolon-separated input item.
4. If there is no semicolon, treat the entire input as ONE seniority value.

Few-shot examples:

Input:
Mid, Senior level

Output:
senior

Input:
Entry level

Output:
junior

Definitions:
- intern: internships, trainees, students
- junior: entry-level, associate, early career
- mid: mid-level, intermediate, level II
- senior: senior-level, experienced individual contributor
- lead: lead, team lead, staff, principal, manager-level below director
- executive: director level and above, VP, Head, C-level, Founder

Rules:
1. Use ONLY the given seniority value to infer seniority.
2. If clear seniority indicators exist, map accordingly.
3. Do NOT deduplicate. Return one output per input, in the same order.

Output Rules:
1. Output ONLY a semicolon-separated list.
2. Use ";" as the delimiter.
3. Do not add spaces before or after semicolons.
4. No trailing semicolon.
5. No explanation.

Few-shot examples:

Input:
Internship;Intern;Trainee;Student

Output:
intern;intern;intern;intern

Input:
Entry level;Entry-Level;Junior;Associate;Early Career

Output:
junior;junior;junior;junior;junior

Input:
Mid-Senior level;Mid Level;Intermediate;Level II

Output:
senior;mid;mid;mid

Input:
Senior level;Senior;Experienced;Level III

Output:
senior;senior;senior;senior

Input:
Lead;Team Lead;Manager;Principal;Staff

Output:
lead;lead;lead;lead;lead

Input:
Director;Executive;VP;Vice President;C-Level;Founder;Owner

Output:
executive;executive;executive;executive;executive;executive;executive

Input:
{seniority_values}

Output:
""",
    "seniority_title": 
"""
Role: You are a data cleaning assistant for job seniority classification.

Task:
Normalize each input job title into one of the following EXACT seniority levels:
intern;junior;mid;senior;lead;executive;not_applicable;unknown

Input Parsing Rules:
1. The input list is separated ONLY by semicolons (;).
2. Commas are part of a single seniority value and must NOT be treated as item separators.
3. Return exactly one output for each semicolon-separated input item.
4. If there is no semicolon, treat the entire input as ONE seniority value.

Few-shot example:

Input:
Python Developer, Full Time (2 years experience)

Output:
junior

Input:
Senior Software Engineer, Backend

Output:
senior

Definitions:
- intern: internships, trainees, students
- junior: entry-level, associate, early-career roles, or explicitly stated 0-2 years of experience
- mid: explicitly mid-level roles or explicitly stated 3-5 years of experience
- senior: senior-level roles or explicitly stated 6+ years of experience
- lead: lead, team lead, staff, principal, or manager-level roles below director
- executive: director, head, VP, C-level, founder
- not_applicable: valid roles where seniority is not explicitly stated and no explicit numeric experience signal is provided
- unknown: not a valid job title, vague, promotional, or cannot be classified

Rules:
1. Use ONLY the job title text to infer seniority.
2. If clear seniority indicators exist, map accordingly.
3. Explicit seniority indicators take priority over years of experience.
4. ONLY use years of experience if an explicit numeric value is present in the text, such as "2 years", "3+ yrs", "5-7 years", or "10 years experience".
   - 0-2 years → junior
   - 3-5 years → mid
   - 6+ years → senior
5. Do NOT infer experience if it is not explicitly stated.
6. If the job title is valid but has no clear seniority indicator and no explicit numeric experience signal, output: not_applicable
7. If the input is not a valid job title or is too vague, output: unknown
8. Do NOT deduplicate. Preserve order.
9. Always output exactly one label per input.

Output Rules:
1. Output ONLY a semicolon-separated list.
2. Use ";" as the delimiter.
3. Do not add spaces before or after semicolons.
4. No trailing semicolon.
5. No explanation.

Few-shot examples:

Input:
Python Developer Full Time (2 years experience);Data Analyst 1 yr exp;Software Engineer 0-1 years

Output:
junior;junior;junior

Input:
Backend Developer (3 years experience);Product Manager 4 yrs;Business Analyst 5 years

Output:
mid;mid;mid

Input:
Data Scientist 6+ years;Software Engineer with 7 years experience;Financial Analyst 10 yrs

Output:
senior;senior;senior

Input:
Mid-Level Software Engineer;Intermediate Analyst;Software Engineer II

Output:
mid;mid;mid

Input:
Software Engineer;Product Manager;Business Analyst;Draftsman (civil/architect)

Output:
not_applicable;not_applicable;not_applicable;not_applicable

Input:
Draftsman (3 years experience);Civil Draftsman 2 yrs;Architectural Draftsman 6+ years

Output:
mid;junior;senior

Input:
Senior Software Engineer;Sr Data Scientist;Senior Analyst

Output:
senior;senior;senior

Input:
Lead Engineer;Staff Software Engineer;Principal Engineer

Output:
lead;lead;lead

Input:
Director of Engineering;VP of Product;Chief Technology Officer

Output:
executive;executive;executive

Input:
Junior Developer;Associate Analyst;Entry Level Accountant

Output:
junior;junior;junior

Input:
Software Engineer Intern;Marketing Intern

Output:
intern;intern

Input:
Floorhand;Driver;Warehouse Worker;Operator;Cashier;Word Processor

Output:
not_applicable;not_applicable;not_applicable;not_applicable;not_applicable;not_applicable

Input:
Registered Nurse;RN;Infection Preventionist

Output:
not_applicable;not_applicable;not_applicable

Input:
Open to Work;Looking for Opportunities;Various Roles

Output:
unknown;unknown;unknown

Input:
{job_titles}

Output:
"""
}

class GroqLLMNormalizer:
    def __init__(self):
        api_key = NormalizationConfig.GROQ_API_KEY.value
        self.client = Groq(api_key=api_key) if api_key else Groq()
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

        user_payload = ";".join(inputs)
        last_error: Exception | None = None

        for retry in range(Setting.MAX_RETRIES.value + 1):
            try:
                if retry > 0:
                    sleep_seconds = Setting.FAIL_RETRY_PENALTY.value * retry
                    sleep(sleep_seconds)

                content = self._call(_PROMPTS[domain], user_payload)
                parsed = self._parse_semicolon(content)

                if len(parsed) != len(inputs):
                    raise ValueError(
                        f"LLM parse size mismatch for domain={domain}: "
                        f"expected {len(inputs)}, got {len(parsed)}; raw={content!r}"
                        f"raw_response={content!r}"
                    )

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