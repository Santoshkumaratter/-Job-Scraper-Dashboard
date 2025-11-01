"""Dice Scraper"""
from typing import List, Dict, Optional
from ..utils.base_scraper import BaseScraper
import json

class DiceScraper(BaseScraper):
    @property
    def portal_name(self) -> str:
        return "Dice"
    
    @property
    def base_url(self) -> str:
        return "https://www.dice.com"
    
    @property
    def requires_selenium(self) -> bool:
        return True
    
    def build_search_url(self, keyword: str) -> str:
        return f"{self.base_url}/jobs?q={keyword}"
    
    def scrape_jobs(self) -> List[Dict]:
        jobs = []
        for keyword in self.keywords:
            url = self.build_search_url(keyword)
            html = self.make_request(url, use_selenium=True)
            if not html:
                continue
            soup = self.parse_html(html)
            job_cards = soup.find_all('div', class_='card')
            for card in job_cards:
                try:
                    title_elem = card.find('h5')
                    if not title_elem:
                        continue
                    
                    job_title = self.clean_text(title_elem.get_text())
                    
                    # ✅ STRICT KEYWORD MATCHING
                    if not self.matches_keyword(job_title, keyword):
                        continue
                    
                    company = self.clean_text(card.find('a', class_='companyName').get_text() if card.find('a', class_='companyName') else '')
                    company_url = None
                    
                    posted_text = card.find('span', class_='posted').get_text() if card.find('span', class_='posted') else ''
                    posted_date = self.parse_date(posted_text)
                    location_text = self.clean_text(card.find('span', class_='location').get_text() if card.find('span', class_='location') else '')

                    job_link = self.base_url + card.find('a', class_='card-title-link')['href'] if card.find('a', class_='card-title-link') else ''

                    detail = self._fetch_job_detail(job_link)
                    description = detail.get('description', '')
                    if detail.get('company'):
                        company = detail['company']
                    if detail.get('company_url'):
                        company_url = detail['company_url']
                    if detail.get('posted_date'):
                        posted_date = detail['posted_date']
                    if detail.get('location'):
                        location_text = detail['location']

                    real_job_type = self.detect_job_type(job_title, location_text, description)
                    if real_job_type == 'UNKNOWN':
                        mapped = self._map_employment(detail.get('employment_type'), detail.get('workplace_type'))
                        if mapped:
                            real_job_type = mapped

                    if not self.matches_job_type_filter(real_job_type):
                        continue

                    if not company:
                        continue

                    job_data = {
                        'job_title': job_title,
                        'company': company,
                        'company_url': company_url,
                        'company_size': detail.get('company_size', 'UNKNOWN'),
                        'market': detail.get('market', 'USA'),
                        'job_link': job_link,
                        'posted_date': posted_date,
                        'location': location_text,
                        'job_description': description,
                        'job_type': real_job_type,
                        'salary_range': detail.get('salary_range', ''),
                    }
                    
                    if self.should_include_job(posted_date):
                        jobs.append(job_data)
                except:
                    continue
        return jobs

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
            'CONTRACTOR': 'FREELANCE',
            'TEMPORARY': 'FREELANCE',
        }
        return mapping.get(employment_upper)

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
                    loc = ', '.join([self.clean_text(p) for p in parts if p])
                    if loc:
                        detail['location'] = loc
                        detail['market'] = 'USA' if 'UNITED STATES' in loc.upper() or 'USA' in loc.upper() else 'OTHER'

            employment = data.get('employmentType')
            if isinstance(employment, list):
                employment = employment[0] if employment else None
            detail['employment_type'] = employment

            workplace = data.get('jobLocationType') or data.get('workplaceType')
            if isinstance(workplace, list):
                workplace = workplace[0]
            detail['workplace_type'] = workplace

            salary = data.get('baseSalary')
            if isinstance(salary, dict):
                value = salary.get('value', {})
                min_value = value.get('minValue')
                max_value = value.get('maxValue')
                unit = value.get('unitText')
                if min_value and max_value:
                    detail['salary_range'] = f"{min_value}-{max_value}{' ' + unit if unit else ''}"

            break

        return detail

