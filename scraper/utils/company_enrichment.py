"""
Company Data Enrichment Service
Fetches real company information including size, domain, etc.
"""
import requests
import logging
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
    
    # Known company sizes database (can be expanded)
    KNOWN_COMPANIES = {
        'google': {'size': 'ENTERPRISE', 'employees': '100000+'},
        'microsoft': {'size': 'ENTERPRISE', 'employees': '100000+'},
        'amazon': {'size': 'ENTERPRISE', 'employees': '100000+'},
        'meta': {'size': 'ENTERPRISE', 'employees': '50000+'},
        'apple': {'size': 'ENTERPRISE', 'employees': '100000+'},
        'netflix': {'size': 'LARGE', 'employees': '10000+'},
        'airbnb': {'size': 'LARGE', 'employees': '5000+'},
        'uber': {'size': 'LARGE', 'employees': '20000+'},
        'shopify': {'size': 'LARGE', 'employees': '10000+'},
        'stripe': {'size': 'LARGE', 'employees': '5000+'},
        'slack': {'size': 'LARGE', 'employees': '2000+'},
        'twitter': {'size': 'LARGE', 'employees': '5000+'},
        'linkedin': {'size': 'ENTERPRISE', 'employees': '20000+'},
        'salesforce': {'size': 'ENTERPRISE', 'employees': '70000+'},
        'adobe': {'size': 'ENTERPRISE', 'employees': '25000+'},
        'oracle': {'size': 'ENTERPRISE', 'employees': '130000+'},
        'ibm': {'size': 'ENTERPRISE', 'employees': '280000+'},
        'intel': {'size': 'ENTERPRISE', 'employees': '120000+'},
        'cisco': {'size': 'ENTERPRISE', 'employees': '80000+'},
        'spotify': {'size': 'LARGE', 'employees': '6000+'},
        'github': {'size': 'MEDIUM', 'employees': '2000+'},
        'gitlab': {'size': 'MEDIUM', 'employees': '1500+'},
        'dropbox': {'size': 'LARGE', 'employees': '3000+'},
        'zoom': {'size': 'LARGE', 'employees': '7000+'},
        'atlassian': {'size': 'LARGE', 'employees': '10000+'},
        'asana': {'size': 'MEDIUM', 'employees': '1000+'},
        'notion': {'size': 'MEDIUM', 'employees': '500+'},
        'figma': {'size': 'MEDIUM', 'employees': '800+'},
        'canva': {'size': 'LARGE', 'employees': '3000+'},
        'webflow': {'size': 'MEDIUM', 'employees': '800+'},
        'vercel': {'size': 'MEDIUM', 'employees': '300+'},
        'netlify': {'size': 'SMALL', 'employees': '200+'},
    }
    
    def get_company_size(self, company_name: str, company_url: Optional[str] = None) -> str:
        """
        Determine company size using multiple methods
        
        Args:
            company_name: Name of the company
            company_url: Company website URL
            
        Returns:
            Company size (SMALL, MEDIUM, LARGE, ENTERPRISE)
        """
        if not company_name:
            return 'UNKNOWN'
        
        company_lower = company_name.lower().strip()
        
        # Method 1: Check known companies database
        for known_company, data in self.KNOWN_COMPANIES.items():
            if known_company in company_lower:
                logger.info(f"Found {company_name} in database: {data['size']}")
                return data['size']
        
        # Method 2: Heuristic based on company name patterns
        size = self._estimate_from_name(company_name)
        if size != 'UNKNOWN':
            return size
        
        # Method 3: Try to scrape from company website (including guessed domain)
        effective_url = company_url
        if not effective_url:
            domain = self.get_company_domain(company_name)
            if domain:
                effective_url = f'https://{domain}'
        if effective_url:
            size = self._scrape_from_website(effective_url)
            if size != 'UNKNOWN':
                return size

        # Method 4: Use Clearbit metrics if API key available
        domain_for_size = self._extract_domain(effective_url) if effective_url else None
        if not domain_for_size:
            domain_for_size = self.get_company_domain(company_name)
        if domain_for_size:
            size = self._size_from_clearbit(domain_for_size)
            if size:
                return size

        # Method 5: No reliable size found
        logger.debug(f"Unable to determine company size for {company_name}; returning UNKNOWN")
        return 'UNKNOWN'
    
    def _estimate_from_name(self, company_name: str) -> str:
        """Estimate company size from name patterns"""
        company_lower = company_name.lower()
        
        # Enterprise indicators - Very strong signals
        if any(x in company_lower for x in ['international', 'global', 'worldwide', 'plc', 'holdings', 'bank', 'insurance']):
            return 'ENTERPRISE'
        
        # Large company indicators - Strong corporate signals
        if any(x in company_lower for x in ['corporation', 'group ltd', 'technologies', 'systems', 'solutions inc']):
            return 'LARGE'
        
        # Startup/Small indicators - Clear small company signals
        if any(x in company_lower for x in ['startup', 'studio', 'labs', 'works', 'ventures']):
            return 'SMALL'
        
        # Medium indicators - Common corporate suffixes
        if any(x in company_lower for x in ['limited', 'ltd', 'inc', 'llc', 'corp']) and not any(x in company_lower for x in ['group', 'international']):
            return 'MEDIUM'
        
        return 'UNKNOWN'
    
    def _scrape_from_website(self, company_url: str) -> str:
        """Try to scrape company size from website"""
        try:
            response = requests.get(company_url, timeout=5, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            })
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'lxml')
                text = soup.get_text().lower()
                
                # Look for employee count mentions
                if any(x in text for x in ['100,000+ employees', '100000+ employees', '100k+ employees']):
                    return 'ENTERPRISE'
                elif any(x in text for x in ['10,000+ employees', '10000+ employees', '10k+ employees']):
                    return 'LARGE'
                elif any(x in text for x in ['1,000+ employees', '1000+ employees', '1k+ employees']):
                    return 'MEDIUM'
                elif any(x in text for x in ['100+ employees', '50+ employees']):
                    return 'SMALL'
        
        except Exception as e:
            logger.debug(f"Could not scrape company size: {str(e)}")
        
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
                timeout=4,
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
        try:
            query = company_name.strip()
            if not query:
                return None
            payload = {
                'q': f"{query} company website",
                'kl': 'us-en',
            }
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept-Language': 'en-US,en;q=0.9',
            }
            with requests.Session() as session:
                session.get('https://duckduckgo.com', timeout=5, headers=headers)
                resp = session.post('https://duckduckgo.com/html/', data=payload, headers=headers, timeout=6)
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, 'lxml')
                for link in soup.select('a.result__url'):
                    domain = link.get_text(strip=True)
                    domain = self._extract_domain(domain)
                    if domain and self._is_domain_candidate(domain):
                        return domain
        except Exception as e:
            logger.debug(f"DuckDuckGo domain lookup failed for {company_name}: {e}")
        # last resort: guess
        guess = self._guess_domain(company_name)
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

    def _guess_domain(self, company_name: str) -> Optional[str]:
        token = ''.join(ch for ch in company_name.lower() if ch.isalnum())
        if len(token) < 3:
            return None
        for tld in ['.com', '.io', '.co', '.ai', '.net']:
            candidate = f"{token}{tld}"
            for scheme in ('https://', 'http://'):
                try:
                    resp = requests.head(f"{scheme}{candidate}", timeout=4, allow_redirects=True)
                    if resp.status_code < 400:
                        return candidate
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
            resp = requests.get(url, params=params, headers=headers, timeout=6)
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

