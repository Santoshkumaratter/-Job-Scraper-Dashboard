"""Glassdoor Scraper"""
from typing import List, Dict
from ..utils.base_scraper import BaseScraper
import urllib.parse

class GlassdoorScraper(BaseScraper):
    @property
    def portal_name(self) -> str:
        return "Glassdoor"
    
    @property
    def base_url(self) -> str:
        return "https://www.glassdoor.com"
    
    @property
    def requires_selenium(self) -> bool:
        return True
    
    def build_search_url(self, keyword: str) -> str:
        params = {'keyword': keyword}
        return f"{self.base_url}/Job/jobs.htm?{urllib.parse.urlencode(params)}"
    
    def scrape_jobs(self) -> List[Dict]:
        jobs = []
        for keyword in self.keywords:
            url = self.build_search_url(keyword)
            html = self.make_request(url, use_selenium=True)
            if not html:
                continue
            soup = self.parse_html(html)
            job_cards = soup.find_all('li', class_='react-job-listing')
            for card in job_cards:
                try:
                    title_elem = card.find('a', class_='job-title')
                    if not title_elem:
                        continue
                    job_data = {
                        'job_title': self.clean_text(title_elem.get_text()),
                        'company': self.clean_text(card.find('div', class_='employer-name').get_text() if card.find('div', class_='employer-name') else 'Unknown'),
                        'company_url': None,
                        'company_size': 'UNKNOWN',
                        'market': 'USA',
                        'job_link': self.base_url + title_elem['href'] if title_elem else '',
                        'posted_date': self.parse_date(card.find('span', class_='job-posted').get_text() if card.find('span', class_='job-posted') else ''),
                        'location': self.clean_text(card.find('span', class_='job-location').get_text() if card.find('span', class_='job-location') else ''),
                        'job_description': '',
                        'job_type': self.job_type if self.job_type != 'ALL' else '',
                    }
                    if self.should_include_job(job_data['posted_date']):
                        jobs.append(job_data)
                except:
                    continue
        return jobs

