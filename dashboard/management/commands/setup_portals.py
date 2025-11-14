"""
Management command to setup initial job portals
"""
from django.core.management.base import BaseCommand
from dashboard.models import JobPortal, Keyword


class Command(BaseCommand):
    help = 'Setup initial job portals and keywords in the database'
    
    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Setting up job portals...'))
        
        portals = [
            # Removed Indeed UK and Glassdoor due to blocking issues
            # {'name': 'Indeed UK', 'base_url': 'https://uk.indeed.com', 'requires_selenium': False, 'priority': 10},
            {'name': 'Linkedin Jobs', 'base_url': 'https://www.linkedin.com', 'requires_selenium': True, 'priority': 10},
            {'name': 'CV-Library', 'base_url': 'https://www.cv-library.co.uk', 'requires_selenium': False, 'priority': 8},
            {'name': 'Adzuna', 'base_url': 'https://www.adzuna.co.uk', 'requires_selenium': False, 'priority': 7},
            {'name': 'Totaljobs', 'base_url': 'https://www.totaljobs.com', 'requires_selenium': False, 'priority': 8},
            {'name': 'Reed', 'base_url': 'https://www.reed.co.uk', 'requires_selenium': False, 'priority': 9},
            {'name': 'Talent', 'base_url': 'https://www.talent.com', 'requires_selenium': False, 'priority': 6},
            # {'name': 'Glassdoor', 'base_url': 'https://www.glassdoor.com', 'requires_selenium': True, 'priority': 9},
            {'name': 'ZipRecruiter', 'base_url': 'https://www.ziprecruiter.com', 'requires_selenium': False, 'priority': 8},
            {'name': 'CWjobs', 'base_url': 'https://www.cwjobs.co.uk', 'requires_selenium': False, 'priority': 7},
            {'name': 'Jobsora', 'base_url': 'https://www.jobsora.com', 'requires_selenium': False, 'priority': 5},
            {'name': 'WelcometotheJungle', 'base_url': 'https://www.welcometothejungle.com', 'requires_selenium': True, 'priority': 6},
            {'name': 'IT Job Board', 'base_url': 'https://www.itjobboard.com', 'requires_selenium': False, 'priority': 7},
            {'name': 'Trueup', 'base_url': 'https://www.trueup.io', 'requires_selenium': False, 'priority': 6},
            {'name': 'Redefined', 'base_url': 'https://redefined.uk', 'requires_selenium': False, 'priority': 5},
            {'name': 'We Work Remotely', 'base_url': 'https://weworkremotely.com', 'requires_selenium': False, 'priority': 8},
            {'name': 'AngelList (Wellfound)', 'base_url': 'https://wellfound.com', 'requires_selenium': True, 'priority': 8},
            {'name': 'Jobspresso', 'base_url': 'https://jobspresso.co', 'requires_selenium': False, 'priority': 6},
            {'name': 'Grabjobs', 'base_url': 'https://www.grabjobs.co', 'requires_selenium': False, 'priority': 5},
            {'name': 'Remote OK', 'base_url': 'https://remoteok.com', 'requires_selenium': False, 'priority': 8},
            {'name': 'Working Nomads', 'base_url': 'https://www.workingnomads.com', 'requires_selenium': False, 'priority': 6},
            {'name': 'WorkInStartups', 'base_url': 'https://workinstartups.com', 'requires_selenium': False, 'priority': 7},
            {'name': 'Jobtensor', 'base_url': 'https://jobtensor.com', 'requires_selenium': False, 'priority': 5},
            {'name': 'Jora', 'base_url': 'https://uk.jora.com', 'requires_selenium': False, 'priority': 6},
            {'name': 'SEOJobs.com', 'base_url': 'https://www.seojobs.com', 'requires_selenium': False, 'priority': 7},
            {'name': 'CareerBuilder', 'base_url': 'https://www.careerbuilder.com', 'requires_selenium': True, 'priority': 8},
            {'name': 'Dice', 'base_url': 'https://www.dice.com', 'requires_selenium': True, 'priority': 9},
            {'name': 'Escape The City', 'base_url': 'https://www.escapethecity.org', 'requires_selenium': False, 'priority': 5},
            {'name': 'Jooble', 'base_url': 'https://uk.jooble.org', 'requires_selenium': False, 'priority': 6},
            {'name': 'Otta', 'base_url': 'https://otta.com', 'requires_selenium': True, 'priority': 7},
            {'name': 'Remote.co', 'base_url': 'https://remote.co', 'requires_selenium': False, 'priority': 7},
            {'name': 'SEL Jobs', 'base_url': 'https://www.seljobs.com', 'requires_selenium': False, 'priority': 5},
            {'name': 'FlexJobs', 'base_url': 'https://www.flexjobs.com', 'requires_selenium': True, 'priority': 7},
            {'name': 'Dynamite Jobs', 'base_url': 'https://dynamitejobs.com', 'requires_selenium': False, 'priority': 6},
            {'name': 'SimplyHired', 'base_url': 'https://www.simplyhired.com', 'requires_selenium': False, 'priority': 7},
            {'name': 'Remotive', 'base_url': 'https://remotive.com', 'requires_selenium': False, 'priority': 7},
        ]
        
        created_count = 0
        for portal_data in portals:
            portal, created = JobPortal.objects.get_or_create(
                name=portal_data['name'],
                defaults=portal_data
            )
            if created:
                created_count += 1
                self.stdout.write(f"✓ Created: {portal.name}")
            else:
                self.stdout.write(f"  Exists: {portal.name}")
        
        self.stdout.write(self.style.SUCCESS(f'\n{created_count} job portals created!'))
        
        # Setup Keywords
        self.stdout.write(self.style.SUCCESS('\nSetting up keywords...'))
        
        # Technical Keywords - Updated as per requirements
        technical_keywords = [
            # React Native Keywords
            'React Native',
            'React Native Developer',
            'Senior React Native Developer',
            'Lead React Native Developer',
            'Mobile Application Developer (React Native)',
            'Mobile Engineer (iOS+Android – React Native)',
            'Frontend Developer (React Native)',
            'Cross-Platform Mobile Developer',
            'Mobile Software Engineer',
            'React Developer (with mobile experience)',
            'Senior Mobile Engineer – React Native',
            
            # Full Stack Keywords
            'Full Stack Developer',
            'Senior Full Stack Developer',
            'Lead Full Stack Engineer',
            'Software Engineer (Python+ JavaScript)',
            'Backend Engineer (Python+ Django+ FastAPI)',
            'Principal Software Engineer',
            'Engineering Lead',
            'Python Developer',
            'Senior Python Engineer',
            'Django Developer',
            'Django Engineer',
            'FastAPI Engineer',
            'Cloud Engineer (AWS+GCP)',
            'DevOps Engineer (Python + Cloud)',
            
            # AI/ML Keywords
            'AI Engineer',
            'AI Research Engineer',
            'Machine Learning Engineer',
            'LLM Engineer',
            'Generative AI Engineer',
            'Applied Scientist (AI+ML)',
            'AI Software Engineer',
        ]
        
        # Non-Technical Keywords - Updated as per requirements
        non_technical_keywords = [
            # SEO Keywords
            'SEO',
            'SEO Specialist',
            'SEO Manager',
            'SEO Analyst',
            'Search Engine Optimisation Expert',
            
            # Digital Marketing Keywords
            'Digital Marketing',
            'Digital Marketing Specialist',
            'Digital Marketing Manager',
            'Digital Marketer',
            'Marketing Specialist',
            'Marketing Manager',
            'Growth Marketing Manager',
            'Content Marketing Specialist',
            
            # Paid Advertising Keywords
            'Paid Advertising Manager',
            'Media Buyer',
            'Digital Media Manager',
            'Paid Media Specialist',
            'Google Ads Expert',
            'PPC Specialist',
            'Paid Search Manager',
        ]
        
        keyword_count = 0
        for keyword in technical_keywords:
            kw, created = Keyword.objects.get_or_create(
                name=keyword,
                defaults={'category': 'TECHNICAL'}
            )
            if created:
                keyword_count += 1
        
        for keyword in non_technical_keywords:
            kw, created = Keyword.objects.get_or_create(
                name=keyword,
                defaults={'category': 'NON_TECHNICAL'}
            )
            if created:
                keyword_count += 1
        
        self.stdout.write(self.style.SUCCESS(f'{keyword_count} keywords created!'))
        
        self.stdout.write(self.style.SUCCESS('\n✅ Setup completed successfully!'))
        self.stdout.write(self.style.WARNING('\nNext steps:'))
        self.stdout.write('1. Create a superuser: python manage.py createsuperuser')
        self.stdout.write('2. Run the server: python manage.py runserver')
        self.stdout.write('3. Access the dashboard at http://localhost:8000/')

