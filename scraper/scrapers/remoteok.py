"""Remote OK Scraper - API Based (Works Well!)"""
from typing import List, Dict
from ..utils.base_scraper import BaseScraper
import requests
import logging

logger = logging.getLogger(__name__)

class RemoteOKScraper(BaseScraper):
    @property
    def portal_name(self) -> str:
        return "Remote OK"
    
    @property
    def base_url(self) -> str:
        return "https://remoteok.com"
    
    def build_search_url(self, keyword: str) -> str:
        return f"{self.base_url}/api"
    
    def scrape_jobs(self) -> List[Dict]:
        """Remote OK has a public API - much more reliable!"""
        jobs = []
        
        try:
            # Remote OK API endpoint
            url = "https://remoteok.com/api"
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            response = requests.get(url, headers=headers, timeout=3)  # 3 second timeout
            response.raise_for_status()
            
            data = response.json()
            
            # First item is metadata, skip it
            job_listings = data[1:] if len(data) > 1 else []
            
            logger.info(f"Remote OK API returned {len(job_listings)} jobs")
            
            # ⚡ Limit for INSTANT results - only process first 20 jobs
            job_listings = job_listings[:20]
            
            logger.info(f"Processing {len(job_listings)} jobs...")
            
            for job_data in job_listings:
                try:
                    # Filter by keywords
                    position = job_data.get('position', '').lower()
                    tags = ' '.join(job_data.get('tags', [])).lower()
                    
                    # ✅ Broaden match: title or tags must contain keyword
                    if self.keywords:
                        position_lower = position.lower()
                        tags_lower = tags.lower()
                        keyword_match = any(
                            (kw.lower() in position_lower) or (kw.lower() in tags_lower)
                            for kw in self.keywords
                        )
                        if not keyword_match:
                            continue
                    
                    # Parse posted date
                    posted_date = None
                    if job_data.get('date'):
                        from datetime import datetime
                        try:
                            posted_date = datetime.fromisoformat(job_data['date'].replace('Z', '+00:00')).date()
                        except:
                            pass
                    
                    # Check time filter
                    if not self.should_include_job(posted_date):
                        continue
                    
                    company_size = 'UNKNOWN'
                    company_url = job_data.get('company_url') if job_data.get('company_url') else None
                    
                    # Remote OK only has remote jobs
                    detected_type = 'REMOTE'
                    
                    # ✅ VALIDATE: If filter is not "ALL" and not "REMOTE", skip
                    if not self.matches_job_type_filter(detected_type):
                        continue  # Skip if filter doesn't match
                    
                    # Build job dict
                    job = {
                        'job_title': job_data.get('position', ''),
                        'company': job_data.get('company', ''),
                        'company_url': company_url,
                        'company_size': company_size,
                        'market': 'USA',
                        'job_link': f"https://remoteok.com/remote-jobs/{job_data.get('id', '')}",
                        'posted_date': posted_date,
                        'location': job_data.get('location', 'Remote'),
                        'job_description': job_data.get('description', '')[:500] if job_data.get('description') else '',
                        'job_type': detected_type,
                        'salary_range': f"${job_data.get('salary_min', 0)}-${job_data.get('salary_max', 0)}" if job_data.get('salary_min') else ''
                    }
                    
                    if job['job_title'] and job['company']:
                        jobs.append(job)
                    
                except Exception as e:
                    logger.error(f"Error parsing Remote OK job: {str(e)}")
                    continue
            
            logger.info(f"Remote OK: Filtered to {len(jobs)} matching jobs")
            
        except Exception as e:
            logger.error(f"Error fetching Remote OK API: {str(e)}")
        
        return jobs
