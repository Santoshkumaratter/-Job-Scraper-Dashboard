"""
Base scraper class with common functionality for all job portal scrapers
"""
import time
import logging
import re
import requests
import random
from abc import ABC, abstractmethod
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from django.conf import settings

logger = logging.getLogger(__name__)

# ✅ STEP 1: Use fake-useragent for random browser headers
try:
    from fake_useragent import UserAgent
    ua = UserAgent()
    FAKE_USERAGENT_AVAILABLE = True
except ImportError:
    FAKE_USERAGENT_AVAILABLE = False
    logger.warning("fake-useragent not installed. Install with: pip install fake-useragent")

# ✅ STEP 4: Use undetected-chromedriver for stealth mode
try:
    import undetected_chromedriver as uc
    UNDETECTED_CHROME_AVAILABLE = True
except ImportError:
    UNDETECTED_CHROME_AVAILABLE = False
    logger.warning("undetected-chromedriver not installed. Install with: pip install undetected-chromedriver")

# ✅ STEP 2: Free Proxy APIs for rotating proxy pool
PROXY_APIS = [
    "https://api.proxyscrape.com/v2/?request=getproxies&protocol=http&timeout=5000&country=all",
    "https://www.proxy-list.download/api/v1/get?type=http",
    "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",
]

# Cache for proxy list to avoid fetching on every request
_PROXY_CACHE = []
_PROXY_CACHE_TIME = 0
PROXY_CACHE_DURATION = 300  # 5 minutes


