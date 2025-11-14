"""CWjobs Scraper"""
from typing import List, Dict, Optional
from ..utils.base_scraper import BaseScraper
import urllib.parse
import json
import logging
import re

logger = logging.getLogger(__name__)

class CWJobsScraper(BaseScraper):
    @property
    def portal_name(self) -> str:
        return "CWjobs"
    
    @property
    def base_url(self) -> str:
        return "https://www.cwjobs.co.uk"
    
    def build_search_url(self, keyword: str) -> str:
        return f"{self.base_url}/jobs/{urllib.parse.quote(keyword)}"
    
    def scrape_jobs(self) -> List[Dict]:
        jobs = []
        seen_job_links = set()
        for keyword in self.keywords:
            url = self.build_search_url(keyword)
            html = self.make_request(url)
            if not html:
                continue
            soup = self.parse_html(html)
            # Try multiple selectors to get maximum jobs
            job_cards = []
            selectors_to_try = [
                ('div', {'class': 'job'}),
                ('article', {'class': 'job'}),
                ('li', {'class': 'job'}),
                ('div', {'class': 'job-card'}),
                ('div', {'class': 'job-item'}),
                ('div', {'class': lambda x: x and 'job' in ' '.join(x).lower()}),
                ('article', {'class': lambda x: x and 'job' in ' '.join(x).lower()}),
            ]
            
            for tag, attrs in selectors_to_try:
                found = soup.find_all(tag, attrs)
                if found:
                    job_cards.extend(found)
                    logger.debug(f"CWjobs: Found {len(found)} cards with {tag} {attrs}")
            
            # Also try CSS selectors
            if not job_cards:
                css_selectors = [
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
                        logger.debug(f"CWjobs: Found {len(found)} cards with CSS selector {selector}")
            
            # Try finding any links that look like job links
            if not job_cards:
                job_links = soup.find_all('a', href=re.compile(r'/job|/position|/career|/vacancy', re.I))
                for link in job_links:
                    parent = link.find_parent(['div', 'article', 'li'])
                    if parent and parent not in job_cards:
                        job_cards.append(parent)
                        logger.debug(f"CWjobs: Found job card from link {link.get('href', '')[:50]}")
            
            # ✅ USE MultiApproachExtractor as fallback if standard selectors fail
            if not job_cards:
                logger.info(f"CWjobs: Standard selectors failed, trying MultiApproachExtractor...")
                from ..utils.multi_approach_scraper import MultiApproachExtractor
                job_cards = MultiApproachExtractor.extract_jobs_from_soup(soup, self.base_url, self.keywords)
            
            if not job_cards:
                logger.warning(f"CWjobs: No job cards found for '{keyword}' after trying all approaches.")
                all_divs = soup.find_all('div', limit=10)
                logger.debug(f"CWjobs: Sample div classes: {[d.get('class') for d in all_divs[:5]]}")
                continue
            
            logger.info(f"CWjobs: Found {len(job_cards)} job cards for '{keyword}'")
            
            for card in job_cards:
                try:
                    # ✅ SIMPLE EXTRACTION - Try multiple methods
                    title_elem = None
                    if hasattr(card, 'find'):
                        title_elem = card.find('h2') or card.find('h3') or card.find('h1') or \
                                   card.find('a', class_=lambda x: x and 'title' in x.lower())
                    
                    if not title_elem:
                        continue
                    
                    job_title = self.clean_text(title_elem.get_text()) if hasattr(title_elem, 'get_text') else str(title_elem).strip()
                    
                    if not job_title or len(job_title) < 3:
                        continue
                    
                    # ✅ REMOVED STRICT KEYWORD CHECK - Extract all jobs
                    
                    # Extract job link
                    job_link = ''
                    if hasattr(card, 'find'):
                        link_elem = card.find('a')
                        if link_elem and link_elem.get('href'):
                            href = link_elem['href']
                            job_link = self.base_url + href if not href.startswith('http') else href
                    
                    if not job_link:
                        continue
                    
                    # Deduplicate by job link
                    if job_link in seen_job_links:
                        continue
                    seen_job_links.add(job_link)
                    
                    # Extract company
                    company = ''
                    if hasattr(card, 'find'):
                        company_elem = card.find('span', class_='company')
                        if company_elem:
                            company = self.clean_text(company_elem.get_text())
                    
                    # Fetch job detail page to get company profile URL and additional info
                    company_profile_url = None
                    company_url = None
                    company_size = 'UNKNOWN'
                    job_description = ''
                    posted_date = None
                    try:
                        detail = self._fetch_job_detail(job_link)
                        if detail:
                            job_description = detail.get('description', '')
                            posted_date = detail.get('posted_date')
                            if detail.get('company') and not company:
                                company = detail['company']
                            company_url = detail.get('company_url')
                            company_profile_url = detail.get('company_profile_url')
                            if detail.get('company_size'):
                                company_size = detail['company_size']
                    except Exception as e:
                        logger.debug(f"CWjobs: Error fetching job detail for {job_link}: {e}")
                    
                    job_data = {
                        'job_title': self.clean_text(title_elem.get_text()),
                        'company': company,
                        'company_url': company_url,
                        'company_size': company_size,
                        'company_profile_url': company_profile_url,  # Pass for ScraperManager enrichment
                        'market': 'UK',
                        'job_link': job_link,
                        'posted_date': posted_date,
                        'location': self.clean_text(card.find('span', class_='location').get_text() if card.find('span', class_='location') else ''),
                        'job_description': job_description,
                        'job_type': self.job_type if self.job_type != 'ALL' else 'UNKNOWN',
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
            logger.debug(f"CWjobs: Error fetching job detail: {e}")
        
        return detail

