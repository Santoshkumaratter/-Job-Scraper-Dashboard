"""Remotive Scraper - API Based (Very Reliable!)"""
from typing import List, Dict
from ..utils.base_scraper import BaseScraper
import requests
import logging

logger = logging.getLogger(__name__)

class RemotiveScraper(BaseScraper):
    @property
    def portal_name(self) -> str:
        return "Remotive"
    
    @property
    def base_url(self) -> str:
        return "https://remotive.com"
    
    def build_search_url(self, keyword: str) -> str:
        return f"{self.base_url}/api/remote-jobs"
    
    def scrape_jobs(self) -> List[Dict]:
        """Remotive has a public API - very reliable!"""
        jobs: List[Dict] = []
        seen_urls: set[str] = set()
        
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            # Query per keyword to maximize matches (API supports search)
            for kw in (self.keywords or ['']):
                kw_param = kw.strip()
                url = "https://remotive.com/api/remote-jobs"
                if kw_param:
                    url += f"?search={requests.utils.quote(kw_param)}"
                
                response = requests.get(url, headers=headers, timeout=4)
                response.raise_for_status()
                data = response.json()
                job_listings = data.get('jobs', [])
                
                # Process ALL jobs from API (no limit per keyword) - user wants all available jobs

                for job_data in job_listings:
                    try:
                        # Filter by keywords across title/category/tags
                        title = (job_data.get('title') or '').lower()
                        category = (job_data.get('category') or '').lower()
                        tags_text = ' '.join(job_data.get('tags') or []).lower()
                        
                        if self.keywords:
                            match = any(
                                (k.lower() in title) or (k.lower() in category) or (k.lower() in tags_text)
                                for k in self.keywords
                            )
                            if not match:
                                continue
                        
                        # Parse posted date
                        posted_date = None
                        if job_data.get('publication_date'):
                            from datetime import datetime
                            try:
                                posted_date = datetime.fromisoformat(job_data['publication_date'].replace('Z', '+00:00')).date()
                            except:
                                pass
                        
                        # Check time filter
                        if not self.should_include_job(posted_date):
                            continue
                        
                        company_size = 'UNKNOWN'
                        company_name = job_data.get('company_name', '')
                        company_url = job_data.get('company_url') or None
                        
                        # Remotive only has remote jobs
                        detected_type = 'REMOTE'
                        
                        # ✅ VALIDATE: If filter is not "ALL" and not "REMOTE", skip
                        if not self.matches_job_type_filter(detected_type):
                            continue  # Skip if filter doesn't match
                        
                        # Build job dict
                        job = {
                            'job_title': job_data.get('title', ''),
                            'company': job_data.get('company_name', ''),
                            'company_url': company_url,
                            'company_size': company_size,
                            'market': 'USA',
                            'job_link': job_data.get('url', ''),
                            'posted_date': posted_date,
                            'location': job_data.get('candidate_required_location', 'Remote'),
                            'job_description': job_data.get('description', '')[:500] if job_data.get('description') else '',
                            'job_type': detected_type,
                            'salary_range': job_data.get('salary', '')
                        }
                        
                        # Deduplicate by job link
                        if job['job_link'] and job['job_link'] not in seen_urls and job['job_title'] and job['company']:
                            seen_urls.add(job['job_link'])
                            jobs.append(job)
                    
                    except Exception as e:
                        logger.error(f"Error parsing Remotive job: {str(e)}")
                        continue
            
            logger.info(f"Remotive: Filtered to {len(jobs)} matching jobs")
            
        except Exception as e:
            logger.error(f"Error fetching Remotive API: {str(e)}")
        
        return jobs
