"""
Celery tasks for scraping operations
"""
from celery import shared_task
from django.utils import timezone
import logging
from .scraper_manager import ScraperManager
from .models import Job
from dashboard.models import SavedFilter, ScraperRun
from google_sheets.models import GoogleSheetConfig
from google_sheets.services import GoogleSheetsService


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
        
        # Run scraper
        manager = ScraperManager(saved_filter, scraper_run)
        result = manager.run()
        
        # Auto-export to Google Sheets if configured
        if result.get('status') == 'success':
            try:
                # Get active sheet config with auto_export enabled
                sheet_config = GoogleSheetConfig.objects.filter(
                    is_active=True,
                    auto_export=True
                ).first()
                
                if sheet_config:
                    # Export new jobs
                    new_jobs = Job.objects.filter(
                        scraper_run=scraper_run,
                        is_exported_to_sheets=False
                    )
                    
                    if new_jobs.exists():
                        logger.info(f"Auto-exporting {new_jobs.count()} jobs to Google Sheets")
                        sheets_service = GoogleSheetsService(sheet_config)
                        sheets_service.export_jobs(list(new_jobs))
            except Exception as e:
                logger.error(f"Error auto-exporting to Google Sheets: {str(e)}")
        
        return result
        
    except SavedFilter.DoesNotExist:
        error_msg = f"SavedFilter with id {saved_filter_id} not found"
        logger.error(error_msg)
        return {'status': 'error', 'error': error_msg}
    
    except Exception as e:
        error_msg = f"Task failed: {str(e)}"
        logger.error(error_msg)
        return {'status': 'error', 'error': error_msg}


@shared_task
def export_to_sheets_task(sheet_config_id: int, job_ids: list = None):
    """
    Celery task to export jobs to Google Sheets
    
    Args:
        sheet_config_id: ID of GoogleSheetConfig
        job_ids: Optional list of specific job IDs to export
        
    Returns:
        Dictionary with task results
    """
    try:
        sheet_config = GoogleSheetConfig.objects.get(id=sheet_config_id)
        sheets_service = GoogleSheetsService(sheet_config)
        
        if job_ids:
            # Export specific jobs
            jobs = Job.objects.filter(id__in=job_ids)
            logger.info(f"Exporting {jobs.count()} specific jobs to Google Sheets")
            export_history = sheets_service.export_jobs(list(jobs))
        else:
            # Export all new jobs
            logger.info("Exporting new jobs to Google Sheets")
            export_history = sheets_service.export_new_jobs()
        
        return {
            'status': 'success',
            'export_history_id': export_history.id,
            'jobs_exported': export_history.jobs_exported
        }
        
    except GoogleSheetConfig.DoesNotExist:
        error_msg = f"GoogleSheetConfig with id {sheet_config_id} not found"
        logger.error(error_msg)
        return {'status': 'error', 'error': error_msg}
    
    except Exception as e:
        error_msg = f"Export task failed: {str(e)}"
        logger.error(error_msg)
        return {'status': 'error', 'error': error_msg}


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

