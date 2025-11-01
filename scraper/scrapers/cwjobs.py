"""CWjobs Scraper"""
from typing import List, Dict
from ..utils.base_scraper import BaseScraper
import urllib.parse

class CWJobsScraper(BaseScraper):
    @property
    def portal_name(self) -> str:
        return "CWjobs"
    
    @property
    def base_url(self) -> str:
        return "https://www.cwjobs.co.uk"
    
    def build_search_url(self, keyword: str) -> str:
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
                    title_elem = card.find('h2')
                    if not title_elem:
                        continue
                    job_data = {
                        'job_title': self.clean_text(title_elem.get_text()),
                        'company': self.clean_text(card.find('span', class_='company').get_text() if card.find('span', class_='company') else 'Unknown'),
                        'company_url': None,
                        'company_size': 'UNKNOWN',
                        'market': 'UK',
                        'job_link': self.base_url + card.find('a')['href'] if card.find('a') else '',
                        'posted_date': None,
                        'location': self.clean_text(card.find('span', class_='location').get_text() if card.find('span', class_='location') else ''),
                        'job_description': '',
                        'job_type': self.job_type if self.job_type != 'ALL' else '',
                    }
                    jobs.append(job_data)
                except:
                    continue
        return jobs

