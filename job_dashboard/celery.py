"""
Celery configuration for job_dashboard project.
"""
import os
from celery import Celery
from celery.schedules import crontab

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'job_dashboard.settings')

app = Celery('job_dashboard')

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Load task modules from all registered Django apps.
app.autodiscover_tasks()

# Celery Beat Schedule (for periodic tasks)
# Schedule runs twice daily: UK time (9:00 AM) and USA time (9:00 AM EST/EDT)
# Using UTC timezone - adjust hours based on your server timezone
# UK time (9:00 AM GMT/BST) = 9:00 AM UTC (GMT) or 8:00 AM UTC (BST)
# USA time (9:00 AM EST/EDT) = 14:00 UTC (EST) or 13:00 UTC (EDT)
app.conf.beat_schedule = {
    'auto-run-scraper-uk-time': {
        'task': 'scraper.tasks.auto_run_scraper_uk_time',
        'schedule': crontab(hour=9, minute=0),  # 9:00 AM UK time (GMT/BST)
        'options': {'timezone': 'Europe/London'},
    },
    'auto-run-scraper-usa-time': {
        'task': 'scraper.tasks.auto_run_scraper_usa_time',
        'schedule': crontab(hour=14, minute=0),  # 9:00 AM EST (2:00 PM UTC)
        'options': {'timezone': 'America/New_York'},
    },
}

@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f'Request: {self.request!r}')

