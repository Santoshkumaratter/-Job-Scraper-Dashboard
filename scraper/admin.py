"""
Admin configuration for Scraper App
"""
from django.contrib import admin
from .models import Job, DecisionMaker, ScraperLog, CompanyCache


class DecisionMakerInline(admin.TabularInline):
    model = DecisionMaker
    extra = 1
    fields = ['name', 'title', 'linkedin_url', 'email']


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = ['job_title', 'company', 'market', 'location', 'source_job_portal', 'posted_date', 'scraped_at']
    list_filter = ['market', 'company_size', 'source_job_portal', 'posted_date', 'is_exported_to_sheets']
    search_fields = ['job_title', 'company', 'location', 'job_description']
    ordering = ['-scraped_at']
    readonly_fields = ['scraped_at', 'updated_at', 'sheets_row_number']
    list_per_page = 50
    inlines = [DecisionMakerInline]
    
    fieldsets = (
        ('Job Information', {
            'fields': ('job_title', 'company', 'company_url', 'company_size', 'market')
        }),
        ('Posting Details', {
            'fields': ('source_job_portal', 'job_link', 'posted_date', 'location', 'job_type', 'salary_range')
        }),
        ('Description', {
            'fields': ('job_description',),
            'classes': ('collapse',)
        }),
        ('Scraper Metadata', {
            'fields': ('scraper_run', 'is_exported_to_sheets', 'sheets_row_number', 'scraped_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(DecisionMaker)
class DecisionMakerAdmin(admin.ModelAdmin):
    list_display = ['name', 'title', 'company', 'email', 'linkedin_url', 'confidence_score']
    list_filter = ['data_source', 'confidence_score']
    search_fields = ['name', 'title', 'company', 'email']
    ordering = ['company', 'title']
    readonly_fields = ['created_at', 'updated_at']
    list_per_page = 50
    
    fieldsets = (
        ('Decision Maker Information', {
            'fields': ('job', 'company', 'name', 'title')
        }),
        ('Contact Information', {
            'fields': ('linkedin_url', 'email', 'phone')
        }),
        ('Additional Details', {
            'fields': ('department', 'data_source', 'confidence_score')
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(ScraperLog)
class ScraperLogAdmin(admin.ModelAdmin):
    list_display = ['level', 'scraper_run', 'job_portal', 'message_preview', 'response_code', 'created_at']
    list_filter = ['level', 'job_portal', 'created_at']
    search_fields = ['message', 'url_scraped']
    ordering = ['-created_at']
    readonly_fields = ['created_at']
    list_per_page = 100
    
    def message_preview(self, obj):
        return obj.message[:100] + '...' if len(obj.message) > 100 else obj.message
    message_preview.short_description = 'Message'


@admin.register(CompanyCache)
class CompanyCacheAdmin(admin.ModelAdmin):
    list_display = ['company_name', 'company_size', 'company_domain', 'last_updated', 'is_valid']
    search_fields = ['company_name', 'company_domain']
    ordering = ['company_name']
    readonly_fields = ['created_at', 'last_updated']
    list_per_page = 50
    
    def is_valid(self, obj):
        return obj.is_cache_valid()
    is_valid.boolean = True
    is_valid.short_description = 'Cache Valid'
