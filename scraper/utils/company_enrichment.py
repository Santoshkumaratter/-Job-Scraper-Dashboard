"""
Company Data Enrichment Service
Fetches real company information including size, domain, etc.
"""
import requests
import logging
import re
from typing import Dict, Optional
from django.conf import settings
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


class CompanyEnrichment:
    """Service to enrich company data with real information"""

    def __init__(self):
        self._domain_cache: Dict[str, Optional[str]] = {}
        self._company_cache: Dict[str, Dict] = {}
        self.clearbit_key: str = getattr(settings, 'CLEARBIT_API_KEY', '') or ''
    
    def get_company_size(self, company_name: str, company_url: Optional[str] = None) -> str:
        """
        Determine company size using REAL data sources only (no hardcoded values)
        
        Methods used (in order):
        1. Scrape from company website (real employee count from website)
        2. Clearbit API (if API key available - real employee metrics)
        
        Returns:
            Company size (SMALL, MEDIUM, LARGE, ENTERPRISE) or UNKNOWN if no real data found
        """
        if not company_name:
            return 'UNKNOWN'
        
        # Method 1: Try to scrape from company website (REAL DATA)
        effective_url = company_url
        if not effective_url:
            domain = self.get_company_domain(company_name)
            if domain:
                effective_url = f'https://{domain}'
        
        if effective_url:
            size = self._scrape_from_website(effective_url)
            if size != 'UNKNOWN':
                logger.info(f"Found company size for {company_name} via website scraping: {size}")
                return size

        # Method 2: Use Clearbit metrics if API key available (REAL DATA)
        domain_for_size = self._extract_domain(effective_url) if effective_url else None
        if not domain_for_size:
            domain_for_size = self.get_company_domain(company_name)
        
        if domain_for_size:
            size = self._size_from_clearbit(domain_for_size)
            if size:
                logger.info(f"Found company size for {company_name} via Clearbit: {size}")
                return size

        # No real data found - return UNKNOWN
        logger.debug(f"No real company size data found for {company_name}; returning UNKNOWN")
        return 'UNKNOWN'
    
    def _scrape_from_website(self, company_url: str) -> str:
        """Try to scrape company size from website"""
        try:
            response = requests.get(company_url, timeout=3, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            })
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'lxml')
                text = soup.get_text().lower()
                
                # Look for employee count mentions - multiple patterns
                # Enterprise (>100k)
                enterprise_patterns = [
                    '100,000+', '100000+', '100k+', '100,000', '100000',
                    'over 100,000', 'more than 100,000', '500000+', '1 million+',
                ]
                if any(p in text for p in enterprise_patterns):
                    return 'ENTERPRISE'
                
                # Large (10k-100k)
                large_patterns = [
                    '10,000+', '10000+', '10k+', '50,000+', '50000+',
                    '10,000-', '10000-', 'between 10,000', 'over 10,000',
                ]
                if any(p in text for p in large_patterns):
                    return 'LARGE'
                
                # Medium (1k-10k)
                medium_patterns = [
                    '1,000+', '1000+', '1k+', '5,000+', '5000+',
                    '1,000-', '1000-', 'between 1,000', 'over 1,000',
                ]
                if any(p in text for p in medium_patterns):
                    return 'MEDIUM'
                
                # Small (<1k) - check for specific ranges
                small_patterns = [
                    '100+ employees', '50+ employees', '200+ employees',
                    'under 500', 'less than 500', 'between 50-500',
                ]
                if any(p in text for p in small_patterns):
                    return 'SMALL'
                
                # Try to extract exact numbers using regex
                employee_count_pattern = re.search(r'(\d{1,3}(?:,\d{3})*)\s*(?:employees?|people|staff)', text)
                if employee_count_pattern:
                    count_str = employee_count_pattern.group(1).replace(',', '')
                    try:
                        count = int(count_str)
                        if count >= 100000:
                            return 'ENTERPRISE'
                        elif count >= 10000:
                            return 'LARGE'
                        elif count >= 1000:
                            return 'MEDIUM'
                        elif count >= 50:
                            return 'SMALL'
                    except ValueError:
                        pass
        
        except Exception as e:
            logger.debug(f"Could not scrape company size from {company_url}: {str(e)}")
        
        return 'UNKNOWN'

    # ===== Domain lookup =====
    def get_company_domain(self, company_name: str) -> Optional[str]:
        if not company_name:
            return None
        key = company_name.strip().lower()
        if key in self._domain_cache:
            return self._domain_cache[key]

        domain = self._fetch_domain_via_clearbit(company_name)
        if not domain and self.clearbit_key:
            company = self._fetch_clearbit_company_by_name(company_name)
            if company:
                domain = company.get('domain')
        if not domain:
            domain = self._fetch_domain_via_search(company_name)
        self._domain_cache[key] = domain
        return domain

    def _fetch_domain_via_clearbit(self, company_name: str) -> Optional[str]:
        try:
            resp = requests.get(
                'https://autocomplete.clearbit.com/v1/companies/suggest',
                params={'query': company_name},
                timeout=2,  # Faster timeout
            )
            resp.raise_for_status()
            suggestions = resp.json()
            if isinstance(suggestions, list):
                for item in suggestions:
                    domain = item.get('domain')
                    if domain:
                        return domain
        except Exception as e:
            logger.debug(f"Clearbit domain lookup failed for {company_name}: {e}")
        return None

    def _fetch_domain_via_search(self, company_name: str) -> Optional[str]:
        """Try multiple search strategies to find company domain"""
        if not company_name or not company_name.strip():
            return None
        
        # Try different search queries
        search_queries = [
            f"{company_name} official website",
            f"{company_name} company",
            f'"{company_name}" website',
        ]
        
        for query in search_queries:
            try:
                # Try Bing search (simpler than DDG)
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                    'Accept-Language': 'en-US,en;q=0.9',
                }
                # Use Bing's HTML search (no API key needed)
                bing_url = 'https://www.bing.com/search'
                params = {'q': query, 'count': 5}
                resp = requests.get(bing_url, params=params, headers=headers, timeout=3)
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, 'lxml')
                
                # Extract domains from search results
                for link in soup.select('ol#b_results li h2 a, div[class*="title"] a'):
                    href = link.get('href', '')
                    domain = self._extract_domain(href)
                    if domain and self._is_domain_candidate(domain):
                        # Verify domain actually belongs to company
                        if self._verify_company_domain(domain, company_name):
                            logger.info(f"Found verified domain via Bing for {company_name}: {domain}")
                            return domain
                        else:
                            logger.debug(f"Domain {domain} found but doesn't match {company_name}, skipping")
            except Exception as e:
                logger.debug(f"Bing search failed for '{query}': {e}")
                continue
        
        # Last resort: try domain guessing
        logger.debug(f"Trying domain guess for {company_name}")
        guess = self._guess_domain(company_name)
        if guess:
            logger.info(f"Guessed domain for {company_name}: {guess}")
        return guess

    def _is_domain_candidate(self, domain: str) -> bool:
        blocked = {
            'linkedin.com', 'indeed.com', 'glassdoor.com', 'monster.com', 'ziprecruiter.com',
            'google.com', 'bing.com', 'facebook.com', 'twitter.com', 'youtube.com',
            'wikipedia.org', 'github.com', 'medium.com', 'news.yahoo.com'
        }
        if not domain:
            return False
        domain = domain.lower()
        if any(b in domain for b in blocked):
            return False
        return True

    def _verify_company_domain(self, domain: str, company_name: str) -> bool:
        """Verify that a domain actually belongs to the company"""
        if not domain or not company_name:
            return False
        
        # Extract meaningful words from company name
        company_words = [re.sub(r'[^a-z0-9]', '', w) for w in company_name.lower().split() if len(w) >= 3]
        if not company_words:
            return False
        
        # Get main domain part (without TLD)
        domain_part = domain.split('.')[0].lower()
        domain_token = re.sub(r'[^a-z0-9]', '', domain_part)
        
        # STRICT: Check if domain contains company name words (exact or partial match)
        matches = False
        
        # For single word company names, require exact or very close match
        if len(company_words) == 1:
            company_word = company_words[0].lower()
            domain_lower = domain_token.lower()
            # Exact match or domain contains company word
            if company_word == domain_lower or company_word in domain_lower:
                matches = True
            # Also check if company word starts domain or vice versa
            elif domain_lower.startswith(company_word[:3]) or company_word.startswith(domain_lower[:3]):
                # Verify by checking website content for company name
                matches = self._verify_domain_by_content(domain, company_name, company_words)
        
        # For multi-word company names
        elif len(company_words) > 1:
            # Check if any meaningful word matches
            for word in company_words:
                if len(word) >= 4 and (word in domain_token or domain_token in word):
                    matches = True
                    break
            
            # Check acronym
            if not matches:
                acronym = ''.join(w[0] for w in company_words if w)
                if len(acronym) >= 2 and acronym.lower() == domain_token.lower():
                    matches = True
            
            # If still no match, verify by content
            if not matches:
                matches = self._verify_domain_by_content(domain, company_name, company_words)
        
        return matches
    
    def _verify_domain_by_content(self, domain: str, company_name: str, company_words: list) -> bool:
        """Verify domain by checking if company name appears in website content"""
        try:
            resp = requests.get(f'https://{domain}', timeout=3, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            })
            if resp.status_code == 200:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(resp.text, 'lxml')
                
                # Check page title
                title = soup.find('title')
                title_text = title.get_text().lower() if title else ''
                
                # Check page content (first 5000 chars to avoid false matches)
                body = soup.find('body')
                body_text = body.get_text().lower()[:5000] if body else ''
                
                # Check meta description
                meta_desc = soup.find('meta', {'name': 'description'})
                meta_text = meta_desc.get('content', '').lower() if meta_desc else ''
                
                # Combine text for checking
                all_text = f"{title_text} {meta_text} {body_text}"
                
                company_lower = company_name.lower()
                company_main_word = company_words[0].lower() if company_words else ''
                
                # Require company name or main word to appear prominently (in title or first part of content)
                if company_lower in title_text or company_main_word in title_text:
                    return True
                # Also check if main word appears early in content (more reliable)
                if company_main_word and len(company_main_word) >= 4:
                    if company_main_word in all_text[:3000]:  # Check first 3000 chars
                        # Additional check: word should appear at least 2 times or in prominent position
                        count = all_text[:3000].count(company_main_word)
                        if count >= 2 or company_main_word in title_text:
                            return True
                
                return False
        except Exception as e:
            logger.debug(f"Content verification failed for {domain}: {e}")
            return False
    
    def _guess_domain(self, company_name: str) -> Optional[str]:
        """Try common domain patterns based on company name"""
        if not company_name:
            return None
        
        # Clean company name
        cleaned = re.sub(r'[^\w\s]', '', company_name.lower())
        words = cleaned.split()
        
        # Try different patterns
        candidates = []
        
        # Pattern 1: Full company name (alphanumeric only)
        token = ''.join(ch for ch in cleaned if ch.isalnum())
        if len(token) >= 3:
            candidates.append(token)
        
        # Pattern 2: First word only
        if words and len(words[0]) >= 3:
            candidates.append(words[0])
        
        # Pattern 3: First letter of each word (acronym)
        if len(words) > 1:
            acronym = ''.join(w[0] for w in words if w)
            if len(acronym) >= 2:
                candidates.append(acronym)
        
        # Try candidates with common TLDs
        tlds = ['.com', '.io', '.co', '.ai', '.net', '.org']
        for candidate in candidates[:3]:  # Limit to avoid too many requests
            for tld in tlds:
                domain = f"{candidate}{tld}"
                try:
                    resp = requests.head(f"https://{domain}", timeout=2, allow_redirects=True)
                    if resp.status_code < 400:
                        # Verify domain actually belongs to company
                        if self._verify_company_domain(domain, company_name):
                            logger.info(f"Guessed and verified domain for {company_name}: {domain}")
                            return domain
                        else:
                            logger.debug(f"Guessed domain {domain} exists but doesn't match {company_name}")
                except Exception:
                    continue
        
        return None

    def _size_from_clearbit(self, domain: str) -> Optional[str]:
        if not self.clearbit_key or not domain:
            return None
        company = self._fetch_clearbit_company_by_domain(domain)
        if not company:
            return None
        metrics = company.get('metrics') or {}
        employees = metrics.get('employees')
        if not employees:
            return None
        try:
            employees = int(employees)
        except Exception:
            return None
        if employees < 50:
            return 'SMALL'
        if employees < 250:
            return 'MEDIUM'
        if employees < 1000:
            return 'LARGE'
        return 'ENTERPRISE'

    def _fetch_clearbit_company_by_domain(self, domain: str) -> Optional[Dict]:
        if not self.clearbit_key:
            return None
        key = f"domain:{domain.lower()}"
        if key in self._company_cache:
            return self._company_cache[key]
        data = self._clearbit_request('https://company.clearbit.com/v2/companies/find', {'domain': domain})
        self._company_cache[key] = data
        return data

    def _fetch_clearbit_company_by_name(self, company_name: str) -> Optional[Dict]:
        if not self.clearbit_key:
            return None
        key = f"name:{company_name.lower()}"
        if key in self._company_cache:
            return self._company_cache[key]
        data = self._clearbit_request('https://company.clearbit.com/v2/companies/find', {'name': company_name})
        self._company_cache[key] = data
        return data

    def _clearbit_request(self, url: str, params: Dict[str, str]) -> Optional[Dict]:
        try:
            headers = {'Authorization': f"Bearer {self.clearbit_key}"}
            resp = requests.get(url, params=params, headers=headers, timeout=3)
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.debug(f"Clearbit request failed: {e}")
            return None

    def _extract_domain(self, url: str) -> Optional[str]:
        try:
            if not url:
                return None
            from urllib.parse import urlparse, parse_qs
            parsed = urlparse(url)
            # DuckDuckGo wraps results as /l/?uddg=<encoded-url>
            if parsed.netloc.endswith('duckduckgo.com') and parsed.path.startswith('/l/'):
                qs = parse_qs(parsed.query)
                inner = qs.get('uddg', [None])[0]
                if inner:
                    return self._extract_domain(inner)
            domain = parsed.netloc
            if domain.startswith('www.'):
                domain = domain[4:]
            return domain or None
        except Exception:
            return None

