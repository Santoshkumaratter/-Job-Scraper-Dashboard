"""
Celery tasks for scraping operations
"""
from celery import shared_task
from django.utils import timezone
import logging
from .scraper_manager import ScraperManager
from .models import Job
from dashboard.models import SavedFilter, ScraperRun


logger = logging.getLogger(__name__)


@shared_task(bind=True)
def scrape_jobs_task(self, saved_filter_id: int):
    """
    Celery task to scrape jobs for a saved filter
    
    Args:
        saved_filter_id: ID of the SavedFilter
        
    Returns:
        Dictionary with task results
    """
    try:
        # Get saved filter
        saved_filter = SavedFilter.objects.get(id=saved_filter_id)
        
        # Update last used
        saved_filter.increment_use_count()
        
        # Create scraper run
        scraper_run = ScraperRun.objects.create(
            saved_filter=saved_filter,
            status='PENDING',
            celery_task_id=self.request.id
        )
        
        logger.info(f"Starting scraper task for filter '{saved_filter.name}' (Run #{scraper_run.id})")
        print(f"🔍 [DEBUG] Starting Celery task for filter '{saved_filter.name}' (Run #{scraper_run.id})")
        
        try:
            # Run scraper
            manager = ScraperManager(saved_filter, scraper_run)
            result = manager.run()
            
            # CRITICAL: Wait a bit to ensure all threads are done before returning
            # This prevents "cannot schedule new futures" errors in Celery
            print(f"🔍 [DEBUG] Scraper run completed, waiting 3 seconds for threads to finish...")
            import time
            time.sleep(3)
            print(f"✅ [DEBUG] Celery task completed successfully")
            
            return result
        except Exception as e:
            print(f"❌ [DEBUG] Celery task error: {e}")
            logger.error(f"Celery task error: {e}", exc_info=True)
            # Wait a bit even on error
            import time
            time.sleep(2)
            raise
        
    except SavedFilter.DoesNotExist:
        error_msg = f"SavedFilter with id {saved_filter_id} not found"
        logger.error(error_msg)
        return {'status': 'error', 'error': error_msg}
    
    except Exception as e:
        error_msg = f"Task failed: {str(e)}"
        logger.error(error_msg)
        return {'status': 'error', 'error': error_msg}


@shared_task
def auto_run_scraper_uk_time():
    """
    Auto-run scraper at UK time (9:00 AM UK time)
    Runs all active filters with time filter set to 24H
    """
    logger.info("Auto-running scraper at UK time (9:00 AM UK)...")
    
    try:
        # Get all active filters and set time filter to 24H for this run
        active_filters = SavedFilter.objects.filter(is_active=True)
        
        if not active_filters.exists():
            logger.info("No active filters found for auto-run")
            return {'status': 'success', 'message': 'No active filters'}
        
        # Run each active filter
        results = []
        for saved_filter in active_filters:
            try:
                # Create scraper run
                scraper_run = ScraperRun.objects.create(
                    saved_filter=saved_filter,
                    status='PENDING',
                    celery_task_id=None
                )
                
                # Run scraper
                manager = ScraperManager(saved_filter, scraper_run)
                result = manager.run()
                results.append({
                    'filter_id': saved_filter.id,
                    'filter_name': saved_filter.name,
                    'status': result.get('status'),
                    'jobs_saved': result.get('saved_jobs', 0)
                })
                
                logger.info(f"Auto-run completed for filter '{saved_filter.name}': {result.get('saved_jobs', 0)} jobs saved")
            except Exception as e:
                logger.error(f"Error auto-running filter '{saved_filter.name}': {str(e)}")
                results.append({
                    'filter_id': saved_filter.id,
                    'filter_name': saved_filter.name,
                    'status': 'error',
                    'error': str(e)
                })
        
        return {
            'status': 'success',
            'message': f'Auto-run completed for {len(results)} filters',
            'results': results
        }
    except Exception as e:
        logger.error(f"Error in auto_run_scraper_uk_time: {str(e)}")
        return {'status': 'error', 'error': str(e)}


@shared_task
def auto_run_scraper_usa_time():
    """
    Auto-run scraper at USA time (9:00 AM EST/EDT)
    Runs all active filters with time filter set to 24H
    """
    logger.info("Auto-running scraper at USA time (9:00 AM EST/EDT)...")
    
    try:
        # Get all active filters and set time filter to 24H for this run
        active_filters = SavedFilter.objects.filter(is_active=True)
        
        if not active_filters.exists():
            logger.info("No active filters found for auto-run")
            return {'status': 'success', 'message': 'No active filters'}
        
        # Run each active filter
        results = []
        for saved_filter in active_filters:
            try:
                # Create scraper run
                scraper_run = ScraperRun.objects.create(
                    saved_filter=saved_filter,
                    status='PENDING',
                    celery_task_id=None
                )
                
                # Run scraper
                manager = ScraperManager(saved_filter, scraper_run)
                result = manager.run()
                results.append({
                    'filter_id': saved_filter.id,
                    'filter_name': saved_filter.name,
                    'status': result.get('status'),
                    'jobs_saved': result.get('saved_jobs', 0)
                })
                
                logger.info(f"Auto-run completed for filter '{saved_filter.name}': {result.get('saved_jobs', 0)} jobs saved")
            except Exception as e:
                logger.error(f"Error auto-running filter '{saved_filter.name}': {str(e)}")
                results.append({
                    'filter_id': saved_filter.id,
                    'filter_name': saved_filter.name,
                    'status': 'error',
                    'error': str(e)
                })
        
        return {
            'status': 'success',
            'message': f'Auto-run completed for {len(results)} filters',
            'results': results
        }
    except Exception as e:
        logger.error(f"Error in auto_run_scraper_usa_time: {str(e)}")
        return {'status': 'error', 'error': str(e)}


@shared_task
def check_scheduled_scrapes():
    """
    Periodic task to check for scheduled scrapes
    This runs every 5 minutes via Celery Beat
    """
    logger.info("Checking for scheduled scrapes...")
    
    # This is a placeholder for future scheduling functionality
    # You can add logic here to automatically trigger scrapes based on schedules
    
    return {'status': 'success', 'message': 'Scheduled scrapes checked'}


@shared_task
def cleanup_old_logs(days: int = 30):
    """
    Cleanup old scraper logs
    
    Args:
        days: Number of days to keep logs
    """
    from .models import ScraperLog
    from datetime import timedelta
    
    cutoff_date = timezone.now() - timedelta(days=days)
    deleted_count, _ = ScraperLog.objects.filter(created_at__lt=cutoff_date).delete()
    
    logger.info(f"Deleted {deleted_count} old log entries")
    
    return {
        'status': 'success',
        'deleted_count': deleted_count
    }

