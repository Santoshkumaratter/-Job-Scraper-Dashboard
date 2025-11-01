"""
Management command to add decision makers to existing jobs
"""
from django.core.management.base import BaseCommand
from scraper.models import Job, DecisionMaker
from scraper.utils.decision_maker_finder import DecisionMakerFinder
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Add decision makers to existing jobs that don\'t have them'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--limit',
            type=int,
            default=50,
            help='Number of jobs to process (default: 50)'
        )
    
    def handle(self, *args, **options):
        limit = options['limit']
        
        # Get jobs without decision makers
        from django.db.models import Count
        jobs_without_dm = Job.objects.annotate(
            dm_count=Count('decision_makers')
        ).filter(dm_count=0)[:limit]
        
        self.stdout.write(f"Found {jobs_without_dm.count()} jobs without decision makers")
        self.stdout.write(f"Processing first {limit}...")
        
        dm_finder = DecisionMakerFinder()
        added_count = 0
        
        for job in jobs_without_dm:
            try:
                decision_makers = dm_finder.find_decision_makers(
                    company_name=job.company,
                    company_url=job.company_url,
                    max_results=1
                )
                
                for dm_data in decision_makers:
                    DecisionMaker.objects.create(
                        job=job,
                        company=job.company,
                        name=dm_data.get('name', ''),
                        title=dm_data.get('title', ''),
                        linkedin_url=dm_data.get('linkedin_url'),
                        email=dm_data.get('email'),
                        phone=dm_data.get('phone'),
                        department=dm_data.get('department'),
                        data_source=dm_data.get('data_source', 'Auto-Generated'),
                        confidence_score=dm_data.get('confidence_score', 0.7)
                    )
                    added_count += 1
                
                self.stdout.write(f"✓ Added decision makers for {job.company}")
                
            except Exception as e:
                logger.error(f"Error adding decision makers for {job.company}: {str(e)}")
                continue
        
        self.stdout.write(self.style.SUCCESS(f"\n✅ Added decision makers to {added_count} jobs"))

