"""Grabjobs Scraper"""
from typing import List, Dict, Optional
from urllib.parse import quote_plus, urljoin
from ..utils.base_scraper import BaseScraper
import logging
import json

logger = logging.getLogger(__name__)

class GrabJobsScraper(BaseScraper):
    @property
    def portal_name(self) -> str:
        return "Grabjobs"
    
    @property
    def base_url(self) -> str:
        return "https://www.grabjobs.co"
    
    def build_search_url(self, keyword: str) -> str:
        encoded_keyword = quote_plus(keyword)
        return f"{self.base_url}/jobs?q={encoded_keyword}"
    
    def _extract_company(self, card) -> str:
        """Extract company name from job card"""
        selectors = [
            '.company', '.company-name', '[class*="company"]',
            'span.company', 'div.company', 'a.company',
            '.employer', '.employer-name', '[data-company]'
        ]
        for selector in selectors:
            elem = card.select_one(selector)
            if elem:
                company = self.clean_text(elem.get_text())
                if company:
                    return company
        return ''
    
    def _extract_location(self, card) -> str:
        """Extract location from job card"""
        selectors = [
            '.location', '.job-location', '[class*="location"]',
            'span.location', 'div.location', '.city', '.place',
            '.address', '.where', '[data-location]'
        ]
        for selector in selectors:
            elem = card.select_one(selector)
            if elem:
                location = self.clean_text(elem.get_text())
                if location:
                    return location
        return ''
    
    def _extract_posted_date(self, card) -> Optional:
        """Extract posted date from job card"""
        selectors = [
            '.date', '.posted-date', '[class*="date"]',
            'time', '[datetime]', '.time-ago', '.posted',
            '.published', '.publish-date', '[data-date]'
        ]
        for selector in selectors:
            elem = card.select_one(selector)
            if elem:
                date_str = elem.get('datetime') or elem.get('data-date') or elem.get_text()
                if date_str:
                    parsed = self.parse_date(date_str)
                    if parsed:
                        return parsed
        return None
    
    def _extract_description(self, card) -> str:
        """Extract job description from card"""
        selectors = [
            '.description', '.job-description', '[class*="description"]',
            '.summary', '.snippet', '.excerpt', 'p'
        ]
        for selector in selectors:
            elem = card.select_one(selector)
            if elem:
                desc = self.clean_text(elem.get_text())
                if desc and len(desc) > 20:
                    return desc[:500]
        return ''
    
    def scrape_jobs(self) -> List[Dict]:
        jobs = []
        for keyword in self.keywords:
            url = self.build_search_url(keyword)
            # Try Selenium first as site often blocks regular requests with 403
            html = self.make_request(url, use_selenium=True)
            if not html:
                logger.warning(f"Grabjobs: Failed to fetch {url} - may be blocked or inaccessible")
                continue
            soup = self.parse_html(html)
            
            # Try multiple selectors for job cards
            job_cards = soup.find_all('div', class_='job-card') or \
                       soup.find_all('article', class_='job') or \
                       soup.find_all('div', class_='job-item') or \
                       soup.select('div[class*="job"], article[class*="job"]')
            
            for card in job_cards:
                try:
                    # Extract job title
                    title_elem = card.find('h2') or card.find('h3') or card.find('a', class_=lambda x: x and 'title' in x.lower())
                    if not title_elem:
                        continue
                    job_title = self.clean_text(title_elem.get_text())
                    
                    # Check keyword match
                    if self.keywords and not any(kw.lower() in job_title.lower() for kw in self.keywords):
                        continue
                    
                    # Extract job link
                    link_elem = card.find('a') or title_elem.find('a') if title_elem else None
                    job_link = ''
                    if link_elem and link_elem.get('href'):
                        href = link_elem['href']
                        job_link = urljoin(self.base_url, href) if not href.startswith('http') else href
                    
                    if not job_link:
                        continue
                    
                    # Extract real data
                    company = self._extract_company(card)
                    location = self._extract_location(card)
                    posted_date = self._extract_posted_date(card)
                    job_description = self._extract_description(card)
                    
                    # Check time filter
                    if not self.should_include_job(posted_date):
                        continue
                    
                    # Detect job type from content
                    detected_type = self.detect_job_type(job_title, location, job_description)
                    if not self.matches_job_type_filter(detected_type):
                        continue
                    
                    # Fetch job detail page to get company profile URL and additional info
                    company_profile_url = None
                    company_url = None
                    company_size = 'UNKNOWN'
                    try:
                        detail = self._fetch_job_detail(job_link)
                        if detail:
                            if detail.get('description') and not job_description:
                                job_description = detail['description']
                            if detail.get('posted_date') and not posted_date:
                                posted_date = detail['posted_date']
                            if detail.get('company') and not company:
                                company = detail['company']
                            company_url = detail.get('company_url')
                            company_profile_url = detail.get('company_profile_url')
                            if detail.get('company_size'):
                                company_size = detail['company_size']
                    except Exception as e:
                        logger.debug(f"Grabjobs: Error fetching job detail for {job_link}: {e}")
                    
                    # Infer market from location
                    market = self._infer_market(location)
                    
                    job_data = {
                        'job_title': job_title,
                        'company': company if company else '',
                        'company_url': company_url,
                        'company_size': company_size,
                        'company_profile_url': company_profile_url,  # Pass for ScraperManager enrichment
                        'market': market,
                        'job_link': job_link,
                        'posted_date': posted_date,
                        'location': location if location else '',
                        'job_description': job_description if job_description else '',
                        'job_type': detected_type,
                    }
                    
                    # Only add if we have at least title and company
                    if job_data['job_title'] and job_data['company']:
                        jobs.append(job_data)
                        
                except Exception as e:
                    logger.debug(f"Grabjobs: Error parsing job card: {e}")
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
            logger.debug(f"Grabjobs: Error fetching job detail: {e}")
        
        return detail
    
    def _infer_market(self, location: str) -> str:
        """Infer market from location"""
        if not location:
            return 'OTHER'
        location_upper = location.upper()
        if 'UK' in location_upper or 'UNITED KINGDOM' in location_upper or 'LONDON' in location_upper:
            return 'UK'
        elif 'USA' in location_upper or 'UNITED STATES' in location_upper or any(state in location_upper for state in ['NY', 'CA', 'TX', 'FL']):
            return 'USA'
        return 'OTHER'

