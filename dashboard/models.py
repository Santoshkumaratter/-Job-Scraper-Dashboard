"""
Models for Dashboard App - Managing Keywords, Filters, and UI settings
"""
from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User


class Keyword(models.Model):
    """Model to store job-related keywords"""
    CATEGORY_CHOICES = [
        ('TECHNICAL', 'Technical'),
        ('NON_TECHNICAL', 'Non-Technical'),
        ('BOTH', 'Both'),
    ]
    
    name = models.CharField(max_length=255, unique=True)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='BOTH')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['name']
        verbose_name = 'Keyword'
        verbose_name_plural = 'Keywords'
    
    def __str__(self):
        return f"{self.name} ({self.category})"


class JobPortal(models.Model):
    """Model to store job portal configurations"""
    name = models.CharField(max_length=100, unique=True)
    base_url = models.URLField(max_length=500)
    is_active = models.BooleanField(default=True)
    requires_selenium = models.BooleanField(default=False)
    rate_limit = models.IntegerField(default=10, help_text="Requests per minute")
    priority = models.IntegerField(default=0, help_text="Higher priority scraped first")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-priority', 'name']
        verbose_name = 'Job Portal'
        verbose_name_plural = 'Job Portals'
    
    def __str__(self):
        return self.name


class SavedFilter(models.Model):
    """Model to store saved filter configurations"""
    JOB_TYPE_CHOICES = [
        ('ALL', 'All Jobs'),
        ('REMOTE', 'Remote'),
        ('FREELANCE', 'Freelance'),
        ('FULL_TIME', 'Full Time'),
        ('HYBRID', 'Hybrid'),
    ]
    
    TIME_FILTER_CHOICES = [
        ('24H', 'Last 24 Hours'),
        ('3D', 'Last 3 Days'),
        ('7D', 'Last 7 Days'),
        ('ALL', 'All Time'),
    ]
    
    LOCATION_CHOICES = [
        ('ALL', 'All Locations'),
        ('USA', 'USA'),
        ('UK', 'UK'),
    ]
    
    name = models.CharField(max_length=255, unique=True)
    description = models.TextField(blank=True, null=True)
    
    # Filter settings
    job_type = models.CharField(max_length=20, choices=JOB_TYPE_CHOICES, default='ALL')
    time_filter = models.CharField(max_length=10, choices=TIME_FILTER_CHOICES, default='ALL')
    location = models.CharField(max_length=10, choices=LOCATION_CHOICES, default='ALL')
    
    # Relationships
    keywords = models.ManyToManyField(Keyword, related_name='saved_filters')
    job_portals = models.ManyToManyField(JobPortal, related_name='saved_filters')
    
    # Metadata
    is_active = models.BooleanField(default=True)
    last_used = models.DateTimeField(null=True, blank=True)
    use_count = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-last_used', '-created_at']
        verbose_name = 'Saved Filter'
        verbose_name_plural = 'Saved Filters'
    
    def __str__(self):
        return self.name
    
    def increment_use_count(self):
        """Increment use count and update last used timestamp"""
        self.use_count += 1
        self.last_used = timezone.now()
        self.save(update_fields=['use_count', 'last_used'])


class ScraperRun(models.Model):
    """Model to track scraper execution history"""
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('RUNNING', 'Running'),
        ('COMPLETED', 'Completed'),
        ('FAILED', 'Failed'),
        ('CANCELLED', 'Cancelled'),
    ]
    
    saved_filter = models.ForeignKey(SavedFilter, on_delete=models.CASCADE, related_name='scraper_runs')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    
    # Statistics
    total_jobs_scraped = models.IntegerField(default=0)
    successful_scrapes = models.IntegerField(default=0)
    failed_scrapes = models.IntegerField(default=0)
    
    # Timing
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    duration_seconds = models.IntegerField(null=True, blank=True)
    
    # Logs
    error_log = models.TextField(blank=True, null=True)
    celery_task_id = models.CharField(max_length=255, blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Scraper Run'
        verbose_name_plural = 'Scraper Runs'
    
    def __str__(self):
        return f"Run #{self.id} - {self.saved_filter.name} - {self.status}"
    
    def calculate_duration(self):
        """Calculate duration if both timestamps exist"""
        if self.started_at and self.completed_at:
            delta = self.completed_at - self.started_at
            self.duration_seconds = int(delta.total_seconds())
            try:
                # Use update_fields when safe, otherwise fallback to full save
                self.save(update_fields=['duration_seconds'])
            except Exception:
                self.save()
