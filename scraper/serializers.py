"""
Serializers for Scraper App
"""
from rest_framework import serializers
from .models import Job, DecisionMaker, ScraperLog, CompanyCache


class DecisionMakerSerializer(serializers.ModelSerializer):
    class Meta:
        model = DecisionMaker
        fields = [
            'id', 'name', 'title', 'linkedin_url', 'email', 'phone',
            'department', 'data_source', 'confidence_score'
        ]


class JobSerializer(serializers.ModelSerializer):
    decision_makers = DecisionMakerSerializer(many=True, read_only=True)
    source_job_portal_name = serializers.CharField(source='source_job_portal.name', read_only=True)
    
    class Meta:
        model = Job
        fields = [
            'id', 'job_title', 'company', 'company_url', 'company_size', 'job_field', 'market',
            'source_job_portal', 'source_job_portal_name', 'job_link', 'posted_date',
            'location', 'job_description', 'job_type', 'salary_range',
            'decision_makers',
            'scraped_at', 'updated_at'
        ]
        read_only_fields = ['scraped_at', 'updated_at']


class JobListSerializer(serializers.ModelSerializer):
    """Lighter serializer for list views"""
    source_job_portal_name = serializers.CharField(source='source_job_portal.name', read_only=True)
    decision_makers_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Job
        fields = [
            'id', 'job_title', 'company', 'market', 'location',
            'source_job_portal_name', 'posted_date', 'job_type', 'job_field',
            'decision_makers_count', 'scraped_at'
        ]
    
    def get_decision_makers_count(self, obj):
        return obj.decision_makers.count()


class ScraperLogSerializer(serializers.ModelSerializer):
    job_portal_name = serializers.CharField(source='job_portal.name', read_only=True)
    
    class Meta:
        model = ScraperLog
        fields = [
            'id', 'scraper_run', 'job_portal', 'job_portal_name', 'level',
            'message', 'exception_traceback', 'url_scraped', 'response_code',
            'created_at'
        ]
        read_only_fields = ['created_at']


class CompanyCacheSerializer(serializers.ModelSerializer):
    is_valid = serializers.SerializerMethodField()
    
    class Meta:
        model = CompanyCache
        fields = [
            'id', 'company_name', 'company_url', 'company_size', 'company_domain',
            'linkedin_company_id', 'linkedin_company_url', 'last_updated',
            'cache_valid_until', 'is_valid', 'created_at'
        ]
    
    def get_is_valid(self, obj):
        return obj.is_cache_valid()

