"""We Work Remotely Scraper - RSS Based (Reliable!)"""
from typing import List, Dict
from ..utils.base_scraper import BaseScraper
import logging
import feedparser
from datetime import datetime

logger = logging.getLogger(__name__)

class WeWorkRemotelyScraper(BaseScraper):
    @property
    def portal_name(self) -> str:
        return "We Work Remotely"
    
    @property
    def base_url(self) -> str:
        return "https://weworkremotely.com"
    
    def build_search_url(self, keyword: str) -> str:
        return f"{self.base_url}/remote-jobs/search?term={keyword}"
    
    def scrape_jobs(self) -> List[Dict]:
        """Scrape using RSS feed - more reliable!"""
        jobs = []
        
        try:
            # We Work Remotely has RSS feeds for different categories
            rss_urls = [
                "https://weworkremotely.com/categories/remote-programming-jobs.rss",
                "https://weworkremotely.com/categories/remote-devops-sysadmin-jobs.rss",
                "https://weworkremotely.com/categories/remote-full-stack-programming-jobs.rss",
            ]
            
            for rss_url in rss_urls:
                try:
                    feed = feedparser.parse(rss_url)
                    
                    # Limit entries for speed
                    entries = feed.entries[:20]
                    
                    for entry in entries:
                        try:
                            title = entry.get('title', '')
                            
                            # Check if any keyword matches
                            keyword_match = False
                            for keyword in self.keywords:
                                if keyword.lower() in title.lower():
                                    keyword_match = True
                                    break
                            
                            if not keyword_match:
                                continue
                            
                            # Parse posted date
                            posted_date = None
                            if hasattr(entry, 'published_parsed'):
                                try:
                                    posted_date = datetime(*entry.published_parsed[:6]).date()
                                except:
                                    pass
                            
                            # Check time filter
                            if not self.should_include_job(posted_date):
                                continue
                            
                            # Extract company from title (format: "Title at Company")
                            company = "Unknown"
                            job_title = title
                            if ' at ' in title:
                                company = title.split(' at ')[-1].strip()
                                job_title = title.split(' at ')[0].strip()
                            
                            # Determine company size
                            company_size = 'MEDIUM'  # Default for remote companies
                            company_lower = company.lower()
                            if 'startup' in company_lower or 'inc' in company_lower:
                                company_size = 'SMALL'
                            elif any(x in company_lower for x in ['corp', 'corporation', 'enterprise']):
                                company_size = 'LARGE'
                            
                            # Generate company URL
                            company_url = None
                            if company != "Unknown":
                                company_name_clean = company.lower().replace(' ', '').replace(',', '').replace('.', '').replace('inc', '').replace('ltd', '').replace('llc', '')[:20]
                                company_url = f"https://www.{company_name_clean}.com"
                            
                            job = {
                                'job_title': job_title,
                                'company': company,
                                'company_url': company_url,
                                'company_size': company_size,
                                'market': 'USA',
                                'job_link': entry.get('link', ''),
                                'posted_date': posted_date,
                                'location': 'Remote',
                                'job_description': entry.get('summary', '')[:500] if entry.get('summary') else '',
                                'job_type': 'REMOTE',
                            }
                            
                            jobs.append(job)
                            
                        except Exception as e:
                            logger.error(f"Error parsing WWR entry: {str(e)}")
                            continue
                
                except Exception as e:
                    logger.error(f"Error fetching WWR RSS: {str(e)}")
                    continue
            
            logger.info(f"We Work Remotely: Found {len(jobs)} matching jobs")
            
        except Exception as e:
            logger.error(f"Error in We Work Remotely scraper: {str(e)}")
        
        return jobs
