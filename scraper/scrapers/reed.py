"""Reed Job Scraper"""
from typing import List, Dict
from ..utils.base_scraper import BaseScraper
import urllib.parse

class ReedScraper(BaseScraper):
    @property
    def portal_name(self) -> str:
        return "Reed"
    
    @property
    def base_url(self) -> str:
        return "https://www.reed.co.uk"
    
    def build_search_url(self, keyword: str) -> str:
        params = {'keywords': keyword}
        return f"{self.base_url}/jobs?{urllib.parse.urlencode(params)}"
    
    def scrape_jobs(self) -> List[Dict]:
        jobs = []
        for keyword in self.keywords:
            url = self.build_search_url(keyword)
            html = self.make_request(url)
            if not html:
                continue
            soup = self.parse_html(html)
            job_cards = soup.find_all('article', class_='job-result')
            for card in job_cards:
                try:
                    title_elem = card.find('h2')
                    if not title_elem:
                        continue
                    job_data = {
                        'job_title': self.clean_text(title_elem.get_text()),
                        'company': self.clean_text(card.find('a', class_='gtmJobListingPostedBy').get_text() if card.find('a', class_='gtmJobListingPostedBy') else 'Unknown'),
                        'company_url': None,
                        'company_size': 'UNKNOWN',
                        'market': 'UK',
                        'job_link': self.base_url + card.find('a', class_='job-result-heading__link')['href'] if card.find('a', class_='job-result-heading__link') else '',
                        'posted_date': self.parse_date(card.find('time').get('datetime') if card.find('time') else ''),
                        'location': self.clean_text(card.find('li', class_='job-metadata__item').get_text() if card.find('li', class_='job-metadata__item') else ''),
                        'job_description': '',
                        'job_type': self.job_type if self.job_type != 'ALL' else '',
                    }
                    if self.should_include_job(job_data['posted_date']):
                        jobs.append(job_data)
                except:
                    continue
        return jobs

