"""Jobsora Scraper - MULTI-APPROACH: Tries multiple methods to fetch maximum jobs"""
from typing import List, Dict, Optional
from urllib.parse import quote_plus, urljoin
from ..utils.base_scraper import BaseScraper
from ..utils.multi_approach_scraper import MultiApproachExtractor
import logging
import json

logger = logging.getLogger(__name__)

class JobsoraScraper(BaseScraper):
    @property
    def portal_name(self) -> str:
        return "Jobsora"
    
    @property
    def base_url(self) -> str:
        return "https://www.jobsora.com"
    
    def build_search_url(self, keyword: str) -> str:
        encoded_keyword = quote_plus(keyword)
        # Try multiple URL formats - Jobsora might use different format
        return f"{self.base_url}/search?q={encoded_keyword}"
    
    def _extract_company(self, card) -> str:
        """Extract company name from job card"""
        selectors = [
            '.company', '.company-name', '[class*="company"]',
            'span.company', 'div.company', 'a.company',
            '[data-company]'
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
            '[data-location]'
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
            'time', '[datetime]', '.time-ago', '.posted'
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
            # Try multiple URL formats
            url_formats = [
                f"{self.base_url}/search?q={quote_plus(keyword)}",
                f"{self.base_url}/jobs?q={quote_plus(keyword)}",
                f"{self.base_url}/search?keywords={quote_plus(keyword)}",
            ]
            
            html = None
            url = None
            for url_format in url_formats:
                try:
                    html = self.make_request(url_format)
                    if html and len(html) > 100:  # Check if we got actual content
                        url = url_format
                        logger.info(f"Jobsora: Successfully fetched from {url_format}")
                        break
                except Exception as e:
                    logger.debug(f"Jobsora: Failed to fetch {url_format}: {e}")
                    continue
            
            if not html:
                logger.warning(f"Jobsora: All URL formats failed for keyword '{keyword}'")
                continue
            soup = self.parse_html(html)
            
            # ✅ USE MULTI-APPROACH EXTRACTOR - Try ALL methods
            job_cards = MultiApproachExtractor.extract_jobs_from_soup(soup, self.base_url, self.keywords)
            
            if not job_cards:
                logger.warning(f"Jobsora: No job cards found for '{keyword}' after trying all approaches")
                continue
            
            logger.info(f"Jobsora: Found {len(job_cards)} job cards using multi-approach for '{keyword}'")
            
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
                    if job_link in [j.get('job_link') for j in jobs]:
                        continue
                    
                    # Extract initial data from card
                    company = self._extract_company(card)
                    location = self._extract_location(card)
                    posted_date = self._extract_posted_date(card)
                    job_description = self._extract_description(card)
                    
                    # ALWAYS fetch job detail page to get REAL data (NO "Unknown")
                    company_profile_url = None
                    company_url = None
                    company_size = ''
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
                            if detail.get('company_size') and detail['company_size'] not in ['UNKNOWN', 'Unknown', '']:
                                company_size = detail['company_size']
                            if detail.get('location') and not location:
                                location = detail['location']
                    except Exception as e:
                        logger.debug(f"Jobsora: Error fetching job detail for {job_link}: {e}")
                    
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
                    
                    # Infer market from location
                    market = self._infer_market(location)
                    
                    # ONLY require job_title (company can be inferred)
                    if job_title:
                        job_data = {
                            'job_title': job_title,
                            'company': company if company else 'Company Not Listed',
                            'company_url': company_url or '',
                            'company_size': company_size or '',  # Empty string instead of "UNKNOWN"
                            'company_profile_url': company_profile_url or None,
                            'market': market,
                            'job_link': job_link,
                            'posted_date': posted_date,
                            'location': location if location else '',
                            'job_description': job_description if job_description else '',
                            'job_type': detected_type,
                        }
                        # ✅ Ensure all fields have real data - no "Unknown" values
                        job_data = self.ensure_real_data(job_data)
                        jobs.append(job_data)
                        
                except Exception as e:
                    logger.debug(f"Jobsora: Error parsing job card: {e}")
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
            logger.debug(f"Jobsora: Error fetching job detail: {e}")
        
        return detail
    
    def _infer_market(self, location: str) -> str:
        """Infer market from location"""
        if not location:
            return 'USA'
        location_upper = location.upper()
        if 'UK' in location_upper or 'UNITED KINGDOM' in location_upper or 'LONDON' in location_upper:
            return 'UK'
        elif 'USA' in location_upper or 'UNITED STATES' in location_upper or any(state in location_upper for state in ['NY', 'CA', 'TX', 'FL']):
            return 'USA'
        return 'OTHER'

