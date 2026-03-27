import re

from bs4 import BeautifulSoup
from urllib import parse as url_parse

class LinkedinParser:
    
    @staticmethod
    def _text_or_none(node):
        return node.get_text(" ", strip=True) if node else None

    @staticmethod
    def _attr_or_none(node, attr):
        return node.get(attr) if node and node.has_attr(attr) else None

    @staticmethod
    def _clean_job_posting_url(url:str) -> str:
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
        
    @staticmethod
    def _extract_job_id(url: str):
        match = re.search(r"-(\d+)(?=\?position)", url)
        if match:
            return match.group(1)

        # fallback
        match = re.search(r"-(\d+)", url)
        return match.group(1) if match else None
    
    @staticmethod
    def _clean_html_text(s: str) -> str:
        s = s.replace("\xa0", " ")
        s = re.sub(r"[ \t]+", " ", s)
        return s.strip()
    
    def parse_job_post_page(self, html:str):

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
            result["title"] = self._clean_html_text(title.get_text())
        if company:
            result["company"] = self._clean_html_text(company.get_text())
        if location:
            result["location"] = self._clean_html_text(location.get_text())
        if posted:
            result["posted"] = self._clean_html_text(posted.get_text())
        if applicants:
            result["applicants"] = self._clean_html_text(applicants.get_text())

        # -------- criteria --------
        for item in soup.select(".description__job-criteria-item"):
            k = item.select_one(".description__job-criteria-subheader")
            v = item.select_one(".description__job-criteria-text--criteria")
            if k and v:
                result["criteria"][self._clean_html_text(k.get_text())] = self._clean_html_text(v.get_text())
            
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
            result["sections"] = self._clean_html_text(text)
            
        return result
        
    def parse_job_search_page(self, html:str):
            
        soup = BeautifulSoup(html, "lxml")
        jobs = []

        for card in soup.select("li"):
            title_el = card.select_one("h3")
            company_el = card.select_one("h4")
            location_el = card.select_one(".job-search-card__location")
            link_el = card.select_one("a.base-card__full-link")

            title = self._text_or_none(title_el)
            company = self._text_or_none(company_el)
            location = self._text_or_none(location_el)
            url = self._attr_or_none(link_el, "href")
            
            if url:
                url = self._clean_job_posting_url(url)
                job_id = self._extract_job_id(url)
            else: 
                job_id = None
            
            # skip empty/non-job li blocks
            if not title and not company and not url:
                continue

            jobs.append(
                {
                    "job_id": job_id,
                    "title": title,
                    "company": company,
                    "location": location,
                    "source_url": url
                }
            )

        return jobs    