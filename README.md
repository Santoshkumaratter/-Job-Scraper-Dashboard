# Job Data Scraping Dashboard

## 📋 Project Overview

An automated job data scraping system with a user-friendly dashboard that collects job listings from **36+ job portals** and exports data to Google Sheets. Built with Django, Celery, and Beautiful Soup/Selenium.

### ✨ Key Features

- ✅ **36 Job Portal Scrapers** - Indeed, LinkedIn, Glassdoor, ZipRecruiter, and 32 more
- ✅ **Smart Filtering** - Filter by job type, location, time posted, keywords
- ✅ **Decision Maker Finder** - Automatically finds hiring managers and their contact info
- ✅ **Google Sheets Export** - Seamless integration with Google Sheets
- ✅ **Async Processing** - Background scraping with Celery
- ✅ **User-Friendly Dashboard** - Intuitive UI for non-technical users
- ✅ **Save & Load Filters** - Create reusable scraping configurations
- ✅ **REST API** - Full API access for automation

---

## 🚀 Quick Start

### Prerequisites

- Python 3.8+
- Redis Server (for Celery)
- Google Sheets API Credentials
- Chrome/Chromium (for Selenium)

### Installation

1. **Clone the repository**
```bash
git clone <repository-url>
cd Dashboard_job_data
```

2. **Create virtual environment**
```bash
python -m venv venv
# On Windows:
venv\Scripts\activate
# On Linux/Mac:
source venv/bin/activate
```

3. **Install dependencies**
```bash
pip install -r requirements.txt
```

4. **Setup environment variables**
```bash
copy .env.example .env
# Edit .env with your configuration
```

5. **Google Sheets Setup**
- Create a Google Cloud Project
- Enable Google Sheets API
- Create Service Account credentials
- Download credentials.json and place in project root
- Share your Google Sheet with the service account email

6. **Database Migration**
```bash
python manage.py makemigrations
python manage.py migrate
```

7. **Create superuser**
```bash
python manage.py createsuperuser
```

8. **Load initial data (Job Portals)**
```bash
python manage.py setup_portals
```

---

## 🎯 Usage

### Starting the Application

**1. Start Redis Server**
```bash
# Windows (if installed via chocolatey):
redis-server

# Linux/Mac:
sudo systemctl start redis
```

**2. Start Django Server**
```bash
python manage.py runserver
```

**3. Start Celery Worker**
```bash
# In a new terminal:
celery -A job_dashboard worker --loglevel=info
```

**4. Start Celery Beat (Optional - for scheduled tasks)**
```bash
# In another terminal:
celery -A job_dashboard beat --loglevel=info
```

### Accessing the Dashboard

- **Dashboard**: http://localhost:8000/
- **Admin Panel**: http://localhost:8000/admin/
- **API**: http://localhost:8000/api/

---

## 📖 User Guide

### 1. Managing Keywords

Navigate to **Keywords** page:
- Click "Add Keyword" button
- Enter keyword name (e.g., "React Developer", "SEO Specialist")
- Select category: Technical, Non-Technical, or Both
- Keywords are used to search across job portals

**Predefined Keywords:**

**Technical:**
- React Native Developer
- Full Stack Developer
- Python Engineer
- DevOps Engineer
- AI/ML Engineer

**Non-Technical:**
- SEO Specialist
- Digital Marketing Manager
- PPC Specialist
- Content Marketing Specialist

### 2. Creating Filters

Navigate to **Saved Filters** page:
- Click "Create Filter" button
- Configure your filter:
  - **Name**: Give your filter a descriptive name
  - **Job Type**: All, Remote, Freelance, Full Time, Hybrid
  - **Time Filter**: 24 hours, 3 days, 7 days, All time
  - **Location**: All, USA, UK
  - **Keywords**: Select keywords to search
  - **Job Portals**: Select which portals to scrape

### 3. Running Scrapers

From **Saved Filters** page:
- Find your filter
- Click "Run Scraper" button
- Monitor progress in Dashboard > Recent Scraper Runs
- Jobs will appear in the Jobs page

### 4. Viewing Jobs

Navigate to **Jobs** page:
- Browse all scraped jobs
- Filter by company, market
- Click info icon to see decision makers
- Click link icon to visit job posting

### 5. Exporting to Google Sheets

From **Jobs** page:
- Click "Export to Google Sheets" button
- Data exports with all fields including decision makers
- Check Google Sheet for results

---

## 🔧 Configuration

### Job Portal Configuration

Edit job portals in Admin Panel:
- Go to Admin > Job Portals
- Enable/disable portals
- Set rate limits
- Adjust priorities

### Google Sheets Configuration

Admin Panel > Google Sheet Configs:
- Create new configuration
- Enter Spreadsheet ID
- Set worksheet name
- Enable auto-export (optional)

### Celery Configuration

Edit `job_dashboard/celery.py` for:
- Periodic task schedules
- Beat schedule configuration
- Task retry policies

---

## 🏗️ Project Structure

