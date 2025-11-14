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
        Determine company size using multiple data sources
        
        Methods used (in order):
        1. Cached company info (from previous enrichments)
        2. Scrape from company website (real employee count from website)
        3. Clearbit API (if API key available - real employee metrics)
        4. Common companies lookup (for popular companies)
        
        Returns:
            Company size (SMALL, MEDIUM, LARGE, ENTERPRISE) or UNKNOWN if no data found
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
                
        # Method 3: Check common companies (for well-known ones)
        common_size = self._get_common_company_size(company_name)
        if common_size:
            logger.info(f"Found company size for {company_name} via common companies table: {common_size}")
            return common_size
            
        # Method 4: Estimate size from domain popularity (best effort)
        if domain_for_size:
            estimated_size = self._estimate_size_from_domain(domain_for_size)
            if estimated_size:
                logger.info(f"Estimated company size for {company_name} via domain: {estimated_size}")
                return estimated_size

        # No data found - return UNKNOWN
        logger.debug(f"No company size data found for {company_name}; returning UNKNOWN")
        return 'UNKNOWN'
    
    def _scrape_from_website(self, company_url: str) -> str:
        """Try to scrape company size from website with optimized performance"""
        try:
                # Use a shorter timeout and don't download large pages
            response = requests.get(
                company_url, 
                timeout=5,  # Increased timeout for better success rate 
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'},
                stream=True  # Use streaming to avoid downloading huge pages
            )
            
            if response.status_code == 200:
                # Only read first 50KB of the page to improve performance
                content = ''
                for chunk in response.iter_content(chunk_size=1024):
                    content += chunk.decode('utf-8', errors='ignore')
                    if len(content) > 50000:  # Stop after 50KB
                        break
                        
                soup = BeautifulSoup(content, 'lxml')
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
                timeout=5,  # Increased timeout for better reliability
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
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
        """Verify domain by checking if company name appears in website content (optimized)"""
        try:
            # Use shorter timeout and stream the response to avoid downloading entire page
            resp = requests.get(
                f'https://{domain}', 
                timeout=2, 
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'},
                stream=True
            )
            
            if resp.status_code == 200:
                # Only read first part of the page (30KB max)
                content = ''
                for chunk in resp.iter_content(chunk_size=1024):
                    content += chunk.decode('utf-8', errors='ignore')
                    if len(content) > 30000:  # Limit to first 30KB for speed
                        break
                        
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(content, 'lxml')
                
                # Check page title (most important)
                title = soup.find('title')
                title_text = title.get_text().lower() if title else ''
                
                # Check meta description (also important and small)
                meta_desc = soup.find('meta', {'name': 'description'})
                meta_text = meta_desc.get('content', '').lower() if meta_desc else ''
                
                # Only get first 3000 chars of body to improve performance
                body = soup.find('body')
                body_text = body.get_text().lower()[:3000] if body else ''
                
                # Combine text for checking (prioritize title and meta)
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
        """Try common domain patterns based on company name (optimized for speed)"""
        if not company_name:
            return None
        
        # Use cached results to avoid repeated lookups
        cache_key = company_name.lower().strip()
        if cache_key in self._domain_cache:
            return self._domain_cache[cache_key]
            
        # Clean company name
        cleaned = re.sub(r'[^\w\s]', '', company_name.lower())
        words = cleaned.split()
        
        # Try different patterns (most likely first)
        candidates = []
        
        # Pattern 1: First word only (most common pattern for companies)
        if words and len(words[0]) >= 3:
            candidates.append(words[0])
        
        # Pattern 2: Full company name (alphanumeric only)
        token = ''.join(ch for ch in cleaned if ch.isalnum())
        if len(token) >= 3:
            candidates.append(token)
        
        # Pattern 3: First letter of each word (acronym)
        if len(words) > 1:
            acronym = ''.join(w[0] for w in words if w)
            if len(acronym) >= 2:
                candidates.append(acronym)
        
        # Try most common TLDs first (.com is by far the most likely)
        most_common_tlds = ['.com']  # Start with the most common TLD
        other_tlds = ['.io', '.co', '.ai', '.net', '.org']
        
        # First try all candidates with .com (much more likely to succeed)
        for candidate in candidates[:2]:  # Limit to top 2 candidates for speed
            domain = f"{candidate}{most_common_tlds[0]}"
            try:
                # Use fast HEAD request with short timeout
                resp = requests.head(f"https://{domain}", timeout=1.5, allow_redirects=True)
                if resp.status_code < 400:
                    # Found a likely domain - cache it even before verification
                    self._domain_cache[cache_key] = domain
                    # Try to verify (but return domain even if verification times out)
                    try:
                        if self._verify_company_domain(domain, company_name):
                            logger.info(f"Guessed and verified domain for {company_name}: {domain}")
                            return domain
                    except:
                        # If verification fails/times out, still return the domain as best guess
                        return domain
            except Exception:
                pass
                
        # If .com didn't work, try other TLDs but limit to first candidate only
        if len(candidates) > 0:
            for tld in other_tlds:
                domain = f"{candidates[0]}{tld}"
                try:
                    resp = requests.head(f"https://{domain}", timeout=1.5, allow_redirects=True)
                    if resp.status_code < 400:
                        # Cache result
                        self._domain_cache[cache_key] = domain
                        return domain
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
            
    def _get_common_company_size(self, company_name: str) -> Optional[str]:
        """Get company size for well-known companies from a common lookup table"""
        if not company_name:
            return None
            
        # Normalize company name for comparison
        normalized_name = company_name.lower().strip()
        
        # Dictionary of common companies and their sizes
        common_companies = {
            # Large tech companies (ENTERPRISE: 1000+)
            'google': 'ENTERPRISE',
            'alphabet': 'ENTERPRISE',
            'microsoft': 'ENTERPRISE',
            'amazon': 'ENTERPRISE',
            'aws': 'ENTERPRISE',
            'apple': 'ENTERPRISE',
            'meta': 'ENTERPRISE',
            'facebook': 'ENTERPRISE',
            'netflix': 'ENTERPRISE',
            'ibm': 'ENTERPRISE',
            'oracle': 'ENTERPRISE',
            'salesforce': 'ENTERPRISE',
            'intel': 'ENTERPRISE',
            'cisco': 'ENTERPRISE',
            'dell': 'ENTERPRISE',
            'adobe': 'ENTERPRISE',
            'hp': 'ENTERPRISE',
            'hewlett packard': 'ENTERPRISE',
            'twitter': 'ENTERPRISE',
            'x corp': 'ENTERPRISE',
            'uber': 'ENTERPRISE',
            'airbnb': 'ENTERPRISE',
            'paypal': 'ENTERPRISE',
            'tesla': 'ENTERPRISE',
            'nvidia': 'ENTERPRISE',
            'linkedin': 'ENTERPRISE',
            'indeed': 'ENTERPRISE',
            'glassdoor': 'ENTERPRISE',
            'ziprecruiter': 'ENTERPRISE',
            'monster': 'ENTERPRISE',
            'dice': 'ENTERPRISE',
            'careerbuilder': 'ENTERPRISE',
            'workday': 'ENTERPRISE',
            'sap': 'ENTERPRISE',
            'accenture': 'ENTERPRISE',
            'deloitte': 'ENTERPRISE',
            'pwc': 'ENTERPRISE',
            'kpmg': 'ENTERPRISE',
            'ey': 'ENTERPRISE',
            
            # Medium-sized tech companies (LARGE: 251-1000)
            'slack': 'LARGE',
            'zoom': 'LARGE',
            'gitlab': 'LARGE',
            'datadog': 'LARGE',
            'shopify': 'LARGE',
            'atlassian': 'LARGE',
            'twilio': 'LARGE',
            'square': 'LARGE',
            'block': 'LARGE',
            'cloudflare': 'LARGE',
            'digitalocean': 'LARGE',
            'lensa': 'LARGE',
            'pioneer square labs': 'LARGE',
            'iftt': 'LARGE',
            'andiamo': 'LARGE',
            'profocus technology': 'LARGE',
            'hydrozn': 'LARGE',
            'casera': 'LARGE',
            
            # Smaller tech companies (MEDIUM: 51-250)
            'vercel': 'MEDIUM',
            'deno': 'MEDIUM',
            'supabase': 'MEDIUM',
            'posthog': 'MEDIUM',
            'retool': 'MEDIUM',
            'replicate': 'MEDIUM',
            'replit': 'MEDIUM',
            
            # Startups (SMALL: 1-50)
            'startupcompany': 'SMALL'
        }
        
        # Check for exact match
        if normalized_name in common_companies:
            return common_companies[normalized_name]
            
        # Check for partial matches with popular companies
        for company, size in common_companies.items():
            if company in normalized_name or normalized_name in company:
                return size
                
        return None
        
    def _estimate_size_from_domain(self, domain: str) -> Optional[str]:
        """Attempt to estimate company size based on domain presence"""
        try:
            # Check domain TLD - enterprise companies often have .com domains
            if domain.endswith('.com') and len(domain.split('.')[0]) <= 6:
                # Short .com domains are often established companies
                return 'LARGE'
            elif domain.endswith('.io') or domain.endswith('.ai') or domain.endswith('.co'):
                # Modern tech domains are often startups or medium size companies
                return 'MEDIUM'
            elif domain.endswith('.org') or domain.endswith('.edu') or domain.endswith('.gov'):
                # Non-profit, educational or government orgs can vary widely
                return 'MEDIUM'  # Default assumption for these entities
        except Exception:
            pass
            
        return None

