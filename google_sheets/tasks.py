"""
Celery tasks for Google Sheets operations
"""
from celery import shared_task
import logging
from .models import GoogleSheetConfig
from .services import GoogleSheetsService
from scraper.models import Job

logger = logging.getLogger(__name__)


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

