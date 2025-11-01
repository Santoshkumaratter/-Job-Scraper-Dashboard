"""
Models for Scraper App - Storing scraped job data and decision makers
"""
from django.db import models
from django.utils import timezone
from dashboard.models import JobPortal, ScraperRun


class Job(models.Model):
    """Model to store scraped job listings"""
    MARKET_CHOICES = [
        ('USA', 'USA'),
        ('UK', 'UK'),
        ('OTHER', 'Other'),
    ]
    
    COMPANY_SIZE_CHOICES = [
        ('SMALL', 'Small (1-50)'),
        ('MEDIUM', 'Medium (51-250)'),
        ('LARGE', 'Large (251-1000)'),
        ('ENTERPRISE', 'Enterprise (1000+)'),
        ('UNKNOWN', 'Unknown'),
    ]
    
    # Core job information
    job_title = models.CharField(max_length=500)
    company = models.CharField(max_length=500)
    company_url = models.URLField(max_length=1000, blank=True, null=True)
    company_size = models.CharField(max_length=20, choices=COMPANY_SIZE_CHOICES, default='UNKNOWN')
    market = models.CharField(max_length=10, choices=MARKET_CHOICES)
    
    # Job portal information
    source_job_portal = models.ForeignKey(JobPortal, on_delete=models.SET_NULL, null=True, related_name='jobs')
    job_link = models.URLField(max_length=2000, unique=True)
    
    # Posting details
    posted_date = models.DateField(null=True, blank=True)
    location = models.CharField(max_length=500)
    
    # Job description (optional)
    job_description = models.TextField(blank=True, null=True)
    job_type = models.CharField(max_length=100, blank=True, null=True)  # Remote, Full-time, etc.
    salary_range = models.CharField(max_length=200, blank=True, null=True)
    
    # Scraper metadata
    scraper_run = models.ForeignKey(ScraperRun, on_delete=models.SET_NULL, null=True, blank=True, related_name='jobs')
    is_exported_to_sheets = models.BooleanField(default=False)
    sheets_row_number = models.IntegerField(null=True, blank=True)
    
    # Timestamps
    scraped_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-scraped_at']
        verbose_name = 'Job'
        verbose_name_plural = 'Jobs'
        indexes = [
            models.Index(fields=['company', 'job_title']),
            models.Index(fields=['source_job_portal', 'posted_date']),
            models.Index(fields=['market', 'location']),
        ]
    
    def __str__(self):
        return f"{self.job_title} at {self.company}"


class DecisionMaker(models.Model):
    """Model to store decision maker information for companies"""
    # Company association (can be multiple decision makers per job)
    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name='decision_makers')
    company = models.CharField(max_length=500)  # Denormalized for easier querying
    
    # Decision maker information
    name = models.CharField(max_length=500)
    title = models.CharField(max_length=500)
    linkedin_url = models.URLField(max_length=1000, blank=True, null=True)
    email = models.EmailField(max_length=500, blank=True, null=True)
    
    # Additional information
    phone = models.CharField(max_length=50, blank=True, null=True)
    department = models.CharField(max_length=200, blank=True, null=True)
    
    # Metadata
    data_source = models.CharField(max_length=100, blank=True, null=True)  # LinkedIn, Hunter.io, etc.
    confidence_score = models.FloatField(default=0.0, help_text="Confidence in data accuracy (0-1)")
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['job', 'title']
        verbose_name = 'Decision Maker'
        verbose_name_plural = 'Decision Makers'
        indexes = [
            models.Index(fields=['company', 'name']),
            models.Index(fields=['job', 'title']),
        ]
    
    def __str__(self):
        return f"{self.name} - {self.title} at {self.company}"


class ScraperLog(models.Model):
    """Model to store detailed scraper logs for debugging"""
    LOG_LEVEL_CHOICES = [
        ('DEBUG', 'Debug'),
        ('INFO', 'Info'),
        ('WARNING', 'Warning'),
        ('ERROR', 'Error'),
        ('CRITICAL', 'Critical'),
    ]
    
    scraper_run = models.ForeignKey(ScraperRun, on_delete=models.CASCADE, related_name='logs')
    job_portal = models.ForeignKey(JobPortal, on_delete=models.SET_NULL, null=True, blank=True)
    
    level = models.CharField(max_length=20, choices=LOG_LEVEL_CHOICES, default='INFO')
    message = models.TextField()
    exception_traceback = models.TextField(blank=True, null=True)
    
    # Context
    url_scraped = models.URLField(max_length=2000, blank=True, null=True)
    response_code = models.IntegerField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Scraper Log'
        verbose_name_plural = 'Scraper Logs'
    
    def __str__(self):
        return f"[{self.level}] {self.message[:50]}"


class CompanyCache(models.Model):
    """Cache company information to avoid redundant lookups"""
    company_name = models.CharField(max_length=500, unique=True)
    company_url = models.URLField(max_length=1000, blank=True, null=True)
    company_size = models.CharField(max_length=20, blank=True, null=True)
    company_domain = models.CharField(max_length=500, blank=True, null=True)
    
    # LinkedIn company data
    linkedin_company_id = models.CharField(max_length=200, blank=True, null=True)
    linkedin_company_url = models.URLField(max_length=1000, blank=True, null=True)
    
    # Metadata
    last_updated = models.DateTimeField(auto_now=True)
    cache_valid_until = models.DateTimeField()
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['company_name']
        verbose_name = 'Company Cache'
        verbose_name_plural = 'Company Cache'
    
    def __str__(self):
        return self.company_name
    
    def is_cache_valid(self):
        """Check if cache is still valid"""
        return timezone.now() < self.cache_valid_until
