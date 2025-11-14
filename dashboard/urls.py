"""
URL configuration for Dashboard App
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views


# API Router
router = DefaultRouter()
router.register(r'keywords', views.KeywordViewSet)
router.register(r'portals', views.JobPortalViewSet)
router.register(r'filters', views.SavedFilterViewSet)
router.register(r'scraper-runs', views.ScraperRunViewSet)
router.register(r'jobs', views.JobViewSet)

urlpatterns = [
    # API endpoints
    path('api/', include(router.urls)),
    path('api/run_scraper/', views.run_scraper_api, name='run_scraper_api'),
    
    # Traditional views
    path('', views.dashboard_home, name='dashboard_home'),
    path('keywords/', views.keywords_page, name='keywords_page'),
    path('keywords/delete/<int:keyword_id>/', views.delete_keyword, name='delete_keyword'),
    path('filters/', views.filters_page, name='filters_page'),
    path('filters/create/', views.create_filter, name='create_filter'),
    path('filters/<int:filter_id>/run/', views.run_scraper, name='run_scraper'),
    path('filters/<int:filter_id>/edit/', views.edit_filter, name='edit_filter'),
    path('filters/<int:filter_id>/delete/', views.delete_filter, name='delete_filter'),
    path('scraper-runs/<int:run_id>/delete/', views.delete_scraper_run, name='delete_scraper_run'),
    path('jobs/', views.jobs_page, name='jobs_page'),
    path('jobs/<int:job_id>/delete/', views.delete_job, name='delete_job'),
    path('jobs/delete-all/', views.delete_all_jobs, name='delete_all_jobs'),
    path('jobs/export/', views.export_jobs, name='export_jobs'),
]
