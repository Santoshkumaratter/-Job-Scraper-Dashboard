"""
LinkedIn Jobs Scraper
"""
from typing import List, Dict, Optional
from ..utils.base_scraper import BaseScraper
import urllib.parse
import json


class LinkedInJobsScraper(BaseScraper):
    """Scraper for LinkedIn Jobs"""
    
    @property
    def portal_name(self) -> str:
        return "Linkedin Jobs"
    
    @property
    def base_url(self) -> str:
        return "https://www.linkedin.com"
    
    @property
    def requires_selenium(self) -> bool:
        return True
    
    def build_search_url(self, keyword: str) -> str:
        """Build LinkedIn Jobs search URL"""
        params = {
            'keywords': keyword,
            'location': self.location if self.location != 'ALL' else '',
            'sortBy': 'DD'  # Date descending
        }
        
        if self.job_type == 'REMOTE':
            params['f_WT'] = '2'  # Remote
        elif self.job_type == 'HYBRID':
            params['f_WT'] = '3'  # Hybrid
        
        if self.time_filter == '24H':
            params['f_TPR'] = 'r86400'
        elif self.time_filter == '3D':
            params['f_TPR'] = 'r259200'
        elif self.time_filter == '7D':
            params['f_TPR'] = 'r604800'
        
        query_string = urllib.parse.urlencode(params)
        return f"{self.base_url}/jobs/search/?{query_string}"
    
    def scrape_jobs(self) -> List[Dict]:
        """Scrape jobs from LinkedIn with detail enrichment"""
        jobs: List[Dict] = []

        for keyword in self.keywords:
            url = self.build_search_url(keyword)
            html = self.make_request(url, use_selenium=True)
            if not html:
                continue

            soup = self.parse_html(html)
            job_cards = soup.find_all('div', class_='base-card')

            for card in job_cards:
                try:
                    title_elem = card.find('h3', class_='base-search-card__title')
                    if not title_elem:
                        continue
                    job_title = self.clean_text(title_elem.get_text())

                    link_elem = card.find('a', class_='base-card__full-link')
                    job_link = link_elem.get('href', '') if link_elem else ''
                    if not job_link:
                        continue

                    company_elem = card.find('h4', class_='base-search-card__subtitle')
                    company = self.clean_text(company_elem.get_text()) if company_elem else ''

                    location_elem = card.find('span', class_='job-search-card__location')
                    location = self.clean_text(location_elem.get_text()) if location_elem else ''

                    date_elem = card.find('time')
                    posted_date = self.parse_date(date_elem.get('datetime', '')) if date_elem else None

                    # Enforce keyword filter strictly
                    if not self.matches_keyword(job_title, keyword):
                        continue

                    company_url = None
                    if company_elem:
                        company_link = company_elem.find('a')
                        if company_link and company_link.has_attr('href'):
                            company_url = urllib.parse.urljoin(self.base_url, company_link['href'])

                    detail = self._fetch_job_detail(job_link)
                    description = detail.get('description', '')

                    if detail.get('company'):
                        company = detail['company']
                    if detail.get('company_url'):
                        company_url = detail['company_url']
                    if detail.get('location'):
                        location = detail['location']
                    if detail.get('posted_date'):
                        posted_date = detail['posted_date']

                    detected_type = self.detect_job_type(job_title, location, description)
                    if detected_type == 'UNKNOWN':
                        mapped = self._map_employment_to_job_type(
                            detail.get('employment_type'), detail.get('workplace_type')
                        )
                        if mapped:
                            detected_type = mapped

                    if not self.matches_job_type_filter(detected_type):
                        continue

                    job_data = {
                        'job_title': job_title,
                        'company': company or detail.get('company', ''),
                        'company_url': company_url,
                        'company_size': 'UNKNOWN',
                        'market': self._infer_market(location),
                        'job_link': job_link,
                        'posted_date': posted_date,
                        'location': location,
                        'job_description': description,
                        'job_type': detected_type,
                        'salary_range': detail.get('salary_range', ''),
                    }

                    if not job_data['company']:
                        continue

                    jobs.append(job_data)

                except Exception:
                    continue

        return jobs

    def _infer_market(self, location: str) -> str:
        location_upper = (location or '').upper()
        if 'UNITED STATES' in location_upper or 'USA' in location_upper:
            return 'USA'
        if 'UNITED KINGDOM' in location_upper or 'UK' in location_upper:
            return 'UK'
        return 'OTHER'

    def _fetch_job_detail(self, job_link: str) -> Dict[str, Optional[str]]:
        detail: Dict[str, Optional[str]] = {}
        if not job_link:
            return detail

        html = self.make_request(job_link, use_selenium=True)
        if not html:
            return detail

        soup = self.parse_html(html)

        for script in soup.find_all('script', type='application/ld+json'):
            try:
                data = json.loads(script.get_text(strip=True) or '{}')
            except Exception:
                continue

            if not isinstance(data, dict) or data.get('@type') != 'JobPosting':
                continue

            description = data.get('description')
            if description:
                detail['description'] = self.clean_text(description)

            date_posted = data.get('datePosted') or data.get('dateposted')
            if date_posted:
                parsed = self.parse_date(date_posted)
                if parsed:
                    detail['posted_date'] = parsed

            employment = data.get('employmentType')
            if isinstance(employment, list):
                employment = employment[0] if employment else None
            detail['employment_type'] = employment

            workplace = data.get('jobLocationType') or data.get('workplaceType')
            if isinstance(workplace, list):
                workplace = workplace[0]
            detail['workplace_type'] = workplace

            hiring = data.get('hiringOrganization') or data.get('hiringorganization')
            if isinstance(hiring, dict):
                name = hiring.get('name')
                if name:
                    detail['company'] = self.clean_text(name)
                company_url = hiring.get('sameAs') or hiring.get('url')
                if company_url:
                    detail['company_url'] = company_url

            job_location = data.get('jobLocation')
            if isinstance(job_location, list):
                job_location = job_location[0] if job_location else None
            if isinstance(job_location, dict):
                address = job_location.get('address')
                if isinstance(address, dict):
                    parts = [address.get('addressLocality'), address.get('addressRegion'), address.get('addressCountry')]
                    location = ', '.join([self.clean_text(p) for p in parts if p])
                    if location:
                        detail['location'] = location

            salary = data.get('baseSalary')
            if isinstance(salary, dict):
                value = salary.get('value', {})
                min_value = value.get('minValue')
                max_value = value.get('maxValue')
                unit = value.get('unitText')
                if min_value and max_value:
                    unit_text = f" {unit}" if unit else ''
                    detail['salary_range'] = f"{min_value}-{max_value}{unit_text}"

            break

        return detail

    def _map_employment_to_job_type(self, employment: Optional[str], workplace: Optional[str]) -> Optional[str]:
        employment_upper = (employment or '').upper()
        workplace_upper = (workplace or '').upper()

        if workplace_upper in {'TELECOMMUTE', 'REMOTE'}:
            return 'REMOTE'
        if workplace_upper == 'HYBRID':
            return 'HYBRID'

        mapping = {
            'FULL_TIME': 'FULL_TIME',
            'PART_TIME': 'PART_TIME',
            'CONTRACT': 'FREELANCE',
            'CONTRACTOR': 'FREELANCE',
            'TEMPORARY': 'FREELANCE',
            'FREELANCE': 'FREELANCE',
        }
        return mapping.get(employment_upper)

