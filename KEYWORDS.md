# 📋 Predefined Keywords List

## Technical Keywords

### React Native / Mobile Development
- React Native Developer
- Senior React Native Developer
- Lead React Native Developer
- Mobile Application Developer (React Native)
- Mobile Engineer (iOS+Android – React Native)
- Frontend Developer (React Native)
- Cross-Platform Mobile Developer
- Mobile Software Engineer
- React Developer (with mobile experience)
- Senior Mobile Engineer – React Native

### Full Stack Development
- Full Stack Developer
- Senior Full Stack Developer
- Lead Full Stack Engineer
- Software Engineer (Python + JavaScript)
- Backend Engineer (Python + Django + FastAPI)
- Principal Software Engineer
- Engineering Lead

### Python Development
- Python Developer
- Senior Python Engineer
- Django Developer
- Django Engineer
- FastAPI Engineer

### Cloud & DevOps
- Cloud Engineer (AWS + GCP)
- DevOps Engineer (Python + Cloud)
- Site Reliability Engineer
- Infrastructure Engineer
- Platform Engineer

### AI & Machine Learning
- AI Engineer
- AI Research Engineer
- Machine Learning Engineer
- LLM Engineer
- Generative AI Engineer
- Applied Scientist (AI + ML)
- AI Software Engineer
- Data Scientist
- ML Ops Engineer

### Frontend Development
- Frontend Developer
- React Developer
- Vue.js Developer
- Angular Developer
- JavaScript Developer
- TypeScript Developer
- UI Engineer

### Backend Development
- Backend Developer
- Backend Engineer
- API Developer
- Microservices Developer
- Node.js Developer

### Data Engineering
- Data Engineer
- Big Data Engineer
- ETL Developer
- Database Administrator
- Data Warehouse Engineer

---

## Non-Technical Keywords

### SEO (Search Engine Optimization)
- SEO Specialist
- SEO Manager
- SEO Analyst
- Search Engine Optimization Expert
- Technical SEO Specialist
- SEO Consultant
- SEO Strategist
- Link Building Specialist
- Local SEO Expert

### Digital Marketing
- Digital Marketing Specialist
- Digital Marketing Manager
- Digital Marketer
- Marketing Specialist
- Marketing Manager
- Growth Marketing Manager
- Performance Marketing Manager
- Online Marketing Specialist
- E-commerce Marketing Manager

### Content Marketing
- Content Marketing Specialist
- Content Marketing Manager
- Content Strategist
- Content Writer
- Copywriter
- Blog Manager
- Editorial Manager

### Paid Advertising / PPC
- Paid Advertising Manager
- Media Buyer
- Digital Media Manager
- Paid Media Specialist
- Google Ads Expert
- PPC Specialist
- Paid Search Manager
- Facebook Ads Specialist
- Programmatic Specialist

### Social Media Marketing
- Social Media Manager
- Social Media Specialist
- Social Media Strategist
- Community Manager
- Social Media Coordinator

### Email Marketing
- Email Marketing Specialist
- Email Marketing Manager
- CRM Manager
- Marketing Automation Specialist

### Analytics & Data
- Marketing Analyst
- Digital Analytics Manager
- Web Analyst
- Conversion Rate Optimizer
- Data Analyst (Marketing)

### Brand & Creative
- Brand Manager
- Creative Director
- Graphic Designer
- UI/UX Designer
- Product Designer

### Product Marketing
- Product Marketing Manager
- Product Manager
- Growth Product Manager
- Technical Product Manager

### Business & Strategy
- Business Development Manager
- Marketing Director
- Head of Marketing
- Chief Marketing Officer
- Growth Manager
- Partnership Manager

---

## How to Use These Keywords

### 1. **Category Selection**

When adding keywords, categorize them:
- **Technical** - For software development, engineering roles
- **Non-Technical** - For marketing, business, operations roles
- **Both** - For hybrid or cross-functional roles

### 2. **Combining Keywords**

