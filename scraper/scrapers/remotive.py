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
            # ✅ FREE TOOLS: Use fake-useragent for random browser headers
            try:
                from fake_useragent import UserAgent
                ua = UserAgent()
                user_agent = ua.random
            except:
                user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            
            headers = {
                'User-Agent': user_agent,
                'Accept': 'application/json, text/plain, */*',
                'Accept-Language': 'en-US,en;q=0.9',
                'Referer': 'https://remotive.com/',
                'Origin': 'https://remotive.com',
            }
            
            # ✅ GET ALL JOBS: Don't filter by keyword - get ALL jobs from API
            seen_job_ids = set()  # Deduplicate across keyword queries
            
            # Try with keyword first, but if no results, try without keyword to get ALL jobs
            for kw in (self.keywords or ['']):
                kw_param = kw.strip()
                url = "https://remotive.com/api/remote-jobs"
                if kw_param:
                    url += f"?search={requests.utils.quote(kw_param)}"
                
                try:
                    response = requests.get(url, headers=headers, timeout=30)
                    response.raise_for_status()
                    data = response.json()
                    job_listings = data.get('jobs', [])
                    
                    logger.info(f"Remotive API returned {len(job_listings)} jobs for keyword '{kw_param if kw_param else 'ALL'}'")
                    
                    # If no jobs with keyword, try without keyword to get ALL jobs
                    if not job_listings and kw_param:
                        logger.info(f"Remotive: No jobs for keyword '{kw_param}', trying ALL jobs...")
                        url_all = "https://remotive.com/api/remote-jobs"
                        response_all = requests.get(url_all, headers=headers, timeout=30)
                        response_all.raise_for_status()
                        data_all = response_all.json()
                        job_listings = data_all.get('jobs', [])
                        logger.info(f"Remotive API returned {len(job_listings)} total jobs (without keyword filter)")
                    
                    # Process ALL jobs from API (no limit) - user wants all available jobs
                    if not job_listings:
                        logger.debug(f"Remotive API returned empty job list")
                        continue
                except Exception as e:
                    logger.error(f"Remotive API error: {e}")
                    continue

                for job_data in job_listings:
                    try:
                        # Deduplicate by job ID
                        job_id = job_data.get('id') or job_data.get('url') or ''
                        if job_id and job_id in seen_job_ids:
                            continue
                        seen_job_ids.add(job_id)
                        
                        # Filter by keywords across title/category/tags - less strict matching
                        title = (job_data.get('title') or '').lower()
                        category = (job_data.get('category') or '').lower()
                        tags_text = ' '.join(job_data.get('tags') or []).lower()
                        description = (job_data.get('description') or '').lower()
                        
                        # ✅ REMOVED ALL KEYWORD FILTERING - Include ALL jobs from API
                        # No keyword filtering - get maximum jobs
                        
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
                        
                        company_size = ''
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
                            'company_profile_url': None,  # Remotive API doesn't provide company profile URLs
                            'market': 'USA',
                            'job_link': job_data.get('url', ''),
                            'posted_date': posted_date,
                            'location': job_data.get('candidate_required_location', 'Remote'),
                            'job_description': job_data.get('description', '')[:500] if job_data.get('description') else '',
                            'job_type': detected_type,
                            'salary_range': job_data.get('salary', '')
                        }
                        
                        # ✅ REMOVED STRICT VALIDATION - Only require job_title
                        # Deduplicate by job link
                        if job['job_link'] and job['job_link'] not in seen_urls and job['job_title']:
                            # Infer company if missing
                            if not job['company'] or job['company'].lower() in ['unknown', '']:
                                try:
                                    from urllib.parse import urlparse
                                    domain = urlparse(job['job_link']).netloc
                                    if domain:
                                        job['company'] = domain.replace('www.', '').split('.')[0].title()
                                except:
                                    job['company'] = 'Company Not Listed'
                            
                            seen_urls.add(job['job_link'])
                            jobs.append(job)
                    
                    except Exception as e:
                        logger.error(f"Error parsing Remotive job: {str(e)}")
                        continue
            
            logger.info(f"Remotive: Filtered to {len(jobs)} matching jobs")
            
        except Exception as e:
            logger.error(f"Error fetching Remotive API: {str(e)}")
        
        return jobs
