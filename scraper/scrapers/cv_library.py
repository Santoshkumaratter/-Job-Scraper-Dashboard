"""CV-Library Job Scraper"""
from typing import List, Dict, Optional
from ..utils.base_scraper import BaseScraper
import urllib.parse
import logging
import json

logger = logging.getLogger(__name__)


class CVLibraryScraper(BaseScraper):
    @property
    def portal_name(self) -> str:
        return "CV-Library"
    
    @property
    def base_url(self) -> str:
        return "https://www.cv-library.co.uk"
    
    @property
    def requires_selenium(self) -> bool:
        return True  # CV-Library heavily rate-limits HTTP requests
    
    def build_search_url(self, keyword: str) -> str:
        params = {
            'q': keyword,
            'geo': '' if self.location == 'ALL' else self.location,
            'posted': self._map_time_filter(),
        }
        return f"{self.base_url}/search-jobs?{urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})}"
    
    def _map_time_filter(self) -> str:
        mapping = {
            '24H': '1',
            '3D': '3',
            '7D': '7',
        }
        return mapping.get(self.time_filter, '')
    
    def scrape_jobs(self) -> List[Dict]:
        jobs: List[Dict] = []
        for keyword in self.keywords:
            url = self.build_search_url(keyword)
            html = self.make_request(url, use_selenium=True)
            if not html:
                logger.warning(f"CV-Library: no HTML returned for keyword '{keyword}'")
                continue
            soup = self.parse_html(html)
            job_cards = soup.find_all('article', class_='job') or soup.select('div.job')
            for card in job_cards:
                try:
                    title_elem = card.find('h2') or card.select_one('a.job__title')
                    if not title_elem:
                        continue
                    job_title = self.clean_text(title_elem.get_text())
                    if not self.matches_keyword(job_title, keyword):
                        continue

                    link_elem = title_elem.find('a') if title_elem else None
                    job_href = link_elem['href'] if link_elem and link_elem.has_attr('href') else None
                    if job_href and not job_href.startswith('http'):
                        job_link = urllib.parse.urljoin(self.base_url, job_href)
                    else:
                        job_link = job_href or ''
                    if not job_link:
                        continue

                    company_raw = self._extract_company(card)
                    company = company_raw or ''

                    location = self._extract_location(card)
                    posted_date = self._extract_posted_date(card)

                    detail = self._fetch_job_detail(job_link)
                    if detail.get('company'):
                        company = detail['company']
                    if detail.get('location'):
                        location = detail['location']
                    if detail.get('posted_date'):
                        posted_date = detail['posted_date']

                    if not self.should_include_job(posted_date):
                        continue

                    job_description = detail.get('job_description', '')

                    company_token = ''.join(ch for ch in company if ch.isalnum())
                    if not company_token or len(company_token) < 2:
                        continue

                    detected_type = self.detect_job_type(job_title, location, job_description)
                    if detected_type == 'UNKNOWN':
                        mapped = self._map_employment(detail.get('employment_type'), detail.get('workplace_type'))
                        if mapped:
                            detected_type = mapped

                    if not self.matches_job_type_filter(detected_type):
                        continue

                    jobs.append({
                        'job_title': job_title,
                        'company': company,
                        'company_url': detail.get('company_url'),
                        'company_size': detail.get('company_size', 'UNKNOWN'),
                        'market': self._infer_market(location),
                        'job_link': job_link,
                        'posted_date': posted_date,
                        'location': location or 'Unknown',
                        'job_description': job_description,
                        'job_type': detected_type,
                        'salary_range': detail.get('salary_range', ''),
                    })
                except Exception as exc:
                    logger.debug(f"CV-Library: failed to parse job card: {exc}")
                    continue
        return jobs

    def _extract_company(self, card) -> str:
        selectors = [
            '[data-testid="job-card-company-name"]',
            'span.company',
            'span.job__company',
            '.job__details__company',
        ]
        for selector in selectors:
            elem = card.select_one(selector)
            if elem:
                company = self.clean_text(elem.get_text())
                if company:
                    return company
        return ''

    def _extract_location(self, card) -> str:
        selectors = [
            '[data-testid="job-card-location"]',
            'span.location',
            '.job__details__location',
            '.job__meta__location',
        ]
        for selector in selectors:
            elem = card.select_one(selector)
            if elem:
                location = self.clean_text(elem.get_text())
                if location:
                    return location
        return ''

    def _extract_posted_date(self, card):
        time_elem = card.find('time') or card.select_one('time')
        if time_elem:
            if time_elem.has_attr('datetime'):
                raw = time_elem['datetime']
                if 'T' in raw:
                    raw = raw.split('T')[0]
                parsed = self.parse_date(raw)
                if parsed:
                    return parsed
            text = self.clean_text(time_elem.get_text())
            parsed = self.parse_date(text)
            if parsed:
                return parsed
        date_candidates = [
            card.select_one('[data-testid="job-card-date"]'),
            card.select_one('.job__details__date'),
            card.select_one('.job__meta__date'),
        ]
        for elem in date_candidates:
            if elem:
                parsed = self.parse_date(self.clean_text(elem.get_text()))
                if parsed:
                    return parsed
        return None

    def _fetch_job_detail(self, job_link: str) -> Dict[str, Optional[str]]:
        detail: Dict[str, Optional[str]] = {}
        if not job_link:
            return detail

        html = self.make_request(job_link, use_selenium=True)
        if not html:
            return detail

        soup = self.parse_html(html)

        company_selectors = [
            '[data-testid="job-company-name"]',
            '.job-header__company-name',
            '.job-header__company a',
            '.job-header__company',
            '.company span',
        ]
        for selector in company_selectors:
            elem = soup.select_one(selector)
            if elem:
                name = self.clean_text(elem.get_text())
                if name and name.lower() not in {'cv-library', 'company', 'employer', 'unknown'}:
                    detail['company'] = name
                    break

        for script in soup.find_all('script', type='application/ld+json'):
            try:
                data = json.loads(script.get_text(strip=True) or '{}')
            except Exception:
                continue
            if isinstance(data, dict):
                hiring = data.get('hiringOrganization') or data.get('hiringorganization')
                if isinstance(hiring, dict):
                    name = hiring.get('name')
                    if name and 'company' not in detail:
                        name_clean = self.clean_text(name)
                        if name_clean and name_clean.lower() not in {'cv-library', 'company', 'employer', 'unknown'}:
                            detail['company'] = name_clean
                    company_url = hiring.get('sameAs') or hiring.get('url')
                    if company_url:
                        detail['company_url'] = company_url
                date_posted = data.get('datePosted') or data.get('dateposted')
                if date_posted and 'posted_date' not in detail:
                    parsed = self.parse_date(date_posted)
                    if parsed:
                        detail['posted_date'] = parsed
                description = data.get('description')
                if description and 'job_description' not in detail:
                    detail['job_description'] = self.clean_text(description)

                employment = data.get('employmentType')
                if isinstance(employment, list):
                    employment = employment[0] if employment else None
                detail['employment_type'] = employment

                workplace = data.get('jobLocationType') or data.get('workplaceType')
                if isinstance(workplace, list):
                    workplace = workplace[0]
                detail['workplace_type'] = workplace

        if 'location' not in detail:
            loc_elem = soup.select_one('[data-testid="job-location"]') or soup.select_one('.job-header__location')
            if loc_elem:
                detail['location'] = self.clean_text(loc_elem.get_text())

        if 'salary_range' not in detail:
            salary_elem = soup.select_one('.job-header__salary') or soup.select_one('[data-testid="job-salary"]')
            if salary_elem:
                detail['salary_range'] = self.clean_text(salary_elem.get_text())

        return detail

    def _map_employment(self, employment: Optional[str], workplace: Optional[str]) -> Optional[str]:
        employment_upper = (employment or '').upper()
        workplace_upper = (workplace or '').upper()

        if workplace_upper in {'REMOTE', 'TELECOMMUTE'}:
            return 'REMOTE'
        if workplace_upper == 'HYBRID':
            return 'HYBRID'

        mapping = {
            'FULLTIME': 'FULL_TIME',
            'FULL-TIME': 'FULL_TIME',
            'PARTTIME': 'PART_TIME',
            'PART-TIME': 'PART_TIME',
            'CONTRACT': 'FREELANCE',
            'TEMPORARY': 'FREELANCE',
        }
        return mapping.get(employment_upper)

    def _infer_market(self, location: str) -> str:
        loc_upper = (location or '').upper()
        if 'UNITED KINGDOM' in loc_upper or 'UK' in loc_upper:
            return 'UK'
        if 'UNITED STATES' in loc_upper or 'USA' in loc_upper:
            return 'USA'
        return 'OTHER'