For best results, combine related keywords:
- "React Native Developer" + "Mobile Engineer"
- "SEO Specialist" + "Digital Marketing Manager"
- "Python Developer" + "Machine Learning Engineer"

### 3. **Location-Specific Keywords**

Some roles have different names in different markets:
- UK: "Software Engineer", "Developer"
- USA: "Software Developer", "Software Architect"

### 4. **Seniority Levels**

Include various levels:
- Junior, Mid-level, Senior
- Lead, Principal, Staff
- Manager, Director, Head of

### 5. **Filter Recommendations**

**For Remote Jobs:**
- Use: "Remote", "Work from Home", "Distributed"
- Portals: We Work Remotely, Remote OK, FlexJobs

**For Startups:**
- Portals: AngelList, WorkInStartups, Otta

**For UK Market:**
- Portals: Indeed UK, CV-Library, Totaljobs, Reed

**For US Market:**
- Portals: Indeed, LinkedIn, ZipRecruiter, Dice

---

## Custom Keywords

You can add your own keywords based on:

### Industry-Specific
- Finance: "FinTech Developer", "Trading Systems Engineer"
- Healthcare: "Healthcare Software Engineer", "Medical AI Engineer"
- E-commerce: "E-commerce Developer", "Shopify Developer"
- Gaming: "Game Developer", "Unity Developer"

### Technology-Specific
- Blockchain: "Blockchain Developer", "Solidity Developer"
- IoT: "IoT Engineer", "Embedded Systems Developer"
- Cybersecurity: "Security Engineer", "Penetration Tester"

### Skill-Specific
- "AWS Certified Developer"
- "Kubernetes Engineer"
- "GraphQL Developer"
- "Salesforce Developer"

---

## Keyword Best Practices

### ✅ DO:
- Use specific job titles
- Include variations of the same role
- Add seniority levels
- Include both abbreviations and full terms (e.g., "SEO" and "Search Engine Optimization")
- Test keywords to see which get best results

### ❌ DON'T:
- Use generic terms like "jobs" or "work"
- Add duplicate keywords
- Use overly specific niche terms (unless targeting specific roles)
- Add location names in keywords (use Location filter instead)

---

## Adding Keywords via Dashboard

1. Go to **Keywords** page
2. Click **Add Keyword** button
3. Enter keyword name
4. Select category (Technical/Non-Technical/Both)
5. Save

## Adding Keywords via Admin Panel

1. Go to http://localhost:8000/admin/
2. Navigate to **Keywords**
3. Click **Add Keyword**
4. Fill in details
5. Save

## Bulk Adding Keywords

Use Django shell:
```python
python manage.py shell

from dashboard.models import Keyword

keywords = [
    {'name': 'React Developer', 'category': 'TECHNICAL'},
    {'name': 'SEO Specialist', 'category': 'NON_TECHNICAL'},
    # Add more...
]

for kw in keywords:
    Keyword.objects.get_or_create(name=kw['name'], defaults={'category': kw['category']})
```

---

## Keyword Strategy Examples

### Example 1: React Native Jobs in UK
**Keywords:**
- React Native Developer
- Mobile Engineer
- Frontend Developer

**Filters:**
- Location: UK
- Job Type: All
- Time: Last 7 days
- Portals: Indeed UK, CV-Library, Totaljobs

### Example 2: Remote SEO Jobs
**Keywords:**
- SEO Specialist
- SEO Manager
- Digital Marketing Manager

**Filters:**
- Location: All
- Job Type: Remote
- Time: Last 3 days
- Portals: We Work Remotely, Remote OK, FlexJobs

### Example 3: AI/ML Engineering in USA
**Keywords:**
- Machine Learning Engineer
- AI Engineer
- Data Scientist

**Filters:**
- Location: USA
- Job Type: Full Time
- Time: Last 24 hours
- Portals: LinkedIn, Glassdoor, Dice

---

**Happy Keyword Hunting! 🎯**

