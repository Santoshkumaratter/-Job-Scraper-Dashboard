"""ZipRecruiter Scraper"""
from typing import List, Dict, Optional
from ..utils.base_scraper import BaseScraper
import urllib.parse
import json
import logging

logger = logging.getLogger(__name__)

class ZipRecruiterScraper(BaseScraper):
    @property
    def portal_name(self) -> str:
        return "ZipRecruiter"
    
    @property
    def base_url(self) -> str:
        return "https://www.ziprecruiter.com"
    
    def build_search_url(self, keyword: str) -> str:
        return f"{self.base_url}/jobs-search?search={urllib.parse.quote(keyword)}"
    
    def scrape_jobs(self) -> List[Dict]:
        jobs = []
        for keyword in self.keywords:
            url = self.build_search_url(keyword)
            html = self.make_request(url)
            if not html:
                continue
            soup = self.parse_html(html)
            job_cards = soup.find_all('article', class_='job_result')
            for card in job_cards:
                try:
                    title_elem = card.find('h2', class_='title')
                    if not title_elem:
                        continue
                    job_link = self.base_url + card.find('a')['href'] if card.find('a') else ''
                    if not job_link:
                        continue
                    
                    company = self.clean_text(card.find('a', class_='company_name').get_text() if card.find('a', class_='company_name') else 'Unknown')
                    posted_date = self.parse_date(card.find('time').get_text() if card.find('time') else '')
                    
                    # Fetch job detail page to get company profile URL and additional info
                    company_profile_url = None
                    company_url = None
                    company_size = 'UNKNOWN'
                    job_description = ''
                    try:
                        detail = self._fetch_job_detail(job_link)
                        if detail:
                            job_description = detail.get('description', '')
                            if detail.get('posted_date') and not posted_date:
                                posted_date = detail['posted_date']
                            if detail.get('company') and not company:
                                company = detail['company']
                            company_url = detail.get('company_url')
                            company_profile_url = detail.get('company_profile_url')
                            if detail.get('company_size'):
                                company_size = detail['company_size']
                    except Exception as e:
                        logger.debug(f"ZipRecruiter: Error fetching job detail for {job_link}: {e}")
                    
                    job_data = {
                        'job_title': self.clean_text(title_elem.get_text()),
                        'company': company,
                        'company_url': company_url,
                        'company_size': company_size,
                        'company_profile_url': company_profile_url,  # Pass for ScraperManager enrichment
                        'market': 'USA',
                        'job_link': job_link,
                        'posted_date': posted_date,
                        'location': self.clean_text(card.find('a', class_='job_location').get_text() if card.find('a', class_='job_location') else ''),
                        'job_description': job_description,
                        'job_type': self.job_type if self.job_type != 'ALL' else 'UNKNOWN',
                    }
                    if self.should_include_job(job_data['posted_date']):
                        jobs.append(job_data)
                except:
                    continue
        return jobs
    
    def _fetch_job_detail(self, job_link: str) -> Dict[str, Optional[str]]:
        """Fetch job detail page to extract company profile URL and additional info"""
        detail: Dict[str, Optional[str]] = {}
        if not job_link:
            return detail
        
        try:
            html = self.make_request(job_link)
            if not html:
                return detail
            
            soup = self.parse_html(html)
            
            # Extract company profile URL using BaseScraper method
            company_profile_url = self._extract_company_profile_url(soup)
            if company_profile_url:
                detail['company_profile_url'] = company_profile_url
            
            # Extract company URL from JSON-LD or HTML
            for script in soup.find_all('script', type='application/ld+json'):
                try:
                    data = json.loads(script.get_text(strip=True) or '{}')
                    if isinstance(data, dict) and data.get('@type') == 'JobPosting':
                        hiring = data.get('hiringOrganization') or data.get('hiringorganization')
                        if isinstance(hiring, dict):
                            company_url = hiring.get('sameAs') or hiring.get('url')
                            if company_url:
                                detail['company_url'] = company_url
                            name = hiring.get('name')
                            if name:
                                detail['company'] = self.clean_text(name)
                        description = data.get('description')
                        if description:
                            detail['description'] = self.clean_text(description)
                        date_posted = data.get('datePosted')
                        if date_posted:
                            parsed = self.parse_date(date_posted)
                            if parsed:
                                detail['posted_date'] = parsed
                        break
                except:
                    continue
        except Exception as e:
            logger.debug(f"ZipRecruiter: Error fetching job detail: {e}")
        
        return detail

