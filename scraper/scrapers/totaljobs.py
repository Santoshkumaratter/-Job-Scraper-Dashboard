"""Totaljobs Scraper"""
from typing import List, Dict
from ..utils.base_scraper import BaseScraper
import urllib.parse

class TotalJobsScraper(BaseScraper):
    @property
    def portal_name(self) -> str:
        return "Totaljobs"
    
    @property
    def base_url(self) -> str:
        return "https://www.totaljobs.com"
    
    def build_search_url(self, keyword: str) -> str:
        params = {'q': keyword}
        return f"{self.base_url}/jobs/{urllib.parse.quote(keyword)}"
    
    def scrape_jobs(self) -> List[Dict]:
        jobs = []
        for keyword in self.keywords:
            url = self.build_search_url(keyword)
            html = self.make_request(url)
            if not html:
                continue
            soup = self.parse_html(html)
            job_cards = soup.find_all('div', class_='job')
            for card in job_cards:
                try:
                    title_elem = card.find('h2', class_='job-title')
                    if not title_elem:
                        continue
                    job_data = {
                        'job_title': self.clean_text(title_elem.get_text()),
                        'company': self.clean_text(card.find('a', class_='company').get_text() if card.find('a', class_='company') else 'Unknown'),
                        'company_url': None,
                        'company_size': 'UNKNOWN',
                        'market': 'UK',
                        'job_link': self.base_url + card.find('a', class_='job-title')['href'] if card.find('a', class_='job-title') else '',
                        'posted_date': self.parse_date(card.find('span', class_='job-posted').get_text() if card.find('span', class_='job-posted') else ''),
                        'location': self.clean_text(card.find('li', class_='location').get_text() if card.find('li', class_='location') else ''),
                        'job_description': '',
                        'job_type': self.job_type if self.job_type != 'ALL' else '',
                    }
                    if self.should_include_job(job_data['posted_date']):
                        jobs.append(job_data)
                except:
                    continue
        return jobs

