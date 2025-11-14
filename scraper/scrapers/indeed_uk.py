"""
Indeed UK Job Scraper
"""
import json
import logging
import re
import urllib.parse
from typing import List, Dict, Optional

from ..utils.base_scraper import BaseScraper

logger = logging.getLogger(__name__)


class IndeedUKScraper(BaseScraper):
    """Scraper for Indeed UK"""
    
    @property
    def portal_name(self) -> str:
        return "Indeed UK"
    
    @property
    def base_url(self) -> str:
        return "https://uk.indeed.com"
    
    @property
    def requires_selenium(self) -> bool:
        return True
    
    def build_search_url(self, keyword: str) -> str:
        """Build Indeed UK search URL"""
        params = {
            'q': keyword,
            'l': self.location if self.location != 'ALL' else '',
            'sort': 'date'
        }
        
        if self.job_type == 'REMOTE':
            params['sc'] = '0kf:attr(DSQF7);'
        elif self.job_type == 'FULL_TIME':
            params['jt'] = 'fulltime'
        
        if self.time_filter == '24H':
            params['fromage'] = '1'
        elif self.time_filter == '3D':
            params['fromage'] = '3'
        elif self.time_filter == '7D':
            params['fromage'] = '7'
        
        query_string = urllib.parse.urlencode(params)
        return f"{self.base_url}/jobs?{query_string}"
    
    def scrape_jobs(self) -> List[Dict]:
        """Scrape jobs from Indeed UK with pagination for maximum jobs"""
        jobs = []
        seen_job_ids = set()  # Deduplicate across pages
        
        for keyword in self.keywords:
            base_url = self.build_search_url(keyword)
            
            # Fetch multiple pages for maximum jobs (500+ jobs)
            max_pages = 50  # Fetch up to 50 pages (10 jobs per page = 500+ jobs)
            for page_num in range(max_pages):
                try:
                    # Build URL with pagination
                    if page_num == 0:
                        url = base_url
                    else:
                        # Indeed uses start parameter for pagination (10 jobs per page)
                        start = page_num * 10
                        url = f"{base_url}&start={start}"
                    
                    logger.info(f"Indeed UK: Fetching page {page_num + 1}/{max_pages} for keyword '{keyword}'")
                    html = self.make_request(url, use_selenium=True)
                    if not html:
                        logger.warning(f"Indeed UK: No HTML returned for page {page_num + 1}")
                        break  # Stop if page fails
                    
                    soup = self.parse_html(html)
                    
                    # Find job cards - try multiple selectors
                    job_cards = []
                    selectors = [
                        ('div', {'class': 'job_seen_beacon'}),
                        ('div', {'class': 'jobCard'}),
                        ('div', {'class': 'job'}),
                        ('div', {'class': lambda x: x and 'job' in ' '.join(x).lower()}),
                    ]
                    
                    for tag, attrs in selectors:
                        found = soup.find_all(tag, attrs)
                        if found:
                            job_cards.extend(found)
                            break
                    
                    # ✅ USE MultiApproachExtractor as fallback if standard selectors fail
                    if not job_cards:
                        logger.info(f"Indeed UK: Standard selectors failed, trying MultiApproachExtractor...")
                        from ..utils.multi_approach_scraper import MultiApproachExtractor
                        job_cards = MultiApproachExtractor.extract_jobs_from_soup(soup, self.base_url, self.keywords)
                    
                    if not job_cards:
                        logger.info(f"Indeed UK: No more job cards found on page {page_num + 1}, stopping pagination")
                        break  # No more jobs on this page
                    
                    logger.info(f"Indeed UK: Found {len(job_cards)} job cards on page {page_num + 1}")
                    
                    page_jobs_count = 0
                    for card in job_cards:
                        try:
                            # Extract job information
                            title_elem = card.find('h2', class_='jobTitle')
                            if not title_elem:
                                continue
                            
                            job_title = self.clean_text(title_elem.get_text())
                            job_link_elem = title_elem.find('a')
                            job_id = job_link_elem.get('data-jk', '') if job_link_elem else ''
                            job_link = f"{self.base_url}/viewjob?jk={job_id}" if job_id else ''
                            
                            # Company name
                            company_elem = card.find('span', class_='companyName')
                            company = self.clean_text(company_elem.get_text()) if company_elem else ''
                            
                            # Location
                            location_elem = card.find('div', class_='companyLocation')
                            location = self.clean_text(location_elem.get_text()) if location_elem else ''
                            
                            # Posted date - try multiple selectors
                            posted_date = None
                            date_elem = card.find('span', class_='date') or card.find('span', class_='dateText')
                            if date_elem:
                                date_text = date_elem.get_text()
                                if date_text:
                                    posted_date = self.parse_date(date_text)
                            
                            # Also try extracting from attributes/data
                            if not posted_date:
                                date_attr = card.get('data-date', '') or card.get('data-posted-date', '')
                                if date_attr:
                                    posted_date = self.parse_date(date_attr)
                            
                            # Check time filter
                            if not self.should_include_job(posted_date):
                                continue
                            
                            # ✅ REMOVED STRICT KEYWORD CHECK - Extract all jobs
                            
                            detail = self._fetch_job_detail(job_link)
                            description = detail.get('description', '')
                            if detail.get('company'):
                                company = detail['company']
                            company_url = detail.get('company_url')
                            
                            # Fetch company profile/detail page for real company URL and size (if available)
                            company_profile_url = detail.get('company_profile_url')
                            if company_profile_url:
                                profile_data = self._fetch_company_profile(company_profile_url)
                                if profile_data:
                                    # Use real website URL from company profile
                                    if profile_data.get('website_url'):
                                        company_url = profile_data['website_url']
                                    # Use real company size from profile
                                    if profile_data.get('company_size'):
                                        detail['company_size'] = profile_data['company_size']
                                    # Update company name if different
                                    if profile_data.get('company_name'):
                                        company = profile_data['company_name']
                            
                            if detail.get('location'):
                                location = detail['location']
                            if detail.get('posted_date'):
                                posted_date = detail['posted_date']

                            real_job_type = self.detect_job_type(job_title, location, description)
                            if real_job_type == 'UNKNOWN':
                                mapped = self._map_employment(detail.get('employment_type'), detail.get('workplace_type'))
                                if mapped:
                                    real_job_type = mapped

                            if not self.matches_job_type_filter(real_job_type):
                                continue

                            # If still no company, infer from job link
                            if not company or company.lower() in ['unknown', 'company not listed', '']:
                                try:
                                    from urllib.parse import urlparse
                                    domain = urlparse(job_link).netloc
                                    if domain:
                                        company = domain.replace('www.', '').split('.')[0].title()
                                except:
                                    company = 'Company Not Listed'

                            # ONLY require job_title (company can be inferred)
                            if job_title:
                                job_data = {
                                    'job_title': job_title,
                                    'company': company if company else 'Company Not Listed',
                                    'company_url': company_url or '',
                                    'company_size': detail.get('company_size', '') if detail.get('company_size') not in ['UNKNOWN', 'Unknown', ''] else '',
                                    'company_profile_url': company_profile_url or None,
                                    'market': self._infer_market(location),
                                    'job_link': job_link,
                                    'posted_date': posted_date,
                                    'location': location if location else '',
                                    'job_description': description if description else '',
                                    'job_type': real_job_type,
                                    'salary_range': detail.get('salary_range', ''),
                                }
                                
                                # Deduplicate by job ID
                                job_id_val = job_data.get('job_link', '').split('jk=')[-1] if 'jk=' in job_data.get('job_link', '') else ''
                                if job_id_val and job_id_val in seen_job_ids:
                                    continue
                                seen_job_ids.add(job_id_val)
                                
                                jobs.append(job_data)
                            page_jobs_count += 1
                            
                            # Stop if we've reached the maximum per keyword
                            if len(jobs) >= self.max_jobs_per_keyword:
                                logger.info(f"Indeed UK: Reached maximum jobs ({self.max_jobs_per_keyword}) for keyword '{keyword}'")
                                break
                            
                        except Exception as e:
                            logger.error(f"Error parsing job card: {str(e)}")
                            continue
                    
                    # If no new jobs found on this page, stop pagination
                    if page_jobs_count == 0:
                        logger.info(f"Indeed UK: No new jobs found on page {page_num + 1}, stopping pagination")
                        break
                    
                    # Stop if we've reached the maximum per keyword
                    if len(jobs) >= self.max_jobs_per_keyword:
                        break
                
                except Exception as e:
                    logger.error(f"Indeed UK: Error fetching page {page_num + 1}: {str(e)}")
                    break  # Stop pagination on error
            
            logger.info(f"Indeed UK: Total jobs found for keyword '{keyword}': {len(jobs)}")
        
        return jobs

    def _infer_market(self, location: str) -> str:
        loc_upper = (location or '').upper()
        if 'UNITED KINGDOM' in loc_upper or 'UK' in loc_upper:
            return 'UK'
        if 'UNITED STATES' in loc_upper or 'USA' in loc_upper:
            return 'USA'
        return 'OTHER'

    def _map_employment(self, employment: Optional[str], workplace: Optional[str]) -> Optional[str]:
        employment_upper = (employment or '').upper()
        workplace_upper = (workplace or '').upper()

        if workplace_upper in {'REMOTE', 'TELECOMMUTE'}:
            return 'REMOTE'
        if workplace_upper == 'HYBRID':
            return 'HYBRID'

        mapping = {
            'FULLTIME': 'FULL_TIME',
            'FULL-TIME': 'FULL_TIME',
            'PARTTIME': 'PART_TIME',
            'PART-TIME': 'PART_TIME',
            'CONTRACT': 'FREELANCE',
            'TEMPORARY': 'FREELANCE',
        }
        return mapping.get(employment_upper)

    def _fetch_job_detail(self, job_link: str) -> Dict[str, Optional[str]]:
        detail: Dict[str, Optional[str]] = {}
        if not job_link:
            return detail

        html = self.make_request(job_link, use_selenium=True)
        if not html:
            return detail

        soup = self.parse_html(html)

        desc_elem = soup.find('div', id='jobDescriptionText')
        if desc_elem:
            detail['description'] = self.clean_text(desc_elem.get_text())

        # Try to extract posted date from visible elements first
        if 'posted_date' not in detail or not detail['posted_date']:
            # Look for date in various locations
            date_selectors = [
                'span[class*="date"]',
                'div[class*="date"]',
                'span.dateText',
                'div.jobsearch-JobMetadataFooter',
            ]
            for selector in date_selectors:
                date_elem = soup.select_one(selector)
                if date_elem:
                    date_text = date_elem.get_text()
                    parsed_date = self.parse_date(date_text)
                    if parsed_date:
                        detail['posted_date'] = parsed_date
                        break

        # Parse JSON-LD for structured data
        for script in soup.find_all('script', type='application/ld+json'):
            try:
                data = json.loads(script.get_text(strip=True) or '{}')
            except Exception:
                continue
            
            # Handle both JobPosting and single object
            job_data = data
            if isinstance(data, dict) and '@graph' in data:
                # Schema.org might wrap in @graph
                graph = data.get('@graph', [])
                for item in graph:
                    if isinstance(item, dict) and item.get('@type') == 'JobPosting':
                        job_data = item
                        break
            
            if not isinstance(job_data, dict) or job_data.get('@type') != 'JobPosting':
                continue

            hiring = job_data.get('hiringOrganization') or job_data.get('hiringorganization')
            if isinstance(hiring, dict):
                name = hiring.get('name')
                if name:
                    detail['company'] = self.clean_text(name)
                company_url = hiring.get('sameAs') or hiring.get('url')
                if company_url:
                    detail['company_url'] = company_url
                # Try to get company size from hiringOrganization
                if 'numberOfEmployees' in hiring:
                    employees = hiring.get('numberOfEmployees')
                    if isinstance(employees, (int, str)):
                        detail['company_size'] = self._parse_company_size_from_count(employees)
                    elif isinstance(employees, dict):
                        # Schema.org Range format
                        min_val = employees.get('minValue')
                        max_val = employees.get('maxValue')
                        if min_val and max_val:
                            detail['company_size'] = self._parse_company_size_from_range(min_val, max_val)

            # Extract company profile URL from job detail page using BaseScraper method
            company_profile_url = self._extract_company_profile_url(soup)
            if company_profile_url:
                detail['company_profile_url'] = company_profile_url
            
            # Extract company size from HTML if not in JSON-LD
            if 'company_size' not in detail:
                company_size = self._extract_company_size_from_html(soup)
                if company_size:
                    detail['company_size'] = company_size

            # Extract date - try multiple formats
            if 'posted_date' not in detail or not detail['posted_date']:
                date_posted = (
                    job_data.get('datePosted') or 
                    job_data.get('dateposted') or 
                    job_data.get('date_posted')
                )
                if date_posted:
                    # Handle ISO format dates (2024-01-15T10:00:00Z)
                    if isinstance(date_posted, str) and 'T' in date_posted:
                        try:
                            from datetime import datetime
                            # Remove timezone info if present
                            date_str = date_posted.replace('Z', '').split('T')[0]
                            dt = datetime.strptime(date_str, '%Y-%m-%d')
                            detail['posted_date'] = dt.date()
                        except:
                            parsed = self.parse_date(date_posted)
                            if parsed:
                                detail['posted_date'] = parsed
                    elif isinstance(date_posted, str):
                        parsed = self.parse_date(date_posted)
                        if parsed:
                            detail['posted_date'] = parsed

            employment = job_data.get('employmentType')
            if isinstance(employment, list):
                employment = employment[0] if employment else None
            detail['employment_type'] = employment

            workplace = job_data.get('jobLocationType') or job_data.get('workplaceType')
            if isinstance(workplace, list):
                workplace = workplace[0]
            detail['workplace_type'] = workplace

            job_location = job_data.get('jobLocation')
            if isinstance(job_location, list):
                job_location = job_location[0] if job_location else None
            if isinstance(job_location, dict):
                address = job_location.get('address')
                if isinstance(address, dict):
                    parts = [address.get('addressLocality'), address.get('addressRegion'), address.get('addressCountry')]
                    location = ', '.join([self.clean_text(p) for p in parts if p])
                    if location:
                        detail['location'] = location

            salary = job_data.get('baseSalary')
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
            return ''
    
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
            return ''
    
    def _extract_company_size_from_html(self, soup) -> Optional[str]:
        """Extract company size from Indeed HTML"""
        try:
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
                        min_val = int(match.group(1).replace(',', ''))
                        max_val = int(match.group(2).replace(',', ''))
                        return self._parse_company_size_from_range(min_val, max_val)
                    else:
                        count = int(match.group(1).replace(',', ''))
                        return self._parse_company_size_from_count(count)
            
            # Try Indeed-specific selectors
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

    def _fetch_company_profile(self, profile_url: str) -> Dict[str, Optional[str]]:
        """Fetch Indeed company profile to get real company website URL and size"""
        profile_data = {}
        if not profile_url:
            return profile_data
        
        try:
            html = self.make_request(profile_url, use_selenium=True)
            if not html:
                return profile_data
            
            soup = self.parse_html(html)
            
            # Extract company website URL from Indeed company profile
            website_selectors = [
                'a[href^="http"]:not([href*="indeed.com"])',
                '.company-website a',
                'a.company-link[href^="http"]',
            ]
            
            for selector in website_selectors:
                website_link = soup.select_one(selector)
                if website_link:
                    href = website_link.get('href', '')
                    if href and href.startswith('http') and 'indeed.com' not in href:
                        profile_data['website_url'] = href
                        logger.info(f"Found website URL from Indeed company profile: {href}")
                        break
            
            # Extract company size from Indeed company profile
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
                        profile_data['company_size'] = self._parse_company_size_from_range(min_val, max_val)
                        logger.info(f"Found company size from Indeed profile: {min_val}-{max_val}")
                        break
                    else:
                        count = int(match.group(1).replace(',', ''))
                        profile_data['company_size'] = self._parse_company_size_from_count(count)
                        logger.info(f"Found company size from Indeed profile: {count}")
                        break
            
            # Extract company name from profile
            company_name_elem = soup.find('h1') or soup.find('h2', class_='company-name')
            if company_name_elem:
                company_name = self.clean_text(company_name_elem.get_text())
                if company_name:
                    profile_data['company_name'] = company_name
            
        except Exception as e:
            logger.debug(f"Error fetching Indeed company profile from {profile_url}: {e}")
        
        return profile_data

