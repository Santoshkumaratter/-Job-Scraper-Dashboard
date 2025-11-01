"""
Admin configuration for Dashboard App
"""
from django.contrib import admin
from .models import Keyword, JobPortal, SavedFilter, ScraperRun


@admin.register(Keyword)
class KeywordAdmin(admin.ModelAdmin):
    list_display = ['name', 'category', 'is_active', 'created_at']
    list_filter = ['category', 'is_active']
    search_fields = ['name']
    ordering = ['name']
    list_per_page = 50


@admin.register(JobPortal)
class JobPortalAdmin(admin.ModelAdmin):
    list_display = ['name', 'is_active', 'requires_selenium', 'rate_limit', 'priority', 'created_at']
    list_filter = ['is_active', 'requires_selenium']
    search_fields = ['name', 'base_url']
    ordering = ['-priority', 'name']
    list_editable = ['is_active', 'priority', 'rate_limit']
    list_per_page = 50


@admin.register(SavedFilter)
class SavedFilterAdmin(admin.ModelAdmin):
    list_display = ['name', 'job_type', 'time_filter', 'location', 'is_active', 'use_count', 'last_used']
    list_filter = ['job_type', 'time_filter', 'location', 'is_active']
    search_fields = ['name', 'description']
    filter_horizontal = ['keywords', 'job_portals']
    ordering = ['-last_used']
    readonly_fields = ['use_count', 'last_used', 'created_at', 'updated_at']
    list_per_page = 50
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'description', 'is_active')
        }),
        ('Filter Settings', {
            'fields': ('job_type', 'time_filter', 'location')
        }),
        ('Keywords & Portals', {
            'fields': ('keywords', 'job_portals')
        }),
        ('Statistics', {
            'fields': ('use_count', 'last_used', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(ScraperRun)
class ScraperRunAdmin(admin.ModelAdmin):
    list_display = ['id', 'saved_filter', 'status', 'total_jobs_scraped', 'started_at', 'completed_at', 'duration_seconds']
    list_filter = ['status', 'started_at']
    search_fields = ['saved_filter__name', 'celery_task_id']
    ordering = ['-created_at']
    readonly_fields = ['started_at', 'completed_at', 'duration_seconds', 'created_at', 'updated_at']
    list_per_page = 50
    
    fieldsets = (
        ('Run Information', {
            'fields': ('saved_filter', 'status', 'celery_task_id')
        }),
        ('Statistics', {
            'fields': ('total_jobs_scraped', 'successful_scrapes', 'failed_scrapes')
        }),
        ('Timing', {
            'fields': ('started_at', 'completed_at', 'duration_seconds')
        }),
        ('Error Log', {
            'fields': ('error_log',),
            'classes': ('collapse',)
        }),
    )
