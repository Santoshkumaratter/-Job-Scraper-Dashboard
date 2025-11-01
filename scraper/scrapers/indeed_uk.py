"""
Indeed UK Job Scraper
"""
from typing import List, Dict, Optional
from ..utils.base_scraper import BaseScraper
import urllib.parse
import logging
import json

logger = logging.getLogger(__name__)


class IndeedUKScraper(BaseScraper):
    """Scraper for Indeed UK"""
    
    @property
    def portal_name(self) -> str:
        return "Indeed UK"
    
    @property
    def base_url(self) -> str:
        return "https://uk.indeed.com"
    
    @property
    def requires_selenium(self) -> bool:
        return True  # Indeed blocks regular requests
    
    def build_search_url(self, keyword: str) -> str:
        """Build Indeed UK search URL"""
        params = {
            'q': keyword,
            'l': self.location if self.location != 'ALL' else '',
            'sort': 'date'
        }
        
        if self.job_type == 'REMOTE':
            params['sc'] = '0kf:attr(DSQF7);'
        elif self.job_type == 'FULL_TIME':
            params['jt'] = 'fulltime'
        
        if self.time_filter == '24H':
            params['fromage'] = '1'
        elif self.time_filter == '3D':
            params['fromage'] = '3'
        elif self.time_filter == '7D':
            params['fromage'] = '7'
        
        query_string = urllib.parse.urlencode(params)
        return f"{self.base_url}/jobs?{query_string}"
    
    def scrape_jobs(self) -> List[Dict]:
        """Scrape jobs from Indeed UK"""
        jobs = []
        
        for keyword in self.keywords:
            url = self.build_search_url(keyword)
            html = self.make_request(url, use_selenium=True)  # Use Selenium
            
            if not html:
                logger.warning(f"Failed to fetch page for keyword: {keyword}")
                continue
            
            soup = self.parse_html(html)
            
            # Find job cards
            job_cards = soup.find_all('div', class_='job_seen_beacon')
            
            for card in job_cards:
                try:
                    # Extract job information
                    title_elem = card.find('h2', class_='jobTitle')
                    if not title_elem:
                        continue
                    
                    job_title = self.clean_text(title_elem.get_text())
                    job_link_elem = title_elem.find('a')
                    job_id = job_link_elem.get('data-jk', '') if job_link_elem else ''
                    job_link = f"{self.base_url}/viewjob?jk={job_id}" if job_id else ''
                    
                    # Company name
                    company_elem = card.find('span', class_='companyName')
                    company = self.clean_text(company_elem.get_text()) if company_elem else 'Unknown'
                    
                    # Location
                    location_elem = card.find('div', class_='companyLocation')
                    location = self.clean_text(location_elem.get_text()) if location_elem else ''
                    
                    # Posted date
                    date_elem = card.find('span', class_='date')
                    posted_date = self.parse_date(date_elem.get_text()) if date_elem else None
                    
                    # Check time filter
                    if not self.should_include_job(posted_date):
                        continue
                    
                    # ✅ STRICT KEYWORD CHECK - Must match current keyword
                    if not self.matches_keyword(job_title, keyword):
                        continue
                    
                    detail = self._fetch_job_detail(job_link)
                    description = detail.get('description', '')
                    if detail.get('company'):
                        company = detail['company']
                    if detail.get('company_url'):
                        company_url = detail['company_url']
                    else:
                        company_url = None
                    if detail.get('location'):
                        location = detail['location']
                    if detail.get('posted_date'):
                        posted_date = detail['posted_date']

                    real_job_type = self.detect_job_type(job_title, location, description)
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
                        'market': self._infer_market(location),
                        'job_link': job_link,
                        'posted_date': posted_date,
                        'location': location,
                        'job_description': description,
                        'job_type': real_job_type,
                        'salary_range': detail.get('salary_range', ''),
                    }
                    
                    jobs.append(job_data)
                    
                except Exception as e:
                    logger.error(f"Error parsing job card: {str(e)}")
                    continue
        
        return jobs

    def _infer_market(self, location: str) -> str:
        loc_upper = (location or '').upper()
        if 'UNITED KINGDOM' in loc_upper or 'UK' in loc_upper:
            return 'UK'
        if 'UNITED STATES' in loc_upper or 'USA' in loc_upper:
            return 'USA'
        return 'OTHER'

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

    def _fetch_job_detail(self, job_link: str) -> Dict[str, Optional[str]]:
        detail: Dict[str, Optional[str]] = {}
        if not job_link:
            return detail

        html = self.make_request(job_link, use_selenium=True)
        if not html:
            return detail

        soup = self.parse_html(html)

        desc_elem = soup.find('div', id='jobDescriptionText')
        if desc_elem:
            detail['description'] = self.clean_text(desc_elem.get_text())

        for script in soup.find_all('script', type='application/ld+json'):
            try:
                data = json.loads(script.get_text(strip=True) or '{}')
            except Exception:
                continue
            if not isinstance(data, dict) or data.get('@type') != 'JobPosting':
                continue

            hiring = data.get('hiringOrganization') or data.get('hiringorganization')
            if isinstance(hiring, dict):
                name = hiring.get('name')
                if name:
                    detail['company'] = self.clean_text(name)
                company_url = hiring.get('sameAs') or hiring.get('url')
                if company_url:
                    detail['company_url'] = company_url

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

