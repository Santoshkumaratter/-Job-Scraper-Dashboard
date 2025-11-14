#!/usr/bin/env python
"""
Final Test Script - Test scraper with filters and verify jobs are being saved
"""
import os
import django
import time
from datetime import datetime

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'job_dashboard.settings')
django.setup()

from dashboard.models import Keyword, JobPortal, SavedFilter, ScraperRun
from scraper.models import Job
from scraper.scraper_manager import ScraperManager

def test_scraper_with_filters():
    """Test scraper with different filters"""
    
    print("\n" + "="*80)
    print("🧪 FINAL SCRAPER TEST - Filters & Jobs Verification")
    print("="*80)
    print(f"Test Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    # Step 1: Get or create test keyword
    print("1️⃣ SETTING UP TEST DATA...")
    keyword = Keyword.objects.filter(name__icontains="AI Engineer").first()
    if not keyword:
        keyword = Keyword.objects.create(name="AI Engineer", category="TECHNICAL")
        print(f"   ✅ Created keyword: {keyword.name}")
    else:
        print(f"   ✅ Using existing keyword: {keyword.name}")
    
    # Step 2: Get active portals (limit to 3 fast ones for quick test)
    fast_portals = JobPortal.objects.filter(
        is_active=True,
        name__in=['Remote OK', 'Remotive', 'We Work Remotely']
    )
    
    if not fast_portals.exists():
        print("   ⚠️  Fast portals not found, using any active portal...")
        fast_portals = JobPortal.objects.filter(is_active=True)[:3]
    
    print(f"   ✅ Selected {fast_portals.count()} portals: {[p.name for p in fast_portals]}")
    
    # Step 3: Test with different filters
    test_cases = [
        {
            'name': 'Test 1: ALL filters (All Time, All Jobs, All Locations)',
            'job_type': 'ALL',
            'time_filter': 'ALL',
            'location': 'ALL'
        },
        {
            'name': 'Test 2: 24H filter (Last 24 Hours, USA)',
            'job_type': 'ALL',
            'time_filter': '24H',
            'location': 'USA'
        },
        {
            'name': 'Test 3: Remote jobs only',
            'job_type': 'REMOTE',
            'time_filter': 'ALL',
            'location': 'ALL'
        }
    ]
    
    results = []
    
    for idx, test_case in enumerate(test_cases, 1):
        print(f"\n{idx}️⃣ {test_case['name']}")
        print("-" * 80)
        
        # Create test filter
        filter_name = f"Test Filter {idx} - {datetime.now().strftime('%H%M%S')}"
        test_filter = SavedFilter.objects.create(
            name=filter_name,
            job_type=test_case['job_type'],
            time_filter=test_case['time_filter'],
            location=test_case['location'],
            is_active=True
        )
        test_filter.keywords.set([keyword])
        test_filter.job_portals.set(fast_portals)
        test_filter.save()
        
        print(f"   Filter: {filter_name}")
        print(f"   - Job Type: {test_case['job_type']}")
        print(f"   - Time Filter: {test_case['time_filter']}")
        print(f"   - Location: {test_case['location']}")
        print(f"   - Keywords: {keyword.name}")
        print(f"   - Portals: {[p.name for p in fast_portals]}")
        
        # Create scraper run
        scraper_run = ScraperRun.objects.create(
            saved_filter=test_filter,
            status='PENDING',
            started_at=datetime.now()
        )
        
        print(f"\n   🚀 Starting scraper run #{scraper_run.id}...")
        start_time = time.time()
        
        try:
            # Run scraper
            manager = ScraperManager(test_filter, scraper_run)
            result = manager.run()
            
            end_time = time.time()
            duration = end_time - start_time
            
            # Get jobs from this run
            jobs = Job.objects.filter(scraper_run=scraper_run)
            job_count = jobs.count()
            
            print(f"\n   📊 RESULTS:")
            print(f"   - Status: {result.get('status', 'N/A')}")
            print(f"   - Total Jobs Found: {result.get('total_jobs', 0)}")
            print(f"   - Jobs Saved to DB: {result.get('saved_jobs', 0)}")
            print(f"   - Jobs in Database: {job_count}")
            print(f"   - Portals Scraped: {result.get('portals_scraped', 0)}")
            print(f"   - Duration: {duration:.2f} seconds")
            
            # Verify filter is working
            if job_count > 0:
                print(f"\n   ✅ SUCCESS: {job_count} jobs saved!")
                
                # Check if jobs match filter
                print(f"\n   🔍 VERIFYING FILTER COMPLIANCE:")
                
                # Check job type
                if test_case['job_type'] != 'ALL':
                    matching_type = jobs.filter(job_type=test_case['job_type']).count()
                    print(f"   - Job Type Filter: {matching_type}/{job_count} jobs match '{test_case['job_type']}'")
                
                # Check location
                if test_case['location'] != 'ALL':
                    matching_location = jobs.filter(market=test_case['location']).count()
                    print(f"   - Location Filter: {matching_location}/{job_count} jobs match '{test_case['location']}'")
                
                # Show sample jobs
                print(f"\n   📋 SAMPLE JOBS (First 3):")
                for i, job in enumerate(jobs[:3], 1):
                    print(f"   {i}. {job.job_title[:60]}...")
                    print(f"      Company: {job.company}")
                    print(f"      Portal: {job.source_job_portal.name if job.source_job_portal else 'Unknown'}")
                    print(f"      Market: {job.market}")
                    print(f"      Posted: {job.posted_date.strftime('%Y-%m-%d') if job.posted_date else 'N/A'}")
                    print()
                
                results.append({
                    'test': test_case['name'],
                    'status': 'SUCCESS',
                    'jobs_found': result.get('total_jobs', 0),
                    'jobs_saved': job_count,
                    'duration': duration
                })
            else:
                print(f"\n   ⚠️  WARNING: No jobs saved!")
                print(f"   Possible reasons:")
                print(f"   - Time filter too restrictive")
                print(f"   - Keywords don't match job titles")
                print(f"   - Portals returned no results")
                
                results.append({
                    'test': test_case['name'],
                    'status': 'NO_JOBS',
                    'jobs_found': result.get('total_jobs', 0),
                    'jobs_saved': 0,
                    'duration': duration
                })
        
        except Exception as e:
            print(f"\n   ❌ ERROR: {str(e)}")
            import traceback
            print(traceback.format_exc())
            results.append({
                'test': test_case['name'],
                'status': 'ERROR',
                'error': str(e)
            })
        
        # Small delay between tests
        if idx < len(test_cases):
            print(f"\n   ⏳ Waiting 2 seconds before next test...")
            time.sleep(2)
    
    # Final Summary
    print("\n" + "="*80)
    print("📊 FINAL TEST SUMMARY")
    print("="*80)
    
    for result in results:
        status_icon = "✅" if result['status'] == 'SUCCESS' else "⚠️" if result['status'] == 'NO_JOBS' else "❌"
        print(f"{status_icon} {result['test']}")
        if result['status'] == 'SUCCESS':
            print(f"   Jobs Found: {result['jobs_found']}, Saved: {result['jobs_saved']}, Duration: {result['duration']:.2f}s")
        elif result['status'] == 'NO_JOBS':
            print(f"   Jobs Found: {result['jobs_found']}, Saved: {result['jobs_saved']}, Duration: {result['duration']:.2f}s")
        else:
            print(f"   Error: {result.get('error', 'Unknown error')}")
        print()
    
    # Overall status
    success_count = sum(1 for r in results if r['status'] == 'SUCCESS')
    total_jobs = sum(r.get('jobs_saved', 0) for r in results)
    
    print(f"✅ Tests Passed: {success_count}/{len(results)}")
    print(f"📊 Total Jobs Saved: {total_jobs}")
    
    if success_count > 0:
        print("\n🎉 SUCCESS: Scraper is working! Jobs are being saved correctly.")
    else:
        print("\n⚠️  WARNING: No jobs were saved. Check filters and portal availability.")
    
    print("="*80 + "\n")

if __name__ == "__main__":
    test_scraper_with_filters()

