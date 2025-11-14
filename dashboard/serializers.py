"""
Serializers for Dashboard App
"""
from rest_framework import serializers
from .models import Keyword, JobPortal, SavedFilter, ScraperRun


class KeywordSerializer(serializers.ModelSerializer):
    class Meta:
        model = Keyword
        fields = ['id', 'name', 'category', 'is_active', 'created_at', 'updated_at']
        read_only_fields = ['created_at', 'updated_at']


class JobPortalSerializer(serializers.ModelSerializer):
    class Meta:
        model = JobPortal
        fields = ['id', 'name', 'base_url', 'is_active', 'requires_selenium', 'rate_limit', 'priority']
        read_only_fields = ['created_at', 'updated_at']


class SavedFilterSerializer(serializers.ModelSerializer):
    keywords = KeywordSerializer(many=True, read_only=True)
    job_portals = JobPortalSerializer(many=True, read_only=True)
    keyword_ids = serializers.ListField(
        child=serializers.IntegerField(),
        write_only=True,
        required=False
    )
    job_portal_ids = serializers.ListField(
        child=serializers.IntegerField(),
        write_only=True,
        required=False
    )
    
    class Meta:
        model = SavedFilter
        fields = [
            'id', 'name', 'description', 'job_type', 'time_filter', 'location',
            'keywords', 'job_portals', 'keyword_ids', 'job_portal_ids',
            'is_active', 'last_used', 'use_count', 'created_at', 'updated_at'
        ]
        read_only_fields = ['last_used', 'use_count', 'created_at', 'updated_at']
    
    def create(self, validated_data):
        keyword_ids = validated_data.pop('keyword_ids', [])
        job_portal_ids = validated_data.pop('job_portal_ids', [])
        
        saved_filter = SavedFilter.objects.create(**validated_data)
        
        if keyword_ids:
            saved_filter.keywords.set(keyword_ids)
        if job_portal_ids:
            saved_filter.job_portals.set(job_portal_ids)
        
        return saved_filter
    
    def update(self, instance, validated_data):
        keyword_ids = validated_data.pop('keyword_ids', None)
        job_portal_ids = validated_data.pop('job_portal_ids', None)
        
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        
        if keyword_ids is not None:
            instance.keywords.set(keyword_ids)
        if job_portal_ids is not None:
            instance.job_portals.set(job_portal_ids)
        
        return instance


class ScraperRunSerializer(serializers.ModelSerializer):
    saved_filter_name = serializers.CharField(source='saved_filter.name', read_only=True)
    
    class Meta:
        model = ScraperRun
        fields = [
            'id', 'saved_filter', 'saved_filter_name', 'status',
            'total_jobs_scraped', 'successful_scrapes', 'failed_scrapes',
            'started_at', 'completed_at', 'duration_seconds', 'error_log',
            'celery_task_id', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'status', 'total_jobs_scraped', 'successful_scrapes', 'failed_scrapes',
            'started_at', 'completed_at', 'duration_seconds', 'celery_task_id',
            'created_at', 'updated_at'
        ]

