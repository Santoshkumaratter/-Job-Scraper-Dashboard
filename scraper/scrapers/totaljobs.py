"""Totaljobs Scraper"""
from typing import List, Dict, Optional
from ..utils.base_scraper import BaseScraper
import urllib.parse
import json
import logging

logger = logging.getLogger(__name__)

class TotalJobsScraper(BaseScraper):
    @property
    def portal_name(self) -> str:
        return "Totaljobs"
    
    @property
    def base_url(self) -> str:
        return "https://www.totaljobs.com"
    
    def build_search_url(self, keyword: str) -> str:
        params = {'q': keyword}
        return f"{self.base_url}/jobs/{urllib.parse.quote(keyword)}"
    
    def scrape_jobs(self) -> List[Dict]:
        jobs = []
        seen_job_ids = set()  # Deduplicate across pages
        
        for keyword in self.keywords:
            base_url = self.build_search_url(keyword)
            
            # Fetch multiple pages for maximum jobs (500+ jobs)
            max_pages = 50  # Fetch up to 50 pages
            for page_num in range(max_pages):
                try:
                    # Build URL with pagination
                    if page_num == 0:
                        url = base_url
                    else:
                        # Totaljobs uses page parameter for pagination
                        url = f"{base_url}?page={page_num + 1}"
                    
                    logger.info(f"Totaljobs: Fetching page {page_num + 1}/{max_pages} for keyword '{keyword}'")
                    html = self.make_request(url)
                    if not html:
                        logger.warning(f"Totaljobs: No HTML returned for page {page_num + 1}")
                        break
                    
                    soup = self.parse_html(html)
                    
                    # Try multiple selectors to get maximum jobs
                    job_cards = []
                    selectors_to_try = [
                        ('div', {'class': 'job'}),
                        ('article', {'class': 'job'}),
                        ('li', {'class': 'job'}),
                        ('div', {'class': 'job-card'}),
                        ('div', {'class': lambda x: x and 'job' in ' '.join(x).lower()}),
                    ]
                    
                    for tag, attrs in selectors_to_try:
                        found = soup.find_all(tag, attrs)
                        if found:
                            job_cards.extend(found)
                            break
                    
                    # ✅ USE MultiApproachExtractor as fallback if standard selectors fail
                    if not job_cards:
                        logger.info(f"Totaljobs: Standard selectors failed, trying MultiApproachExtractor...")
                        from ..utils.multi_approach_scraper import MultiApproachExtractor
                        job_cards = MultiApproachExtractor.extract_jobs_from_soup(soup, self.base_url, self.keywords)
                    
                    if not job_cards:
                        logger.info(f"Totaljobs: No more job cards found on page {page_num + 1}, stopping pagination")
                        break
                    
                    logger.info(f"Totaljobs: Found {len(job_cards)} job cards on page {page_num + 1}")
                    
                    page_jobs_count = 0
                    for card in job_cards:
                        try:
                            title_elem = card.find('h2', class_='job-title')
                            if not title_elem:
                                continue
                            job_link = self.base_url + card.find('a', class_='job-title')['href'] if card.find('a', class_='job-title') else ''
                            if not job_link:
                                continue
                            
                            company = self.clean_text(card.find('a', class_='company').get_text() if card.find('a', class_='company') else '') or ''
                            posted_date = self.parse_date(card.find('span', class_='job-posted').get_text() if card.find('span', class_='job-posted') else '')
                            location = self.clean_text(card.find('li', class_='location').get_text() if card.find('li', class_='location') else '') or ''
                            
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
                                logger.debug(f"Totaljobs: Error fetching job detail for {job_link}: {e}")
                            
                            # If still no company, infer from job link
                            if not company or company.lower() in ['unknown', 'company not listed', '']:
                                try:
                                    from urllib.parse import urlparse
                                    domain = urlparse(job_link).netloc
                                    if domain:
                                        company = domain.replace('www.', '').split('.')[0].title()
                                except:
                                    company = 'Company Not Listed'
                            
                            # Detect job type
                            job_title = self.clean_text(title_elem.get_text())
                            detected_type = self.detect_job_type(job_title, location, job_description)
                            if detected_type == 'UNKNOWN' and self.job_type != 'ALL':
                                detected_type = self.job_type
                            
                            # Check filters
                            if not self.should_include_job(posted_date):
                                continue
                            if not self.matches_job_type_filter(detected_type):
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
                            
                            # Deduplicate by job link
                            if job_data['job_link'] in seen_job_ids:
                                continue
                            seen_job_ids.add(job_data['job_link'])
                            
                            if self.should_include_job(job_data['posted_date']):
                                jobs.append(job_data)
                                page_jobs_count += 1
                                
                                # Stop if we've reached the maximum per keyword
                                if len(jobs) >= self.max_jobs_per_keyword:
                                    logger.info(f"Totaljobs: Reached maximum jobs ({self.max_jobs_per_keyword}) for keyword '{keyword}'")
                                    break
                        except Exception as e:
                            logger.debug(f"Totaljobs: Error parsing job card: {e}")
                            continue
                    
                    # If no new jobs found on this page, stop pagination
                    if page_jobs_count == 0:
                        logger.info(f"Totaljobs: No new jobs found on page {page_num + 1}, stopping pagination")
                        break
                    
                    # Stop if we've reached the maximum per keyword
                    if len(jobs) >= self.max_jobs_per_keyword:
                        break
                
                except Exception as e:
                    logger.error(f"Totaljobs: Error fetching page {page_num + 1}: {str(e)}")
                    break  # Stop pagination on error
            
            logger.info(f"Totaljobs: Total jobs found for keyword '{keyword}': {len(jobs)}")
        
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
            logger.debug(f"Totaljobs: Error fetching job detail: {e}")
        
        return detail