```
Dashboard_job_data/
├── job_dashboard/          # Main project settings
│   ├── settings.py
│   ├── urls.py
│   └── celery.py
├── dashboard/              # Dashboard app
│   ├── models.py          # Keywords, Filters, ScraperRuns
│   ├── views.py           # Dashboard views & API
│   ├── serializers.py
│   └── admin.py
├── scraper/               # Scraper app
│   ├── models.py         # Jobs, DecisionMakers
│   ├── tasks.py          # Celery tasks
│   ├── scraper_manager.py
│   ├── scrapers/         # Individual portal scrapers
│   │   ├── indeed_uk.py
│   │   ├── linkedin_jobs.py
│   │   └── ... (34 more)
│   └── utils/
│       ├── base_scraper.py
│       └── decision_maker_finder.py
├── google_sheets/         # Google Sheets integration
│   ├── models.py
│   └── services.py
├── templates/            # HTML templates
│   ├── base.html
│   └── dashboard/
├── static/              # CSS, JS, images
├── requirements.txt     # Python dependencies
└── README.md           # This file
```

---

## 🌐 Supported Job Portals

### UK Portals
1. Indeed UK
2. CV-Library
3. Totaljobs
4. Reed
5. CWjobs
6. Adzuna
7. Jora

### US Portals
8. LinkedIn Jobs
9. Glassdoor
10. ZipRecruiter
11. CareerBuilder
12. Dice
13. SimplyHired

### Remote Job Portals
14. We Work Remotely
15. Remote OK
16. Working Nomads
17. Remote.co
18. FlexJobs
19. Dynamite Jobs
20. Remotive

### Startup & Tech
21. AngelList (Wellfound)
22. Otta
23. WorkInStartups
24. Trueup

### Specialized
25. SEOJobs.com
26. IT Job Board
27. SEL Jobs
28. Jobspresso
29. Grabjobs

### Aggregators
30. Talent
31. Jobsora
32. Jobtensor
33. Jooble

### Additional
34. WelcometotheJungle
35. Redefined
36. Escape The City

---

## 🛠️ API Documentation

### REST API Endpoints

**Keywords**
- `GET /api/keywords/` - List all keywords
- `POST /api/keywords/` - Create keyword
- `GET /api/keywords/{id}/` - Get keyword details
- `PUT /api/keywords/{id}/` - Update keyword
- `DELETE /api/keywords/{id}/` - Delete keyword

**Filters**
- `GET /api/filters/` - List all filters
- `POST /api/filters/` - Create filter
- `POST /api/filters/{id}/run_scraper/` - Run scraper
- `GET /api/filters/{id}/scraper_runs/` - Get scraper runs

**Jobs**
- `GET /api/jobs/` - List jobs
- `GET /api/jobs/{id}/` - Get job details
- `POST /api/jobs/export_to_sheets/` - Export jobs

**Query Parameters:**
- `company` - Filter by company name
- `market` - Filter by market (USA/UK)
- `portal` - Filter by portal ID
- `is_exported` - Filter by export status

---

## 🔐 Security Notes

- **Never commit** `.env` file or `credentials.json`
- Change `SECRET_KEY` in production
- Set `DEBUG=False` in production
- Use environment variables for sensitive data
- Restrict Google Sheets API access

---

## 📊 Data Fields

Each job entry includes:
- Job Title
- Company Name & URL
- Company Size
- Market (USA/UK)
- Source Job Portal
- Job Link
- Posted Date
- Location
- Job Type
- Decision Maker Name(s)
- Decision Maker Title(s)
- Decision Maker LinkedIn
- Decision Maker Email
- Scraped At timestamp

---

## 🐛 Troubleshooting

### Common Issues

**1. Celery not working**
- Ensure Redis is running
- Check Celery worker logs
- Verify `CELERY_BROKER_URL` in settings

**2. Google Sheets export fails**
- Verify `credentials.json` exists
- Check service account has edit access to sheet
- Ensure Spreadsheet ID is correct

**3. Selenium errors**
- Install Chrome/Chromium
- Update chromedriver: `pip install --upgrade webdriver-manager`
- Check headless mode settings

**4. Scraper not finding jobs**
- Website structure may have changed
- Check scraper logs
- Verify portal is active
- Check rate limiting

---

## 🤝 Contributing

Contributions are welcome! To add a new job portal:

1. Create new scraper file in `scraper/scrapers/`
2. Inherit from `BaseScraper`
3. Implement required methods
4. Add to `SCRAPER_REGISTRY` in `__init__.py`
5. Create JobPortal entry in database

---

## 📝 License

This project is for educational and personal use. Ensure compliance with job portal terms of service and robots.txt when scraping.

---

## 👨‍💻 Support

For issues and questions:
- Check troubleshooting section
- Review Django and Celery logs
- Inspect browser network tab for API errors

---

## 🎓 Tech Stack

- **Backend**: Django 5.2, Python 3.8+
- **Database**: SQLite (PostgreSQL recommended for production)
- **Task Queue**: Celery + Redis
- **Scraping**: BeautifulSoup4, Selenium, Requests
- **API**: Django REST Framework
- **Frontend**: Bootstrap 5, jQuery
- **Integration**: Google Sheets API

---

## 📈 Future Enhancements

- [ ] Email notifications
- [ ] Advanced analytics dashboard
- [ ] Job matching algorithm
- [ ] Auto-application system
- [ ] Multi-language support
- [ ] Mobile app
- [ ] LinkedIn API integration
- [ ] Salary predictions
- [ ] Company reviews integration

---

**Happy Scraping! 🚀**

