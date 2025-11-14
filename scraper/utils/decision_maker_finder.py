"""
Decision Maker Finder - Finds decision makers for companies
Uses LinkedIn scraping, Hunter.io API, and other sources
"""
import requests
import logging
from typing import List, Dict, Optional
from django.conf import settings
from bs4 import BeautifulSoup


logger = logging.getLogger(__name__)


class DecisionMakerFinder:
    """
    Service to find decision makers for companies
    """
    
    def __init__(self):
        self.hunter_api_key = settings.HUNTER_API_KEY
        self.common_titles = [
            'CEO', 'CTO', 'CFO', 'COO',
            'Founder', 'Co-Founder',
            'VP Engineering', 'VP Technology',
            'Engineering Manager', 'Technical Director',
            'Head of Engineering', 'Head of Technology',
            'Hiring Manager', 'HR Manager', 'Talent Acquisition',
            'Recruiter', 'Technical Recruiter',
            'Tech Lead', 'Engineering Lead', 'Team Lead'
        ]
        
    def find_decision_makers(self, company_name: str, company_url: Optional[str] = None,
                           max_results: int = 5) -> List[Dict]:
        """
        Find decision makers for a company
        
        Args:
            company_name: Name of the company
            company_url: Company website URL
            max_results: Maximum number of decision makers to return
            
        Returns:
            List of decision maker dictionaries
        """
        decision_makers = []
        
        # Try Hunter.io first if API key is available
        if self.hunter_api_key and company_url:
            decision_makers.extend(self.find_via_hunter(company_url, max_results))
        
        # If no results, do not fabricate contacts; return empty list
        if len(decision_makers) == 0:
            logger.debug(f"No verified decision makers found for {company_name}; skipping fallback")
            return []
        
        return decision_makers[:max_results]
    
    def generate_fallback_decision_makers(self, company_name: str, company_url: Optional[str] = None, 
                                         max_results: int = 2) -> List[Dict]:
        """Deprecated: retained for backwards compatibility."""
        logger.debug("Fallback decision maker generation requested but disabled to avoid synthetic data")
        return []
    
    def extract_domain(self, url: str) -> str:
        """Extract domain from URL"""
        if not url:
            return "example.com"
        
        from urllib.parse import urlparse
        try:
            parsed = urlparse(url)
            domain = parsed.netloc or parsed.path
            return domain.replace('www.', '')
        except:
            return "example.com"
    
    def generate_phone_number(self) -> str:
        """Generate realistic phone number"""
        import random
        
        # US/UK format
        if random.choice([True, False]):
            # US format
            area = random.randint(200, 999)
            exchange = random.randint(200, 999)
            number = random.randint(1000, 9999)
            return f"+1-{area}-{exchange}-{number}"
        else:
            # UK format
            area = random.randint(1000, 9999)
            number = random.randint(100000, 999999)
            return f"+44-{area}-{number}"
    
    def find_via_hunter(self, company_domain: str, max_results: int = 5) -> List[Dict]:
        """
        Find decision makers using Hunter.io API
        
        Args:
            company_domain: Company domain (e.g., 'company.com')
            max_results: Maximum results
            
        Returns:
            List of decision makers
        """
        if not self.hunter_api_key:
            return []
        
        try:
            # Extract domain from URL if full URL provided
            if company_domain.startswith('http'):
                from urllib.parse import urlparse
                company_domain = urlparse(company_domain).netloc
            
            # Hunter.io Domain Search API
            url = f"https://api.hunter.io/v2/domain-search"
            params = {
                'domain': company_domain,
                'api_key': self.hunter_api_key,
                'limit': max_results
            }
            
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            decision_makers = []
            
            if 'data' in data and 'emails' in data['data']:
                for email_data in data['data']['emails']:
                    # Filter by seniority/position
                    position = email_data.get('position', '').lower()
                    if any(title.lower() in position for title in self.common_titles):
                        decision_makers.append({
                            'name': f"{email_data.get('first_name', '')} {email_data.get('last_name', '')}".strip(),
                            'title': email_data.get('position', ''),
                            'email': email_data.get('value', ''),
                            'linkedin_url': email_data.get('linkedin', ''),
                            'data_source': 'Hunter.io',
                            'confidence_score': email_data.get('confidence', 0) / 100.0
                        })
            
            logger.info(f"Hunter.io found {len(decision_makers)} decision makers for {company_domain}")
            return decision_makers
            
        except Exception as e:
            logger.error(f"Error finding decision makers via Hunter.io: {str(e)}")
            return []
    
    def find_via_linkedin(self, company_name: str, max_results: int = 5) -> List[Dict]:
        """
        Find decision makers via LinkedIn
        Note: Requires proper LinkedIn API access or linkedin-api library setup
        
        Args:
            company_name: Company name
            max_results: Maximum results
            
        Returns:
            List of decision makers
        """
        # This is a placeholder for LinkedIn integration
        # Requires proper authentication and API access
        
        try:
            # from linkedin_api import Linkedin
            # api = Linkedin(settings.LINKEDIN_USERNAME, settings.LINKEDIN_PASSWORD)
            # company = api.get_company(company_name)
            # employees = api.search_people(
            #     keywords=f"{company_name} (CEO OR CTO OR Founder OR Manager)",
            #     limit=max_results
            # )
            # Process and return decision makers
            pass
        except Exception as e:
            logger.error(f"Error finding decision makers via LinkedIn: {str(e)}")
        
        return []
    
    def find_via_company_website(self, company_url: str, max_results: int = 5) -> List[Dict]:
        """
        Try to find decision makers by scraping company website
        
        Args:
            company_url: Company website URL
            max_results: Maximum results
            
        Returns:
            List of decision makers
        """
        decision_makers = []
        
        try:
            # Common pages to check
            pages_to_check = [
                '/about',
                '/team',
                '/about-us',
                '/our-team',
                '/leadership',
                '/contact',
                '/company'
            ]
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            for page in pages_to_check:
                if len(decision_makers) >= max_results:
                    break
                
                try:
                    url = company_url.rstrip('/') + page
                    response = requests.get(url, headers=headers, timeout=10)
                    
                    if response.status_code == 200:
                        soup = BeautifulSoup(response.text, 'lxml')
                        
                        # Look for common patterns
                        # This is a simplified version - real implementation would be more sophisticated
                        team_sections = soup.find_all(['div', 'section'], class_=lambda x: x and ('team' in x.lower() or 'leader' in x.lower()))
                        
                        for section in team_sections:
                            # Extract names and titles
                            # This is very basic - would need to be customized per site
                            pass
                
                except Exception as e:
                    continue
            
            logger.info(f"Website scraping found {len(decision_makers)} decision makers")
            
        except Exception as e:
            logger.error(f"Error scraping company website: {str(e)}")
        
        return decision_makers
    
    def extract_email_from_name(self, name: str, company_domain: str) -> Optional[str]:
        """
        Generate likely email addresses from name and company domain
        
        Args:
            name: Person's name
            company_domain: Company domain
            
        Returns:
            Most likely email address
        """
        if not name or not company_domain:
            return None
        
        # Clean domain
        if company_domain.startswith('http'):
            from urllib.parse import urlparse
            company_domain = urlparse(company_domain).netloc
        
        # Split name
        parts = name.lower().strip().split()
        if len(parts) < 2:
            return None
        
        first_name = parts[0]
        last_name = parts[-1]
        
        # Common email patterns (most common first)
        patterns = [
            f"{first_name}.{last_name}@{company_domain}",
            f"{first_name}@{company_domain}",
            f"{first_name[0]}{last_name}@{company_domain}",
            f"{first_name}_{last_name}@{company_domain}",
        ]
        
        # Return the first pattern (most common)
        return patterns[0]

