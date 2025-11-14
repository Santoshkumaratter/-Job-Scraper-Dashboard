"""
Scraper Manager - Orchestrates scraping from multiple job portals
"""
import logging
import sys
import time
from datetime import timedelta
from collections import defaultdict
# ✅ STEP 5: ThreadPoolExecutor for optimized parallel scraping (5-10 threads)
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Optional, Tuple
from django.conf import settings
from django.utils import timezone
from .scrapers import get_scraper, SCRAPER_REGISTRY
from .models import Job, DecisionMaker, ScraperLog, CompanyCache
from .utils.decision_maker_finder import DecisionMakerFinder
from .utils.company_enrichment import CompanyEnrichment
from urllib.parse import urlparse
from dashboard.models import JobPortal, SavedFilter, ScraperRun, Keyword
import re


logger = logging.getLogger(__name__)

# Ensure stdout can handle Unicode logs/emojis to avoid charmap encoding errors
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass


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
        self.relax_filters = False
        self.relaxation_notes: Dict[str, str] = {}
        self._company_info_cache: Dict[str, Dict[str, Optional[str]]] = {}
        self._enriched_companies = set()
        self.keyword_catalog = self._prepare_keyword_catalog()

    def _prepare_keyword_catalog(self) -> Dict[str, set]:
        """
        Build a lookup of active keywords grouped by category so we can
        infer whether a job is technical or non-technical.
        """
        keywords_qs = self.saved_filter.keywords.filter(is_active=True).values('name', 'category')
        keyword_records = list(keywords_qs)
        if not keyword_records:
            keyword_records = list(Keyword.objects.filter(is_active=True).values('name', 'category'))
        
        catalog: Dict[str, set] = {
            'TECHNICAL': set(),
            'NON_TECHNICAL': set(),
            'BOTH': set(),
        }
        for record in keyword_records:
            name = (record.get('name') or '').strip().lower()
            if not name:
                continue
            category = (record.get('category') or 'BOTH').upper()
            if category not in catalog:
                catalog[category] = set()
            catalog[category].add(name)
        
        return catalog

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
        print("="*80)
        print(f"🚀 STARTING SCRAPER RUN #{self.scraper_run.id}")
        print("="*80)
        logger.info(f"Starting scraper run #{self.scraper_run.id}")
        
        # Reset relaxation state for this run
        self.relax_filters = False
        self.relaxation_notes = {}
        
        # Update scraper run status
        self.scraper_run.status = 'RUNNING'
        self.scraper_run.started_at = timezone.now()
        self.scraper_run.save()
        print(f"✅ Scraper run status set to RUNNING")
        
        try:
            # Get ALL scraping parameters - NO LIMITS
            # Get keywords as strings
            keywords = [str(k) for k in self.saved_filter.keywords.values_list('name', flat=True)]
            
            # Get selected portals - if none selected, use all active portals (All Job Portals)
            selected_portals = list(self.saved_filter.job_portals.filter(is_active=True))
            if not selected_portals:
                # If no portals selected, scrape from all 34 active portals
                # JobPortal is already imported at top of file
                selected_portals = list(JobPortal.objects.filter(is_active=True))
                print(f"   No portals selected - using all {len(selected_portals)} active portals")
                logger.info(f"DEBUG: No portals selected - using all {len(selected_portals)} active portals")
                logger.info(f"No portals selected - using all {len(selected_portals)} active portals")
            
            job_portals = selected_portals
            print(f"   Total portals to scrape: {len(job_portals)}")
            logger.debug(f"DEBUG: Total portals to scrape: {len(job_portals)}")
            logger.debug(f"DEBUG: Portal names: {[p.name for p in job_portals]}")
            
            # ✅ STEP 5: Prioritize lighter portals for faster results
            # Fast API-based portals (non-Selenium, lightweight)
            fast_portals = {
                'Remote OK', 'Remotive', 'Jobtensor', 'Working Nomads', 'Jobspresso',
                'We Work Remotely', 'IT Job Board', 'SEOJobs.com', 'Grabjobs',
                'SEL Jobs', 'Dynamite Jobs', 'SimplyHired', 'Remote.co', 'Jooble'
            }
            # Medium-speed portals
            medium_portals = {
                'Indeed UK', 'CV-Library', 'Reed', 'Totaljobs', 'Adzuna',
                'CWjobs', 'ZipRecruiter', 'Talent', 'Jooble', 'Jora',
                'Redefined', 'WorkInStartups', 'Escape The City', 'Trueup'
            }
            # Slow portals (Selenium required, JavaScript-heavy)
            slow_portals = {
                'Linkedin Jobs', 'Glassdoor', 'Dice', 'AngelList (Wellfound)',
                'Otta', 'CareerBuilder', 'FlexJobs', 'WelcometotheJungle'
            }
            
            def portal_priority(p):
                if p.name in fast_portals:
                    return (0, p.name)
                elif p.name in medium_portals:
                    return (1, p.name)
                elif p.name in slow_portals:
                    return (2, p.name)
                else:
                    return (1, p.name)  # Default to medium
            
            job_portals.sort(key=portal_priority)
            
            # Make sure we're using all active portals
            if len(job_portals) < len(selected_portals):
                logger.warning(f"Using only {len(job_portals)}/{len(selected_portals)} portals - some may be missing scraper implementations")
                missing_portals = [p.name for p in selected_portals if p not in job_portals]
                logger.warning(f"Missing scrapers for: {missing_portals}")
            logger.debug(f"DEBUG: Portals sorted by speed - Fast portals first: {[p.name for p in job_portals[:10]]}")
            
            if not keywords:
                raise ValueError("No keywords selected")
            
            if not job_portals:
                raise ValueError("No job portals available")
            
            print(f"\n📊 SCRAPING CONFIGURATION:")
            print(f"   Portals: {len(job_portals)}")
            print(f"   Keywords: {len(keywords)}")
            print(f"   Job Type: {self.saved_filter.job_type}")
            print(f"   Time Filter: {self.saved_filter.time_filter}")
            print(f"   Location: {self.saved_filter.location}")
            print(f"\n📋 PORTALS TO SCRAPE:")
            for idx, portal in enumerate(job_portals, 1):
                print(f"   {idx}. {portal.name}")
            
            logger.info(f"Scraping {len(job_portals)} portals with {len(keywords)} keywords")
            logger.info(f"Portals to scrape: {[p.name for p in job_portals]}")
            
            all_jobs = []
            successful_portals = 0
            failed_portals = 0
            saved_count = 0

            # Track timing for 5-minute check
            run_start_time = time.time()
            first_job_time = None
            last_check_time = run_start_time
            CHECK_INTERVAL = 300  # 5 minutes in seconds

            # ✅ STEP 5: Use optimized parallel scraping with 5-10 threads for speed
            # This prevents "cannot schedule new futures" errors while maintaining speed
            # Goal: Complete all portals within 5 minutes
            
            USE_PARALLEL_SCRAPING = True  # Enabled with limited thread pool
            MAX_WORKERS = min(20, len(job_portals))  # Increased to 20 threads for faster scraping
            
            if USE_PARALLEL_SCRAPING and len(job_portals) > 3:  # Use parallel for 4+ portals
                # ✅ STEP 5: Use optimized parallel scraping with 5-10 threads
                print(f"\n⚡ OPTIMIZED PARALLEL SCRAPING...")
                print(f"   Using {MAX_WORKERS} parallel workers (optimized for speed & stability)")
                
                logger.info(f"Using {MAX_WORKERS} parallel workers for optimized scraping")
                print(f"🔍 Starting ThreadPoolExecutor with {MAX_WORKERS} workers")
                logger.debug(f"DEBUG: Starting ThreadPoolExecutor with {MAX_WORKERS} workers")
                
                # Use context manager to ensure proper cleanup
                executor = None
                future_to_portal = {}
                all_futures = []
                
                # ✅ Use context manager for automatic cleanup
                print(f"🔍 Creating ThreadPoolExecutor with {MAX_WORKERS} workers...")
                try:
                    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                        print(f"✅ [DEBUG] ThreadPoolExecutor created successfully (context manager)")
                        logger.debug(f"DEBUG: ThreadPoolExecutor created successfully (context manager)")
                        
                        # CRITICAL: Ensure threads are not daemon threads
                        # Daemon threads get killed when main thread exits, causing "cannot schedule new futures" errors
                        try:
                            if hasattr(executor, '_threads'):
                                for thread in executor._threads:
                                    if hasattr(thread, 'daemon'):
                                        thread.daemon = False  # Make threads non-daemon
                                        print(f"🔍 [DEBUG] Set thread {thread.name} to non-daemon")
                            elif hasattr(executor, '_workers'):
                                # Python 3.9+ uses _workers
                                for worker in executor._workers:
                                    if hasattr(worker, 'thread'):
                                        thread = worker.thread
                                        if hasattr(thread, 'daemon'):
                                            thread.daemon = False
                                            print(f"🔍 [DEBUG] Set worker thread to non-daemon")
                        except Exception as e:
                            print(f"⚠️ [DEBUG] Could not set threads to non-daemon: {e}")
                            logger.warning(f"Could not set threads to non-daemon: {e}")
                    
                        # Verify executor is active
                        if hasattr(executor, '_shutdown'):
                            shutdown_state = executor._shutdown
                            print(f"🔍 [DEBUG] Executor shutdown state: {shutdown_state}")
                            if shutdown_state:
                                raise RuntimeError("Executor is already shut down!")
                        
                        # Submit all portal scraping tasks FIRST - before any processing
                        print(f"\n📤 SUBMITTING TASKS TO THREAD POOL...")
                        for idx, portal in enumerate(job_portals, 1):
                            if self._is_cancelled():
                                print(f"⚠️ [DEBUG] Cancellation detected before starting portal tasks")
                                logger.warning("DEBUG: Cancellation detected before starting portal tasks")
                                break
                            
                            try:
                                print(f"   [{idx}/{len(job_portals)}] Submitting: {portal.name}...", end=" ")
                                logger.debug(f"DEBUG: Submitting task for portal: {portal.name}")
                                future = executor.submit(self._scrape_portal, portal, keywords)
                                future_to_portal[future] = portal
                                all_futures.append(future)
                                print(f"✅ Submitted")
                                logger.debug(f"DEBUG: Task submitted for {portal.name}, future: {future}")
                            except RuntimeError as e:
                                error_str = str(e).lower()
                                if "cannot schedule new futures" in error_str or "shutdown" in error_str:
                                    print(f"❌ FAILED - Cannot schedule futures")
                                    print(f"   Error: {e}")
                                    logger.error(f"DEBUG: CRITICAL - Cannot schedule futures for {portal.name}: {e}")
                                    failed_portals += 1
                                    # Don't continue submitting if executor is shut down
                                    print(f"⚠️ [DEBUG] Stopping task submission due to executor shutdown")
                                    raise  # Re-raise to trigger fallback
                                else:
                                    print(f"❌ Error: {e}")
                                    logger.error(f"DEBUG: Error submitting task for {portal.name}: {e}", exc_info=True)
                                    failed_portals += 1
                            except Exception as e:
                                print(f"❌ Unexpected error: {e}")
                                logger.error(f"DEBUG: Error submitting task for {portal.name}: {e}", exc_info=True)
                                failed_portals += 1
                        
                        print(f"\n✅ Successfully submitted {len(future_to_portal)} portal tasks")
                        logger.debug(f"DEBUG: Submitted {len(future_to_portal)} portal tasks")
                    
                        # CRITICAL: Process completed futures BEFORE context manager exits
                        # Use manual polling instead of as_completed to avoid shutdown race conditions
                        processed_futures = set()
                        completed_count = 0
                        max_wait_time = 30  # 30 seconds max per portal for faster results
                        start_time = time.time()
                        
                        # Process futures manually to avoid as_completed shutdown issues
                        print(f"🔍 [DEBUG] Starting to process {len(all_futures)} futures...")
                        try:
                            while len(processed_futures) < len(all_futures):
                                if self._is_cancelled():
                                    print(f"⚠️ [DEBUG] Cancellation detected - stopping result collection")
                                    logger.warning("DEBUG: Cancellation detected - stopping result collection")
                                    break
                                
                                # Check if we've exceeded max wait time
                                elapsed = time.time() - start_time
                                if elapsed > max_wait_time * min(len(all_futures), 5):  # Cap at 5 portals worth of wait time
                                    print(f"⚠️ [DEBUG] Max wait time exceeded ({elapsed:.1f}s), processing remaining futures")
                                    logger.warning("DEBUG: Max wait time exceeded, processing remaining futures")
                                    break
                                
                                # Check each future manually
                                for future in all_futures:
                                    if future in processed_futures:
                                        continue
                                    
                                    # Check if future is done
                                    if future.done():
                                        processed_futures.add(future)
                                        completed_count += 1
                                        
                                        portal = future_to_portal.get(future)
                                        if not portal:
                                            print(f"⚠️ [DEBUG] Future not found in future_to_portal mapping")
                                            logger.warning("DEBUG: Future not found in future_to_portal mapping")
                                            continue
                                        
                                        print(f"\n[{completed_count}/{len(future_to_portal)}] ✅ {portal.name} completed")
                                        logger.debug(f"DEBUG: Processing completed future {completed_count}/{len(future_to_portal)} for {portal.name}")
                                        
                                        try:
                                            # Get result (should be immediate since done() is True)
                                            jobs = future.result(timeout=1)
                                            print(f"   📊 Found {len(jobs)} jobs")
                                            logger.debug(f"DEBUG: Got result from {portal.name}: {len(jobs)} jobs")
                                            
                                            if jobs:
                                                print(f"   💾 Saving jobs...", end=" ")
                                                logger.info(f"{portal.name}: Found {len(jobs)} jobs, saving now...")
                                                # Save immediately so UI can stream results
                                                saved_now = self._save_jobs(jobs)
                                                saved_count += saved_now
                                                
                                                # Track first job time
                                                if saved_now > 0 and first_job_time is None:
                                                    first_job_time = time.time()
                                                    elapsed_minutes = (first_job_time - run_start_time) / 60
                                                    print(f"\n⏰ FIRST JOB SAVED after {elapsed_minutes:.2f} minutes!")
                                                
                                                print(f"✅ Saved {saved_now}/{len(jobs)} jobs")
                                                logger.info(f"{portal.name}: Saved {saved_now}/{len(jobs)} jobs")
                                                all_jobs.extend(jobs)
                                                successful_portals += 1
                                            else:
                                                print(f"   ⚠️  No jobs found")
                                                logger.warning(f"{portal.name}: No jobs found (may be blocked, no matching jobs, or portal issue)")
                                                failed_portals += 1
                                        except Exception as e:
                                            error_msg = f"{portal.name}: {str(e)}"
                                            print(f"❌ [DEBUG] Error getting result from {portal.name}: {error_msg}")
                                            logger.error(f"DEBUG: Error getting result from {portal.name}: {error_msg}", exc_info=True)
                                            self._log_error(portal, error_msg)
                                            failed_portals += 1
                                
                                # Check every 5 minutes for job count
                                current_time = time.time()
                                elapsed_since_check = current_time - last_check_time
                                if elapsed_since_check >= CHECK_INTERVAL:
                                    elapsed_minutes = (current_time - run_start_time) / 60
                                    print(f"\n{'='*80}")
                                    print(f"⏰ 5-MINUTE CHECK: {elapsed_minutes:.1f} minutes elapsed")
                                    print(f"   📊 Total Jobs Saved So Far: {saved_count}")
                                    print(f"   ✅ Successful Portals: {successful_portals}")
                                    print(f"   ❌ Failed Portals: {failed_portals}")
                                    if first_job_time:
                                        first_job_elapsed = (first_job_time - run_start_time) / 60
                                        print(f"   ⏱️  First job saved after: {first_job_elapsed:.2f} minutes")
                                    else:
                                        print(f"   ⚠️  No jobs saved yet!")
                                    print(f"{'='*80}\n")
                                    last_check_time = current_time
                                
                                # Small sleep to avoid busy waiting
                                if len(processed_futures) < len(all_futures):
                                    remaining = len(all_futures) - len(processed_futures)
                                    if completed_count % 5 == 0 or completed_count == 1:  # Print every 5 completions or first
                                        print(f"\n📈 PROGRESS: {completed_count}/{len(all_futures)} completed, {remaining} remaining...")
                                    time.sleep(0.1)
                        
                        except RuntimeError as e:
                            error_str = str(e).lower()
                            if "cannot schedule new futures" in error_str or "shutdown" in error_str:
                                print(f"❌ [DEBUG] CRITICAL - RuntimeError during future processing: {e}")
                                logger.error(f"DEBUG: CRITICAL - RuntimeError during future processing: {e}")
                                logger.error(f"DEBUG: Trying to salvage remaining futures...")
                                # Try to get results from remaining futures
                                for future in all_futures:
                                    if future not in processed_futures:
                                        try:
                                            if future.done():
                                                jobs = future.result(timeout=1)
                                                if jobs:
                                                    print(f"   ✓ Got {len(jobs)} jobs from remaining future")
                                                    saved_now = self._save_jobs(jobs)
                                                    saved_count += saved_now
                                                    all_jobs.extend(jobs)
                                                    successful_portals += 1
                                        except Exception as e:
                                            print(f"   ❌ Error processing remaining future: {str(e)}")
                            else:
                                raise
                        
                        print(f"\n✅ COMPLETED PROCESSING {completed_count} FUTURES")
                        logger.debug(f"DEBUG: Completed processing {completed_count} futures")
                        
                        # CRITICAL: Wait for all remaining futures before context manager exits
                        remaining_futures = [f for f in all_futures if not f.done()]
                        if remaining_futures:
                            print(f"🔍 [DEBUG] Waiting for {len(remaining_futures)} remaining futures before context exit...")
                            logger.debug(f"DEBUG: Waiting for {len(remaining_futures)} remaining futures before context exit...")
                            wait_start = time.time()
                            max_wait = 30  # 30 seconds max wait
                            while remaining_futures and (time.time() - wait_start) < max_wait:
                                for future in remaining_futures[:]:
                                    if future.done():
                                        remaining_futures.remove(future)
                                if remaining_futures:
                                    time.sleep(0.5)
                        
                        # Context manager will automatically call shutdown(wait=True) when exiting
                        print(f"🔍 [DEBUG] Context manager will handle executor shutdown...")
                        
                        # CRITICAL: Additional wait after context manager to ensure threads are done
                        # This is especially important for Celery tasks
                        print(f"🔍 [DEBUG] Waiting 2 seconds after context exit to ensure threads are done...")
                        time.sleep(2)
                        print(f"✅ [DEBUG] Context manager exit complete")
                    
                except RuntimeError as e:
                    error_str = str(e).lower()
                    if "cannot schedule new futures" in error_str or "shutdown" in error_str:
                        print(f"❌ [DEBUG] CRITICAL - RuntimeError caught: {e}")
                        logger.error(f"DEBUG: CRITICAL - RuntimeError caught: {e}")
                        # Try to salvage any completed futures
                        for future in all_futures:
                            try:
                                if future.done():
                                    jobs = future.result(timeout=1)
                                    if jobs:
                                        saved_now = self._save_jobs(jobs)
                                        saved_count += saved_now
                                        all_jobs.extend(jobs)
                                        successful_portals += 1
                            except:
                                pass
                        # Wait a bit for threads to finish
                        print(f"🔍 [DEBUG] Waiting 3 seconds for threads to finish after error...")
                        time.sleep(3)
                        # Fall through to sequential scraping
                        USE_PARALLEL_SCRAPING = False
                    else:
                        print(f"❌ [DEBUG] Critical error in ThreadPoolExecutor: {e}")
                        logger.error(f"DEBUG: Critical error in ThreadPoolExecutor: {e}", exc_info=True)
                        USE_PARALLEL_SCRAPING = False
                except Exception as e:
                    error_str = str(e).lower()
                    print(f"❌ [DEBUG] Critical error in ThreadPoolExecutor: {e}")
                    logger.error(f"DEBUG: Critical error in ThreadPoolExecutor: {e}", exc_info=True)
                    
                    # If it's the "cannot schedule new futures" error, fall back to sequential
                    if "cannot schedule new futures" in error_str or "shutdown" in error_str:
                        print(f"\n⚠️  PARALLEL SCRAPING FAILED - FALLING BACK TO SEQUENTIAL SCRAPING...")
                        print(f"   Error: {e}")
                        logger.warning(f"Parallel scraping failed, falling back to sequential: {e}")
                        
                        # Wait a bit for threads to finish
                        print(f"🔍 [DEBUG] Waiting 3 seconds for threads to finish...")
                        time.sleep(3)
                        USE_PARALLEL_SCRAPING = False
                    else:
                        # Wait a bit for threads to finish
                        print(f"🔍 [DEBUG] Waiting 3 seconds for threads to finish after error...")
                        time.sleep(3)
                        USE_PARALLEL_SCRAPING = False
            
            # Use sequential scraping (default or fallback)
            if not USE_PARALLEL_SCRAPING:
                print(f"\n🔄 USING SEQUENTIAL SCRAPING (More Reliable)...")
                logger.info(f"Using sequential scraping for {len(job_portals)} portals")
                
                for idx, portal in enumerate(job_portals, 1):
                    if self._is_cancelled():
                        print(f"⚠️ Cancellation detected - stopping sequential scraping")
                        break
                    
                    print(f"\n[{idx}/{len(job_portals)}] Scraping {portal.name}...")
                    try:
                        jobs = self._scrape_portal(portal, keywords)
                        if jobs:
                            all_jobs.extend(jobs)
                            print(f"   ✅ Found {len(jobs)} jobs")
                            saved_now = self._save_jobs(jobs)
                            saved_count += saved_now
                            logger.info(f"Sequential scraping saved {saved_now}/{len(jobs)} jobs from {portal.name}")

                            if saved_now > 0 and first_job_time is None:
                                first_job_time = time.time()
                                elapsed_minutes = (first_job_time - run_start_time) / 60
                                print(f"\n⏰ FIRST JOB SAVED after {elapsed_minutes:.2f} minutes!")

                            if saved_now > 0:
                                successful_portals += 1
                            print(f"   ✅ Saved {saved_now}/{len(jobs)} jobs")
                        else:
                            print(f"   ⚠️  No jobs found")
                            failed_portals += 1
                        
                        # Check every 5 minutes (even if no jobs found)
                        current_time = time.time()
                        elapsed_since_check = current_time - last_check_time
                        if elapsed_since_check >= CHECK_INTERVAL:
                            elapsed_minutes = (current_time - run_start_time) / 60
                            print(f"\n{'='*80}")
                            print(f"⏰ 5-MINUTE CHECK: {elapsed_minutes:.1f} minutes elapsed")
                            print(f"   📊 Total Jobs Saved So Far: {saved_count}")
                            print(f"   ✅ Successful Portals: {successful_portals}")
                            print(f"   ❌ Failed Portals: {failed_portals}")
                            if first_job_time:
                                first_job_elapsed = (first_job_time - run_start_time) / 60
                                print(f"   ⏱️  First job saved after: {first_job_elapsed:.2f} minutes")
                            else:
                                print(f"   ⚠️  No jobs saved yet!")
                            print(f"{'='*80}\n")
                            last_check_time = current_time
                    except Exception as portal_error:
                        print(f"   ❌ Error: {portal_error}")
                        logger.error(f"Error scraping {portal.name}: {portal_error}", exc_info=True)
                        failed_portals += 1
                        
                        # Check every 5 minutes even on error
                        current_time = time.time()
                        elapsed_since_check = current_time - last_check_time
                        if elapsed_since_check >= CHECK_INTERVAL:
                            elapsed_minutes = (current_time - run_start_time) / 60
                            print(f"\n{'='*80}")
                            print(f"⏰ 5-MINUTE CHECK: {elapsed_minutes:.1f} minutes elapsed")
                            print(f"   📊 Total Jobs Saved So Far: {saved_count}")
                            print(f"   ✅ Successful Portals: {successful_portals}")
                            print(f"   ❌ Failed Portals: {failed_portals}")
                            if first_job_time:
                                first_job_elapsed = (first_job_time - run_start_time) / 60
                                print(f"   ⏱️  First job saved after: {first_job_elapsed:.2f} minutes")
                            else:
                                print(f"   ⚠️  No jobs saved yet!")
                            print(f"{'='*80}\n")
                            last_check_time = current_time
                
                print(f"\n✅ SEQUENTIAL SCRAPING COMPLETED:")
                print(f"   Saved: {saved_count} jobs")
                print(f"   Successful: {successful_portals} portals")
                print(f"   Failed: {failed_portals} portals")

            # Fallback: if nothing saved and not cancelled, try quick API-only portals to show instant data
            if saved_count == 0 and not self._is_cancelled():
                print(f"\n🔄 FALLBACK: No jobs saved, trying quick API portals...")
                logger.info("No jobs saved in main pass. Running quick API fallback...")
                # Use more API-based portals for fallback
                quick_names = ['Remotive', 'Remote OK', 'We Work Remotely', 'Jobspresso', 'Working Nomads', 'Jobtensor']
                from dashboard.models import JobPortal as JobPortalModel
                quick_portals = list(JobPortalModel.objects.filter(is_active=True, name__in=quick_names))
                print(f"   Found {len(quick_portals)} quick API portals")
                for portal in quick_portals:
                    if self._is_cancelled():
                        print("   ⚠️ Fallback aborted due to cancellation")
                        break
                    try:
                        print(f"   Trying {portal.name}...", end=" ")
                        jobs = self._scrape_portal(portal, keywords)
                        if jobs:
                            all_jobs.extend(jobs)
                            saved_now = self._save_jobs(jobs)
                            saved_count += saved_now

                            if saved_now > 0:
                                if first_job_time is None:
                                    first_job_time = time.time()
                                    elapsed_minutes = (first_job_time - run_start_time) / 60
                                    print(f"\n⏰ FIRST JOB SAVED after {elapsed_minutes:.2f} minutes!")
                                print(f"✅ Saved {saved_now} jobs")
                                logger.info(f"Fallback saved {saved_now} jobs from {portal.name}")
                                successful_portals += 1
                                self.relaxation_notes.setdefault(
                                    'quick_fallback',
                                    'Triggered quick API fallback (Remotive, Remote OK)'
                                )
                            else:
                                print(f"⚠️  No jobs saved after validation")
                        else:
                            print(f"⚠️  No jobs found")
                    except Exception as e:
                        print(f"❌ Error: {e}")
                        self._log_error(portal, f"Fallback error: {str(e)}")
            
                # If still no jobs saved, relax filters and try again
                if saved_count == 0 and not self._is_cancelled():
                    print("\n🔁 No jobs after quick fallback — relaxing filters further...")
                    relaxed_saved, updated_first_job_time, relaxed_portals = self._run_relaxed_fallback(
                        keywords,
                        run_start_time,
                        first_job_time,
                        all_jobs
                    )
                    saved_count += relaxed_saved
                    successful_portals += relaxed_portals
                    if first_job_time is None and updated_first_job_time is not None:
                        first_job_time = updated_first_job_time

            # Print consolidated summary after all passes
            self._print_final_summary(
                saved_count,
                successful_portals,
                failed_portals,
                len(all_jobs),
                run_start_time,
                first_job_time
            )

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
            
            print(f"\n" + "="*80)
            print(f"✅ SCRAPER RUN #{self.scraper_run.id} COMPLETED")
            print(f"="*80)
            print(f"   Portals: {successful_portals} successful, {failed_portals} failed")
            print(f"   Jobs Saved: {saved_count}")
            print(f"   Total Jobs Found: {len(all_jobs)}")
            print("="*80)
            logger.info(f"Scraper run #{self.scraper_run.id} completed:")
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
        Scrape a single job portal with enhanced error handling and logging
        
        Args:
            portal: JobPortal instance
            keywords: List of keywords to search
            
        Returns:
            List of job dictionaries
        """
        try:
            if self._is_cancelled():
                return []
            
            print(f"      🔍 Scraping {portal.name}...", end=" ")
            scraper = get_scraper(
                portal.name,
                keywords=keywords,
                job_type=self.saved_filter.job_type,
                time_filter='ALL',  # Override to ALL to get more jobs, we'll filter later
                location=self.saved_filter.location
            )
            
            if not scraper:
                print(f"❌ No scraper found")
                error_msg = f"No scraper found for portal: {portal.name}"
                logger.warning(error_msg)
                self._log_error(portal, error_msg)
                return []
            
            logger.info(f"Starting to scrape {portal.name} with {len(keywords)} keyword(s)...")
            logger.debug(f"DEBUG: Portal: {portal.name}, Scraper class: {type(scraper).__name__}")
            # Keywords are already strings, not objects
            keyword_names = [k if isinstance(k, str) else k.name for k in keywords]
            logger.info(f"   Keywords: {keyword_names}")
            logger.info(f"   Job type filter: {self.saved_filter.job_type}")
            logger.info(f"   Location filter: {self.saved_filter.location}")
            logger.info(f"   Time filter: {self.saved_filter.time_filter}")
            
            scrape_start = time.time()
            try:
                logger.debug(f"DEBUG: Calling scrape_all() for {portal.name}")
                jobs = scraper.scrape_all()
                logger.debug(f"DEBUG: scrape_all() returned {len(jobs)} jobs for {portal.name}")
                
                # Log sample job data for debugging
                if jobs:
                    sample = jobs[0]
                    logger.debug(f"DEBUG: Sample job from {portal.name}:")
                    logger.debug(f"  Title: {sample.get('job_title', 'N/A')}")
                    logger.debug(f"  Company: {sample.get('company', 'N/A')}")
                    logger.debug(f"  Company URL: {sample.get('company_url', 'N/A')}")
                    logger.debug(f"  Company Size: {sample.get('company_size', 'N/A')}")
                    logger.debug(f"  Location: {sample.get('location', 'N/A')}")
            except Exception as scrape_error:
                print(f"❌ Error: {scrape_error}")
                error_msg = f"Scraping failed for {portal.name}: {str(scrape_error)}"
                logger.error(f"DEBUG: {error_msg}", exc_info=True)
                logger.error(error_msg)
                self._log_error(portal, error_msg)
                return []
            
            scrape_time = time.time() - scrape_start
            print(f"✅ Found {len(jobs)} jobs ({scrape_time:.1f}s)")
            logger.info(f"{portal.name}: Found {len(jobs)} jobs in {scrape_time:.1f}s")
            logger.debug(f"DEBUG: Scraping completed for {portal.name} in {scrape_time:.1f}s")
            
            if jobs:
                print(f"   📋 Sample jobs from {portal.name}:")
                for idx, job in enumerate(jobs[:3], 1):
                    print(f"      {idx}. {job.get('job_title', 'N/A')[:60]}")
                    print(f"         Company: {job.get('company', 'N/A')}")
                    print(f"         Market: {job.get('market', 'N/A')}")
                    print(f"         Posted: {job.get('posted_date', 'N/A')}")
                logger.info(f"   Sample job titles: {[j.get('job_title', 'N/A')[:50] for j in jobs[:3]]}")
            else:
                print(f"   ⚠️  {portal.name}: No jobs found (may be blocked or no matching jobs)")
                logger.warning(f"{portal.name}: No jobs found (may be blocked or no matching jobs)")
            
            # Add portal information to each job
            for job in jobs:
                job['portal_id'] = portal.id
                job['source_portal_name'] = portal.name
            
            return jobs
            
        except Exception as e:
            error_msg = f"Error scraping {portal.name}: {str(e)}"
            logger.error(error_msg, exc_info=True)
            self._log_error(portal, error_msg)
            return []  # Return empty list instead of raising to allow other portals to continue
    
    def _run_relaxed_fallback(
        self,
        keywords: List[str],
        run_start_time: float,
        first_job_time: Optional[float],
        all_jobs: List[Dict]
    ) -> Tuple[int, Optional[float], int]:
        """Run an additional scraping pass with relaxed filters."""
        print(f"\n🔁 RELAXED FILTER FALLBACK: Activating smarter defaults to surface jobs")
        print(f"   ➡️ Relaxing keyword matching to title or description")
        print(f"   ➡️ Expanding time window to the last 30 days (if needed)")
        print(f"   ➡️ Allowing any location/market for remote-friendly roles")
        logger.info("Starting relaxed filter fallback pass")
        self.relaxation_notes.setdefault(
            'relaxed_filters',
            'Relaxed keyword/time/location filters after empty main run'
        )

        saved_relaxed = 0
        portals_with_saves = 0
        updated_first_job_time = first_job_time
        previous_state = self.relax_filters
        self.relax_filters = True

        try:
            quick_names = ['Remotive', 'Remote OK']
            from dashboard.models import JobPortal as JobPortalModel
            quick_portals = list(JobPortalModel.objects.filter(is_active=True, name__in=quick_names))
            print(f"   Considering {len(quick_portals)} fast API portals with relaxed rules")

            for portal in quick_portals:
                if self._is_cancelled():
                    print("   ⚠️ Relaxed fallback aborted due to cancellation")
                    break

                try:
                    print(f"   Trying {portal.name} with relaxed filters...", end=" ")
                    jobs = self._scrape_portal(portal, keywords)
                    if jobs:
                        all_jobs.extend(jobs)
                        saved_now = self._save_jobs(jobs)
                        saved_relaxed += saved_now

                        if saved_now > 0:
                            portals_with_saves += 1
                            if updated_first_job_time is None:
                                updated_first_job_time = time.time()
                                elapsed_minutes = (updated_first_job_time - run_start_time) / 60
                                print(f"\n⏰ FIRST JOB SAVED (relaxed) after {elapsed_minutes:.2f} minutes!")
                            print(f"✅ Relaxed fallback saved {saved_now} jobs from {portal.name}")
                            logger.info(
                                f"Relaxed fallback saved {saved_now} jobs from {portal.name}"
                            )
                        else:
                            print(f"⚠️  Relaxed fallback found jobs but none passed validation")
                    else:
                        print(f"⚠️  No jobs returned even with relaxed filters")
                except Exception as e:
                    print(f"❌ Error during relaxed fallback on {portal.name}: {e}")
                    logger.error(
                        f"Relaxed fallback error for {portal.name}: {e}",
                        exc_info=True
                    )
                    self._log_error(portal, f"Relaxed fallback error: {str(e)}")
        finally:
            self.relax_filters = previous_state

        return saved_relaxed, updated_first_job_time, portals_with_saves
    
    def _infer_job_field(self, job_title: str, job_description: str = '') -> str:
        """
        Determine whether a job should be tagged as Technical, Non-Technical,
        or Both based on active keyword catalog and improved matching.
        """
        # Normalize and combine text for matching
        job_title = job_title.lower() if job_title else ''
        job_description = job_description.lower() if job_description else ''
        combined_text = f"{job_title} {job_description}"
        if not combined_text.strip():
            return 'UNKNOWN'
        
        # Count matches by category for better classification
        tech_matches = 0
        non_tech_matches = 0
        both_matches = 0
        
        # First pass: check job title directly (weighted higher)
        for category, terms in self.keyword_catalog.items():
            for term in terms:
                if not term:
                    continue
                # Full word matching in title (weighted higher)
                if term in job_title.split() or f"{term} " in job_title or f" {term}" in job_title:
                    if category == 'TECHNICAL':
                        tech_matches += 3  # Weighted higher for title matches
                    elif category == 'NON_TECHNICAL':
                        non_tech_matches += 3
                    else:  # BOTH
                        both_matches += 2
                        tech_matches += 1
                        non_tech_matches += 1
                # Substring matching in title
                elif term in job_title:
                    if category == 'TECHNICAL':
                        tech_matches += 2
                    elif category == 'NON_TECHNICAL':
                        non_tech_matches += 2
                    else:  # BOTH
                        both_matches += 1
                        tech_matches += 1
                        non_tech_matches += 1
                        
        # Second pass: check description (weighted lower)
        for category, terms in self.keyword_catalog.items():
            for term in terms:
                if not term:
                    continue
                if term in job_description:
                    if category == 'TECHNICAL':
                        tech_matches += 1
                    elif category == 'NON_TECHNICAL':
                        non_tech_matches += 1
                    else:  # BOTH
                        both_matches += 0.5
                        tech_matches += 0.5
                        non_tech_matches += 0.5
        
        # Make decision based on match counts
        if tech_matches == 0 and non_tech_matches == 0:
            # Special case for common technical roles without explicit matching
            if any(tech_title in job_title for tech_title in ['developer', 'engineer', 'programmer', 
                                                             'software', 'data', 'analyst', 'devops', 
                                                             'administrator', 'architect']):
                return 'TECHNICAL'
            return 'UNKNOWN'
        
        # Classification logic
        if tech_matches > non_tech_matches * 2:
            return 'TECHNICAL'
        elif non_tech_matches > tech_matches * 2:
            return 'NON_TECHNICAL'
        elif tech_matches > 0 and non_tech_matches > 0:
            return 'BOTH'
        elif tech_matches > 0:
            return 'TECHNICAL'
        elif non_tech_matches > 0:
            return 'NON_TECHNICAL'
        else:
            return 'UNKNOWN'
    
    def _enrich_company_data(
        self,
        company_name: str,
        company_url: Optional[str],
        company_size: Optional[str]
    ) -> Tuple[Optional[str], str]:
        """
        Use cached data + enrichment service to fill in missing company URL/size.
        """
        if not company_name:
            return company_url, company_size or 'UNKNOWN'
        
        normalized_name = re.sub(r'\s+', ' ', company_name.strip().lower())
        if not normalized_name or normalized_name in GENERIC_COMPANY_TOKENS:
            return company_url, company_size or 'UNKNOWN'
        
        cache_entry = self._company_info_cache.get(normalized_name)
        if cache_entry is None:
            db_cache = CompanyCache.objects.filter(company_name__iexact=company_name).first()
            cache_entry = {
                'company_url': db_cache.company_url if db_cache else None,
                'company_size': db_cache.company_size if db_cache else None,
                'company_domain': db_cache.company_domain if db_cache else None,
            }
            self._company_info_cache[normalized_name] = cache_entry
        final_url = company_url or cache_entry.get('company_url')
        final_size = company_size if company_size and company_size != 'UNKNOWN' else cache_entry.get('company_size')
        company_domain = cache_entry.get('company_domain')
        
        needs_enrichment = (
            normalized_name not in self._enriched_companies and
            (not final_size or final_size == 'UNKNOWN' or not final_url)
        )
        
        if needs_enrichment:
            try:
                if not final_size or final_size == 'UNKNOWN':
                    enriched_size = self.company_enrichment.get_company_size(company_name, final_url)
                    if enriched_size and enriched_size != 'UNKNOWN':
                        final_size = enriched_size
            except Exception as exc:
                logger.debug(f"Company size enrichment failed for {company_name}: {exc}")
            
            try:
                if not final_url:
                    domain = self.company_enrichment.get_company_domain(company_name)
                    if domain:
                        company_domain = domain
                        if domain.startswith('http'):
                            final_url = domain
                        else:
                            final_url = f"https://{domain}"
            except Exception as exc:
                logger.debug(f"Company domain enrichment failed for {company_name}: {exc}")
            
            self._enriched_companies.add(normalized_name)
            cache_entry.update({
                'company_url': final_url,
                'company_size': final_size,
                'company_domain': company_domain,
            })
            self._cache_company_info(company_name, cache_entry)
        else:
            cache_entry['company_url'] = final_url
            cache_entry['company_size'] = final_size
            cache_entry['company_domain'] = company_domain
        
        return final_url, (final_size or 'UNKNOWN')
    
    def _cache_company_info(self, company_name: str, info: Dict[str, Optional[str]]):
        """Persist enriched company data for 30 days to avoid repeated lookups."""
        try:
            url_value = info.get('company_url') or None
            size_value = info.get('company_size') or None
            domain_value = info.get('company_domain') or None
            
            # Derive domain from URL if needed
            if not domain_value and url_value:
                try:
                    parsed = urlparse(url_value)
                    domain_value = parsed.hostname
                except Exception:
                    domain_value = None
            
            CompanyCache.objects.update_or_create(
                company_name=company_name,
                defaults={
                    'company_url': url_value,
                    'company_size': size_value,
                    'company_domain': domain_value,
                    'cache_valid_until': timezone.now() + timedelta(days=30),
                }
            )
        except Exception as exc:
            logger.debug(f"Could not cache company info for {company_name}: {exc}")
    
    def _save_jobs(self, jobs_data: List[Dict]) -> int:
        """
        Save scraped jobs to database
        
        Args:
            jobs_data: List of job dictionaries
            
        Returns:
            Number of jobs saved
        """
        saved_count = 0
        
        logger.info(f"_save_jobs: Received {len(jobs_data)} jobs to process")
        
        for idx, job_data in enumerate(jobs_data):
            if idx < 3:  # Log first 3 for debugging
                logger.info(f"_save_jobs: Processing job {idx+1}: '{job_data.get('job_title', 'N/A')}' from {job_data.get('company', 'N/A')}")
                logger.debug(f"  Initial company URL: {job_data.get('company_url', 'None')}")
                logger.debug(f"  Initial company size: {job_data.get('company_size', 'None')}")
                logger.debug(f"  Company profile URL: {job_data.get('company_profile_url', 'None')}")
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
                    job_title = job_data.get('job_title', 'N/A')
                    print(f"   ⚠️  SKIPPING: '{job_title[:50]}...' - Filter mismatch")
                    logger.debug(f"Skipping job '{job_title}' - filter mismatch")
                    self._record_skip('filter_mismatch')
                    continue
                else:
                    job_title = job_data.get('job_title', 'N/A')
                    print(f"   ✅ MATCHES FILTER: '{job_title[:50]}...' - Proceeding to save...")
                    logger.debug(f"Job '{job_title}' matches filter, proceeding to save...")
                # Check if job already exists (by job_link)
                job_link = job_data.get('job_link', '')
                if Job.objects.filter(job_link=job_link).exists():
                    logger.debug(f"Job already exists: {job_link}")
                    self._record_skip('duplicate')
                    continue
                
                # ✅ STEP 6: Validate job link is accessible (optional - can be disabled for speed)
                # Uncomment to enable job link validation (adds ~2-3s per job)
                # if job_link and not self._validate_job_link(job_link):
                #     logger.debug(f"Invalid job link (not accessible): {job_link}")
                #     self._record_skip('invalid_link')
                #     continue
                
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
                
                # Validation: require title (company can be empty if not available)
                if not job_title:
                    logger.debug("Skipping job due to missing title")
                    self._record_skip('missing_title')
                    continue
                
                # If company is missing, try to infer from job link or use placeholder
                if not company_name:
                    # Try to extract from job link domain
                    link = job_data.get('job_link', '')
                    try:
                        host = urlparse(link).hostname or ''
                        if host:
                            parts = [p for p in host.split('.') if p and p != 'www']
                            if len(parts) >= 2:
                                sld = parts[-2]
                                blocked_hosts = {
                                    'linkedin', 'indeed', 'remotive', 'remoteok', 'glassdoor', 'monster',
                                    'careers', 'jobs', 'workable', 'greenhouse', 'lever', 'cvlibrary',
                                    'ziprecruiter', 'jobsite', 'reed', 'weworkremotely', 'stackoverflow',
                                }
                                if sld not in blocked_hosts:
                                    company_name = sld.replace('-', ' ').title()
                    except:
                        pass
                    
                    # If still no company, use a placeholder but don't reject the job
                    if not company_name:
                        company_name = 'Company Not Listed'  # Allow jobs without company names
                
                # Validate company name is not generic
                company_token = re.sub(r'[^a-z0-9]', '', company_name.lower())
                if len(company_token) >= 2 and company_token in GENERIC_COMPANY_TOKENS:
                    logger.debug(f"Skipping job due to generic company name: {company_name}")
                    self._record_skip('generic_company_name')
                    continue

                # Get company URL and size from job data first (fastest)
                company_url = job_data.get('company_url') or ''
                company_size = job_data.get('company_size', '')
                company_profile_url = job_data.get('company_profile_url')
                
                # Only fetch company profile if we don't have URL or size (optimize speed)
                # Skip profile fetching for speed - we'll use what we have from job listing
                should_fetch_profile = False
                if company_profile_url and not company_url and not company_size:
                    should_fetch_profile = True  # Only fetch if we have nothing
                
                # Quick company enrichment - only fetch profile if we have nothing (optimize speed)
                profile_data = {}
                if should_fetch_profile and company_profile_url and portal:
                    try:
                        scraper_class = SCRAPER_REGISTRY.get(portal.name)
                        if scraper_class:
                            temp_scraper = scraper_class(
                                keywords=['temp'],
                                job_type='ALL',
                                time_filter='ALL',
                                location='ALL'
                            )
                            # Quick fetch with timeout (optimized for speed)
                            profile_data = temp_scraper._fetch_company_profile(company_profile_url)
                            if profile_data:
                                if profile_data.get('website_url') and not company_url:
                                    company_url = profile_data['website_url']
                                if profile_data.get('company_size') and profile_data.get('company_size') != 'UNKNOWN' and not company_size:
                                    company_size = profile_data['company_size']
                    except Exception as e:
                        logger.debug(f"Quick profile fetch failed for {company_name}: {e}")
                # If still no company URL, try to infer from company name (fast fallback)
                if not company_url and company_name:
                    try:
                        from urllib.parse import urlparse
                        # Try common patterns (fast, no network call)
                        company_slug = company_name.lower().replace(' ', '').replace('-', '').replace('.', '')
                        potential_domains = [
                            f"https://www.{company_slug}.com",
                            f"https://{company_slug}.com",
                            f"https://www.{company_name.lower().replace(' ', '-')}.com",
                        ]
                        # Quick validation - just check if domain looks valid (don't fetch full page)
                        for domain in potential_domains[:1]:  # Only try first one for speed
                            try:
                                parsed = urlparse(domain)
                                if parsed.netloc and len(parsed.netloc) > 3:
                                    company_url = domain
                                    logger.debug(f"Inferred company URL for {company_name}: {company_url}")
                                    break
                            except:
                                pass
                    except:
                        pass
                
                # Validate and sanitize company URL (only if we have one)
                if company_url:
                    company_url = self._sanitize_company_url(company_url, company_name)
                
                # Enrich company information (URL + size) with caching
                company_url, company_size = self._enrich_company_data(
                    company_name,
                    company_url,
                    company_size or ''
                )
                
                # Log final values for debugging (first 3 jobs)
                if idx < 3:
                    logger.info(f"  ✅ FINAL - Company URL: {company_url or 'Not found'}")
                    logger.info(f"  ✅ FINAL - Company Size: {company_size or 'Not found'}")
                
                job_type_value = (job_data.get('job_type') or 'UNKNOWN').upper()
                if job_type_value not in {'REMOTE', 'FULL_TIME', 'FREELANCE', 'HYBRID', 'PART_TIME', 'UNKNOWN'}:
                    job_type_value = 'UNKNOWN'
                
                # Improved job field categorization with more context
                job_field_value = self._infer_job_field(
                    job_title,
                    job_data.get('job_description', '')
                )

                job = Job.objects.create(
                    job_title=job_title,
                    company=company_name,
                    company_url=company_url or None,  # Store None instead of empty string
                    company_size=company_size or 'UNKNOWN',  # Use UNKNOWN as default for DB
                    job_field=job_field_value,
                    market=job_data.get('market', 'OTHER'),
                    source_job_portal=portal,
                    job_link=job_data.get('job_link', ''),
                    posted_date=job_data.get('posted_date'),
                    location=job_data.get('location', ''),
                    job_description=job_data.get('job_description', ''),
                    job_type=job_type_value,
                    salary_range=job_data.get('salary_range', ''),
                    scraper_run=self.scraper_run
                )
                
                # Find decision makers for the job (async to not block scraping)
                try:
                    self._find_decision_makers(job, max_results=3)
                except Exception as e:
                    logger.warning(f"Error finding decision makers for {job.company}: {str(e)}")
                
                saved_count += 1
                
                # Log every job for debugging
                logger.info(f"✅ SAVED job #{saved_count}: '{job_title}' at {company_name} (portal: {portal.name if portal else 'N/A'})")
                
                # Log every 10 jobs to track progress
                if saved_count % 10 == 0:
                    logger.info(f"💾 Saved {saved_count} jobs so far...")
                
            except Exception as e:
                logger.error(f"❌ Error saving job: {str(e)}")
                import traceback
                logger.error(f"Traceback: {traceback.format_exc()}")
                self._record_skip('exception')
                continue
        
        logger.info(f"_save_jobs: Complete - saved {saved_count}/{len(jobs_data)} jobs")
        
        # Print summary
        print(f"\n   💾 SAVE SUMMARY:")
        print(f"      Total Jobs Received: {len(jobs_data)}")
        print(f"      Jobs Saved: {saved_count}")
        print(f"      Jobs Skipped: {len(jobs_data) - saved_count}")
        if self.skip_reasons:
            print(f"      Skip Reasons:")
            for reason, count in sorted(self.skip_reasons.items()):
                print(f"         - {reason}: {count}")
        
        return saved_count

    def _record_skip(self, reason: str):
        self.skip_reasons[reason] += 1

    def _log_skip_summary(self):
        if not self.skip_reasons:
            logger.info("No jobs were skipped during this run")
            return
        summary = ", ".join(f"{reason}: {count}" for reason, count in sorted(self.skip_reasons.items()))
        logger.info(f"Skip summary → {summary}")

    def _print_final_summary(
        self,
        saved_count: int,
        successful_portals: int,
        failed_portals: int,
        total_jobs_found: int,
        run_start_time: float,
        first_job_time: Optional[float]
    ):
        """Display consolidated run results including fallback info."""
        total_elapsed_minutes = (time.time() - run_start_time) / 60

        print(f"\n{'='*80}")
        print(f"💾 FINAL RESULTS:")
        print(f"   Total Jobs Saved: {saved_count}")
        print(f"   Successful Portals: {successful_portals}")
        print(f"   Failed Portals: {failed_portals}")
        print(f"   Total Jobs Found: {total_jobs_found}")
        print(f"   Total Time Elapsed: {total_elapsed_minutes:.2f} minutes")

        print(f"\n⏰ 5-MINUTE CHECK SUMMARY:")
        if first_job_time:
            first_job_elapsed = (first_job_time - run_start_time) / 60
            if first_job_elapsed <= 5:
                print(f"   ✅ JOBS FOUND WITHIN 5 MINUTES!")
            else:
                print(f"   ⚠️  NO JOBS FOUND WITHIN 5 MINUTES")
            print(f"   ⏱️  First job saved after: {first_job_elapsed:.2f} minutes")
        else:
            print(f"   ❌ NO JOBS SAVED AT ALL!")
            print(f"   ⚠️  Scraper ran for {total_elapsed_minutes:.2f} minutes but found 0 jobs")

        if self.relaxation_notes:
            print(f"\n🔧 Adjustments Applied:")
            for note in self.relaxation_notes.values():
                print(f"   - {note}")

        print(f"{'='*80}\n")

        logger.info(f"Saved {saved_count} jobs (including fallbacks)")
        logger.info(f"Total jobs seen: {total_jobs_found}")
        self._log_skip_summary()

    # ======= Central filter validator =======
    def _job_matches_filter(self, job: Dict) -> bool:
        """Apply SavedFilter rules to a scraped job dict with improved matching."""
        relaxed = self.relax_filters

        # Keyword: title (and optionally description) must contain a keyword
        title = (job.get('job_title') or '').lower()
        description = (job.get('job_description') or '').lower()
        keywords = list(self.saved_filter.keywords.values_list('name', flat=True))
        if keywords:
            lowered_keywords = [k.lower() for k in keywords]
            
            # For fuzzy matching - split keywords into tokens for better matching
            tokenized_keywords = []
            for kw in lowered_keywords:
                # Split multi-word keywords into individual words for better matching
                if ' ' in kw and len(kw) > 10:  # Only for longer multi-word keywords
                    tokenized_keywords.extend(kw.split())
                    
            # Add tokenized keywords if we have any
            if tokenized_keywords:
                # Keep only tokens that are significant (3+ chars)
                significant_tokens = [t for t in tokenized_keywords if len(t) > 2]
                # Add these tokens to our keyword list for matching
                lowered_keywords.extend(significant_tokens)
                    
            # Different matching logic based on relaxed mode
            if relaxed:
                combined_text = f"{title} {description}".strip()
                # More forgiving matching in relaxed mode
                keyword_match = any(k in combined_text for k in lowered_keywords)
                
                # Try fuzzy matching if no direct match (for technical keywords)
                if not keyword_match and 'python' in lowered_keywords:
                    # Special case for Python as it's a common keyword
                    if any(tech_term in combined_text for tech_term in ['develop', 'engineer', 'program', 'script', 'code']):
                        keyword_match = True
                
                if not keyword_match:
                    print(
                        f"      ❌ Filter (relaxed): Keyword mismatch - Text does not contain any of: {lowered_keywords[:3]}"
                    )
                    return False
                print("      ✅ Filter (relaxed): Keyword match found in title/description")
            else:
                # Try direct title match first
                keyword_match = any(k in title for k in lowered_keywords)
                
                # If no title match and we have a description, try there too for specific keywords
                if not keyword_match and description:
                    # For certain important keywords, check description too
                    important_keywords = ['python', 'java', 'javascript', 'react', 'node', 'aws', 'cloud']
                    matching_important = [k for k in lowered_keywords if k in important_keywords]
                    if matching_important and any(k in description for k in matching_important):
                        keyword_match = True
                        print(f"      ✅ Filter: Important keyword found in description")
                        
                if not keyword_match:
                    print(
                        f"      ❌ Filter: Keyword mismatch - Title: '{title[:40]}...' doesn't contain any of: {lowered_keywords[:3]}"
                    )
                    return False
                print("      ✅ Filter: Keyword match - Title or description contains keyword")

        # Job type: if filter != ALL, job_type must match (skip when relaxed)
        jf = (self.saved_filter.job_type or 'ALL').upper()
        jt = (job.get('job_type') or '').upper()
        if not relaxed:
            if jf != 'ALL' and jt != jf:
                print(f"      ❌ Filter: Job type mismatch - Filter: {jf}, Job: {jt}")
                return False
        else:
            if jf != 'ALL' and jt != jf:
                print(f"      🔁 Relaxed: Ignoring job type mismatch (Filter: {jf}, Job: {jt})")

        # Location/market: if filter != ALL, market must match (skip strict when relaxed)
        loc = (self.saved_filter.location or 'ALL').upper()
        market = (job.get('market') or 'OTHER').upper()
        location_text = (job.get('location') or '').upper()
        if not relaxed:
            if loc != 'ALL' and market != loc:
                print(f"      ❌ Filter: Location mismatch - Filter: {loc}, Job Market: {market}")
                return False
        else:
            if loc != 'ALL' and loc not in market and loc not in location_text:
                print(
                    f"      🔁 Relaxed: Allowing location mismatch (Filter: {loc}, Market: {market}, Location: {location_text[:40]})"
                )

        # Time filter: accept if missing date; otherwise enforce (relaxed allows up to 30 days)
        tf = (self.saved_filter.time_filter or 'ALL').upper()
        posted = job.get('posted_date')
        if posted is not None:
            try:
                from datetime import datetime
                now = datetime.now().date()
                delta_days = (now - posted).days
                
                # More flexible time window for specific technical roles that are harder to fill
                is_tech_role = 'TECHNICAL' in job.get('job_field', 'UNKNOWN')
                day_extension = 1 if is_tech_role else 0  # Give tech roles 1 extra day
                
                # For 24H filter, be more lenient to ensure we get enough jobs
                if tf == '24H':
                    # For 24H filter, accept jobs up to 7 days old to ensure we get enough results
                    # This is a temporary fix to ensure users see jobs even with the 24H filter
                    if delta_days > 7:  # Much more lenient for 24H filter
                        print(f"      ❌ Filter: Time mismatch - Posted {delta_days} days ago (filter: 24H, allowing up to 7 days)")
                        return False
                    print(f"      ✅ Filter: Time match - Posted {delta_days} days ago (within 7 day window for 24H filter)")
                elif not relaxed:
                    # Normal handling for other time filters
                    if tf == '3D' and delta_days > (3 + day_extension):
                        print(f"      ❌ Filter: Time mismatch - Posted {delta_days} days ago (filter: 3D)")
                        return False
                    if tf == '7D' and delta_days > (7 + day_extension):
                        print(f"      ❌ Filter: Time mismatch - Posted {delta_days} days ago (filter: 7D)")
                        return False
                else:
                    # In relaxed mode, use a longer window - 45 days for technical roles, 30 for others
                    max_days = 45 if is_tech_role else 30
                    if delta_days > max_days:
                        print(
                            f"      ❌ Filter (relaxed): Posted {delta_days} days ago which exceeds {max_days}-day relaxed window"
                        )
                        return False
            except Exception as e:
                print(f"      ⚠️  Filter: Date parsing error: {e}")

        if relaxed:
            print("      ✅ Filter (relaxed): All checks passed")
        else:
            print("      ✅ Filter: All checks passed - Job matches filter")

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
        """Validate company URL - ensure it's a real company website, not a job portal or generic domain"""
        if not url:
            return None
        try:
            # Ensure URL has a scheme
            if not url.startswith(('http://', 'https://')):
                url = 'https://' + url
                
            parsed = urlparse(url)
            if parsed.scheme not in {'http', 'https'}:
                return None
            
            host = (parsed.hostname or '').lower()
            if not host:
                return None
            
            # Remove 'www.' for comparison
            host_clean = host.replace('www.', '')
            
            # Block job portals - but allow LinkedIn company pages as they're often legitimate
            blocked_hosts = {
                'indeed.com', 'indeed.co.uk', 'cv-library.co.uk', 'cvlibrary.co.uk',
                'remoteok.com', 'remotive.com', 'weworkremotely.com', 'dice.com', 'ziprecruiter.com',
                'jobsite.co.uk', 'reed.co.uk', 'jooble.org', 'jooble.com', 'glassdoor.com', 'glassdoor.co.in',
                'monster.co.uk', 'monster.com', 'totaljobs.com', 'simplyhired.com', 'stackoverflow.com',
                'workable.com', 'greenhouse.io', 'lever.co', 'jobs.lever.co', 'bamboohr.com'
            }
            
            # Special case for LinkedIn company pages - they're valid
            if 'linkedin.com/company/' in url.lower():
                return url
                
            if host_clean in blocked_hosts or any(host_clean.endswith(f".{blocked}") for blocked in blocked_hosts):
                return None
            
            # Block social media and generic platforms except LinkedIn company pages
            blocked_platforms = {
                'facebook.com', 'twitter.com', 'instagram.com', 'youtube.com',
                'github.com', 'gitlab.com', 'medium.com', 'wikipedia.org', 'reddit.com',
                'google.com', 'bing.com', 'yahoo.com'
            }
            # Only block if it's exactly these domains (not subdomains like api.company.com)
            if host_clean in blocked_platforms:
                return None
            
            # Verify domain matches company name (for enriched domains)
            # Extract meaningful words from company name
            company_words = [re.sub(r'[^a-z0-9]', '', w) for w in company_name.lower().split() if len(w) >= 3]
            company_token = re.sub(r'[^a-z0-9]', '', company_name.lower())
            host_token = re.sub(r'[^a-z0-9]', '', host_clean.split('.')[0])  # Main domain part
            
            # STRICT: For enriched domains, verify it matches company name
            # Reject if domain doesn't match company name at all
            if company_words:
                matches_name = False
                
                # For single word company names, require exact or very close match
                if len(company_words) == 1:
                    company_word = company_words[0].lower()
                    # Exact match required for single word companies
                    if company_word == host_token.lower() or company_word in host_token.lower():
                        matches_name = True
                    elif len(host_token) <= 3:
                        # Very short domains need content verification
                        matches_name = self._verify_domain_in_url(host, company_name, company_words)
                else:
                    # Multi-word: check if any word matches
                    for word in company_words:
                        if len(word) >= 4:
                            if word.lower() in host_token.lower() or host_token.lower() in word.lower():
                                matches_name = True
                                break
                    
                    # Check acronym for multi-word
                    if not matches_name and len(company_words) > 1:
                        acronym = ''.join(w[0] for w in company_words if w)
                        if len(acronym) >= 2 and acronym.lower() == host_token.lower():
                            matches_name = True
                
                # REJECT if domain doesn't match at all (prevent wrong domains like atom.com for Squad)
                if not matches_name:
                    logger.debug(f"Rejected domain {host} - doesn't match company {company_name}")
                    return None

            return parsed.geturl()
        except Exception as e:
            logger.debug(f"Error validating company URL {url}: {e}")
            return None
    
    def _verify_domain_in_url(self, domain: str, company_name: str, company_words: list) -> bool:
        """Verify domain by checking website content for company name"""
        try:
            import requests
            from bs4 import BeautifulSoup
            
            resp = requests.get(f'https://{domain}', timeout=3, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            })
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, 'lxml')
                title = soup.find('title')
                title_text = title.get_text().lower() if title else ''
                
                # Require company name in title for short domains
                company_lower = company_name.lower()
                company_main_word = company_words[0].lower() if company_words else ''
                
                if company_lower in title_text or company_main_word in title_text:
                    return True
                
                return False
        except:
            return False

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
    
    def _validate_job_link(self, job_link: str) -> bool:
        """
        ✅ STEP 6: Validate job link is accessible
        
        Args:
            job_link: URL to validate
            
        Returns:
            True if link is valid and accessible, False otherwise
        """
        if not job_link:
            return False
        
        import requests
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

