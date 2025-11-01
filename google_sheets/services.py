"""
Google Sheets Service - Exports job data to Google Sheets
"""
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from django.conf import settings
from typing import List, Dict
import logging
from .models import GoogleSheetConfig, ExportHistory
from scraper.models import Job
from datetime import datetime


logger = logging.getLogger(__name__)


class GoogleSheetsService:
    """
    Service to export job data to Google Sheets
    """
    
    def __init__(self, config: GoogleSheetConfig):
        self.config = config
        self.client = None
        self.worksheet = None
    
    def connect(self):
        """Connect to Google Sheets API"""
        try:
            scope = [
                'https://spreadsheets.google.com/feeds',
                'https://www.googleapis.com/auth/drive'
            ]
            
            creds = ServiceAccountCredentials.from_json_keyfile_name(
                settings.GOOGLE_SHEETS_CREDENTIALS_FILE,
                scope
            )
            
            self.client = gspread.authorize(creds)
            
            # Open spreadsheet
            spreadsheet = self.client.open_by_key(self.config.spreadsheet_id)
            
            # Get or create worksheet
            try:
                self.worksheet = spreadsheet.worksheet(self.config.worksheet_name)
            except gspread.WorksheetNotFound:
                self.worksheet = spreadsheet.add_worksheet(
                    title=self.config.worksheet_name,
                    rows=1000,
                    cols=20
                )
            
            logger.info(f"Connected to Google Sheet: {self.config.name}")
            return True
            
        except Exception as e:
            logger.error(f"Error connecting to Google Sheets: {str(e)}")
            return False
    
    def get_headers(self) -> List[str]:
        """Get column headers"""
        return [
            'Job Title',
            'Company',
            'Company URL',
            'Company Size',
            'Market (USA/UK)',
            'Source Job Portal',
            'Job Link',
            'Posted Date',
            'Location',
            'Job Type',
            'Decision Maker Name',
            'Decision Maker Title',
            'Decision Maker LinkedIn',
            'Decision Maker Email',
            'Scraped At'
        ]
    
    def export_jobs(self, jobs: List[Job]) -> ExportHistory:
        """
        Export jobs to Google Sheets
        
        Args:
            jobs: List of Job instances
            
        Returns:
            ExportHistory instance
        """
        # Create export history
        export_history = ExportHistory.objects.create(
            sheet_config=self.config,
            status='IN_PROGRESS',
            started_at=datetime.now()
        )
        
        try:
            # Connect to Google Sheets
            if not self.connect():
                raise Exception("Failed to connect to Google Sheets")
            
            # Get existing data
            try:
                existing_rows = self.worksheet.row_count
            except:
                existing_rows = 1
            
            # Prepare data
            rows_to_add = []
            
            # Add headers if this is the first export
            if self.config.include_headers and existing_rows == 1:
                headers = self.get_headers()
                rows_to_add.append(headers)
            
            # Prepare job data
            for job in jobs:
                # Get all decision makers for this job
                decision_makers = job.decision_makers.all()
                
                if decision_makers.exists():
                    # Create a row for each decision maker
                    for dm in decision_makers:
                        row = self._prepare_job_row(job, dm)
                        rows_to_add.append(row)
                else:
                    # Create a row without decision maker
                    row = self._prepare_job_row(job, None)
                    rows_to_add.append(row)
            
            # Export data
            if rows_to_add:
                # Get the next available row
                next_row = existing_rows + 1
                
                # Append data
                self.worksheet.append_rows(rows_to_add, value_input_option='RAW')
                
                # Update job records
                for job in jobs:
                    job.is_exported_to_sheets = True
                    job.save(update_fields=['is_exported_to_sheets'])
                
                # Update export history
                export_history.status = 'COMPLETED'
                export_history.completed_at = datetime.now()
                export_history.jobs_exported = len(jobs)
                export_history.rows_added = len(rows_to_add)
                export_history.calculate_duration()
                export_history.save()
                
                # Update config
                self.config.total_rows_exported += len(rows_to_add)
                self.config.last_export_at = datetime.now()
                self.config.save()
                
                logger.info(f"Exported {len(jobs)} jobs ({len(rows_to_add)} rows) to Google Sheets")
            else:
                export_history.status = 'COMPLETED'
                export_history.completed_at = datetime.now()
                export_history.calculate_duration()
                export_history.save()
            
            return export_history
            
        except Exception as e:
            logger.error(f"Error exporting to Google Sheets: {str(e)}")
            
            export_history.status = 'FAILED'
            export_history.completed_at = datetime.now()
            export_history.error_message = str(e)
            export_history.calculate_duration()
            export_history.save()
            
            raise
    
    def _prepare_job_row(self, job: Job, decision_maker=None) -> List[str]:
        """
        Prepare a row of data for export
        
        Args:
            job: Job instance
            decision_maker: DecisionMaker instance (optional)
            
        Returns:
            List of values for the row
        """
        return [
            job.job_title,
            job.company,
            job.company_url or '',
            dict(Job.COMPANY_SIZE_CHOICES).get(job.company_size, job.company_size),
            job.market,
            job.source_job_portal.name if job.source_job_portal else '',
            job.job_link,
            job.posted_date.strftime('%Y-%m-%d') if job.posted_date else '',
            job.location,
            job.job_type or '',
            decision_maker.name if decision_maker else '',
            decision_maker.title if decision_maker else '',
            decision_maker.linkedin_url if decision_maker else '',
            decision_maker.email if decision_maker else '',
            job.scraped_at.strftime('%Y-%m-%d %H:%M:%S')
        ]
    
    def export_new_jobs(self) -> ExportHistory:
        """
        Export all new (not yet exported) jobs
        
        Returns:
            ExportHistory instance
        """
        new_jobs = Job.objects.filter(is_exported_to_sheets=False)
        logger.info(f"Found {new_jobs.count()} new jobs to export")
        
        return self.export_jobs(list(new_jobs))
    
    def clear_sheet(self):
        """Clear all data from the worksheet"""
        try:
            if not self.connect():
                raise Exception("Failed to connect to Google Sheets")
            
            self.worksheet.clear()
            logger.info(f"Cleared worksheet: {self.config.worksheet_name}")
            
        except Exception as e:
            logger.error(f"Error clearing worksheet: {str(e)}")
            raise

