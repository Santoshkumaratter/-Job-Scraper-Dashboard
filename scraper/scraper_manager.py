"""
Scraper Manager - Orchestrates scraping from multiple job portals
"""
import logging
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Optional
from django.conf import settings
from django.utils import timezone
from .scrapers import get_scraper, SCRAPER_REGISTRY
from .models import Job, DecisionMaker, ScraperLog
from .utils.decision_maker_finder import DecisionMakerFinder
from .utils.company_enrichment import CompanyEnrichment
from urllib.parse import urlparse
from dashboard.models import JobPortal, SavedFilter, ScraperRun
import re


logger = logging.getLogger(__name__)


GENERIC_COMPANY_TOKENS = {
    'company', 'employer', 'hiringcompany', 'hiringmanager', 'confidential', 'unknown', 'na', 'n/a',
    'notprovided', 'notdisclosed', 'privatelyheld'
}


class ScraperManager:
    """
    Manages the scraping process across multiple job portals
    """
    
    def __init__(self, saved_filter: SavedFilter, scraper_run: ScraperRun):
        self.saved_filter = saved_filter
        self.scraper_run = scraper_run
        self.decision_maker_finder = DecisionMakerFinder()
        self.company_enrichment = CompanyEnrichment()
        self.skip_reasons = defaultdict(int)

    def _is_cancelled(self) -> bool:
        """Return True if the current run has been marked as CANCELLED or deleted."""
        try:
            from dashboard.models import ScraperRun as ScrRun
            current = ScrRun.objects.only('status').get(id=self.scraper_run.id)
            return current.status == 'CANCELLED'
        except Exception:
            # If the run no longer exists, treat as cancelled
            return True
    
    def run(self) -> Dict:
        """
        Execute scraping for all selected job portals
        
        Returns:
            Dictionary with scraping statistics
        """
        logger.info(f"Starting scraper run #{self.scraper_run.id}")
        
        # Update scraper run status
        self.scraper_run.status = 'RUNNING'
        self.scraper_run.started_at = timezone.now()
        self.scraper_run.save()
        
        try:
            # Get ALL scraping parameters - NO LIMITS
            keywords = list(self.saved_filter.keywords.values_list('name', flat=True))
            job_portals = list(self.saved_filter.job_portals.filter(is_active=True))
            # Prioritize fast API-based portals for instant results
            api_first = {'Remotive', 'Remote OK'}
            job_portals.sort(key=lambda p: (p.name not in api_first, p.name))
            
            if not keywords:
                raise ValueError("No keywords selected")
            
            if not job_portals:
                raise ValueError("No job portals selected")
            
            logger.info(f"🚀 Scraping {len(job_portals)} portals with {len(keywords)} keywords")
            
            all_jobs = []
            successful_portals = 0
            failed_portals = 0
            saved_count = 0

            # Scrape portals in parallel for speed
            max_workers = min(6, len(job_portals)) or 1
            executor = ThreadPoolExecutor(max_workers=max_workers)
            future_to_portal = {}
            try:
                for portal in job_portals:
                    if self._is_cancelled():
                        logger.info("Cancellation detected before starting portal tasks")
                        break
                    future = executor.submit(self._scrape_portal, portal, keywords)
                    future_to_portal[future] = portal

                for future in as_completed(future_to_portal):
                    if self._is_cancelled():
                        logger.info("Cancellation detected - stopping result collection")
                        break
                    portal = future_to_portal[future]
                    try:
                        jobs = future.result()
                        if jobs:
                            logger.info(f"✓ {portal.name}: Found {len(jobs)} jobs")
                            # Save immediately so UI can stream results
                            saved_now = self._save_jobs(jobs)
                            saved_count += saved_now
                            all_jobs.extend(jobs)
                            successful_portals += 1
                        else:
                            logger.warning(f"⚠️ {portal.name}: No jobs found")
                            failed_portals += 1
                    except Exception as e:
                        error_msg = f"{portal.name}: {str(e)}"
                        logger.error(error_msg)
                        self._log_error(portal, error_msg)
                        failed_portals += 1
            finally:
                executor.shutdown(wait=False, cancel_futures=True)
            
            # Already saved incrementally; log final count
            logger.info(f"💾 Saved {saved_count} jobs (incremental)")
            self._log_skip_summary()

            # Fallback: if nothing saved and not cancelled, try quick API-only portals to show instant data
            if saved_count == 0 and not self._is_cancelled():
                logger.info("No jobs saved in main pass. Running quick API fallback (Remotive, Remote OK)...")
                quick_names = ['Remotive', 'Remote OK']
                quick_portals = [p for p in JobPortal.objects.filter(is_active=True, name__in=quick_names)]
                for portal in quick_portals:
                    if self._is_cancelled():
                        break
                    try:
                        jobs = self._scrape_portal(portal, keywords)
                        if jobs:
                            saved_now = self._save_jobs(jobs)
                            saved_count += saved_now
                            logger.info(f"Fallback saved {saved_now} jobs from {portal.name}")
                    except Exception as e:
                        self._log_error(portal, f"Fallback error: {str(e)}")
            
            # Update scraper run status
            if self._is_cancelled():
                self.scraper_run.refresh_from_db()
                self.scraper_run.status = 'CANCELLED'
                self.scraper_run.completed_at = timezone.now()
                self.scraper_run.total_jobs_scraped = saved_count
                self.scraper_run.successful_scrapes = successful_portals
                self.scraper_run.failed_scrapes = failed_portals
                self.scraper_run.calculate_duration()
                self.scraper_run.save()
            else:
                self.scraper_run.status = 'COMPLETED'
                self.scraper_run.completed_at = timezone.now()
                self.scraper_run.total_jobs_scraped = saved_count
                self.scraper_run.successful_scrapes = successful_portals
                self.scraper_run.failed_scrapes = failed_portals
                self.scraper_run.calculate_duration()
                self.scraper_run.save()
            
            logger.info(f"✅ Scraper run #{self.scraper_run.id} completed:")
            logger.info(f"   - Portals scraped: {successful_portals} successful, {failed_portals} failed")
            logger.info(f"   - Total jobs saved: {saved_count}")
            
            return {
                'status': 'success',
                'total_jobs': len(all_jobs),
                'saved_jobs': saved_count,
                'portals_scraped': successful_portals,
                'total_portals': len(job_portals),
                'portals_failed': failed_portals,
            }
            
        except Exception as e:
            logger.error(f"Scraper run #{self.scraper_run.id} failed: {str(e)}")
            
            self.scraper_run.status = 'FAILED'
            self.scraper_run.completed_at = timezone.now()
            self.scraper_run.error_log = str(e)
            self.scraper_run.calculate_duration()
            self.scraper_run.save()
            
            return {
                'status': 'error',
                'error': str(e)
            }
    
    def _scrape_portal(self, portal: JobPortal, keywords: List[str]) -> List[Dict]:
        """
        Scrape a single job portal
        
        Args:
            portal: JobPortal instance
            keywords: List of keywords to search
            
        Returns:
            List of job dictionaries
        """
        try:
            if self._is_cancelled():
                return []
            scraper = get_scraper(
                portal.name,
                keywords=keywords,
                job_type=self.saved_filter.job_type,
                time_filter=self.saved_filter.time_filter,
                location=self.saved_filter.location
            )
            
            if not scraper:
                logger.warning(f"No scraper found for portal: {portal.name}")
                return []
            
            jobs = scraper.scrape_all()
            
            # Add portal information to each job
            for job in jobs:
                job['portal_id'] = portal.id
            
            return jobs
            
        except Exception as e:
            logger.error(f"Error scraping {portal.name}: {str(e)}")
            raise
    
    def _save_jobs(self, jobs_data: List[Dict]) -> int:
        """
        Save scraped jobs to database
        
        Args:
            jobs_data: List of job dictionaries
            
        Returns:
            Number of jobs saved
        """
        saved_count = 0
        
        for job_data in jobs_data:
            try:
                # Stop saving if cancelled or run removed
                if self._is_cancelled():
                    break
                from dashboard.models import ScraperRun as ScrRun
                if not ScrRun.objects.filter(id=self.scraper_run.id).exists():
                    logger.warning("ScraperRun deleted during save; aborting saves")
                    break
                # Enforce filter accuracy BEFORE saving
                if not self._job_matches_filter(job_data):
                    self._record_skip('filter_mismatch')
                    continue
                # Check if job already exists (by job_link)
                if Job.objects.filter(job_link=job_data['job_link']).exists():
                    logger.debug(f"Job already exists: {job_data['job_link']}")
                    self._record_skip('duplicate')
                    continue
                
                # Get portal
                portal_id = job_data.pop('portal_id', None)
                portal = JobPortal.objects.get(id=portal_id) if portal_id else None
                
                # Fill missing company from job link hostname if needed
                job_title = job_data.get('job_title', '').strip()
                company_name = (job_data.get('company') or '').strip()
                if not company_name or company_name.lower() in ['unknown', 'unknown company', 'n/a']:
                    link = job_data.get('job_link', '')
                    try:
                        host = urlparse(link).hostname or ''
                        # take second-level domain as company, remove common job hosts
                        if host:
                            parts = [p for p in host.split('.') if p and p != 'www']
                            if len(parts) >= 2:
                                sld = parts[-2]
                                # Handle common multi-part TLDs (co.uk, com.au, etc.)
                                multi_tlds = {'co', 'com', 'org', 'net'}
                                if sld in multi_tlds and len(parts) >= 3:
                                    sld = parts[-3]
                                blocked_hosts = {
                                    'linkedin', 'indeed', 'remotive', 'remoteok', 'glassdoor', 'monster',
                                    'careers', 'jobs', 'workable', 'greenhouse', 'lever', 'cvlibrary',
                                    'ziprecruiter', 'jobsite', 'reed', 'weworkremotely', 'stackoverflow',
                                }
                                if sld not in blocked_hosts:
                                    company_name = sld.replace('-', ' ').title()
                    except:
                        pass
                
                # Strict validation: require title and company after inference
                if not job_title or not company_name:
                    logger.debug("Skipping job due to missing company/title after inference")
                    self._record_skip('missing_company_or_title')
                    continue
                
                company_token = re.sub(r'[^a-z0-9]', '', company_name.lower())
                if len(company_token) < 2 or company_token in GENERIC_COMPANY_TOKENS:
                    logger.debug("Skipping job due to unreliable company name")
                    continue

                # Enrich company size with real data
                company_size = job_data.get('company_size', 'UNKNOWN')
                if company_size == 'UNKNOWN':
                    company_size = self.company_enrichment.get_company_size(
                        company_name,
                        job_data.get('company_url')
                    )
                
                # Create job
                raw_company_url = job_data.get('company_url')
                if not raw_company_url:
                    domain = self.company_enrichment.get_company_domain(company_name)
                    if domain:
                        raw_company_url = f'https://{domain}'
                company_url = self._sanitize_company_url(raw_company_url, company_name)
                job_type_value = (job_data.get('job_type') or 'UNKNOWN').upper()
                if job_type_value not in {'REMOTE', 'FULL_TIME', 'FREELANCE', 'HYBRID', 'PART_TIME', 'UNKNOWN'}:
                    job_type_value = 'UNKNOWN'

                job = Job.objects.create(
                    job_title=job_title,
                    company=company_name,
                    company_url=company_url,
                    company_size=company_size,
                    market=job_data.get('market', 'OTHER'),
                    source_job_portal=portal,
                    job_link=job_data.get('job_link', ''),
                    posted_date=job_data.get('posted_date'),
                    location=job_data.get('location', ''),
                    job_description=job_data.get('job_description', ''),
                    job_type=job_type_value,
                    scraper_run=self.scraper_run
                )
                
                # Find and save decision makers
                self._find_decision_makers(job, max_results=1)
                
                saved_count += 1
                
            except Exception as e:
                logger.error(f"Error saving job: {str(e)}")
                self._record_skip('exception')
                continue
        
        return saved_count

    def _record_skip(self, reason: str):
        self.skip_reasons[reason] += 1

    def _log_skip_summary(self):
        if not self.skip_reasons:
            logger.info("No jobs were skipped during this run")
            return
        summary = ", ".join(f"{reason}: {count}" for reason, count in sorted(self.skip_reasons.items()))
        logger.info(f"Skip summary → {summary}")

    # ======= Central filter validator =======
    def _job_matches_filter(self, job: Dict) -> bool:
        """Apply SavedFilter rules strictly to a scraped job dict."""
        # Keyword: title must contain at least one selected keyword
        title = (job.get('job_title') or '').lower()
        keywords = list(self.saved_filter.keywords.values_list('name', flat=True))
        if keywords:
            if not any(k.lower() in title for k in keywords):
                return False

        # Job type: if filter != ALL, job_type must match
        jf = (self.saved_filter.job_type or 'ALL').upper()
        jt = (job.get('job_type') or '').upper()
        if jf != 'ALL' and jt != jf:
            return False

        # Location/market: if filter != ALL, market must match
        loc = (self.saved_filter.location or 'ALL').upper()
        market = (job.get('market') or 'OTHER').upper()
        if loc != 'ALL' and market != loc:
            return False

        # Time filter: accept if missing date; otherwise enforce
        tf = (self.saved_filter.time_filter or 'ALL').upper()
        posted = job.get('posted_date')
        if tf != 'ALL' and posted is not None:
            try:
                from datetime import datetime, timedelta
                now = datetime.now().date()
                delta_days = (now - posted).days
                if tf == '24H' and delta_days > 1:
                    return False
                if tf == '3D' and delta_days > 3:
                    return False
                if tf == '7D' and delta_days > 7:
                    return False
            except Exception:
                pass

        return True
    
    def _find_decision_makers(self, job: Job, max_results: int = 1):
        """
        Find and save decision makers for a job
        
        Args:
            job: Job instance
            max_results: Number of decision makers to find
        """
        try:
            decision_makers = self.decision_maker_finder.find_decision_makers(
                company_name=job.company,
                company_url=job.company_url,
                max_results=max_results  # Configurable for speed
            )
            
            for dm_data in decision_makers:
                # Sanitize fields: blank instead of Unknown/fake
                name = self._sanitize(dm_data.get('name'))
                title = self._sanitize(dm_data.get('title'))
                linkedin_url = self._sanitize(dm_data.get('linkedin_url'))
                email = self._sanitize_email(dm_data.get('email'))
                phone = self._sanitize_phone(dm_data.get('phone'))
                department = self._sanitize(dm_data.get('department'))
                data_source = self._sanitize(dm_data.get('data_source', 'Auto-Generated')) or 'Auto-Generated'
                confidence = dm_data.get('confidence_score', 0.7) or 0.7
                
                DecisionMaker.objects.create(
                    job=job,
                    company=job.company,
                    name=name,
                    title=title,
                    linkedin_url=linkedin_url or None,
                    email=email or None,
                    phone=phone or None,
                    department=department,
                    data_source=data_source,
                    confidence_score=confidence
                )
            
            logger.debug(f"Found {len(decision_makers)} decision makers for {job.company}")
            
        except Exception as e:
            logger.error(f"Error finding decision makers for {job.company}: {str(e)}")

    def _sanitize_company_url(self, url: Optional[str], company_name: str) -> Optional[str]:
        if not url:
            return None
        try:
            parsed = urlparse(url)
            if parsed.scheme not in {'http', 'https'}:
                return None
            host = (parsed.hostname or '').lower()
            if not host:
                return None
            blocked_hosts = {
                'linkedin.com', 'indeed.com', 'indeed.co.uk', 'cv-library.co.uk', 'cvlibrary.co.uk',
                'remoteok.com', 'remotive.com', 'weworkremotely.com', 'dice.com', 'ziprecruiter.com',
                'jobsite.co.uk', 'reed.co.uk', 'jooble.org', 'jooble.com', 'glassdoor.com', 'glassdoor.co.in',
                'monster.co.uk', 'monster.com', 'totaljobs.com', 'simplyhired.com'
            }
            if host in blocked_hosts or any(host.endswith(f".{blocked}") for blocked in blocked_hosts):
                return None

            # Basic check: ensure company token appears in host (after stripping non-alphanumerics)
            words = [re.sub(r'[^a-z0-9]', '', part) for part in company_name.lower().split() if part]
            host_token = re.sub(r'[^a-z0-9]', '', host)
            meaningful_words = [w for w in words if len(w) >= 3]
            initials = ''.join(w[0] for w in words if w)
            if meaningful_words:
                if not any(word in host_token for word in meaningful_words):
                    if not (initials and initials in host_token):
                        return None

            return parsed.geturl()
        except Exception:
            return None

    # ======= Sanitizers =======
    def _sanitize(self, value: str) -> str:
        if not value:
            return ''
        val = str(value).strip()
        if val.lower() in {'unknown', 'n/a', 'na', 'none', '-', '--'}:
            return ''
        return val

    def _sanitize_email(self, value: str) -> str:
        val = self._sanitize(value)
        if not val:
            return ''
        # basic email regex
        if not re.match(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$", val):
            return ''
        # ignore obvious placeholders
        if any(bad in val for bad in ['example.com', 'no-reply', 'noreply', 'test@']):
            return ''
        return val

    def _sanitize_phone(self, value: str) -> str:
        val = self._sanitize(value)
        if not val:
            return ''
        digits = re.sub(r"\D", "", val)
        # accept numbers with at least 8 digits
        if len(digits) < 8:
            return ''
        return val
    
    def _log_error(self, portal: JobPortal, message: str):
        """
        Log scraping error
        
        Args:
            portal: JobPortal instance
            message: Error message
        """
        try:
            ScraperLog.objects.create(
                scraper_run=self.scraper_run,
                job_portal=portal,
                level='ERROR',
                message=message
            )
        except:
            pass

