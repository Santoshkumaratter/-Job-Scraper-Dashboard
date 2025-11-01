"""
Management command to fix company sizes for existing jobs
"""
from django.core.management.base import BaseCommand
from scraper.models import Job
from scraper.utils.company_enrichment import CompanyEnrichment


class Command(BaseCommand):
    help = 'Update company sizes for all existing jobs with realistic data'
    
    def handle(self, *args, **options):
        enrichment = CompanyEnrichment()
        
        jobs = Job.objects.all()
        total = jobs.count()
        
        self.stdout.write(f"Updating company sizes for {total} jobs...")
        
        updated = 0
        sizes_count = {'SMALL': 0, 'MEDIUM': 0, 'LARGE': 0, 'ENTERPRISE': 0}
        
        for job in jobs:
            # Get realistic company size
            new_size = enrichment.get_company_size(job.company, job.company_url)
            
            if new_size != job.company_size:
                job.company_size = new_size
                job.save(update_fields=['company_size'])
                updated += 1
            
            sizes_count[new_size] = sizes_count.get(new_size, 0) + 1
        
        self.stdout.write(self.style.SUCCESS(f'\n✅ Updated {updated} jobs!'))
        self.stdout.write('\n📊 Company Size Distribution:')
        self.stdout.write(f'   - Small (1-50): {sizes_count["SMALL"]} jobs')
        self.stdout.write(f'   - Medium (51-250): {sizes_count["MEDIUM"]} jobs')
        self.stdout.write(f'   - Large (251-1000): {sizes_count["LARGE"]} jobs')
        self.stdout.write(f'   - Enterprise (1000+): {sizes_count["ENTERPRISE"]} jobs')
        self.stdout.write('\n🎯 Data is now realistic and varied!')

