"""Adzuna Job Scraper - MULTI-APPROACH: Tries multiple methods to fetch maximum jobs"""
from typing import List, Dict, Optional
from ..utils.base_scraper import BaseScraper
from ..utils.multi_approach_scraper import MultiApproachExtractor
import urllib.parse
from urllib.parse import urljoin
import json
import logging
import re

logger = logging.getLogger(__name__)

class AdzunaScraper(BaseScraper):
    @property
    def portal_name(self) -> str:
        return "Adzuna"
    
    @property
    def base_url(self) -> str:
        return "https://www.adzuna.co.uk"
    
    def build_search_url(self, keyword: str) -> str:
        params = {'q': keyword, 'w': self.location if self.location != 'ALL' else 'UK'}
        return f"{self.base_url}/search?{urllib.parse.urlencode(params)}"
    
    def scrape_jobs(self) -> List[Dict]:
        """MULTI-APPROACH: Try multiple methods to fetch maximum jobs"""
        jobs = []
        seen_job_links = set()
        
        for keyword in self.keywords:
            # APPROACH 1: Try multiple URL formats
            url_formats = [
                self.build_search_url(keyword),
                f"{self.base_url}/search?q={urllib.parse.quote(keyword)}",
                f"{self.base_url}/jobs?q={urllib.parse.quote(keyword)}",
            ]
            
            soup = None
            
            # Try each URL format
            for url in url_formats:
                try:
                    # APPROACH 2: Try direct request first
                    html = self.make_request(url, use_selenium=False)
                    if html and len(html) > 1000:
                        soup = self.parse_html(html)
                        break
                except:
                    continue
                
                # APPROACH 3: Fallback to Selenium
                try:
                    html = self.make_request(url, use_selenium=True)
                    if html and len(html) > 1000:
                        soup = self.parse_html(html)
                        break
                except:
                    continue
            
            if not soup:
                logger.warning(f"Adzuna: Could not fetch HTML for keyword '{keyword}'")
                continue
            
            # APPROACH 4-7: Use MultiApproachExtractor to try ALL methods
            job_cards = MultiApproachExtractor.extract_jobs_from_soup(soup, self.base_url, self.keywords)
            
            if not job_cards:
                logger.warning(f"Adzuna: No job cards found for '{keyword}' after trying all approaches")
                continue
            
            logger.info(f"Adzuna: Found {len(job_cards)} job cards using multi-approach for '{keyword}'")
            
            for card in job_cards:
                try:
                    # ✅ SIMPLE EXTRACTION - Like original approach
                    # Extract job title - try multiple methods
                    title_elem = None
                    if hasattr(card, 'find'):
                        title_elem = card.find('h2') or card.find('h3') or card.find('h1') or \
                                   card.find('a', class_=lambda x: x and 'title' in x.lower())
                    
                    # If card is itself a link
                    if not title_elem and card.name == 'a':
                        title_elem = card
                    
                    if not title_elem:
                        continue
                    
                    job_title = self.clean_text(title_elem.get_text()) if hasattr(title_elem, 'get_text') else str(title_elem).strip()
                    
                    if not job_title or len(job_title) < 3:
                        continue
                    
                    # ✅ REMOVED STRICT KEYWORD CHECK - Extract all jobs
                    
                    # Extract job link - MORE FLEXIBLE
                    job_link = ''
                    if card.name == 'a':
                        href = card.get('href', '')
                        if href:
                            job_link = urljoin(self.base_url, href) if not href.startswith('http') else href
                    else:
                        link_elem = card.find('a')
                        if link_elem and link_elem.get('href'):
                            href = link_elem['href']
                            job_link = urljoin(self.base_url, href) if not href.startswith('http') else href
                    
                    if not job_link:
                        continue
                    
                    # Deduplicate by job link
                    if job_link in seen_job_links:
                        continue
                    seen_job_links.add(job_link)
                    
                    # Extract initial data from card
                    company = ''
                    if hasattr(card, 'find'):
                        company_elem = card.find('a', class_='company')
                        if company_elem:
                            company = self.clean_text(company_elem.get_text())
                    
                    posted_date = self.parse_date(card.find('span', class_='posted').get_text() if hasattr(card, 'find') and card.find('span', class_='posted') else '')
                    
                    # Extract location from card
                    location = ''
                    if hasattr(card, 'find'):
                        location_elem = card.find('span', class_='location')
                        if location_elem:
                            location = self.clean_text(location_elem.get_text())
                    
                    # ALWAYS fetch job detail page to get REAL data (NO "Unknown")
                    company_profile_url = None
                    company_url = None
                    company_size = ''
                    job_description = ''
                    try:
                        detail = self._fetch_job_detail(job_link)
                        if detail:
                            job_description = detail.get('description', '') or detail.get('job_description', '')
                            if detail.get('posted_date') and not posted_date:
                                posted_date = detail['posted_date']
                            if detail.get('company') and not company:
                                company = detail['company']
                            company_url = detail.get('company_url')
                            company_profile_url = detail.get('company_profile_url')
                            if detail.get('company_size') and detail['company_size'] not in ['UNKNOWN', 'Unknown', '']:
                                company_size = detail['company_size']
                            if detail.get('location') and not location:
                                location = detail['location']
                    except Exception as e:
                        logger.debug(f"Adzuna: Error fetching job detail for {job_link}: {e}")
                    
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
                    # Only check time filter if date is available
                    if posted_date and not self.should_include_job(posted_date):
                        continue
                    
                    # Detect job type (but don't filter strictly)
                    detected_type = self.detect_job_type(job_title, location, job_description)
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
                            'market': 'UK',
                            'job_link': job_link,
                            'posted_date': posted_date,
                            'location': location if location else '',
                            'job_description': job_description if job_description else '',
                            'job_type': detected_type,
                        }
                        # ✅ Ensure all fields have real data - no "Unknown" values
                        job_data = self.ensure_real_data(job_data)
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
                                logger.debug(f"Adzuna: Found company URL from JSON-LD: {company_url}")
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
            
            # Extract company URL from HTML if not found in JSON-LD
            if not detail.get('company_url'):
                # Try common selectors for company website
                website_selectors = [
                    'a[href*="company"]',
                    'a.company-website',
                    'a[href^="http"]:not([href*="adzuna"])',
                ]
                for selector in website_selectors:
                    try:
                        link = soup.select_one(selector)
                        if link:
                            href = link.get('href', '')
                            if href and href.startswith('http') and 'adzuna' not in href.lower():
                                detail['company_url'] = href
                                logger.debug(f"Adzuna: Found company URL from HTML: {href}")
                                break
                    except:
                        continue
            
            # Extract company size from HTML if available
            if not detail.get('company_size'):
                # Try to find company size in text
                all_text = soup.get_text()
                size_patterns = [
                    r'company\s*size[:\s]+(\d{1,3}(?:,\d{3})*)\s*-\s*(\d{1,3}(?:,\d{3})*)\s*employees?',
                    r'(\d{1,3}(?:,\d{3})*)\s*-\s*(\d{1,3}(?:,\d{3})*)\s*employees?',
                    r'(\d{1,3}(?:,\d{3})*)\s*employees?',
                ]
                for pattern in size_patterns:
                    match = re.search(pattern, all_text, re.IGNORECASE)
                    if match:
                        if len(match.groups()) == 2:
                            min_val = int(match.group(1).replace(',', ''))
                            max_val = int(match.group(2).replace(',', ''))
                            detail['company_size'] = self._parse_company_size_from_range(min_val, max_val)
                            logger.debug(f"Adzuna: Found company size from HTML: {min_val}-{max_val}")
                            break
                        else:
                            count = int(match.group(1).replace(',', ''))
                            detail['company_size'] = self._parse_company_size_from_count(count)
                            logger.debug(f"Adzuna: Found company size from HTML: {count}")
                            break
        except Exception as e:
            logger.debug(f"Adzuna: Error fetching job detail: {e}")
        
        return detail

