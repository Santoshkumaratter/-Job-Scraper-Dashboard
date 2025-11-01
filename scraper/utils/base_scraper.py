"""
Base scraper class with common functionality for all job portal scrapers
"""
import time
import logging
import requests
from abc import ABC, abstractmethod
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from django.conf import settings


logger = logging.getLogger(__name__)


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
        self.timeout = 10  # Faster first-byte for initial fetch
        self.rate_limit = 1  # 1 second between requests
        self.jobs_data = []
        self.max_jobs_per_keyword = 50  # More results per keyword
        
        # Request headers - Enhanced to avoid blocking
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
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
            'DNT': '1'
        }
        self.session = None
        
        # Proxy/User-Agent rotation (config via settings)
        self.proxy_list: List[str] = getattr(settings, 'SCRAPER_HTTP_PROXIES', []) or []
        self._proxy_index: int = 0
        self.user_agents: List[str] = getattr(settings, 'SCRAPER_USER_AGENTS', []) or [
            self.headers['User-Agent'],
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15',
        ]
        self._ua_index: int = 0
        self._bad_proxies: set[str] = set()
        self.scraperapi_key: str = getattr(settings, 'SCRAPERAPI_KEY', '') or ''
        self.scraperapi_render: bool = bool(getattr(settings, 'SCRAPERAPI_RENDER', False))
    
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
    
    def get_driver(self, proxy: Optional[str] = None):
        """Initialize and return Selenium WebDriver with anti-detection"""
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
        chrome_options.add_argument('--disable-web-security')
        chrome_options.add_argument('--ignore-certificate-errors')
        # Suppress GPU errors
        chrome_options.add_argument('--disable-gl-drawing-for-tests')
        chrome_options.add_argument('--disable-accelerated-2d-canvas')
        chrome_options.add_argument('--disable-accelerated-video-decode')
        chrome_options.add_argument('--use-gl=swiftshader')
        chrome_options.add_argument(f'user-agent={self.headers["User-Agent"]}')
        chrome_options.add_experimental_option('excludeSwitches', ['enable-logging', 'enable-automation'])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        # Suppress console logs and notifications
        import os
        import sys
        chrome_options.add_experimental_option('prefs', {
            'profile.default_content_setting_values.notifications': 2,
        })
        
        # Suppress ALL DevTools and GPU messages
        if sys.platform == 'win32':
            chrome_options.add_argument('--disable-features=VizDisplayCompositor')
        
        # Suppress output completely
        chrome_options.add_argument('--disable-infobars')
        chrome_options.add_experimental_option('excludeSwitches', ['enable-logging', 'enable-automation'])
        
        # Create driver with suppressed output
        import logging
        logging.getLogger('selenium').setLevel(logging.ERROR)
        
        # Attach proxy if configured
        if proxy:
            chrome_options.add_argument(f'--proxy-server={proxy}')
        
        driver = webdriver.Chrome(options=chrome_options)
        driver.set_page_load_timeout(10)  # 10 second max
        driver.implicitly_wait(3)  # 3 second implicit wait
        
        # Execute CDP commands to hide automation
        try:
            driver.execute_cdp_cmd('Network.setUserAgentOverride', {
                "userAgent": self.headers["User-Agent"]
            })
            driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        except:
            pass  # Ignore if fails
        
        return driver
    
    def make_request(self, url: str, use_selenium: bool = False) -> Optional[str]:
        """
        Make HTTP request with error handling and retry logic
        
        Args:
            url: URL to request
            use_selenium: Whether to use Selenium
            
        Returns:
            HTML content or None
        """
        # Try ScraperAPI first if configured (handles proxy rotation automatically)
        if self.scraperapi_key:
            render = use_selenium or self.requires_selenium
            html = self._fetch_via_scraperapi(url, render=render)
            if html:
                return html
            else:
                logger.warning(f"ScraperAPI request failed for {url}; falling back to direct scraping")
        # Simple and reliable request logic
        max_retries = 3
        
        for attempt in range(max_retries):
            try:
                if use_selenium or self.requires_selenium:
                    proxy = self._get_next_valid_proxy()
                    driver = self.get_driver(proxy)
                    driver.get(url)
                    time.sleep(2)  # Wait for page load
                    html = driver.page_source
                    driver.quit()
                    return html
                else:
                    # Use session for connection pooling
                    if not self.session:
                        self.session = requests.Session()
                        self.session.headers.update(self.headers)
                    
                    # Rotate UA and proxy per attempt
                    ua = self._get_next_user_agent()
                    self.session.headers.update({'User-Agent': ua})
                    proxy_url = self._get_next_valid_proxy()
                    if not proxy_url and self.proxy_list:
                        logger.warning("All configured proxies exhausted or invalid; falling back to direct connection")
                        self._bad_proxies.clear()
                    proxies = {'http': proxy_url, 'https': proxy_url} if proxy_url else None
                    
                    try:
                        response = self.session.get(url, timeout=self.timeout, proxies=proxies)
                    except Exception as prox_err:
                        if proxy_url:
                            self._bad_proxies.add(proxy_url)
                            logger.warning(f"Proxy failed {proxy_url}: {prox_err}")
                            continue
                        else:
                            logger.warning(f"Direct request failed: {prox_err}")
                            continue
                    
                    # If 403, try with Selenium
                    if response.status_code in (403, 429):
                        if proxy_url:
                            logger.warning(f"Proxy blocked with status {response.status_code}; rotating")
                            self._bad_proxies.add(proxy_url)
                            continue
                        logger.warning(f"Got status {response.status_code}, trying with Selenium: {url}")
                        return self.make_request(url, use_selenium=True)
                    
                    response.raise_for_status()
                    return response.text
                    
            except Exception as e:
                if attempt < max_retries - 1:
                    logger.warning(f"Retry {attempt + 1} for {url}")
                    time.sleep(2)
                    continue
                else:
                    logger.error(f"Error fetching {url}: {str(e)}")
                    return None
        
        return None
    
    def parse_html(self, html: str) -> BeautifulSoup:
        """Parse HTML content with BeautifulSoup"""
        return BeautifulSoup(html, 'lxml')
    
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
            # Handle "today", "yesterday"
            if 'today' in date_str or 'just now' in date_str:
                return now.date()
            elif 'yesterday' in date_str:
                return (now - timedelta(days=1)).date()
            
            # Handle "X hours/days/weeks ago"
            if 'hour' in date_str:
                hours = int(''.join(filter(str.isdigit, date_str)))
                return (now - timedelta(hours=hours)).date()
            elif 'day' in date_str:
                days = int(''.join(filter(str.isdigit, date_str)))
                return (now - timedelta(days=days)).date()
            elif 'week' in date_str:
                weeks = int(''.join(filter(str.isdigit, date_str)))
                return (now - timedelta(weeks=weeks)).date()
            elif 'month' in date_str:
                months = int(''.join(filter(str.isdigit, date_str)))
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
        """Apply rate limiting delay - MINIMAL for speed"""
        time.sleep(0.1)  # Minimal delay for API-based scrapers

    # ===== Utility: Rotation helpers =====
    def _fetch_via_scraperapi(self, url: str, render: bool = False) -> Optional[str]:
        if not self.scraperapi_key:
            return None
        params = {
            'api_key': self.scraperapi_key,
            'url': url,
            'keep_headers': 'true',
        }
        if render and self.scraperapi_render:
            params['render'] = 'true'
        try:
            response = requests.get(
                'https://api.scraperapi.com',
                params=params,
                timeout=self.timeout,
                headers=self.headers,
            )
            response.raise_for_status()
            return response.text
        except Exception as e:
            logger.warning(f"ScraperAPI request failed: {e}")
            return None

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
        all_jobs = []
        
        for keyword in self.keywords:
            logger.info(f"{self.portal_name}: Scraping jobs for keyword '{keyword}'")
            try:
                jobs = self.scrape_jobs()
                all_jobs.extend(jobs)
                logger.info(f"{self.portal_name}: Found {len(jobs)} jobs for '{keyword}'")
            except Exception as e:
                logger.error(f"{self.portal_name}: Error scraping '{keyword}': {str(e)}")
            
            self.rate_limit_delay()
        
        return all_jobs