class BaseScraper(ABC):
    """
    Base scraper class that all job portal scrapers inherit from
    """
    
    def __init__(self, keywords: List[str], job_type: str = 'ALL', 
                 time_filter: str = 'ALL', location: str = 'ALL'):
        """
        Initialize the scraper
        
        Args:
            keywords: List of keywords to search for
            job_type: Type of job (REMOTE, FREELANCE, FULL_TIME, HYBRID, ALL)
            time_filter: Time filter (24H, 3D, 7D, ALL)
            location: Location filter (USA, UK, ALL)
        """
        self.keywords = keywords
        self.job_type = job_type
        self.time_filter = time_filter
        self.location = location
        self.timeout = 8  # Balanced timeout - fast but ensures all jobs are fetched
        self.rate_limit = 0.5  # Reduced delay for faster scraping but prevents rate limiting
        self.jobs_data = []
        self.max_jobs_per_keyword = 500  # Increased limit to fetch maximum jobs per keyword (500+ jobs)
        
        # ✅ FREE TOOLS: Use fake-useragent for random browser headers
        self._get_random_user_agent = self._init_fake_useragent()
        
        # Request headers - Enhanced to avoid blocking (using free tools)
        self.headers = {
            'User-Agent': self._get_random_user_agent(),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-GB,en-US;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Cache-Control': 'max-age=0',
            'DNT': '1',
            'Referer': 'https://www.google.com/',  # Look like coming from Google
        }
        self.session = None
        
        # ✅ FREE TOOLS: No paid proxies/APIs - use free rotation only
        self.proxy_list: List[str] = getattr(settings, 'SCRAPER_HTTP_PROXIES', []) or []  # Free proxies if configured
        self._proxy_index: int = 0
        self._bad_proxies: set[str] = set()
        
        # ✅ REMOVED: ScraperAPI (paid service) - using free tools only
    
    @property
    @abstractmethod
    def portal_name(self) -> str:
        """Return the name of the job portal"""
        pass
    
    @property
    @abstractmethod
    def base_url(self) -> str:
        """Return the base URL of the job portal"""
        pass
    
    @property
    def requires_selenium(self) -> bool:
        """Override if scraper requires Selenium"""
        return False
    
    def _init_fake_useragent(self):
        """✅ STEP 1: Initialize fake-useragent for random browser headers"""
        if FAKE_USERAGENT_AVAILABLE:
            try:
                return lambda: ua.random
            except:
                pass
        # Fallback to hardcoded user agents if fake-useragent not available
        fallback_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
        ]
        return lambda: random.choice(fallback_agents)
    
    def _get_rotating_headers(self):
        """✅ STEP 1: Get rotating headers with random User-Agent and Accept-Language"""
        random_ua = self._get_random_user_agent()
        accept_languages = [
            "en-US,en;q=0.9",
            "en-GB,en;q=0.8",
            "en-US,en;q=0.9,es;q=0.8",
            "en-GB,en;q=0.9,fr;q=0.8"
        ]
        
        return {
            'User-Agent': random_ua,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': random.choice(accept_languages),
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Cache-Control': 'max-age=0',
            'DNT': '1',
            'Referer': 'https://www.google.com/',
        }
    
    def _fetch_free_proxies(self):
        """✅ STEP 2: Fetch free proxies from public APIs"""
        global _PROXY_CACHE, _PROXY_CACHE_TIME
        
        # Use cached proxies if available and not expired
        current_time = time.time()
        if _PROXY_CACHE and (current_time - _PROXY_CACHE_TIME) < PROXY_CACHE_DURATION:
            return _PROXY_CACHE
        
        proxy_list = []
        for api_url in PROXY_APIS:
            try:
                response = requests.get(api_url, timeout=10)
                if response.status_code == 200:
                    proxies = response.text.strip().split('\n')
                    proxy_list.extend([p.strip() for p in proxies if p.strip()])
            except Exception as e:
                logger.debug(f"Failed to fetch proxies from {api_url}: {e}")
                continue
        
        # Update cache
        if proxy_list:
            _PROXY_CACHE = list(set(proxy_list))  # Remove duplicates
            _PROXY_CACHE_TIME = current_time
            logger.info(f"Loaded {len(_PROXY_CACHE)} proxies from public APIs")
        
        return _PROXY_CACHE
    
    def _get_random_proxy_dict(self):
        """✅ STEP 2: Get random proxy for requests"""
        # First try configured proxies from settings
        if self.proxy_list and len(self.proxy_list) > 0:
            proxy_url = random.choice(self.proxy_list)
            if proxy_url and not self._is_proxy_placeholder(proxy_url):
                return {'http': proxy_url, 'https': proxy_url}
        
        # Fallback to free proxies
        free_proxies = self._fetch_free_proxies()
        if free_proxies:
            proxy = random.choice(free_proxies)
            return {'http': f'http://{proxy}', 'https': f'http://{proxy}'}
        
        return None
    
    def get_driver(self, proxy: Optional[str] = None):
        """✅ STEP 4: Initialize and return Selenium WebDriver with stealth mode (undetected-chromedriver)"""
        import os
        import sys
        
        # ✅ Use undetected-chromedriver for maximum stealth
        if UNDETECTED_CHROME_AVAILABLE:
            try:
                options = uc.ChromeOptions()
                options.add_argument('--headless=new')
                options.add_argument('--no-sandbox')
                options.add_argument('--disable-dev-shm-usage')
                options.add_argument('--disable-gpu')
                
                # Add proxy if provided
                if proxy:
                    options.add_argument(f'--proxy-server={proxy}')
                
                # Suppress logging
                options.add_argument('--log-level=3')
                options.add_argument('--silent')
                
                # Create undetected Chrome driver (bypasses Cloudflare, CAPTCHA)
                driver = uc.Chrome(options=options, use_subprocess=False)
                driver.set_page_load_timeout(30)
                driver.implicitly_wait(3)
                
                return driver
            except Exception as e:
                logger.warning(f"Failed to create undetected Chrome driver: {e}. Falling back to regular Chrome.")
        
        # Fallback to regular Chrome with anti-detection
        chrome_options = Options()
        chrome_options.add_argument('--headless=new')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--disable-software-rasterizer')
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_argument('--disable-extensions')
        chrome_options.add_argument('--disable-logging')
        chrome_options.add_argument('--log-level=3')
        chrome_options.add_argument('--silent')
        chrome_options.add_argument(f'user-agent={self._get_random_user_agent()}')
        chrome_options.add_experimental_option('excludeSwitches', ['enable-logging', 'enable-automation'])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        chrome_options.add_experimental_option('prefs', {
            'profile.default_content_setting_values.notifications': 2,
        })
        
        # Add proxy if configured
        if proxy:
            chrome_options.add_argument(f'--proxy-server={proxy}')
        
        # Suppress logging
        os.environ['WDM_LOG_LEVEL'] = '0'
        os.environ['WDM_PRINT_FIRST_LINE'] = 'False'
        
        service = Service()
        service.log_path = os.devnull
        
        driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.set_page_load_timeout(30)
        driver.implicitly_wait(3)
        
        # Hide automation
        try:
            driver.execute_cdp_cmd('Network.setUserAgentOverride', {
                "userAgent": self._get_random_user_agent()
            })
            driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        except:
            pass
        
        return driver
    
    def make_request(self, url: str, use_selenium: bool = False, retry_count: int = 0) -> Optional[str]:
        """
        ✅ OPTIMIZED: Make HTTP request with rotating headers, proxies, and exponential backoff
        
        Args:
            url: URL to request
            use_selenium: Whether to use Selenium (for JavaScript-heavy sites)
            retry_count: Current retry attempt (for exponential backoff)
            
        Returns:
            HTML content or None
        """
        max_retries = 3
        
        for attempt in range(max_retries):
            driver = None
            try:
                if use_selenium or self.requires_selenium:
                    proxy = self._get_next_valid_proxy()
                    driver = self.get_driver(proxy)
                    
                    # Set page load timeout to handle slow pages
                    driver.set_page_load_timeout(30)
                    
                    try:
                        driver.get(url)
                    except Exception as page_load_err:
                        # Handle network errors, timeouts, and Selenium exceptions
                        error_str = str(page_load_err).lower()
                        error_type = type(page_load_err).__name__
                        
                        # Check for network/timeout errors
                        is_network_error = (
                            isinstance(page_load_err, (TimeoutException, WebDriverException)) or
                            'timeout' in error_str or 
                            'disconnected' in error_str or 
                            'network' in error_str or
                            'internet' in error_str or
                            'connection' in error_str or
                            error_type in ['TimeoutException', 'WebDriverException', 'ConnectionRefusedError']
                        )
                        
                        if is_network_error:
                            # Suppress verbose logging - only log critical errors
                            # Always try to close driver on error
                            if driver:
                                try:
                                    driver.quit()
                                except:
                                    pass
                                driver = None
                            
                            # Retry with exponential backoff
                            if attempt < max_retries - 1:
                                wait_time = 2 * (attempt + 1)
                                time.sleep(wait_time)
                                continue
                            else:
                                # Only log critical failures
                                pass
                                if driver:
                                    try:
                                        driver.quit()
                                    except:
                                        pass
                                return None
                        else:
                            # Unexpected error - suppress verbose logging
                            if driver:
                                try:
                                    driver.quit()
                                except:
                                    pass
                            raise  # Re-raise if not a network/timeout error
                    
                    # Wait for JavaScript-heavy pages - REDUCED for speed
                    time.sleep(1)  # Reduced from 2s to 1s for faster loading
                    # Quick scroll to trigger lazy loading
                    try:
                        driver.execute_script("window.scrollTo(0, document.body.scrollHeight/2);")
                        time.sleep(0.5)  # Reduced from 1s to 0.5s
                        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                        time.sleep(0.5)  # Reduced from 1s to 0.5s
                    except:
                        pass
                    
                    # Check for captcha or blocking
                    html = driver.page_source
                    if self._is_blocked_or_captcha(html, driver):
                        logger.warning(f"Captcha or blocking detected for {url}, trying with different proxy/user agent")
                        if driver:
                            try:
                                driver.quit()
                            except:
                                pass
                            driver = None
                        
                        # Rotate proxy and user agent
                        if attempt < max_retries - 1:
                            self._proxy_index += 1  # Rotate proxy
                            self.headers['User-Agent'] = self._get_random_user_agent()  # Rotate UA
                            time.sleep(3 * (attempt + 1))  # Wait longer before retry
                            continue
                        else:
                            logger.error(f"Failed to bypass captcha/blocking after {max_retries} attempts")
                            return None
                    
                    # Always close driver when done
                    try:
                        if driver:
                            driver.quit()
                    except:
                        pass
                    
                    if not html or len(html) < 100:
                        # Suppress verbose logging
                        if attempt < max_retries - 1:
                            time.sleep(2 * (attempt + 1))
                            continue
                    
                    return html
                else:
                    # ✅ STEP 3: Add random delay before request (anti-detection)
                    if attempt > 0:
                        delay = random.uniform(0.5, 2.0) * (2 ** attempt)  # Exponential backoff
                        time.sleep(delay)
                    else:
                        time.sleep(random.uniform(0.1, 0.5))  # Small random delay
                    
                    # ✅ STEP 1: Use rotating headers with random User-Agent
                    if not self.session:
                        self.session = requests.Session()
                    
                    # Get fresh rotating headers for each request
                    headers = self._get_rotating_headers()
                    self.session.headers.update(headers)
                    
                    # ✅ STEP 2: Use rotating proxies (free or configured)
                    proxies = self._get_random_proxy_dict()
                    
                    try:
                        # Increase timeout for slow portals - some sites need more time
                        timeout = max(self.timeout, 20)  # At least 20 seconds for slow portals like cwjobs
                        response = self.session.get(url, timeout=timeout, proxies=proxies)
                    except requests.exceptions.Timeout as timeout_err:
                        # Suppress verbose logging - only retry
                        if attempt < max_retries - 1:
                            wait_time = 2 * (attempt + 1)
                            time.sleep(wait_time)
                            continue
                        else:
                            return None
                    except requests.exceptions.ConnectionError as conn_err:
                        error_str = str(conn_err).lower()
                        # Handle DNS resolution errors silently
                        if 'name resolution' in error_str or 'getaddrinfo failed' in error_str or 'failed to resolve' in error_str:
                            if attempt < max_retries - 1:
                                continue
                            else:
                                return None
                        if proxy_url:
                            self._bad_proxies.add(proxy_url)
                            continue
                        else:
                            continue
                    except Exception as prox_err:
                        if proxy_url:
                            self._bad_proxies.add(proxy_url)
                            continue
                        else:
                            continue
                    
                    # Check for captcha or blocking in response
                    if self._is_blocked_or_captcha(response.text, None):
                        logger.warning(f"Captcha or blocking detected for {url}, trying with Selenium")
                        if proxy_url:
                            self._bad_proxies.add(proxy_url)
                        # Rotate proxy and user agent
                        if attempt < max_retries - 1:
                            self._proxy_index += 1
                            self.headers['User-Agent'] = self._get_random_user_agent()
                            time.sleep(3 * (attempt + 1))
                            continue
                        # Try with Selenium as fallback
                        return self.make_request(url, use_selenium=True)
                    
                    # If 403, 429, try with Selenium (silently)
                    if response.status_code in (403, 429):
                        if proxy_url:
                            self._bad_proxies.add(proxy_url)
                        # Try with Selenium without verbose logging
                        return self.make_request(url, use_selenium=True)
                    
                    response.raise_for_status()
                    return response.text
                    
            except Exception as e:
                if attempt < max_retries - 1:
                    # Suppress verbose logging - just retry
                    time.sleep(2)
                    continue
                else:
                    # Suppress verbose error logging
                    return None
        
        return None
    
    def parse_html(self, html: str) -> BeautifulSoup:
        """Parse HTML content with BeautifulSoup"""
        return BeautifulSoup(html, 'lxml')
    
    def ensure_real_data(self, job_data: Dict) -> Dict:
        """
        Ensure all fields have real data - no "Unknown" values
        Infers company from URL if missing, ensures all fields are populated
        """
        from urllib.parse import urlparse
        
        # Remove "Unknown" values
        if job_data.get('company', '').lower() in ['unknown', '']:
            # Try to infer company from job link
            job_link = job_data.get('job_link', '')
            if job_link:
                try:
                    domain = urlparse(job_link).netloc
                    if domain:
                        company = domain.replace('www.', '').split('.')[0].title()
                        if company and company.lower() not in ['job', 'jobs', 'career', 'careers']:
                            job_data['company'] = company
                except:
                    pass
            
            # If still no company, use "Company Not Listed" instead of "Unknown"
            if not job_data.get('company') or job_data['company'].lower() in ['unknown', '']:
                job_data['company'] = 'Company Not Listed'
        
        # Remove "UNKNOWN" from company_size
        if job_data.get('company_size', '').upper() in ['UNKNOWN', '']:
            job_data['company_size'] = ''
        
        # Ensure all fields have values (empty string instead of None)
        for key in ['company_url', 'location', 'job_description', 'salary_range']:
            if job_data.get(key) is None:
                job_data[key] = ''
        
        return job_data
    
    def parse_date(self, date_str: str) -> Optional[datetime]:
        """
        Parse relative date strings like '2 days ago' into datetime
        
        Args:
            date_str: Date string to parse
            
        Returns:
            datetime object or None
        """
        if not date_str:
            return None
        
        date_str = date_str.lower().strip()
        now = datetime.now()
        
        try:
            # Handle "today", "yesterday", "just posted", etc.
            if any(x in date_str for x in ['today', 'just now', 'just posted', 'active today']):
                return now.date()
            elif 'yesterday' in date_str:
                return (now - timedelta(days=1)).date()
            
            # Handle "X hours/days/weeks/months ago"
            if 'hour' in date_str:
                match = re.search(r'(\d+)', date_str)
                if match:
                    hours = int(match.group(1))
                    return (now - timedelta(hours=hours)).date()
            elif 'day' in date_str:
                match = re.search(r'(\d+)', date_str)
                if match:
                    days = int(match.group(1))
                    return (now - timedelta(days=days)).date()
            elif 'week' in date_str:
                match = re.search(r'(\d+)', date_str)
                if match:
                    weeks = int(match.group(1))
                    return (now - timedelta(weeks=weeks)).date()
            elif 'month' in date_str:
                match = re.search(r'(\d+)', date_str)
                if match:
                    months = int(match.group(1))
                    return (now - timedelta(days=months*30)).date()
            
            # Try parsing standard date formats
            for fmt in ['%Y-%m-%d', '%d-%m-%Y', '%m/%d/%Y', '%B %d, %Y']:
                try:
                    return datetime.strptime(date_str, fmt).date()
                except:
                    continue
            
            return None
        except Exception as e:
            logger.warning(f"Error parsing date '{date_str}': {str(e)}")
            return None
    
    def should_include_job(self, posted_date: Optional[datetime]) -> bool:
        """
        Check if job should be included based on time filter
        
        Args:
            posted_date: Job posting date
            
        Returns:
            Boolean indicating if job should be included
        """
        if self.time_filter == 'ALL' or not posted_date:
            return True
        
        now = datetime.now().date()
        delta = now - posted_date
        
        if self.time_filter == '24H':
            return delta.days <= 1
        elif self.time_filter == '3D':
            return delta.days <= 3
        elif self.time_filter == '7D':
            return delta.days <= 7
        
        return True
    
    def matches_keyword(self, job_title: str, keyword: str) -> bool:
        """
        ✅ STRICT KEYWORD MATCHING - Job title MUST contain keyword
        
        Args:
            job_title: The job title to check
            keyword: The keyword that must be present
            
        Returns:
            Boolean indicating if keyword is found in job title
        """
        if not job_title or not keyword:
            return False
        
        job_title_lower = job_title.lower()
        keyword_lower = keyword.lower()
        
        # Strict match: keyword must be in job title
        return keyword_lower in job_title_lower
    
    def detect_job_type(self, job_title: str, location: str = '', description: str = '') -> str:
        """
        ✅ DETECT REAL JOB TYPE from job posting data
        
        Args:
            job_title: Job title
            location: Job location
            description: Job description
            
        Returns:
            Detected job type (REMOTE, FULL_TIME, FREELANCE, HYBRID, PART_TIME)
        """
        text = f"{job_title} {location} {description}".lower()
        
        # Remote indicators (very strong)
        remote_keywords = ['remote', 'work from home', 'wfh', 'anywhere', 'distributed', 'worldwide', 'location independent']
        if any(word in text for word in remote_keywords):
            return 'REMOTE'
        
        # Hybrid indicators
        hybrid_keywords = ['hybrid', 'flexible location', 'office + remote', 'partially remote', 'flex']
        if any(word in text for word in hybrid_keywords):
            return 'HYBRID'
        
        # Freelance/Contract indicators
        freelance_keywords = ['freelance', 'contract', 'contractor', 'temp', 'temporary', 'project-based', 'gig', 'consultancy']
        if any(word in text for word in freelance_keywords):
            return 'FREELANCE'
        
        # Part-time indicators
        parttime_keywords = ['part-time', 'part time', 'parttime']
        if any(word in text for word in parttime_keywords):
            return 'PART_TIME'
        
        # Full-time indicators (only if explicitly mentioned)
        fulltime_keywords = ['full-time', 'full time', 'fulltime', 'permanent', 'ft ', 'fte']
        if any(word in text for word in fulltime_keywords):
            return 'FULL_TIME'
        
        # ✅ Fallback: unknown when we cannot infer confidently
        return 'UNKNOWN'
    
    def matches_job_type_filter(self, detected_type: str) -> bool:
        """
        ✅ CHECK if detected job type matches user's filter
        
        Args:
            detected_type: The detected job type from posting
            
        Returns:
            Boolean - True if matches filter, False if should skip
        """
        # If filter is "ALL", accept all job types
        if self.job_type == 'ALL':
            return True
        
        # Otherwise, detected type MUST match filter
        return detected_type == self.job_type
    
    def extract_company_url(self, soup: BeautifulSoup, company: str) -> Optional[str]:
        """
        Try to extract company URL from job page
        
        Args:
            soup: BeautifulSoup object
            company: Company name
            
        Returns:
            Company URL or None
        """
        # This is a placeholder - override in specific scrapers
        return None
    
    @abstractmethod
    def build_search_url(self, keyword: str) -> str:
        """
        Build search URL for the given keyword
        
        Args:
            keyword: Search keyword
            
        Returns:
            Search URL
        """
        pass
    
    @abstractmethod
    def scrape_jobs(self) -> List[Dict]:
        """
        Main scraping method - must be implemented by each scraper
        
        Returns:
            List of job dictionaries
        """
        pass
    
    def clean_text(self, text: str) -> str:
        """Clean and normalize text"""
        if not text:
            return ""
        return ' '.join(text.split()).strip()
    
    def rate_limit_delay(self):
        """✅ STEP 3: Apply rate limiting delay with randomness"""
        # Add random jitter to avoid detection patterns
        delay = self.rate_limit + random.uniform(0, 0.3)
        time.sleep(delay)
    
    def _validate_job_link(self, job_link: str) -> bool:
        """✅ STEP 6: Validate job link is accessible and returns 200 OK"""
        if not job_link:
            return False
        
        try:
            # Quick HEAD request to check if link is valid
            response = requests.head(job_link, timeout=5, allow_redirects=True)
            return response.status_code == 200
        except:
            # If HEAD fails, try GET with short timeout
            try:
                response = requests.get(job_link, timeout=5, allow_redirects=True)
                return response.status_code == 200
            except:
                return False

    # ===== Utility: Rotation helpers =====
    # ✅ REMOVED: ScraperAPI method - using free tools only (requests + fake-useragent)

    def _get_next_proxy(self) -> Optional[str]:
        if not self.proxy_list:
            return None
        proxy = self.proxy_list[self._proxy_index % len(self.proxy_list)]
        self._proxy_index += 1
        return proxy

    def _get_next_valid_proxy(self) -> Optional[str]:
        if not self.proxy_list:
            return None

        total = len(self.proxy_list)
        checked = 0
        while checked < total:
            proxy = self._get_next_proxy()
            if not proxy:
                break
            if self._is_proxy_placeholder(proxy):
                checked += 1
                continue
            if proxy in self._bad_proxies:
                checked += 1
                continue
            return proxy
        return None

    def _get_requests_proxy_dict(self) -> Optional[Dict[str, str]]:
        proxy = self._get_next_valid_proxy()
        if not proxy:
            return None
        return {
            'http': proxy,
            'https': proxy,
        }
    
    def _is_proxy_placeholder(self, proxy_url: str) -> bool:
        # Heuristic to skip example placeholders
        if not proxy_url:
            return True
        lowered = proxy_url.lower()
        return any(token in lowered for token in ['ip1', 'ip2', 'port', 'user:pass'])
    
    def _get_next_user_agent(self) -> str:
        if not self.user_agents:
            return self.headers['User-Agent']
        ua = self.user_agents[self._ua_index % len(self.user_agents)]
        self._ua_index += 1
        return ua
    
    def scrape_all(self) -> List[Dict]:
        """
        Scrape jobs for all keywords
        
        Returns:
            List of all scraped jobs
        """
        # Simple user-friendly log
        keywords_str = ', '.join(self.keywords[:3]) + ('...' if len(self.keywords) > 3 else '')
        print(f"🔍 {self.portal_name}: Fetching jobs for '{keywords_str}'...")
        
        try:
            start_time = time.time()
            # Call scrape_jobs() once - it handles all keywords internally
            jobs = self.scrape_jobs()
            elapsed = time.time() - start_time
            
            # Simple user-friendly result
            if jobs:
                print(f"✅ {self.portal_name}: Found {len(jobs)} jobs ({elapsed:.1f}s)")
            else:
                print(f"⚠️ {self.portal_name}: No jobs found")
            
            return jobs
        except Exception as e:
            print(f"❌ {self.portal_name}: Error - {str(e)}")
            logger.error(f"{self.portal_name}: Error scraping: {str(e)}")
            return []

    def _extract_company_profile_url(self, soup: BeautifulSoup) -> Optional[str]:
        """
        Generic method to extract company profile URL from job detail page
        Checks common patterns used by different portals
        """
        import urllib.parse
        
        # Common patterns for company profile URLs across different portals
        patterns = [
            r'/company/[^/\s"\']+',  # LinkedIn: /company/perplexity
            r'/employer/[^/\s"\']+',  # Dice: /employer/xyz
            r'/employers/[^/\s"\']+',  # CV-Library: /employers/xyz
            r'/cmp/[^/\s"\']+',  # Indeed: /cmp/xyz
            r'/companies/[^/\s"\']+',  # General: /companies/xyz
            r'/org/[^/\s"\']+',  # General: /org/xyz
        ]
        
        # Look for company profile links in HTML - check all links
        all_links = soup.find_all('a', href=True)
        domain = self.base_url.split('//')[1].split('/')[0] if '//' in self.base_url else ''
        
        for link in all_links:
            href = link.get('href', '').strip()
            if not href:
                continue
            
            # Check if href matches any company profile pattern
            for pattern in patterns:
                # Use regex to match pattern
                import re
                if re.search(pattern, href, re.I):
                    # Make full URL if relative
                    if href.startswith('/'):
                        full_url = urllib.parse.urljoin(self.base_url, href)
                        logger.debug(f"Found company profile URL: {full_url} (from pattern: {pattern})")
                        return full_url
                    elif href.startswith('http') and domain in href:
                        logger.debug(f"Found company profile URL: {href} (from pattern: {pattern})")
                        return href
        
        company_keywords = ['company', 'employer', 'employers', 'cmp', 'org', 'organization']
        for link in all_links:
            href = link.get('href', '').strip()
            if not href:
                continue
            
            # Check if link text or href contains company-related keywords
            link_text = (link.get_text() or '').lower()
            href_lower = href.lower()
            
            if any(kw in href_lower for kw in company_keywords):
                # Make sure it's not the same as base URL
                if domain and domain in href and href.startswith('http'):
                    if href.startswith('/'):
                        full_url = urllib.parse.urljoin(self.base_url, href)
                        logger.debug(f"Found company profile URL (keyword match): {full_url}")
                        return full_url
                    elif href.startswith('http'):
                        logger.debug(f"Found company profile URL (keyword match): {href}")
                        return href
        
        logger.debug("No company profile URL found in job detail page")
        return None

    def _fetch_company_profile(self, profile_url: str) -> Dict[str, Optional[str]]:
        """
        Generic method to fetch company profile page and extract real company website URL and size
        Works for most job portals that have company profile pages
        """
        profile_data = {}
        if not profile_url:
            return profile_data
        
        try:
            html = self.make_request(profile_url, use_selenium=True)
            if not html:
                return profile_data
            
            soup = self.parse_html(html)
            domain = self.base_url.split('//')[1].split('/')[0] if '//' in self.base_url else ''
            
            # Extract company website URL from company profile
            website_selectors = [
                'a[href^="http"]:not([href*="' + domain + '"])',
                '.company-website a',
                'a.company-link[href^="http"]',
                'a[data-control-name="topcard_website"]',
                '.org-top-card-summary-info-list__info-item a[href^="http"]',
                'dd.org-top-card-summary-info-list__info-item a[href^="http"]',
                'a[href*="website"]',
            ]
            
            for selector in website_selectors:
                try:
                    website_link = soup.select_one(selector)
                    if website_link:
                        href = website_link.get('href', '')
                        # Clean redirect URLs
                        if 'redirect' in href.lower() or '/redirect' in href:
                            from urllib.parse import parse_qs, urlparse
                            parsed = urlparse(href)
                            params = parse_qs(parsed.query)
                            if 'url' in params:
                                href = params['url'][0]
                        if href and href.startswith('http') and domain not in href.lower():
                            # Additional validation - make sure it's a real website, not a job portal
                            invalid_domains = [domain, 'linkedin.com', 'indeed.com', 'glassdoor.com', 'monster.com', 'jobs.', 'careers.']
                            if not any(inv_domain in href.lower() for inv_domain in invalid_domains if inv_domain):
                                profile_data['website_url'] = href
                                logger.info(f"✅ Found website URL from {self.portal_name} company profile: {href}")
                                break
                            else:
                                logger.debug(f"⚠️ Skipped invalid website URL: {href}")
                except:
                    continue
            
            # Extract company size from company profile - Method 1: JSON-LD
            for script in soup.find_all('script', type='application/ld+json'):
                try:
                    import json
                    data = json.loads(script.get_text(strip=True) or '{}')
                    if isinstance(data, dict):
                        if data.get('@type') == 'Organization':
                            employees = data.get('numberOfEmployees')
                            if employees:
                                if isinstance(employees, (int, str)):
                                    profile_data['company_size'] = self._parse_company_size_from_count(employees)
                                    logger.info(f"Found company size from {self.portal_name} JSON-LD: {employees}")
                                    break
                                elif isinstance(employees, dict):
                                    min_val = employees.get('minValue')
                                    max_val = employees.get('maxValue')
                                    if min_val and max_val:
                                        profile_data['company_size'] = self._parse_company_size_from_range(min_val, max_val)
                                        logger.info(f"Found company size from {self.portal_name} JSON-LD: {min_val}-{max_val}")
                                        break
                except:
                    continue
            
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
                            min_val = int(match.group(1).replace(',', ''))
                            max_val = int(match.group(2).replace(',', ''))
                            profile_data['company_size'] = self._parse_company_size_from_range(min_val, max_val)
                            logger.info(f"Found company size from {self.portal_name} profile: {min_val}-{max_val}")
                            break
                        else:
                            count = int(match.group(1).replace(',', ''))
                            profile_data['company_size'] = self._parse_company_size_from_count(count)
                            logger.info(f"Found company size from {self.portal_name} profile: {count}")
                            break
            
            # Extract company name from profile
            company_name_elem = soup.find('h1') or soup.find('h2', class_=re.compile('company', re.I))
            if company_name_elem:
                company_name = self.clean_text(company_name_elem.get_text())
                if company_name:
                    profile_data['company_name'] = company_name
            
        except Exception as e:
            logger.debug(f"Error fetching {self.portal_name} company profile from {profile_url}: {e}")
        
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
    
    def _is_blocked_or_captcha(self, html: str, driver=None) -> bool:
        """
        Detect if page is blocked or shows captcha
        
        Args:
            html: HTML content or response text
            driver: Optional Selenium driver for additional checks
            
        Returns:
            True if blocked/captcha detected, False otherwise
        """
        if not html:
            return False
        
        html_lower = html.lower()
        
        # Common captcha indicators
        captcha_indicators = [
            'captcha',
            'recaptcha',
            'hcaptcha',
            'cloudflare',
            'checking your browser',
            'please wait',
            'access denied',
            'blocked',
            'unusual traffic',
            'verify you are human',
            'challenge',
            'security check',
            'rate limit',
            'too many requests'
        ]
        
        # Check HTML content
        for indicator in captcha_indicators:
            if indicator in html_lower:
                return True
        
        # Check page title
        if driver:
            try:
                title = driver.title.lower()
                for indicator in captcha_indicators:
                    if indicator in title:
                        return True
            except:
                pass
        
        # Check for common blocking patterns
        blocking_patterns = [
            '403 forbidden',
            '429 too many',
            'access denied',
            'forbidden',
            'blocked by',
            'your ip has been',
            'temporarily blocked'
        ]
        
        for pattern in blocking_patterns:
            if pattern in html_lower:
                return True
        
        return False

