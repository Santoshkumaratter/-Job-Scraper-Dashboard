"""Dice Scraper"""
import json
import logging
import re
import urllib.parse
from typing import List, Dict, Optional

from ..utils.base_scraper import BaseScraper

logger = logging.getLogger(__name__)

class DiceScraper(BaseScraper):
    @property
    def portal_name(self) -> str:
        return "Dice"
    
    @property
    def base_url(self) -> str:
        return "https://www.dice.com"
    
    @property
    def requires_selenium(self) -> bool:
        return True
    
    def build_search_url(self, keyword: str) -> str:
        return f"{self.base_url}/jobs?q={keyword}"
    
    def scrape_jobs(self) -> List[Dict]:
        jobs = []
        for keyword in self.keywords:
            url = self.build_search_url(keyword)
            html = self.make_request(url, use_selenium=True)
            if not html:
                continue
            soup = self.parse_html(html)
            job_cards = soup.find_all('div', class_='card')
            for card in job_cards:
                try:
                    title_elem = card.find('h5')
                    if not title_elem:
                        continue
                    
                    job_title = self.clean_text(title_elem.get_text())
                    
                    # ✅ STRICT KEYWORD MATCHING
                    # ✅ DYNAMIC KEYWORD FILTER: Check ALL keywords, not just current one
                    keyword_match = False
                    if self.keywords:
                        keyword_match = any(
                            self.matches_keyword(job_title, kw) 
                            for kw in self.keywords
                        )
                    else:
                        keyword_match = True  # No keywords = accept all
                    
                    if not keyword_match:
                        continue
                    
                    company = self.clean_text(card.find('a', class_='companyName').get_text() if card.find('a', class_='companyName') else '')
                    company_url = None
                    
                    posted_text = card.find('span', class_='posted').get_text() if card.find('span', class_='posted') else ''
                    posted_date = self.parse_date(posted_text)
                    location_text = self.clean_text(card.find('span', class_='location').get_text() if card.find('span', class_='location') else '')

                    job_link = self.base_url + card.find('a', class_='card-title-link')['href'] if card.find('a', class_='card-title-link') else ''

                    detail = self._fetch_job_detail(job_link)
                    description = detail.get('description', '')
                    company_url = detail.get('company_url')
                    
                    if detail.get('company'):
                        company = detail['company']
                    if detail.get('posted_date'):
                        posted_date = detail['posted_date']
                    if detail.get('location'):
                        location_text = detail['location']
                    
                    # Fetch company profile/detail page for real company URL and size
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

                    real_job_type = self.detect_job_type(job_title, location_text, description)
                    if real_job_type == 'UNKNOWN':
                        mapped = self._map_employment(detail.get('employment_type'), detail.get('workplace_type'))
                        if mapped:
                            real_job_type = mapped

                    if not self.matches_job_type_filter(real_job_type):
                        continue

                    if not company:
                        continue

                    job_data = {
                        'job_title': job_title,
                        'company': company,
                        'company_url': company_url,
                        'company_size': detail.get('company_size', 'UNKNOWN'),
                        'company_profile_url': company_profile_url,  # Pass for ScraperManager enrichment
                        'market': detail.get('market', 'USA'),
                        'job_link': job_link,
                        'posted_date': posted_date,
                        'location': location_text,
                        'job_description': description,
                        'job_type': real_job_type,
                        'salary_range': detail.get('salary_range', ''),
                    }
                    
                    if self.should_include_job(posted_date):
                        jobs.append(job_data)
                except:
                    continue
        return jobs

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
            'CONTRACTOR': 'FREELANCE',
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

            hiring = data.get('hiringOrganization') or data.get('hiringorganization')
            if isinstance(hiring, dict):
                name = hiring.get('name')
                if name:
                    detail['company'] = self.clean_text(name)
                company_url = hiring.get('sameAs') or hiring.get('url')
                if company_url:
                    detail['company_url'] = company_url
            
            # Extract company profile URL from Dice job detail page using BaseScraper method
            company_profile_url = self._extract_company_profile_url(soup)
            if company_profile_url:
                detail['company_profile_url'] = company_profile_url

            job_location = data.get('jobLocation')
            if isinstance(job_location, list):
                job_location = job_location[0] if job_location else None
            if isinstance(job_location, dict):
                address = job_location.get('address')
                if isinstance(address, dict):
                    parts = [address.get('addressLocality'), address.get('addressRegion'), address.get('addressCountry')]
                    loc = ', '.join([self.clean_text(p) for p in parts if p])
                    if loc:
                        detail['location'] = loc
                        detail['market'] = 'USA' if 'UNITED STATES' in loc.upper() or 'USA' in loc.upper() else 'OTHER'

            employment = data.get('employmentType')
            if isinstance(employment, list):
                employment = employment[0] if employment else None
            detail['employment_type'] = employment

            workplace = data.get('jobLocationType') or data.get('workplaceType')
            if isinstance(workplace, list):
                workplace = workplace[0]
            detail['workplace_type'] = workplace

            salary = data.get('baseSalary')
            if isinstance(salary, dict):
                value = salary.get('value', {})
                min_value = value.get('minValue')
                max_value = value.get('maxValue')
                unit = value.get('unitText')
                if min_value and max_value:
                    detail['salary_range'] = f"{min_value}-{max_value}{' ' + unit if unit else ''}"

            break

        return detail

    def _fetch_company_profile(self, profile_url: str) -> Dict[str, Optional[str]]:
        """Fetch Dice company profile to get real company website URL and size"""
        profile_data = {}
        if not profile_url:
            return profile_data
        
        try:
            html = self.make_request(profile_url, use_selenium=True)
            if not html:
                return profile_data
            
            soup = self.parse_html(html)
            
            # Extract company website URL from Dice company profile
            website_selectors = [
                'a[href^="http"]:not([href*="dice.com"])',
                '.company-website a',
                'a.company-link[href^="http"]',
            ]
            
            for selector in website_selectors:
                website_link = soup.select_one(selector)
                if website_link:
                    href = website_link.get('href', '')
                    if href and href.startswith('http') and 'dice.com' not in href:
                        profile_data['website_url'] = href
                        logger.info(f"Found website URL from Dice company profile: {href}")
                        break
            
            # Extract company size from Dice company profile
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
                        logger.info(f"Found company size from Dice profile: {min_val}-{max_val}")
                        break
                    else:
                        count = int(match.group(1).replace(',', ''))
                        profile_data['company_size'] = self._parse_company_size_from_count(count)
                        logger.info(f"Found company size from Dice profile: {count}")
                        break
            
            # Extract company name from profile
            company_name_elem = soup.find('h1') or soup.find('h2', class_='company-name')
            if company_name_elem:
                company_name = self.clean_text(company_name_elem.get_text())
                if company_name:
                    profile_data['company_name'] = company_name
            
        except Exception as e:
            logger.debug(f"Error fetching Dice company profile from {profile_url}: {e}")
        
        return profile_data

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

