"""
Views for Dashboard App
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import JsonResponse
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import Keyword, JobPortal, SavedFilter, ScraperRun
from scraper.models import Job
from .serializers import (
    KeywordSerializer, JobPortalSerializer,
    SavedFilterSerializer, ScraperRunSerializer
)
from scraper.serializers import JobSerializer, JobListSerializer
from scraper.tasks import scrape_jobs_task


# ============== REST API ViewSets ==============

class KeywordViewSet(viewsets.ModelViewSet):
    """API ViewSet for Keywords"""
    queryset = Keyword.objects.all()
    serializer_class = KeywordSerializer
    
    def get_queryset(self):
        queryset = super().get_queryset()
        category = self.request.query_params.get('category', None)
        if category:
            queryset = queryset.filter(category=category)
        return queryset


class JobPortalViewSet(viewsets.ModelViewSet):
    """API ViewSet for Job Portals"""
    queryset = JobPortal.objects.all()
    serializer_class = JobPortalSerializer
    
    def get_queryset(self):
        queryset = super().get_queryset()
        is_active = self.request.query_params.get('is_active', None)
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == 'true')
        return queryset


class SavedFilterViewSet(viewsets.ModelViewSet):
    """API ViewSet for Saved Filters"""
    queryset = SavedFilter.objects.all()
    serializer_class = SavedFilterSerializer
    
    @action(detail=True, methods=['post'])
    def run_scraper(self, request, pk=None):
        """Trigger scraper for this filter"""
        saved_filter = self.get_object()
        
        # Start scraping task
        task = scrape_jobs_task.delay(saved_filter.id)
        
        return Response({
            'message': f'Scraper started for filter "{saved_filter.name}"',
            'task_id': task.id,
            'filter_id': saved_filter.id
        })
    
    @action(detail=True, methods=['get'])
    def scraper_runs(self, request, pk=None):
        """Get scraper runs for this filter"""
        saved_filter = self.get_object()
        runs = saved_filter.scraper_runs.all()[:10]
        serializer = ScraperRunSerializer(runs, many=True)
        return Response(serializer.data)


class ScraperRunViewSet(viewsets.ReadOnlyModelViewSet):
    """API ViewSet for Scraper Runs (read-only)"""
    queryset = ScraperRun.objects.all()
    serializer_class = ScraperRunSerializer
    
    @action(detail=True, methods=['get'])
    def jobs(self, request, pk=None):
        """Get jobs from this scraper run"""
        scraper_run = self.get_object()
        jobs = scraper_run.jobs.all()
        serializer = JobListSerializer(jobs, many=True)
        return Response(serializer.data)


class JobViewSet(viewsets.ReadOnlyModelViewSet):
    """API ViewSet for Jobs (read-only)"""
    queryset = Job.objects.all()
    
    def get_serializer_class(self):
        if self.action == 'list':
            return JobListSerializer
        return JobSerializer
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filter by company
        company = self.request.query_params.get('company', None)
        if company:
            queryset = queryset.filter(company__icontains=company)
        
        # Filter by market
        market = self.request.query_params.get('market', None)
        if market:
            queryset = queryset.filter(market=market)
        
        # Filter by portal
        portal = self.request.query_params.get('portal', None)
        if portal:
            queryset = queryset.filter(source_job_portal_id=portal)
        
        # Filter by exported status
        is_exported = self.request.query_params.get('is_exported', None)
        if is_exported is not None:
            queryset = queryset.filter(is_exported_to_sheets=is_exported.lower() == 'true')
        
        return queryset
    
    @action(detail=False, methods=['get'])
    def stream(self, request):
        """Return jobs scraped after a given timestamp for live updates.
        Shape matches the frontend JS expectations.
        """
        from django.utils.dateparse import parse_datetime
        after_str = request.query_params.get('after')
        limit = int(request.query_params.get('limit', 100))
        qs = self.get_queryset().order_by('scraped_at')
        if after_str:
            after_dt = parse_datetime(after_str)
            if after_dt is not None:
                qs = qs.filter(scraped_at__gt=after_dt)
        qs = qs.select_related('source_job_portal')[:limit]
        
        data = []
        for job in qs:
            data.append({
                'id': job.id,
                'job_title': job.job_title,
                'company': job.company,
                'company_url': job.company_url,
                'company_size_display': job.get_company_size_display(),
                'job_link': job.job_link,
                'posted_date': job.posted_date.strftime('%m/%d/%Y') if job.posted_date else '-',
                'job_type': job.job_type or 'OTHER',
                'location': job.location or '-',
                'market': job.market,
                'source_portal': job.source_job_portal.name if job.source_job_portal else '-',
                'scraped_at': job.scraped_at.isoformat() if job.scraped_at else None,
            })
        return Response(data)

    @action(detail=False, methods=['post'])
    def export_to_sheets(self, request):
        """Export selected jobs to Google Sheets"""
        job_ids = request.data.get('job_ids', [])
        
        # Get active sheet config
        sheet_config = GoogleSheetConfig.objects.filter(is_active=True).first()
        
        if not sheet_config:
            return Response(
                {'error': 'No active Google Sheet configuration found'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if job_ids:
            # Export specific jobs
            task = export_to_sheets_task.delay(sheet_config.id, job_ids)
            message = f'Exporting {len(job_ids)} jobs to Google Sheets'
        else:
            # Export all new jobs
            task = export_to_sheets_task.delay(sheet_config.id)
            message = 'Exporting all new jobs to Google Sheets'
        
        return Response({
            'message': message,
            'task_id': task.id
        })


# ============== Traditional Django Views ==============

def dashboard_home(request):
    """Main dashboard view"""
    context = {
        'total_keywords': Keyword.objects.filter(is_active=True).count(),
        'total_portals': JobPortal.objects.filter(is_active=True).count(),
        'total_filters': SavedFilter.objects.filter(is_active=True).count(),
        'total_jobs': Job.objects.count(),
        'recent_runs': ScraperRun.objects.all()[:5],
        'recent_jobs': Job.objects.all()[:10],
    }
    return render(request, 'dashboard/home.html', context)


def keywords_page(request):
    """Keywords management page"""
    if request.method == 'POST':
        # Add new keyword
        name = request.POST.get('name')
        category = request.POST.get('category', 'BOTH')
        
        if name:
            keyword, created = Keyword.objects.get_or_create(
                name=name,
                defaults={'category': category}
            )
            if created:
                messages.success(request, f'Keyword "{name}" added successfully!')
            else:
                messages.info(request, f'Keyword "{name}" already exists.')
        
        return redirect('keywords_page')
    
    keywords = Keyword.objects.all()
    context = {
        'keywords': keywords,
        'technical_keywords': keywords.filter(category='TECHNICAL'),
        'non_technical_keywords': keywords.filter(category='NON_TECHNICAL'),
    }
    return render(request, 'dashboard/keywords.html', context)


def filters_page(request):
    """Saved filters page"""
    filters = SavedFilter.objects.all()
    keywords = Keyword.objects.filter(is_active=True)
    portals = JobPortal.objects.filter(is_active=True)
    
    context = {
        'filters': filters,
        'keywords': keywords,
        'portals': portals,
    }
    return render(request, 'dashboard/filters.html', context)


def create_filter(request):
    """Create new filter"""
    if request.method == 'POST':
        name = request.POST.get('name')
        description = request.POST.get('description', '')
        job_type = request.POST.get('job_type', 'ALL')
        time_filter = request.POST.get('time_filter', 'ALL')
        location = request.POST.get('location', 'ALL')
        keyword_ids = request.POST.getlist('keywords')
        portal_ids = request.POST.getlist('portals')
        
        if name:
            saved_filter = SavedFilter.objects.create(
                name=name,
                description=description,
                job_type=job_type,
                time_filter=time_filter,
                location=location
            )
            
            if keyword_ids:
                saved_filter.keywords.set(keyword_ids)
            if portal_ids:
                saved_filter.job_portals.set(portal_ids)
            
            messages.success(request, f'Filter "{name}" created successfully!')
            return redirect('filters_page')
    
    return redirect('filters_page')


def run_scraper(request, filter_id):
    """Run scraper for a specific filter - Synchronous version"""
    saved_filter = get_object_or_404(SavedFilter, id=filter_id)
    
    # Import scraper manager
    from scraper.scraper_manager import ScraperManager
    from dashboard.models import ScraperRun
    from django.utils import timezone
    
    # Create scraper run
    scraper_run = ScraperRun.objects.create(
        saved_filter=saved_filter,
        status='RUNNING',
        started_at=timezone.now()
    )
    
    try:
        # Run scraper synchronously
        manager = ScraperManager(saved_filter, scraper_run)
        result = manager.run()
        
        if result['status'] == 'success':
            total_portals = result.get('total_portals', 0)
            successful = result.get('portals_scraped', 0)
            failed = result.get('portals_failed', 0)
            
            if failed > 0:
                messages.success(
                    request,
                    f'✅ Scraping completed! Found {result["saved_jobs"]} jobs from {successful}/{total_portals} portals ({failed} failed).'
                )
            else:
                messages.success(
                    request,
                    f'✅ Scraping completed! Found {result["saved_jobs"]} jobs from {successful} portals.'
                )
        else:
            messages.error(request, f'❌ Scraping failed: {result.get("error", "Unknown error")}')
    
    except Exception as e:
        messages.error(request, f'❌ Error: {str(e)}')
        scraper_run.status = 'FAILED'
        scraper_run.error_log = str(e)
        scraper_run.completed_at = timezone.now()
        scraper_run.save()
    
    # Redirect to jobs page
    return redirect('jobs_page')


def jobs_page(request):
    """Jobs listing page with pagination"""
    from django.core.paginator import Paginator
    
    jobs = Job.objects.all().order_by('-scraped_at')
    
    # Apply filters
    company = request.GET.get('company')
    if company:
        jobs = jobs.filter(company__icontains=company)
    
    market = request.GET.get('market')
    if market:
        jobs = jobs.filter(market=market)
    
    # Get total before pagination
    total_jobs = jobs.count()
    
    # Pagination - 50 jobs per page
    jobs = jobs.select_related('source_job_portal')
    paginator = Paginator(jobs, 50)  # 50 jobs per page
    
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    
    # Process jobs to add split names and serial numbers
    jobs_data = []
    start_index = (page_obj.number - 1) * paginator.per_page
    
    for idx, job in enumerate(page_obj, start=start_index + 1):
        job_dict = {
            'sr_no': idx,  # Serial number
            'job': job,
        }
        jobs_data.append(job_dict)
    
    context = {
        'jobs_data': jobs_data,
        'total_jobs': total_jobs,
        'page_obj': page_obj,
        'paginator': paginator,
    }
    return render(request, 'dashboard/jobs.html', context)


def edit_filter(request, filter_id):
    """Edit existing filter"""
    saved_filter = get_object_or_404(SavedFilter, id=filter_id)
    
    if request.method == 'POST':
        saved_filter.name = request.POST.get('name', saved_filter.name)
        saved_filter.description = request.POST.get('description', saved_filter.description)
        saved_filter.job_type = request.POST.get('job_type', saved_filter.job_type)
        saved_filter.time_filter = request.POST.get('time_filter', saved_filter.time_filter)
        saved_filter.location = request.POST.get('location', saved_filter.location)
        
        keyword_ids = request.POST.getlist('keywords')
        portal_ids = request.POST.getlist('portals')
        
        if keyword_ids:
            saved_filter.keywords.set(keyword_ids)
        if portal_ids:
            saved_filter.job_portals.set(portal_ids)
        
        saved_filter.save()
        
        messages.success(request, f'Filter "{saved_filter.name}" updated successfully!')
        return redirect('filters_page')
    
    return redirect('filters_page')


def delete_filter(request, filter_id):
    """Delete a filter"""
    saved_filter = get_object_or_404(SavedFilter, id=filter_id)
    filter_name = saved_filter.name
    saved_filter.delete()
    
    messages.success(request, f'Filter "{filter_name}" deleted successfully!')
    return redirect('filters_page')


def delete_keyword(request, keyword_id):
    """Delete a keyword"""
    keyword = get_object_or_404(Keyword, id=keyword_id)
    keyword_name = keyword.name
    keyword.delete()
    
    messages.success(request, f'Keyword "{keyword_name}" deleted successfully!')
    return redirect('keywords_page')


def export_jobs(request):
    """Export jobs as CSV file (download)"""
    from scraper.models import Job
    import csv
    from django.http import HttpResponse
    from datetime import datetime
    
    # Get all jobs
    jobs = Job.objects.all().select_related('source_job_portal').order_by('-scraped_at')
    
    if jobs.count() == 0:
        messages.warning(request, '⚠️ No jobs to export!')
        return redirect('jobs_page')
    
    # Create CSV file
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="jobs_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv"'
    
    writer = csv.writer(response)
    
    # Write header row
    writer.writerow([
        'Sr. No.',
        'Job Title',
        'Company',
        'Company URL',
        'Company Size',
        'Market (USA/UK)',
        'Location',
        'Job Type',
        'Posted Date',
        'Job Link',
        'Job Portal',
        'Scraped At'
    ])
    
    # Write job data
    for idx, job in enumerate(jobs, start=1):
        writer.writerow([
            idx,
            job.job_title,
            job.company,
            job.company_url or '-',
            job.get_company_size_display(),
            job.market,
            job.location or '-',
            job.job_type or '-',
            job.posted_date.strftime('%m/%d/%Y') if job.posted_date else '-',
            job.job_link,
            job.source_job_portal.name if job.source_job_portal else '-',
            job.scraped_at.strftime('%Y-%m-%d %H:%M:%S') if job.scraped_at else '-'
        ])
    
    return response


def delete_scraper_run(request, run_id):
    """Delete a scraper run and all associated data"""
    from scraper.models import Job
    
    scraper_run = get_object_or_404(ScraperRun, id=run_id)
    run_name = f"#{scraper_run.id}"
    
    # If the run is still running, request cancellation and avoid immediate deletion
    if scraper_run.status == 'RUNNING':
        scraper_run.status = 'CANCELLED'
        scraper_run.save()
        messages.info(
            request,
            f'🛑 Scraper run {run_name} is cancelling. It will stop shortly and can then be deleted.'
        )
        return redirect('dashboard_home')

    # Delete all jobs associated with this scraper run
    jobs_count = Job.objects.filter(scraper_run=scraper_run).count()
    Job.objects.filter(scraper_run=scraper_run).delete()
    
    # Delete the scraper run itself
    scraper_run.delete()
    
    messages.success(
        request,
        f'✅ Scraper run {run_name} deleted successfully! ({jobs_count} jobs removed)'
    )
    
    return redirect('dashboard_home')


def delete_job(request, job_id):
    """Delete a single job"""
    from scraper.models import Job
    
    job = get_object_or_404(Job, id=job_id)
    job_title = job.job_title
    
    # Delete the job (decision makers will be cascaded)
    job.delete()
    
    messages.success(
        request,
        f'✅ Job "{job_title}" deleted successfully!'
    )
    
    # Return to jobs page with same page number
    page = request.GET.get('page', 1)
    return redirect(f'/jobs/?page={page}')


def delete_all_jobs(request):
    """Delete all jobs"""
    from scraper.models import Job
    
    total_jobs = Job.objects.count()
    
    if total_jobs == 0:
        messages.info(request, 'No jobs to delete.')
        return redirect('jobs_page')
    
    # Delete all jobs
    Job.objects.all().delete()
    
    messages.success(
        request,
        f'✅ Successfully deleted all {total_jobs} jobs!'
    )
    
    return redirect('jobs_page')
