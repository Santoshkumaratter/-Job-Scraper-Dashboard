"""
Management command to set up default keywords for job field categorization
Usage: python manage.py setup_keywords
"""
from django.core.management.base import BaseCommand
from dashboard.models import Keyword


class Command(BaseCommand):
    help = 'Sets up default keywords for job field categorization'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Setting up default keywords for job categorization...'))
        
        # Define default keywords by category
        technical_keywords = [
            # Programming languages
            'python', 'java', 'javascript', 'typescript', 'c++', 'c#', 'ruby', 'go', 'golang', 'php', 'swift', 
            'kotlin', 'rust', 'scala', 'perl', 'r language', 'objective-c', 'dart', 'assembly', 'haskell',
            
            # Engineering roles
            'software engineer', 'software developer', 'developer', 'programmer', 'coder', 'backend engineer', 
            'frontend engineer', 'full stack engineer', 'backend developer', 'frontend developer', 
            'full stack developer', 'mobile developer', 'ios developer', 'android developer',
            
            # Technical specialties
            'data scientist', 'data engineer', 'machine learning engineer', 'ml engineer', 'ai engineer',
            'devops engineer', 'cloud engineer', 'site reliability engineer', 'sre', 'database administrator',
            'dba', 'systems administrator', 'network engineer', 'security engineer', 'qa engineer',
            'test engineer', 'quality assurance', 'automation engineer',
            
            # Technical skills
            'html', 'css', 'sql', 'nosql', 'aws', 'azure', 'gcp', 'kubernetes', 'docker', 'terraform',
            'jenkins', 'git', 'ci/cd', 'linux', 'unix', 'rest api', 'graphql', 'microservices',
            'data science', 'machine learning', 'deep learning', 'nlp', 'neural networks', 'big data',
            'hadoop', 'spark', 'tableau', 'power bi', 'data visualization', 'data analysis',
            
            # Web technologies
            'react', 'angular', 'vue', 'node.js', 'express', 'django', 'flask', 'spring', 'bootstrap',
            'jquery', 'webpack', 'redux', 'laravel', 'rails', 'asp.net',
            
            # Cloud platforms
            'aws', 'amazon web services', 'azure', 'microsoft azure', 'gcp', 'google cloud', 'firebase',
            
            # Databases
            'mysql', 'postgresql', 'oracle', 'mongodb', 'dynamodb', 'redis', 'elasticsearch', 'cassandra', 
            'sql server', 'sqlite',
            
            # Cybersecurity
            'cybersecurity', 'security engineer', 'penetration tester', 'ethical hacker', 'security analyst',
            
            # AI/ML specific
            'tensorflow', 'pytorch', 'keras', 'opencv', 'scikit-learn', 'machine learning', 'deep learning',
            'computer vision', 'natural language processing', 'reinforcement learning', 'data mining',
            
            # Mobile development
            'ios', 'android', 'swift', 'kotlin', 'react native', 'flutter', 'xamarin', 'mobile development',
        ]
        
        non_technical_keywords = [
            # Business & management
            'product manager', 'project manager', 'program manager', 'business analyst', 'scrum master', 
            'product owner', 'agile coach', 'operations manager', 'account manager', 'client manager',
            
            # Marketing
            'marketing manager', 'digital marketing', 'social media', 'seo', 'content marketing', 
            'marketing specialist', 'brand manager', 'growth hacker', 'marketing strategist', 
            'content strategist', 'copywriter',
            
            # Sales
            'sales representative', 'sales manager', 'account executive', 'business development', 
            'sales director', 'sales associate', 'customer success', 'account manager',
            
            # HR & recruitment
            'recruiter', 'hr manager', 'human resources', 'talent acquisition', 'people operations', 
            'hr business partner', 'compensation', 'benefits', 'employee relations',
            
            # Finance & accounting
            'financial analyst', 'accountant', 'controller', 'bookkeeper', 'finance manager', 
            'cfo', 'cpa', 'auditor', 'tax specialist', 'finance director',
            
            # Design (non-technical)
            'graphic designer', 'ui designer', 'ux designer', 'web designer', 'product designer', 
            'visual designer', 'creative director', 'art director', 'brand designer',
            
            # Customer service
            'customer service', 'customer support', 'help desk', 'technical support', 'account manager', 
            'client services', 'service desk', 'customer success',
            
            # Administration
            'administrative assistant', 'executive assistant', 'office manager', 'receptionist', 
            'office administrator', 'operations coordinator', 'executive secretary',
            
            # Legal
            'lawyer', 'attorney', 'legal counsel', 'compliance', 'contract manager', 'paralegal', 
            'legal assistant', 'general counsel',
            
            # Operations
            'operations coordinator', 'operations analyst', 'operations specialist', 'supply chain', 
            'logistics', 'procurement', 'inventory', 'facilities', 'warehouse',
        ]
        
        # Keywords that could be both technical and non-technical
        both_keywords = [
            'analyst', 'consultant', 'coordinator', 'specialist', 'manager', 'director', 'lead',
            'architect', 'designer', 'researcher', 'advisor', 'strategist', 'supervisor',
            'ui/ux', 'ux/ui', 'ui ux', 'user experience', 'user interface', 'product design',
            'data analyst', 'business intelligence', 'bi', 'analytics', 'reporting',
            'quality assurance', 'qa', 'testing', 'communication', 'project management',
            'agile', 'scrum', 'kanban', 'jira', 'confluence', 'slack', 'trello',
            'technical writer', 'documentation', 'content', 'technology', 'innovation',
        ]
        
        # Create technical keywords
        tech_count = 0
        for keyword in technical_keywords:
            keyword = keyword.lower().strip()
            obj, created = Keyword.objects.update_or_create(
                name=keyword,
                defaults={'category': 'TECHNICAL', 'is_active': True}
            )
            if created:
                tech_count += 1
        
        # Create non-technical keywords
        non_tech_count = 0
        for keyword in non_technical_keywords:
            keyword = keyword.lower().strip()
            obj, created = Keyword.objects.update_or_create(
                name=keyword,
                defaults={'category': 'NON_TECHNICAL', 'is_active': True}
            )
            if created:
                non_tech_count += 1
        
        # Create both category keywords
        both_count = 0
        for keyword in both_keywords:
            keyword = keyword.lower().strip()
            obj, created = Keyword.objects.update_or_create(
                name=keyword,
                defaults={'category': 'BOTH', 'is_active': True}
            )
            if created:
                both_count += 1
        
        total_count = Keyword.objects.count()
        self.stdout.write(self.style.SUCCESS(f'✅ Finished setting up keywords:'))
        self.stdout.write(f'   - {tech_count} technical keywords created/updated')
        self.stdout.write(f'   - {non_tech_count} non-technical keywords created/updated')
        self.stdout.write(f'   - {both_count} multi-category keywords created/updated')
        self.stdout.write(f'   - {total_count} total keywords in database')
