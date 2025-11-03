"""
LinkedIn Jobs Scraper
"""
from typing import List, Dict, Optional
from ..utils.base_scraper import BaseScraper
import urllib.parse
import json
import re
import logging

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
            'sortBy': 'DD'  # Date descending
        }
        
        if self.job_type == 'REMOTE':
            params['f_WT'] = '2'  # Remote
        elif self.job_type == 'HYBRID':
            params['f_WT'] = '3'  # Hybrid
        
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

        for keyword in self.keywords:
            url = self.build_search_url(keyword)
            logger.info(f"LinkedIn: Fetching jobs for keyword '{keyword}' from {url}")
            html = self.make_request(url, use_selenium=True)
            if not html:
                logger.warning(f"LinkedIn: No HTML returned for keyword '{keyword}'")
                continue
            
            # Check if we got a login page - be more specific to avoid false positives
            html_lower = html.lower()
            # Only treat as login page if we see specific login page indicators AND NO job-related content
            has_login_indicators = ('sign in' in html_lower or 'join linkedin' in html_lower or 'welcome to linkedin' in html_lower)
            has_job_content = ('base-card' in html_lower or 'jobs-search' in html_lower or '/jobs/view/' in html_lower or 'job-result' in html_lower)
            
            if has_login_indicators and not has_job_content:
                logger.warning(f"LinkedIn: Got login/blocked page for keyword '{keyword}'. LinkedIn may require authentication.")
                logger.info(f"LinkedIn: Still attempting to parse jobs in case there's some content...")
                # Don't skip - try to find jobs anyway in case page has mixed content
            elif has_job_content:
                logger.info(f"LinkedIn: Found job content on page despite potential login indicators")

            soup = self.parse_html(html)
            # LinkedIn uses multiple possible selectors for job cards
            # Try each selector and combine results
            job_cards = []
            selectors = [
                soup.find_all('div', class_='base-card'),
                soup.find_all('div', class_='job-search-card'),
                soup.find_all('li', class_='jobs-search-results__list-item'),
                soup.find_all('div', {'data-job-id': True}),
                soup.select('div[data-job-id]'),
                soup.select('li.jobs-search-results__list-item'),
                soup.find_all('div', class_='job-result-card'),
                soup.find_all('div', class_='result-card'),
            ]
            
            for cards in selectors:
                if cards:
                    job_cards.extend(cards)
                    break  # Use first working selector
            
            # Remove duplicates while preserving order
            seen_ids = set()
            unique_cards = []
            for card in job_cards:
                card_id = card.get('data-job-id') or card.get('id') or str(card)
                if card_id not in seen_ids:
                    seen_ids.add(card_id)
                    unique_cards.append(card)
            job_cards = unique_cards
            
            if not job_cards:
                # Try to find any job-related elements
                logger.warning(f"LinkedIn: No job cards found with standard selectors for keyword '{keyword}'. Checking page content...")
                
                # Try alternative approach - look for links to job detail pages directly
                job_links = soup.find_all('a', href=re.compile(r'/jobs/view/'))
                if job_links:
                    logger.info(f"LinkedIn: Found {len(job_links)} job links directly. Extracting jobs from links...")
                    # Create virtual cards from links
                    for link in job_links[:50]:  # Limit to first 50 to avoid too many
                        try:
                            href = link.get('href', '')
                            if href:
                                # Create a minimal card-like structure from the link
                                parent = link.find_parent(['div', 'li', 'article'])
                                if parent:
                                    job_cards.append(parent)
                        except:
                            continue
                
                if not job_cards:
                    # Log page structure for debugging
                    all_divs = soup.find_all('div', limit=20)
                    logger.debug(f"LinkedIn: Found {len(all_divs)} divs on page. First few classes: {[d.get('class') for d in all_divs[:5]]}")
                    # Check for JSON-LD data
                    json_scripts = soup.find_all('script', type='application/ld+json')
                    if json_scripts:
                        logger.info(f"LinkedIn: Found {len(json_scripts)} JSON-LD scripts. May contain job data.")
            
            for card in job_cards:
                try:
                    # Try multiple selectors for title
                    title_elem = (
                        card.find('h3', class_='base-search-card__title') or
                        card.find('h3', class_='job-result-card__title') or
                        card.find('h2', class_='job-result-card__title') or
                        card.find('a', class_='job-result-card__title-link') or
                        card.find('a', href=re.compile(r'/jobs/view/')) or
                        card.select_one('h3, h2, a[href*="/jobs/view/"]')
                    )
                    if not title_elem:
                        continue
                    job_title = self.clean_text(title_elem.get_text())

                    # Try multiple selectors for job link
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
                    # Make sure it's a full URL
                    if job_link.startswith('/'):
                        job_link = urllib.parse.urljoin(self.base_url, job_link)

                    # Try multiple selectors for company
                    company_elem = (
                        card.find('h4', class_='base-search-card__subtitle') or
                        card.find('h4', class_='job-result-card__subtitle-link') or
                        card.find('a', class_='job-result-card__subtitle-link') or
                        card.select_one('h4, a[href*="/company/"]')
                    )
                    company = self.clean_text(company_elem.get_text()) if company_elem else ''

                    # Try multiple selectors for location
                    location_elem = (
                        card.find('span', class_='job-search-card__location') or
                        card.find('span', class_='job-result-card__location') or
                        card.select_one('span[class*="location"]')
                    )
                    location = self.clean_text(location_elem.get_text()) if location_elem else ''

                    date_elem = card.find('time')
                    posted_date = self.parse_date(date_elem.get('datetime', '')) if date_elem else None

                    # Enforce keyword filter strictly
                    if not self.matches_keyword(job_title, keyword):
                        continue

                    # Initialize variables
                    company_url = None
                    company_profile_url = None
                    
                    # Extract LinkedIn company profile URL from card (not website URL)
                    if company_elem:
                        company_link = company_elem.find('a')
                        if company_link and company_link.has_attr('href'):
                            href = company_link['href']
                            # LinkedIn company profile URLs are like /company/perplexity or /company/...
                            if '/company/' in href:
                                company_profile_url = urllib.parse.urljoin(self.base_url, href)

                    detail = self._fetch_job_detail(job_link)
                    description = detail.get('description', '')

                    if detail.get('company'):
                        company = detail['company']
                    # Use company profile URL from detail if available, otherwise from card
                    if detail.get('company_profile_url'):
                        company_profile_url = detail['company_profile_url']
                    if detail.get('company_url'):
                        company_url = detail['company_url']  # Website URL from profile
                    if detail.get('location'):
                        location = detail['location']
                    if detail.get('posted_date'):
                        posted_date = detail['posted_date']
                    
                    # Note: Company profile fetching moved to ScraperManager for better performance
                    # This avoids fetching company profile for every job here (too slow)
                    # ScraperManager will fetch company profile automatically if company_profile_url is set

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
                        'company_url': company_url,  # Will be enriched by ScraperManager from company profile
                        'company_size': detail.get('company_size', 'UNKNOWN'),  # Will be enriched by ScraperManager from company profile
                        'company_profile_url': company_profile_url,  # Pass to ScraperManager for enrichment
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
                    detail['company_url'] = company_url  # This might be website URL
            
            # Extract company profile URL from job detail page using BaseScraper method
            company_profile_url = self._extract_company_profile_url(soup)
            if company_profile_url:
                detail['company_profile_url'] = company_profile_url
            
            # Try to get company size from hiringOrganization (fallback)
            if isinstance(hiring, dict) and 'numberOfEmployees' in hiring:
                employees = hiring.get('numberOfEmployees')
                if isinstance(employees, (int, str)):
                    detail['company_size'] = self._parse_company_size_from_count(employees)
                elif isinstance(employees, dict):
                    # Schema.org Range format
                    min_val = employees.get('minValue')
                    max_val = employees.get('maxValue')
                    if min_val and max_val:
                        detail['company_size'] = self._parse_company_size_from_range(min_val, max_val)

            # Extract company size from HTML if not in JSON-LD
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
                # Remove commas and extract number
                count = int(''.join(filter(str.isdigit, count)))
            else:
                count = int(count)
            
            if count >= 100000:
                return 'ENTERPRISE'
            elif count >= 10000:
                return 'LARGE'
            elif count >= 1000:
                return 'MEDIUM'
            elif count >= 50:
                return 'SMALL'
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
            
            # Use max for categorization if available, otherwise min
            if isinstance(max_val, str):
                max_val = int(''.join(filter(str.isdigit, max_val)))
            else:
                max_val = int(max_val)
            
            # Use average for better categorization
            avg = (min_val + max_val) / 2
            
            if avg >= 100000:
                return 'ENTERPRISE'
            elif avg >= 10000:
                return 'LARGE'
            elif avg >= 1000:
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
            html = self.make_request(profile_url, use_selenium=True)
            if not html:
                return profile_data
            
            soup = self.parse_html(html)
            
            # Extract company website URL from profile
            # Look for website link in multiple locations
            # LinkedIn shows website in "About us" section as external link
            website_selectors = [
                'a[data-control-name="topcard_website"]',
                'a[href^="http"]:not([href*="linkedin.com"])',
                '.org-top-card-summary-info-list__info-item a[href^="http"]',
                'dd.org-top-card-summary-info-list__info-item a[href^="http"]',
                'a[href*="website"]',
            ]
            
            for selector in website_selectors:
                website_link = soup.select_one(selector)
                if website_link:
                    href = website_link.get('href', '')
                    # Clean LinkedIn tracking URLs
                    if 'linkedin.com/redirect' in href or '/redirect' in href:
                        # Extract actual URL from redirect
                        from urllib.parse import parse_qs, urlparse
                        parsed = urlparse(href)
                        params = parse_qs(parsed.query)
                        if 'url' in params:
                            href = params['url'][0]
                    if href and href.startswith('http') and 'linkedin.com' not in href:
                        profile_data['website_url'] = href
                        logger.info(f"Found website URL from LinkedIn profile: {href}")
                        break
            
            # Extract company size from profile - multiple methods
            # Method 1: Look in structured data (JSON-LD)
            for script in soup.find_all('script', type='application/ld+json'):
                try:
                    data = json.loads(script.get_text(strip=True) or '{}')
                    if isinstance(data, dict):
                        # Look for Organization type
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
            
            # Method 2: Extract from HTML text patterns
            if 'company_size' not in profile_data:
                all_text = soup.get_text()
                size_patterns = [
                    r'company\s*size[:\s]+(\d{1,3}(?:,\d{3})*)\s*-\s*(\d{1,3}(?:,\d{3})*)\s*employees?',
                    r'(\d{1,3}(?:,\d{3})*)\s*-\s*(\d{1,3}(?:,\d{3})*)\s*employees?',
                    r'view\s*all\s*(\d{1,3}(?:,\d{3})*)\s*employees?',
                    r'(\d{1,3}(?:,\d{3})*)\s*employees?',
                ]
            
            for pattern in size_patterns:
                match = re.search(pattern, all_text, re.IGNORECASE)
                if match:
                    if len(match.groups()) == 2:
                        # Range format like "201-500 employees"
                        min_val = int(match.group(1).replace(',', ''))
                        max_val = int(match.group(2).replace(',', ''))
                        profile_data['company_size'] = self._parse_company_size_from_range(min_val, max_val)
                        break
                    else:
                        # Single count like "1,831 employees"
                        count = int(match.group(1).replace(',', ''))
                        profile_data['company_size'] = self._parse_company_size_from_count(count)
                        break
            
            # Extract company name from profile
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
            # LinkedIn shows company size in various formats
            # Pattern 1: "11-50 employees" or "201-500 employees"
            text = soup.get_text()
            
            # Look for employee count patterns
            patterns = [
                r'(\d{1,3}(?:,\d{3})*)\s*-\s*(\d{1,3}(?:,\d{3})*)\s*employees?',
                r'(\d{1,3}(?:,\d{3})*)\+?\s*employees?',
                r'company\s*size[:\s]+(\d{1,3}(?:,\d{3})*)\s*-\s*(\d{1,3}(?:,\d{3})*)',
            ]
            
            for pattern in patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    if len(match.groups()) == 2:
                        # Range format
                        min_val = int(match.group(1).replace(',', ''))
                        max_val = int(match.group(2).replace(',', ''))
                        return self._parse_company_size_from_range(min_val, max_val)
                    else:
                        # Single count
                        count = int(match.group(1).replace(',', ''))
                        return self._parse_company_size_from_count(count)
            
            # Try to find in specific LinkedIn elements
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

