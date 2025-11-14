"""CareerBuilder Scraper - MULTI-APPROACH: Tries multiple methods to fetch maximum jobs"""
from typing import List, Dict, Optional
from ..utils.base_scraper import BaseScraper
from ..utils.multi_approach_scraper import MultiApproachExtractor
import urllib.parse
import json
import logging
import re

logger = logging.getLogger(__name__)

class CareerBuilderScraper(BaseScraper):
    @property
    def portal_name(self) -> str:
        return "CareerBuilder"
    
    @property
    def base_url(self) -> str:
        return "https://www.careerbuilder.com"
    
    @property
    def requires_selenium(self) -> bool:
        return True
    
    def build_search_url(self, keyword: str) -> str:
        return f"{self.base_url}/jobs?keywords={urllib.parse.quote(keyword)}"
    
    def scrape_jobs(self) -> List[Dict]:
        jobs = []
        for keyword in self.keywords:
            url = self.build_search_url(keyword)
            html = self.make_request(url, use_selenium=True)
            if not html:
                continue
            soup = self.parse_html(html)
            # Try multiple selectors to get maximum jobs
            job_cards = []
            selectors_to_try = [
                ('div', {'data-testid': 'job-result-item'}),
                ('div', {'class': 'job-result-item'}),
                ('div', {'class': 'job'}),
                ('article', {'class': 'job'}),
                ('li', {'class': 'job'}),
                ('div', {'class': lambda x: x and 'job' in ' '.join(x).lower()}),
                ('article', {'class': lambda x: x and 'job' in ' '.join(x).lower()}),
            ]
            
            for tag, attrs in selectors_to_try:
                found = soup.find_all(tag, attrs)
                if found:
                    job_cards.extend(found)
                    logger.debug(f"CareerBuilder: Found {len(found)} cards with {tag} {attrs}")
            
            # Also try CSS selectors
            if not job_cards:
                css_selectors = [
                    'div[data-testid*="job"]',
                    'div[class*="job"]',
                    'article[class*="job"]',
                    'li[class*="job"]',
                    '[data-job-id]',
                    '[data-job]',
                ]
                for selector in css_selectors:
                    found = soup.select(selector)
                    if found:
                        job_cards.extend(found)
                        logger.debug(f"CareerBuilder: Found {len(found)} cards with CSS selector {selector}")
            
            # Try finding any links that look like job links
            if not job_cards:
                job_links = soup.find_all('a', href=re.compile(r'/job|/position|/career|/vacancy', re.I))
                for link in job_links:
                    parent = link.find_parent(['div', 'article', 'li'])
                    if parent and parent not in job_cards:
                        job_cards.append(parent)
                        logger.debug(f"CareerBuilder: Found job card from link {link.get('href', '')[:50]}")
            
            # APPROACH 4-7: If no cards found, use MultiApproachExtractor as fallback
            if not job_cards:
                logger.info(f"CareerBuilder: Standard selectors failed, trying MultiApproachExtractor...")
                job_cards = MultiApproachExtractor.extract_jobs_from_soup(soup, self.base_url, self.keywords)
            
            if not job_cards:
                logger.warning(f"CareerBuilder: No job cards found for '{keyword}' after trying all approaches.")
                all_divs = soup.find_all('div', limit=10)
                logger.debug(f"CareerBuilder: Sample div classes: {[d.get('class') for d in all_divs[:5]]}")
                continue
            
            logger.info(f"CareerBuilder: Found {len(job_cards)} job cards for '{keyword}'")
            
            for card in job_cards:
                try:
                    title_elem = card.find('h2')
                    if not title_elem:
                        continue
                    job_link = self.base_url + card.find('a')['href'] if card.find('a') else ''
                    if not job_link:
                        continue
                    
                    company = self.clean_text(card.find('div', attrs={'data-testid': 'job-company'}).get_text() if card.find('div', attrs={'data-testid': 'job-company'}) else '') or ''
                    
                    # ALWAYS fetch job detail page to get REAL data (NO "Unknown")
                    company_profile_url = None
                    company_url = None
                    company_size = ''
                    job_description = ''
                    posted_date = None
                    location = self.clean_text(card.find('div', attrs={'data-testid': 'job-location'}).get_text() if card.find('div', attrs={'data-testid': 'job-location'}) else '') or ''
                    try:
                        detail = self._fetch_job_detail(job_link)
                        if detail:
                            job_description = detail.get('description', '') or detail.get('job_description', '')
                            posted_date = detail.get('posted_date')
                            if detail.get('company') and not company:
                                company = detail['company']
                            company_url = detail.get('company_url')
                            company_profile_url = detail.get('company_profile_url')
                            if detail.get('company_size') and detail['company_size'] not in ['UNKNOWN', 'Unknown', '']:
                                company_size = detail['company_size']
                            if detail.get('location') and not location:
                                location = detail['location']
                    except Exception as e:
                        logger.debug(f"CareerBuilder: Error fetching job detail for {job_link}: {e}")
                    
                    # If still no company, infer from job link
                    if not company or company.lower() in ['unknown', 'company not listed', '']:
                        try:
                            from urllib.parse import urlparse
                            domain = urlparse(job_link).netloc
                            if domain:
                                company = domain.replace('www.', '').split('.')[0].title()
                        except:
                            company = 'Company Not Listed'
                    
                    # ✅ REMOVED STRICT FILTERS - Let all jobs through
                    # Detect job type
                    job_title = self.clean_text(title_elem.get_text())
                    detected_type = self.detect_job_type(job_title, location, job_description)
                    if detected_type == 'UNKNOWN' and self.job_type != 'ALL':
                        detected_type = self.job_type
                    
                    # Only check time filter if date is available
                    if posted_date and not self.should_include_job(posted_date):
                        continue
                    # Only filter if job type filter is very specific (not ALL)
                    if self.job_type != 'ALL' and not self.matches_job_type_filter(detected_type):
                        continue
                    
                    # ONLY require job_title (company can be inferred)
                    if job_title:
                        job_data = {
                            'job_title': job_title,
                            'company': company if company else 'Company Not Listed',
                            'company_url': company_url or '',
                            'company_size': company_size or '',  # Empty string instead of "UNKNOWN"
                            'company_profile_url': company_profile_url or None,
                            'market': 'USA',
                            'job_link': job_link,
                            'posted_date': posted_date,
                            'location': location if location else '',
                            'job_description': job_description if job_description else '',
                            'job_type': detected_type,
                        }
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
            html = self.make_request(job_link, use_selenium=True)
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
            logger.debug(f"CareerBuilder: Error fetching job detail: {e}")
        
        return detail

