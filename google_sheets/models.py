"""
Models for Google Sheets App - Managing Google Sheets integration
"""
from django.db import models
from django.utils import timezone


class GoogleSheetConfig(models.Model):
    """Model to store Google Sheets configuration"""
    name = models.CharField(max_length=255, unique=True)
    spreadsheet_id = models.CharField(max_length=255)
    worksheet_name = models.CharField(max_length=255, default='Jobs')
    
    # Column mapping (to customize which columns to export)
    column_mapping = models.JSONField(default=dict, blank=True)
    
    # Settings
    is_active = models.BooleanField(default=True)
    auto_export = models.BooleanField(default=True, help_text="Automatically export new jobs")
    include_headers = models.BooleanField(default=True)
    
    # Statistics
    total_rows_exported = models.IntegerField(default=0)
    last_export_at = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-is_active', 'name']
        verbose_name = 'Google Sheet Config'
        verbose_name_plural = 'Google Sheet Configs'
    
    def __str__(self):
        return self.name


class ExportHistory(models.Model):
    """Model to track Google Sheets export history"""
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('IN_PROGRESS', 'In Progress'),
        ('COMPLETED', 'Completed'),
        ('FAILED', 'Failed'),
    ]
    
    sheet_config = models.ForeignKey(GoogleSheetConfig, on_delete=models.CASCADE, related_name='export_history')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    
    # Statistics
    jobs_exported = models.IntegerField(default=0)
    rows_added = models.IntegerField(default=0)
    rows_updated = models.IntegerField(default=0)
    
    # Error tracking
    error_message = models.TextField(blank=True, null=True)
    
    # Timing
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    duration_seconds = models.FloatField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Export History'
        verbose_name_plural = 'Export Histories'
    
    def __str__(self):
        return f"Export #{self.id} - {self.status} ({self.jobs_exported} jobs)"
    
    def calculate_duration(self):
        """Calculate export duration"""
        if self.started_at and self.completed_at:
            delta = self.completed_at - self.started_at
            self.duration_seconds = delta.total_seconds()
            self.save(update_fields=['duration_seconds'])
