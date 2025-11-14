"""
LinkedIn Jobs Scraper
"""
import json
import logging
import re
import time
import urllib.parse
from typing import Dict, List, Optional

from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from ..utils.base_scraper import BaseScraper

logger = logging.getLogger(__name__)


class LinkedInJobsScraper(BaseScraper):
    """Scraper for LinkedIn Jobs"""
    
    @property
    def portal_name(self) -> str:
        return "Linkedin Jobs"
    
    @property
    def base_url(self) -> str:
        return "https://www.linkedin.com"
    
    @property
    def requires_selenium(self) -> bool:
        return True
    
    def build_search_url(self, keyword: str) -> str:
        """Build LinkedIn Jobs search URL"""
        params = {
            'keywords': keyword,
            'location': self.location if self.location != 'ALL' else '',
            'sortBy': 'DD'
        }
        
        if self.job_type == 'REMOTE':
            params['f_WT'] = '2'
        elif self.job_type == 'HYBRID':
            params['f_WT'] = '3'
        
        if self.time_filter == '24H':
            params['f_TPR'] = 'r86400'
        elif self.time_filter == '3D':
            params['f_TPR'] = 'r259200'
        elif self.time_filter == '7D':
            params['f_TPR'] = 'r604800'
        
        query_string = urllib.parse.urlencode(params)
        return f"{self.base_url}/jobs/search/?{query_string}"
    
    def scrape_jobs(self) -> List[Dict]:
        """Scrape jobs from LinkedIn with detail enrichment"""
        jobs: List[Dict] = []
        
        logger.info(f"LinkedIn: Starting scrape for {len(self.keywords)} keyword(s)")

        for keyword in self.keywords:
            url = self.build_search_url(keyword)
            logger.info(f"LinkedIn: Fetching jobs for keyword '{keyword}' from {url}")
            
            start_time = time.time()
            html = self._fetch_linkedin_page_with_scrolling(url)
            elapsed = time.time() - start_time
            logger.info(f"LinkedIn: Page loaded with scrolling in {elapsed:.1f}s for '{keyword}'")
            
            if not html:
                logger.warning(f"LinkedIn: No HTML returned for keyword '{keyword}'")
                continue
            
            html_size = len(html) if html else 0
            logger.info(f"LinkedIn: Got HTML of size {html_size} bytes for '{keyword}'")
            
            html_lower = html.lower()
            has_login_indicators = ('sign in' in html_lower or 'join linkedin' in html_lower or 'welcome to linkedin' in html_lower)
            has_job_content = ('base-card' in html_lower or 'jobs-search' in html_lower or '/jobs/view/' in html_lower or 'job-result' in html_lower)
            
            if has_login_indicators and not has_job_content:
                logger.warning(f"LinkedIn: Got login/blocked page for keyword '{keyword}'. LinkedIn may require authentication.")

            soup = self.parse_html(html)
            logger.info(f"LinkedIn: Parsing HTML for '{keyword}'...")
            
            job_cards = []
            selectors = [
                ('base-card', soup.find_all('div', class_='base-card')),
                ('job-search-card', soup.find_all('div', class_='job-search-card')),
                ('jobs-search-results__list-item', soup.find_all('li', class_='jobs-search-results__list-item')),
                ('data-job-id div', soup.find_all('div', {'data-job-id': True})),
                ('data-job-id select', soup.select('div[data-job-id]')),
                ('li.jobs-search-results__list-item', soup.select('li.jobs-search-results__list-item')),
                ('job-result-card', soup.find_all('div', class_='job-result-card')),
                ('result-card', soup.find_all('div', class_='result-card')),
            ]
            
            for selector_name, cards in selectors:
                if cards:
                    logger.info(f"LinkedIn: Found {len(cards)} cards using selector '{selector_name}'")
                    job_cards.extend(cards)
                    break
            
            seen_ids = set()
            unique_cards = []
            for card in job_cards:
                card_id = card.get('data-job-id') or card.get('id') or str(card)
                if card_id not in seen_ids:
                    seen_ids.add(card_id)
                    unique_cards.append(card)
            job_cards = unique_cards
            logger.info(f"LinkedIn: After deduplication, have {len(job_cards)} unique cards for '{keyword}'")
            
            if not job_cards:
                logger.warning(f"LinkedIn: No job cards found with standard selectors for keyword '{keyword}'. Checking page content...")
                
                job_links = soup.find_all('a', href=re.compile(r'/jobs/view/'))
                if job_links:
                    logger.info(f"LinkedIn: Found {len(job_links)} job links directly. Extracting jobs from links...")
                    # NO LIMIT - fetch all jobs
                    for link in job_links:
                        try:
                            href = link.get('href', '')
                            if href:
                                parent = link.find_parent(['div', 'li', 'article'])
                                if parent:
                                    job_cards.append(parent)
                        except:
                            continue
                
                if not job_cards:
                    all_divs = soup.find_all('div', limit=20)
                    logger.debug(f"LinkedIn: Found {len(all_divs)} divs on page. First few classes: {[d.get('class') for d in all_divs[:5]]}")
                    json_scripts = soup.find_all('script', type='application/ld+json')
                    if json_scripts:
                        logger.info(f"LinkedIn: Found {len(json_scripts)} JSON-LD scripts. May contain job data.")
            
            logger.info(f"LinkedIn: Processing {len(job_cards)} job cards for '{keyword}'...")
            processed = 0
            skipped_no_title = 0
            
            for card in job_cards:
                try:
                    title_elem = (
                        card.find('h3', class_='base-search-card__title') or
                        card.find('h3', class_='job-result-card__title') or
                        card.find('h2', class_='job-result-card__title') or
                        card.find('a', class_='job-result-card__title-link') or
                        card.find('a', href=re.compile(r'/jobs/view/')) or
                        card.select_one('h3, h2, a[href*="/jobs/view/"]')
                    )
                    if not title_elem:
                        skipped_no_title += 1
                        continue
                    job_title = self.clean_text(title_elem.get_text())
                    if not job_title:
                        skipped_no_title += 1
                        continue

                    link_elem = (
                        card.find('a', class_='base-card__full-link') or
                        card.find('a', class_='job-result-card__title-link') or
                        card.find('a', href=re.compile(r'/jobs/view/')) or
                        title_elem.find('a') if title_elem else None
                    )
                    job_link = ''
                    if link_elem and link_elem.has_attr('href'):
                        job_link = link_elem.get('href', '')
                    if not job_link:
                        continue
                    if job_link.startswith('/'):
                        job_link = urllib.parse.urljoin(self.base_url, job_link)

                    company_elem = (
                        card.find('h4', class_='base-search-card__subtitle') or
                        card.find('h4', class_='job-result-card__subtitle-link') or
                        card.find('a', class_='job-result-card__subtitle-link') or
                        card.select_one('h4, a[href*="/company/"]')
                    )
                    company = self.clean_text(company_elem.get_text()) if company_elem else ''

                    location_elem = (
                        card.find('span', class_='job-search-card__location') or
                        card.find('span', class_='job-result-card__location') or
                        card.select_one('span[class*="location"]')
                    )
                    location = self.clean_text(location_elem.get_text()) if location_elem else ''

                    date_elem = card.find('time')
                    posted_date = self.parse_date(date_elem.get('datetime', '')) if date_elem else None

                    keyword_match = False
                    if self.keywords:
                        keyword_match = any(
                            self.matches_keyword(job_title, kw) 
                            for kw in self.keywords
                        )
                    else:
                        keyword_match = True
                    
                    if not keyword_match:
                        continue

                    company_url = None
                    company_profile_url = None
                    
                    if company_elem:
                        company_link = company_elem.find('a')
                        if company_link and company_link.has_attr('href'):
                            href = company_link.get('href', '')
                            if '/company/' in href:
                                company_profile_url = urllib.parse.urljoin(self.base_url, href)
                                logger.debug(f"LinkedIn: Extracted company profile URL from card: {company_profile_url}")

                    detail = self._fetch_job_detail(job_link)
                    description = detail.get('description', '')

                    if detail.get('company'):
                        company = detail['company']
                    if detail.get('company_profile_url'):
                        company_profile_url = detail['company_profile_url']
                        logger.debug(f"LinkedIn: Found company profile URL from detail page: {company_profile_url}")
                    
                    if not company_profile_url and company:
                        company_profile_url = self._build_linkedin_company_url(company)
                        if company_profile_url:
                            logger.info(f"LinkedIn: Built company profile URL from company name '{company}': {company_profile_url}")
                    
                    if detail.get('company_url'):
                        company_url = detail['company_url']  # Website URL from profile
                    if detail.get('location'):
                        location = detail['location']
                    if detail.get('posted_date'):
                        posted_date = detail['posted_date']
                    
                    detected_type = self.detect_job_type(job_title, location, description)
                    if detected_type == 'UNKNOWN':
                        mapped = self._map_employment_to_job_type(
                            detail.get('employment_type'), detail.get('workplace_type')
                        )
                        if mapped:
                            detected_type = mapped

                    if not self.matches_job_type_filter(detected_type):
                        continue

                    job_data = {
                        'job_title': job_title,
                        'company': company or detail.get('company', ''),
                        'company_url': company_url,
                        'company_size': detail.get('company_size', 'UNKNOWN'),
                        'company_profile_url': company_profile_url,
                        'market': self._infer_market(location),
                        'job_link': job_link,
                        'posted_date': posted_date,
                        'location': location,
                        'job_description': description,
                        'job_type': detected_type,
                        'salary_range': detail.get('salary_range', ''),
                    }

                    if not job_data['company']:
                        continue

                    jobs.append(job_data)
                    logger.debug(f"LinkedIn: Added job '{job_title}' at {company}")

                except Exception as e:
                    logger.debug(f"LinkedIn: Error parsing job card: {e}")
                    continue
            
            logger.info(f"LinkedIn: Found {len(jobs)} jobs for keyword '{keyword}'")

        logger.info(f"LinkedIn: Total jobs found: {len(jobs)}")
        return jobs

    def _infer_market(self, location: str) -> str:
        location_upper = (location or '').upper()
        if 'UNITED STATES' in location_upper or 'USA' in location_upper:
            return 'USA'
        if 'UNITED KINGDOM' in location_upper or 'UK' in location_upper:
            return 'UK'
        return 'OTHER'

    def _fetch_job_detail(self, job_link: str) -> Dict[str, Optional[str]]:
        detail: Dict[str, Optional[str]] = {}
        if not job_link:
            return detail

        html = self.make_request(job_link, use_selenium=True)
        if not html:
            return detail

        soup = self.parse_html(html)

        for script in soup.find_all('script', type='application/ld+json'):
            try:
                data = json.loads(script.get_text(strip=True) or '{}')
            except Exception:
                continue

            if not isinstance(data, dict) or data.get('@type') != 'JobPosting':
                continue

            description = data.get('description')
            if description:
                detail['description'] = self.clean_text(description)

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

            hiring = data.get('hiringOrganization') or data.get('hiringorganization')
            if isinstance(hiring, dict):
                name = hiring.get('name')
                if name:
                    detail['company'] = self.clean_text(name)
                company_url = hiring.get('sameAs') or hiring.get('url')
                if company_url:
                    detail['company_url'] = company_url
            
            company_profile_url = self._extract_company_profile_url(soup)
            if company_profile_url:
                detail['company_profile_url'] = company_profile_url
                logger.debug(f"LinkedIn: Extracted company profile URL from detail page: {company_profile_url}")
            
            if isinstance(hiring, dict) and 'numberOfEmployees' in hiring:
                employees = hiring.get('numberOfEmployees')
                if isinstance(employees, (int, str)):
                    detail['company_size'] = self._parse_company_size_from_count(employees)
                elif isinstance(employees, dict):
                    min_val = employees.get('minValue')
                    max_val = employees.get('maxValue')
                    if min_val and max_val:
                        detail['company_size'] = self._parse_company_size_from_range(min_val, max_val)

            if 'company_size' not in detail:
                company_size = self._extract_company_size_from_html(soup)
                if company_size:
                    detail['company_size'] = company_size

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

    def _parse_company_size_from_count(self, count: any) -> str:
        """Convert employee count to size category"""
        try:
            if isinstance(count, str):
                count = int(''.join(filter(str.isdigit, count)))
            else:
                count = int(count)
            
            if count >= 10001:
                return 'ENTERPRISE'
            elif count >= 1001:
                return 'LARGE'
            elif count >= 51:
                return 'MEDIUM'
            else:
                return 'SMALL'
        except:
            return 'UNKNOWN'
    
    def _parse_company_size_from_range(self, min_val: any, max_val: any) -> str:
        """Convert employee range to size category"""
        try:
            if isinstance(min_val, str):
                min_val = int(''.join(filter(str.isdigit, min_val)))
            else:
                min_val = int(min_val)
            
            if isinstance(max_val, str):
                max_val = int(''.join(filter(str.isdigit, max_val)))
            else:
                max_val = int(max_val)
            
            if max_val >= 10001:
                return 'ENTERPRISE'
            elif max_val >= 1001:
                return 'LARGE'
            elif max_val >= 51:
                return 'MEDIUM'
            else:
                return 'SMALL'
        except:
            return 'UNKNOWN'
    
    def _fetch_company_profile(self, profile_url: str) -> Dict[str, Optional[str]]:
        """Fetch LinkedIn company profile to get real company website URL and size"""
        profile_data = {}
        if not profile_url:
            return profile_data
        
        try:
            logger.info(f"LinkedIn: Fetching company profile from {profile_url}")
            html = self.make_request(profile_url, use_selenium=True)
            if not html:
                logger.warning(f"LinkedIn: No HTML returned from company profile URL")
                return profile_data
            
            soup = self.parse_html(html)
            logger.debug(f"LinkedIn: Parsed company profile HTML, looking for website URL and size")
            
            website_selectors = [
                'a[data-control-name="topcard_website"]',
                'a[data-tracking-control-name*="website"]',
                '.org-top-card-summary-info-list__info-item a[href^="http"]',
                'dd.org-top-card-summary-info-list__info-item a[href^="http"]',
                '.top-card-layout__entity-info a[href^="http"]',
                '.top-card-layout__first-subline a[href^="http"]',
                'a[href*="website"]',
                'a[href^="http"]:not([href*="linkedin.com"]):not([href*="redirect"])',
            ]
            
            website_found = False
            for selector in website_selectors:
                try:
                    website_links = soup.select(selector)
                    for website_link in website_links:
                        href = website_link.get('href', '').strip()
                        if not href:
                            continue
                        
                        if 'linkedin.com/redirect' in href or '/redirect' in href or 'linkedin.com/voyager/api/redirect' in href:
                            parsed = urllib.parse.urlparse(href)
                            params = urllib.parse.parse_qs(parsed.query)
                            
                            redirect_url = None
                            for param_name in ['url', 'redirectUrl', 'redirect', 'targetUrl']:
                                if param_name in params:
                                    redirect_url = params[param_name][0]
                                    break
                            
                            if redirect_url:
                                href = urllib.parse.unquote(redirect_url)
                            elif parsed.fragment:
                                href = urllib.parse.unquote(parsed.fragment)
                        
                        if href and href.startswith('http') and 'linkedin.com' not in href.lower():
                            invalid_domains = [
                                'linkedin.com', 'indeed.com', 'glassdoor.com', 'monster.com', 
                                'jobs.', 'careers.', 'workable.com', 'greenhouse.io', 'lever.co',
                                'ats.', 'apply.', 'recruiting.', 'talent.', 'hiring.'
                            ]
                            
                            href_lower = href.lower()
                            if not any(domain in href_lower for domain in invalid_domains):
                                profile_data['website_url'] = href
                                logger.info(f"LinkedIn: Found website URL from profile: {href}")
                                website_found = True
                                break
                    
                    if website_found:
                        break
                except Exception as e:
                    logger.debug(f"Error extracting website URL with selector {selector}: {e}")
                    continue
            
            for script in soup.find_all('script', type='application/ld+json'):
                try:
                    data = json.loads(script.get_text(strip=True) or '{}')
                    if isinstance(data, dict):
                        if data.get('@type') == 'Organization':
                            employees = data.get('numberOfEmployees')
                            if employees:
                                if isinstance(employees, (int, str)):
                                    profile_data['company_size'] = self._parse_company_size_from_count(employees)
                                    logger.info(f"Found company size from JSON-LD: {employees}")
                                    break
                                elif isinstance(employees, dict):
                                    min_val = employees.get('minValue')
                                    max_val = employees.get('maxValue')
                                    if min_val and max_val:
                                        profile_data['company_size'] = self._parse_company_size_from_range(min_val, max_val)
                                        logger.info(f"Found company size from JSON-LD: {min_val}-{max_val}")
                                        break
                except:
                    continue
            
            if 'company_size' not in profile_data:
                all_text = soup.get_text()
                
                size_sections = [
                    soup.select('.org-top-card-summary-info-list__info-item'),
                    soup.select('.top-card-layout__entity-info'),
                    soup.select('.about-us-section'),
                    soup.select('[class*="company-size"]'),
                ]
                
                size_found = False
                for section_list in size_sections:
                    for section in section_list:
                        section_text = section.get_text()
                        size_patterns = [
                            r'(\d{1,3}(?:,\d{3})*)\s*-\s*(\d{1,3}(?:,\d{3})*)\s*employees?',
                            r'(\d{1,3}(?:,\d{3})*)\+\s*employees?',
                            r'company\s*size[:\s]+(\d{1,3}(?:,\d{3})*)\s*-\s*(\d{1,3}(?:,\d{3})*)',
                        ]
                        
                        for pattern in size_patterns:
                            match = re.search(pattern, section_text, re.IGNORECASE)
                            if match:
                                try:
                                    if len(match.groups()) == 2:
                                        min_val = int(match.group(1).replace(',', ''))
                                        max_val = int(match.group(2).replace(',', ''))
                                        profile_data['company_size'] = self._parse_company_size_from_range(min_val, max_val)
                                        logger.debug(f"LinkedIn: Found company size from HTML range: {min_val}-{max_val} → {profile_data['company_size']}")
                                        size_found = True
                                        break
                                    else:
                                        count = int(match.group(1).replace(',', ''))
                                        profile_data['company_size'] = self._parse_company_size_from_count(count)
                                        logger.debug(f"LinkedIn: Found company size from HTML count: {count}+ → {profile_data['company_size']}")
                                        size_found = True
                                        break
                                except (ValueError, IndexError) as e:
                                    logger.debug(f"Error parsing size pattern: {e}")
                                    continue
                        
                        if size_found:
                            break
                    if size_found:
                        break
                
                if not size_found:
                    size_patterns = [
                        r'(\d{1,3}(?:,\d{3})*)\s*-\s*(\d{1,3}(?:,\d{3})*)\s*employees?',
                        r'company\s*size[:\s]+(\d{1,3}(?:,\d{3})*)\s*-\s*(\d{1,3}(?:,\d{3})*)\s*employees?',
                        r'(\d{1,3}(?:,\d{3})*)\+\s*employees?',
                        r'(\d{1,3}(?:,\d{3})*)\s*employees?\s*on\s*linkedin',
                        r'view\s*all\s*(\d{1,3}(?:,\d{3})*)\s*employees?',
                        r'(\d{1,3}(?:,\d{3})*)\s*employees?',
                    ]
                    
                    for pattern in size_patterns:
                        match = re.search(pattern, all_text, re.IGNORECASE)
                        if match:
                            try:
                                if len(match.groups()) == 2:
                                    min_val = int(match.group(1).replace(',', ''))
                                    max_val = int(match.group(2).replace(',', ''))
                                    profile_data['company_size'] = self._parse_company_size_from_range(min_val, max_val)
                                    logger.debug(f"LinkedIn: Found company size from HTML: {min_val}-{max_val} → {profile_data['company_size']}")
                                    break
                                else:
                                    count = int(match.group(1).replace(',', ''))
                                    profile_data['company_size'] = self._parse_company_size_from_count(count)
                                    logger.debug(f"LinkedIn: Found company size from HTML: {count} → {profile_data['company_size']}")
                                    break
                            except (ValueError, IndexError) as e:
                                logger.debug(f"Error parsing size pattern: {e}")
                                continue
            
            company_name_elem = soup.find('h1', class_='text-heading-xlarge')
            if not company_name_elem:
                company_name_elem = soup.find('h1')
            if company_name_elem:
                company_name = self.clean_text(company_name_elem.get_text())
                if company_name:
                    profile_data['company_name'] = company_name
            
        except Exception as e:
            logger.debug(f"Error fetching company profile from {profile_url}: {e}")
        
        return profile_data

    def _extract_company_size_from_html(self, soup) -> Optional[str]:
        """Extract company size from LinkedIn HTML"""
        try:
            text = soup.get_text()
            patterns = [
                r'(\d{1,3}(?:,\d{3})*)\s*-\s*(\d{1,3}(?:,\d{3})*)\s*employees?',
                r'(\d{1,3}(?:,\d{3})*)\+?\s*employees?',
                r'company\s*size[:\s]+(\d{1,3}(?:,\d{3})*)\s*-\s*(\d{1,3}(?:,\d{3})*)',
            ]
            
            for pattern in patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    if len(match.groups()) == 2:
                        min_val = int(match.group(1).replace(',', ''))
                        max_val = int(match.group(2).replace(',', ''))
                        return self._parse_company_size_from_range(min_val, max_val)
                    else:
                        count = int(match.group(1).replace(',', ''))
                        return self._parse_company_size_from_count(count)
            
            size_elem = soup.find('span', class_=re.compile('company-size|employees', re.I))
            if size_elem:
                size_text = size_elem.get_text()
                match = re.search(r'(\d{1,3}(?:,\d{3})*)', size_text)
                if match:
                    count = int(match.group(1).replace(',', ''))
                    return self._parse_company_size_from_count(count)
        except Exception as e:
            logger.debug(f"Error extracting company size from HTML: {e}")
        
        return None
    
    def _build_linkedin_company_url(self, company_name: str) -> Optional[str]:
        """Build LinkedIn company profile URL from company name"""
        if not company_name:
            return None
        
        try:
            cleaned = re.sub(r'[^\w\s-]', '', company_name)
            slug = re.sub(r'\s+', '-', cleaned.lower().strip())
            slug = re.sub(r'-+', '-', slug)
            slug = slug.strip('-')
            
            if not slug:
                return None
            
            company_url = f"{self.base_url}/company/{slug}/"
            logger.debug(f"Built LinkedIn company URL: {company_url} from company name: '{company_name}'")
            return company_url
        except Exception as e:
            logger.debug(f"Error building LinkedIn company URL for '{company_name}': {e}")
            return None
    
    def _fetch_linkedin_page_with_scrolling(self, url: str) -> Optional[str]:
        """Fetch LinkedIn page with multiple scrolls to load maximum jobs"""
        try:
            chrome_options = Options()
            chrome_options.add_argument('--headless')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--window-size=1920,1080')
            chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
            
            driver = webdriver.Chrome(options=chrome_options)
            driver.set_page_load_timeout(30)
            driver.get(url)
            time.sleep(2)
            
            max_scrolls = 50  # Increased to get maximum jobs
            scroll_pause = 1.5  # Slightly longer pause to ensure content loads
            
            last_height = 0
            no_change_count = 0
            max_no_change = 5  # Increased tolerance before stopping
            
            for scroll_num in range(max_scrolls):
                # Scroll to bottom
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                if scroll_num % 10 == 0:
                    logger.info(f"LinkedIn: Scroll {scroll_num + 1}/{max_scrolls}")
                time.sleep(scroll_pause)
                
                # Check if page height changed
                current_height = driver.execute_script("return document.body.scrollHeight")
                if current_height == last_height:
                    no_change_count += 1
                    if no_change_count >= max_no_change:
                        logger.info(f"LinkedIn: No new content after {no_change_count} scrolls, stopping early")
                        break
                else:
                    no_change_count = 0
                    last_height = current_height
                
                # Try to click "Show more" buttons more frequently
                if scroll_num % 3 == 0:  # Check every 3 scrolls instead of 5
                    try:
                        # Try multiple selectors for "Show more" / "See more" buttons
                        show_more_selectors = [
                            'button[aria-label*="Show more"]',
                            'button[aria-label*="see more"]',
                            'button[aria-label*="See more"]',
                            '.jobs-search-results__pagination button',
                            'button[data-tracking-control-name*="show more"]',
                            'button.jobs-search-results__pagination-button',
                            'button[aria-label*="Load more"]',
                        ]
                        for selector in show_more_selectors:
                            try:
                                show_more_button = driver.find_element(By.CSS_SELECTOR, selector)
                                if show_more_button and show_more_button.is_displayed():
                                    driver.execute_script("arguments[0].click();", show_more_button)
                                    logger.debug(f"LinkedIn: Clicked 'Show more' button (selector: {selector})")
                                    time.sleep(2)  # Wait longer after clicking
                                    break
                            except:
                                continue
                    except:
                        pass
            
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1)
            
            html = driver.page_source
            driver.quit()
            
            logger.info(f"LinkedIn: Scrolled {max_scrolls} times, page size: {len(html)} bytes")
            return html
            
        except Exception as e:
            logger.error(f"LinkedIn: Error fetching page with scrolling: {e}")
            if 'driver' in locals():
                try:
                    driver.quit()
                except:
                    pass
            return self.make_request(url, use_selenium=True)
    
    def _map_employment_to_job_type(self, employment: Optional[str], workplace: Optional[str]) -> Optional[str]:
        employment_upper = (employment or '').upper()
        workplace_upper = (workplace or '').upper()

        if workplace_upper in {'TELECOMMUTE', 'REMOTE'}:
            return 'REMOTE'
        if workplace_upper == 'HYBRID':
            return 'HYBRID'

        mapping = {
            'FULL_TIME': 'FULL_TIME',
            'PART_TIME': 'PART_TIME',
            'CONTRACT': 'FREELANCE',
            'CONTRACTOR': 'FREELANCE',
            'TEMPORARY': 'FREELANCE',
            'FREELANCE': 'FREELANCE',
        }
        return mapping.get(employment_upper)

