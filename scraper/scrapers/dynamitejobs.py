"""Dynamite Jobs Scraper - MULTI-APPROACH: Tries multiple methods to fetch maximum jobs"""
from typing import List, Dict, Optional
from ..utils.base_scraper import BaseScraper
from ..utils.multi_approach_scraper import MultiApproachExtractor
import json
import logging
import re
from urllib.parse import urljoin

logger = logging.getLogger(__name__)

class DynamiteJobsScraper(BaseScraper):
    @property
    def portal_name(self) -> str:
        return "Dynamite Jobs"
    
    @property
    def base_url(self) -> str:
        return "https://dynamitejobs.com"
    
    @property
    def requires_selenium(self) -> bool:
        return True  # Dynamite Jobs requires JavaScript rendering
    
    def build_search_url(self, keyword: str) -> str:
        return f"{self.base_url}/jobs?search={keyword}"
    
    def scrape_jobs(self) -> List[Dict]:
        jobs = []
        for keyword in self.keywords:
            url = self.build_search_url(keyword)
            # Try with Selenium first since it requires JavaScript
            html = self.make_request(url, use_selenium=True)
            if not html:
                continue
            soup = self.parse_html(html)
            # Try multiple selectors to get maximum jobs - need to check each one
            job_cards = []
            selectors_to_try = [
                ('div', {'class': 'job-listing'}),
                ('article', {'class': 'job'}),
                ('div', {'class': 'job-card'}),
                ('div', {'class': 'job-item'}),
                ('li', {'class': 'job'}),
                ('div', {'class': lambda x: x and 'job' in ' '.join(x).lower()}),
                ('article', {'class': lambda x: x and 'job' in ' '.join(x).lower()}),
            ]
            
            for tag, attrs in selectors_to_try:
                found = soup.find_all(tag, attrs)
                if found:
                    job_cards.extend(found)
                    logger.debug(f"Dynamite Jobs: Found {len(found)} cards with {tag} {attrs}")
            
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
                        logger.debug(f"Dynamite Jobs: Found {len(found)} cards with CSS selector {selector}")
            
            # Try finding any links that look like job links
            if not job_cards:
                job_links = soup.find_all('a', href=re.compile(r'/job|/position|/career|/vacancy', re.I))
                for link in job_links:
                    parent = link.find_parent(['div', 'article', 'li'])
                    if parent and parent not in job_cards:
                        job_cards.append(parent)
                        logger.debug(f"Dynamite Jobs: Found job card from link {link.get('href', '')[:50]}")
            
            # APPROACH 4-7: If no cards found, use MultiApproachExtractor as fallback
            if not job_cards:
                logger.info(f"Dynamite Jobs: Standard selectors failed, trying MultiApproachExtractor...")
                job_cards = MultiApproachExtractor.extract_jobs_from_soup(soup, self.base_url, self.keywords)
            
            if not job_cards:
                logger.warning(f"Dynamite Jobs: No job cards found for '{keyword}' after trying all approaches.")
                all_divs = soup.find_all('div', limit=10)
                logger.debug(f"Dynamite Jobs: Sample div classes: {[d.get('class') for d in all_divs[:5]]}")
                continue
            
            logger.info(f"Dynamite Jobs: Found {len(job_cards)} job cards for '{keyword}'")
            
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
                    company_elem = card.find('div', class_='company') or \
                                  card.find('span', class_='company') or \
                                  card.find('div', class_='company-name')
                    if company_elem:
                        company = self.clean_text(company_elem.get_text())
                    
                    location = 'Remote'
                    location_elem = card.find('span', class_='location') or \
                                   card.find('div', class_='location')
                    if location_elem:
                        location = self.clean_text(location_elem.get_text())
                    
                    posted_date = None
                    date_elem = card.find('time') or card.find('span', class_='date')
                    if date_elem:
                        date_str = date_elem.get('datetime') or date_elem.get_text()
                        posted_date = self.parse_date(date_str)
                    
                    # Fetch job detail page to get ALL real data
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
                            if detail.get('location') and location == 'Remote':
                                location = detail['location']
                    except Exception as e:
                        logger.debug(f"Dynamite Jobs: Error fetching job detail for {job_link}: {e}")
                    
                    # If still no company, infer from job link
                    if not company or company.lower() in ['unknown', 'company not listed', '']:
                        try:
                            from urllib.parse import urlparse
                            domain = urlparse(job_link).netloc
                            if domain:
                                company = domain.replace('www.', '').split('.')[0].title()
                        except:
                            company = 'Company Not Listed'
                    
                    job_title = self.clean_text(title_elem.get_text())
                    if not job_title:
                        continue
                    
                    detected_type = self.detect_job_type(job_title, location, job_description)
                    if detected_type == 'UNKNOWN' and self.job_type != 'ALL':
                        detected_type = self.job_type
                    
                    # ✅ REMOVED STRICT FILTERS - Let all jobs through
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
                            'location': location or '',
                            'job_description': job_description or '',
                            'job_type': detected_type,
                        }
                        jobs.append(job_data)
                except Exception as e:
                    logger.debug(f"Dynamite Jobs: Error parsing job card: {e}")
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
            
            # Extract location from job detail page
            location_elem = soup.find('span', class_='location') or \
                           soup.find('div', class_='location') or \
                           soup.find('p', class_='location')
            if location_elem:
                location_text = self.clean_text(location_elem.get_text())
                if location_text:
                    detail['location'] = location_text
            
            # Extract posted date from job detail page
            if not detail.get('posted_date'):
                date_elem = soup.find('time') or soup.find('span', class_='date') or soup.find('div', class_='date')
                if date_elem:
                    date_str = date_elem.get('datetime') or date_elem.get_text()
                    parsed = self.parse_date(date_str)
                    if parsed:
                        detail['posted_date'] = parsed
            
            # Extract job description from job detail page
            if not detail.get('description'):
                desc_elem = soup.find('div', class_='description') or \
                           soup.find('div', class_='job-description') or \
                           soup.find('div', id='job-description')
                if desc_elem:
                    desc_text = self.clean_text(desc_elem.get_text())
                    if desc_text:
                        detail['description'] = desc_text
        except Exception as e:
            logger.debug(f"Dynamite Jobs: Error fetching job detail: {e}")
        
        return detail

