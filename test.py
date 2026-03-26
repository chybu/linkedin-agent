import requests, re

from bs4 import BeautifulSoup
from urllib import parse as url_parse
from time import sleep

def fetch_jobs_html(start=0):
    url = (
        "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
        f"?keywords=&geoId=106420769&f_TPR=&f_PP=&start={start}"
    )

    headers = {
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.5",
        "user-agent": "Mozilla/5.0",
    }

    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()
    return response.text

def fetch_job_page(jobId:str):
    
    url = (
        "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/"
        f"{jobId}"
    )    
    headers = {
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.5",
        "user-agent": "Mozilla/5.0",
    }

    res = requests.get(url, headers=headers, timeout=30)
    res.raise_for_status()
    return res.text

def clean(s: str) -> str:
    s = s.replace("\xa0", " ")
    s = re.sub(r"[ \t]+", " ", s)
    return s.strip()

def get_jd(jobId:str):
    html = fetch_job_page(jobId)
    # with open("test.html", "w", encoding="utf-8") as file:
    #     file.write(html)
    soup = BeautifulSoup(html, "lxml")
    # remove junk
    for tag in soup(["script", "style", "svg", "path", "img", "icon", "button", "form"]):
        tag.decompose()

    result = {
        "title": None,
        "company": None,
        "location": None,
        "posted": None,
        "applicants": None,
        "criteria": {},
        "sections": ""
    }

    # -------- top info --------
    title = soup.select_one(".top-card-layout__title, .topcard__title, h1, h2")
    company = soup.select_one(".topcard__org-name-link")
    location = soup.select_one(".topcard__flavor--bullet")
    posted = soup.select_one(".posted-time-ago__text")
    applicants = soup.select_one(".num-applicants__caption")

    if title:
        result["title"] = clean(title.get_text())
    if company:
        result["company"] = clean(company.get_text())
    if location:
        result["location"] = clean(location.get_text())
    if posted:
        result["posted"] = clean(posted.get_text())
    if applicants:
        result["applicants"] = clean(applicants.get_text())

    # -------- criteria --------
    for item in soup.select(".description__job-criteria-item"):
        k = item.select_one(".description__job-criteria-subheader")
        v = item.select_one(".description__job-criteria-text--criteria")
        if k and v:
            result["criteria"][clean(k.get_text())] = clean(v.get_text())
            
    # -------- full JD --------
    jd = soup.select_one(".show-more-less-html__markup")

    if jd:
        # normalize
        for br in jd.find_all("br"):
            br.replace_with("\n")

        for a in jd.find_all("a"):
            a.unwrap()

        # keep structure via newline
        text = jd.get_text("\n", strip=True)
        result["sections"] = clean(text)
        
    return result
    
def text_or_none(node):
    return node.get_text(" ", strip=True) if node else None

def attr_or_none(node, attr):
    return node.get(attr) if node and node.has_attr(attr) else None

def extract_job_id(url: str):
    match = re.search(r"-(\d+)(?=\?position)", url)
    if match:
        return match.group(1)

    # fallback
    match = re.search(r"-(\d+)", url)
    return match.group(1) if match else None

def clean_link(url:str) -> str:
    parsed = url_parse.urlparse(url)
    query= url_parse.parse_qs(parsed.query, keep_blank_values=True)
    
    keep = {}
    if "position" in query:
        keep["position"] = query["position"][0]
    if "pageNum" in query:
        keep["pageNum"] = query["pageNum"][0]
        
    new_query = url_parse.urlencode(keep, doseq=False)
    
    return url_parse.urlunparse((
        parsed.scheme,
        parsed.netloc,
        parsed.path,
        parsed.params,
        new_query,
        parsed.fragment
    ))

def parse_jobs(html: str):
    
    soup = BeautifulSoup(html, "lxml")
    jobs = []

    for card in soup.select("li"):
        title_el = card.select_one("h3")
        company_el = card.select_one("h4")
        location_el = card.select_one(".job-search-card__location")
        link_el = card.select_one("a.base-card__full-link")

        title = text_or_none(title_el)
        company = text_or_none(company_el)
        location = text_or_none(location_el)
        link = attr_or_none(link_el, "href")
        
        if link:
            link = clean_link(link)
            job_id = extract_job_id(link)
            jd = get_jd(job_id)
        else: 
            job_id = None
            jd = None
        

        # skip empty/non-job li blocks
        if not title and not company and not link:
            continue

        

        jobs.append(
            {
                "title": title,
                "company": company,
                "location": location,
                "link": link,
                "jobId": job_id,
                "jd": jd
            }
        )

    return jobs

if __name__ == "__main__":
    for start in range(0, 10, 10):
        html = fetch_jobs_html(start)
        jobs = parse_jobs(html)

        for i, job in enumerate(jobs, start+1):
            print(f"{i}. {job['title']}")
            print(f"   Company : {job['company']}")
            print(f"   Location: {job['location']}")
            print(f"   Link    : {job['link']}")
            print(f"   JobId   : {job['jobId']}")
            print(f"   JobJD   : {job['jd']}")
        
        sleep(10)
        
