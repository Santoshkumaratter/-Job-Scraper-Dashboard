"""Jooble Scraper"""
from typing import List, Dict, Optional
from ..utils.base_scraper import BaseScraper
import json
import logging
from urllib.parse import urljoin

logger = logging.getLogger(__name__)

class JoobleScraper(BaseScraper):
    @property
    def portal_name(self) -> str:
        return "Jooble"
    
    @property
    def base_url(self) -> str:
        return "https://uk.jooble.org"
    
    def build_search_url(self, keyword: str) -> str:
        return f"{self.base_url}/SearchResult?keywords={keyword}"
    
    def scrape_jobs(self) -> List[Dict]:
        jobs = []
        for keyword in self.keywords:
            url = self.build_search_url(keyword)
            html = self.make_request(url)
            if not html:
                continue
            soup = self.parse_html(html)
            # Try multiple selectors to get maximum jobs
            job_cards = soup.find_all('article', class_='vacancy-item') or \
                       soup.find_all('div', class_='job') or \
                       soup.find_all('article', class_='job') or \
                       soup.select('article[class*="job"], article[class*="vacancy"]')
            
            for card in job_cards:
                try:
                    title_elem = card.find('h2') or card.find('h3') or card.find('a', class_=lambda x: x and 'title' in x.lower())
                    if not title_elem:
                        continue
                    
                    job_link = ''
                    link_elem = card.find('a') or title_elem.find('a') if title_elem else None
                    if link_elem and link_elem.get('href'):
                        href = link_elem['href']
                        job_link = urljoin(self.base_url, href) if not href.startswith('http') else href
                    
                    if not job_link:
                        continue
                    
                    # Extract from card
                    company = ''
                    company_elem = card.find('span', class_='company-name') or \
                                  card.find('span', class_='company') or \
                                  card.find('div', class_='company')
                    if company_elem:
                        company = self.clean_text(company_elem.get_text())
                    
                    location = ''
                    location_elem = card.find('span', class_='location') or \
                                   card.find('div', class_='location')
                    if location_elem:
                        location = self.clean_text(location_elem.get_text())
                    
                    posted_date = None
                    date_elem = card.find('time') or card.find('span', class_='date')
                    if date_elem:
                        date_str = date_elem.get('datetime') or date_elem.get_text()
                        posted_date = self.parse_date(date_str)
                    
                    # Fetch job detail page to get real data
                    company_profile_url = None
                    company_url = None
                    company_size = ''
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
                            if detail.get('location') and not location:
                                location = detail['location']
                    except Exception as e:
                        logger.debug(f"Jooble: Error fetching job detail for {job_link}: {e}")
                    
                    # Only add if we have real data
                    if not company or not company.strip():
                        continue
                    
                    job_title = self.clean_text(title_elem.get_text())
                    if not job_title:
                        continue
                    
                    detected_type = self.detect_job_type(job_title, location, job_description)
                    
                    job_data = {
                        'job_title': job_title,
                        'company': company,
                        'company_url': company_url or '',
                        'company_size': company_size or '',
                        'company_profile_url': company_profile_url,  # Pass for ScraperManager enrichment
                        'market': 'UK',
                        'job_link': job_link,
                        'posted_date': posted_date,
                        'location': location or '',
                        'job_description': job_description or '',
                        'job_type': detected_type if detected_type != 'UNKNOWN' else (self.job_type if self.job_type != 'ALL' else ''),
                    }
                    
                    if self.should_include_job(job_data['posted_date']):
                        if self.matches_job_type_filter(detected_type):
                            jobs.append(job_data)
                except Exception as e:
                    logger.debug(f"Jooble: Error parsing job card: {e}")
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
            logger.debug(f"Jooble: Error fetching job detail: {e}")
        
        return detail

