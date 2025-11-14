# Job Data Scraper with Dashboard Management

## Project Overview

This application provides an automated job data scraper integrated with a user-friendly dashboard. The scraper collects detailed job listings from various job portals and stores the data for easy access. The dashboard allows non-technical users to manage job-related keywords, apply filters, save and load specific job search filters, and retrieve job data.

## Features

### Job Data Scraper

The scraper extracts the following fields from job portals:

- **Job_Title**: The title of the job
- **Company**: The name of the hiring company
- **Company_URL**: The website link to the company
- **Company_Size**: The size of the company (e.g., small, medium, large)
- **Market**: The market of the job posting (USA or UK)
- **Source_Job-Portal**: The name of the job portal
- **Job_Link**: The URL for the job listing
- **Posted_Date**: The date the job was posted
- **Location**: The location of the job
- **Decision_Maker_Name**: The name of the decision maker (HR, Hiring Manager, etc.)
- **Decision_Maker_Title**: The title of the decision-maker
- **Decision_Maker_LinkedIn**: LinkedIn profile URL of the decision-maker
- **Decision_Maker_Email**: Email address of the decision-maker

### Supported Job Portals

The system scrapes jobs from **32 active job portals** (Indeed UK and Glassdoor are disabled due to blocking issues):

1. LinkedIn Jobs
2. CV-Library
3. Adzuna
4. Totaljobs
5. Reed
6. Talent
7. ZipRecruiter
8. CWjobs
9. Jobsora
10. WelcometotheJungle
11. IT Job Board
12. Trueup
13. Redefined
14. We Work Remotely
15. AngelList (Wellfound)
16. Jobspresso
17. Grabjobs
18. Remote OK
19. Working Nomads
20. WorkInStartups
21. Jobtensor
22. Jora
23. SEOJobs.com
24. CareerBuilder
25. Dice
26. Escape The City
27. Jooble
28. Otta
29. Remote.co
30. SEL Jobs
31. FlexJobs
32. Dynamite Jobs
33. SimplyHired
34. Remotive

**Note:** Indeed UK and Glassdoor are currently disabled due to anti-scraping measures. They can be re-enabled in the future with improved anti-blocking techniques.

### Dashboard Functionality

The dashboard provides a user-friendly interface for:

- **Keyword Management**: Add, edit, and delete job-related keywords
- **Filter Options**: 
  - Job Type: Remote, Freelance, Full-time, Hybrid, or All
  - Time Filter: Last 24 hours, 3 days, 7 days, All Time
  - Location: USA, UK, or All
- **Save and Load Filters**: Save specific combinations of keywords and filters for future use
- **Job Data Export**: Export job data to CSV format
- **Real-time Job Tracking**: View scraped jobs in real-time

## Getting Started

### Prerequisites

- Python 3.8 or higher
- pip (Python package manager)
- Virtual environment (recommended)

### Installation

1. Clone the repository
2. Create and activate a virtual environment (recommended)
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install the dependencies
```bash
pip install -r requirements.txt
```

4. Set up the database
```bash
python manage.py migrate
```

5. Set up initial data (job portals and default keywords)
```bash
python manage.py setup_portals
```

**Note:** The `setup_portals` command will:
- Create all 32 active job portals in the database
- Add all technical keywords (27+ keywords)
- Add all non-technical keywords (16+ keywords)
- Set portal priorities and configurations

6. (Optional) Configure environment variables
   
   Create a `.env` file in the project root for production settings:
```bash
   SECRET_KEY=your-secret-key-here
   DEBUG=False
   ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com
   CELERY_BROKER_URL=redis://localhost:6379/0
   HUNTER_API_KEY=your-hunter-api-key  # Optional: for email finding
   SCRAPERAPI_KEY=your-scraperapi-key  # Optional: for proxy service
   CLEARBIT_API_KEY=your-clearbit-key  # Optional: for company enrichment
   ```

7. Run the development server
```bash
python manage.py runserver
```

8. Access the dashboard at http://127.0.0.1:8000/

## Usage Instructions

1. **Keyword Management**:
   - Go to the Keywords page to add or remove job-related keywords
   - Keywords are categorized as Technical, Non-Technical, or Both

2. **Running a Scraper**:
   - From the Dashboard, select your desired keywords
   - Choose your filters (job type, time period, location)
   - Select job portals (or use "All Job Portals")
   - Click "Run Now" to start the scraper

3. **Viewing Results**:
   - Go to the Jobs page to see all scraped jobs
   - Use filters to narrow down the results
   - Click on job titles to see details

4. **Exporting Data**:
   - Click "Download CSV" to export all job data
   - The CSV file will contain all scraped job fields

5. **Saving Filters**:
   - After configuring your filters, you can save them for future use
   - Access saved filters from the Filters page

## Important Notes

### Blocked Portals

Indeed UK and Glassdoor are currently disabled due to anti-scraping measures. The system uses 32 active portals that work reliably. These blocked portals can be re-enabled in the future with improved anti-blocking techniques (rotating proxies, CAPTCHA solving, etc.).

### Performance

- Scraping typically completes in **2-10 minutes** depending on the number of portals selected
- Use "All Job Portals" for maximum results
- Use "Last 24 Hours" filter for fresh jobs (recommended)
- The system uses parallel scraping for faster performance

### Company Size Detection

Company sizes are automatically detected using:
- Known company database
- Website scraping
- Domain estimation

If a company size shows as "UNKNOWN", it means the company information wasn't found in our database or couldn't be scraped.

## Troubleshooting

### No Jobs Found
- Verify keywords match job titles
- Try using "All Time" filter instead of "Last 24 Hours"
- Check if portals are active in the database
- Review `scraper.log` for errors

### Scraping Too Slow
- Try selecting fewer job portals
- Use faster portals (Remote OK, Remotive, We Work Remotely)
- Check your internet connection

### Portals Not Working
- Some portals may block requests (they're automatically disabled)
- Check `scraper.log` for specific portal errors
- Try running with different portals

### Database Issues
- Clear old jobs periodically: Use "Delete All Jobs" button
- Reset database if needed: `python manage.py flush`
- Run migrations: `python manage.py migrate`

## Environment Variables

For production deployment, create a `.env` file in the project root with the following variables:

```bash
# Django Settings
SECRET_KEY=your-secret-key-here
DEBUG=False
ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com

# Celery Configuration
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0

# Optional API Keys (for enhanced features)
HUNTER_API_KEY=your-hunter-api-key          # For email finding
SCRAPERAPI_KEY=your-scraperapi-key          # For proxy service
CLEARBIT_API_KEY=your-clearbit-key          # For company enrichment

# Scraper Configuration
MAX_CONCURRENT_SCRAPERS=5
SCRAPER_TIMEOUT=30
USE_PROXY=False
```

**Security Note:** Never commit `.env` files to version control. The `.gitignore` file already excludes `.env` files.

## Documentation

- **QUICK_START.md** - Quick setup guide
- **USER_GUIDE.md** - Detailed user instructions
- **DEPLOYMENT_GUIDE.md** - Production deployment guide

## Support

For any issues or questions, please check the documentation files or review the logs in `scraper.log`.