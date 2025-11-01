"""
Admin configuration for Google Sheets App
"""
from django.contrib import admin
from .models import GoogleSheetConfig, ExportHistory


@admin.register(GoogleSheetConfig)
class GoogleSheetConfigAdmin(admin.ModelAdmin):
    list_display = ['name', 'worksheet_name', 'is_active', 'auto_export', 'total_rows_exported', 'last_export_at']
    list_filter = ['is_active', 'auto_export']
    search_fields = ['name', 'spreadsheet_id', 'worksheet_name']
    ordering = ['-is_active', 'name']
    readonly_fields = ['total_rows_exported', 'last_export_at', 'created_at', 'updated_at']
    list_per_page = 50
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'spreadsheet_id', 'worksheet_name')
        }),
        ('Settings', {
            'fields': ('is_active', 'auto_export', 'include_headers', 'column_mapping')
        }),
        ('Statistics', {
            'fields': ('total_rows_exported', 'last_export_at', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(ExportHistory)
class ExportHistoryAdmin(admin.ModelAdmin):
    list_display = ['id', 'sheet_config', 'status', 'jobs_exported', 'rows_added', 'rows_updated', 'started_at', 'duration_seconds']
    list_filter = ['status', 'started_at']
    search_fields = ['sheet_config__name']
    ordering = ['-created_at']
    readonly_fields = ['started_at', 'completed_at', 'duration_seconds', 'created_at']
    list_per_page = 50
    
    fieldsets = (
        ('Export Information', {
            'fields': ('sheet_config', 'status')
        }),
        ('Statistics', {
            'fields': ('jobs_exported', 'rows_added', 'rows_updated')
        }),
        ('Timing', {
            'fields': ('started_at', 'completed_at', 'duration_seconds')
        }),
        ('Error Information', {
            'fields': ('error_message',),
            'classes': ('collapse',)
        }),
    )
