"""
Multi-Approach Scraper - Comprehensive fallback strategies
Tries multiple methods to extract jobs from any portal
"""
import logging
import re
import json
from typing import List, Dict, Optional
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


class MultiApproachExtractor:
    """Extracts jobs using multiple approaches - keeps trying until it finds jobs"""
    
    @staticmethod
    def extract_jobs_from_soup(soup: BeautifulSoup, base_url: str, keywords: List[str] = None) -> List:
        """
        Try ALL possible methods to extract jobs from a soup object
        Returns list of job cards/elements found by any method
        """
        job_cards = []
        seen_hrefs = set()
        
        # APPROACH 1: Standard selectors (most common) - COLLECT ALL, DON'T STOP
        logger.debug("Multi-Approach: Trying standard selectors...")
        standard_selectors = [
            ('div', {'class': 'job-card'}),
            ('div', {'class': 'job'}),
            ('article', {'class': 'job'}),
            ('li', {'class': 'job'}),
            ('div', {'class': 'job-item'}),
            ('div', {'class': 'job-result'}),
            ('div', {'class': 'job-listing'}),
            ('article', {'class': 'job-card'}),
            ('div', {'class': lambda x: x and 'job' in ' '.join(x).lower()}),
            ('article', {'class': lambda x: x and 'job' in ' '.join(x).lower()}),
            ('li', {'class': lambda x: x and 'job' in ' '.join(x).lower()}),
        ]
        
        for tag, attrs in standard_selectors:
            try:
                found = soup.find_all(tag, attrs)
                if found:
                    job_cards.extend(found)
                    logger.debug(f"Multi-Approach: Found {len(found)} cards with {tag} {attrs}")
            except:
                continue
        
        # APPROACH 2: CSS selectors - ALWAYS TRY, DON'T SKIP
        logger.debug("Multi-Approach: Trying CSS selectors...")
        css_selectors = [
            'div[class*="job"]',
            'article[class*="job"]',
            'li[class*="job"]',
            '[data-job-id]',
            '[data-job]',
            '[id*="job"]',
            '[class*="position"]',
            '[class*="listing"]',
            '[class*="result"]',
            '[class*="card"]',
            '[class*="item"]',
        ]
        for selector in css_selectors:
            try:
                found = soup.select(selector)
                if found:
                    # Deduplicate - only add if not already in job_cards
                    for item in found:
                        if item not in job_cards:
                            job_cards.append(item)
                    logger.debug(f"Multi-Approach: Found {len(found)} with CSS {selector}")
            except:
                continue
        
        # APPROACH 3: Find job links and extract parent containers - ALWAYS TRY
        logger.debug("Multi-Approach: Trying link-based extraction...")
        job_link_patterns = [
            r'/job',
            r'/position',
            r'/career',
            r'/vacancy',
            r'/search',
            r'/detail',
            r'/apply',
            r'/view',
            r'/listing',
            r'/opening',
            r'/opportunity',
            r'/role',
            r'/posting',
        ]
        
        for pattern in job_link_patterns:
            try:
                job_links = soup.find_all('a', href=re.compile(pattern, re.I))
                for link in job_links[:300]:  # Increased limit
                    try:
                        href = link.get('href', '')
                        if not href or href.startswith('#') or href in seen_hrefs:
                            continue
                        seen_hrefs.add(href)
                        
                        # Try to find parent container
                        parent = link.find_parent(['div', 'article', 'li', 'section', 'tr', 'td'])
                        if parent and parent not in job_cards:
                            job_cards.append(parent)
                        elif not parent:
                            # If no parent, use link itself
                            if link not in job_cards:
                                job_cards.append(link)
                    except:
                        continue
            except:
                continue
        
        if job_cards:
            logger.info(f"Multi-Approach: Found {len(job_cards)} job cards via link extraction")
        
        # APPROACH 4: Extract from JSON-LD scripts - ALWAYS TRY
        logger.debug("Multi-Approach: Trying JSON-LD extraction...")
        try:
            scripts = soup.find_all('script', type='application/ld+json')
            json_ld_count = 0
            for script in scripts:
                try:
                    data = json.loads(script.get_text(strip=True) or '{}')
                    if isinstance(data, dict):
                        # Handle @graph
                        if '@graph' in data:
                            graph = data['@graph']
                            for item in graph:
                                if isinstance(item, dict) and item.get('@type') == 'JobPosting':
                                    if item not in job_cards:
                                        job_cards.append(item)  # Store as dict
                                        json_ld_count += 1
                        elif data.get('@type') == 'JobPosting':
                            if data not in job_cards:
                                job_cards.append(data)
                                json_ld_count += 1
                except:
                    continue
            
            if json_ld_count > 0:
                logger.info(f"Multi-Approach: Found {json_ld_count} jobs via JSON-LD")
        except:
            pass
        
        # APPROACH 5: Find any element with job-related attributes - ALWAYS TRY
        logger.debug("Multi-Approach: Trying attribute-based extraction...")
        try:
            # Find elements with data-job-id, data-job, etc.
            for attr in ['data-job-id', 'data-job', 'data-position', 'data-listing']:
                found = soup.find_all(attrs={attr: True})
                if found:
                    for item in found:
                        if item not in job_cards:
                            job_cards.append(item)
                    logger.debug(f"Multi-Approach: Found {len(found)} with {attr}")
        except:
            pass
        
        # APPROACH 6: Find all links that might be jobs (very aggressive) - ALWAYS TRY
        logger.debug("Multi-Approach: Trying very aggressive link extraction...")
        try:
            all_links = soup.find_all('a', href=True)
            for link in all_links[:2000]:  # Increased limit significantly
                try:
                    href = link.get('href', '').lower()
                    text = link.get_text().strip()
                    text_lower = text.lower()
                    
                    # ✅ VERY AGGRESSIVE - Accept ANY link with reasonable text length
                    # Accept if:
                    # 1. Has job indicators OR
                    # 2. Has reasonable text length (10-200 chars) OR
                    # 3. Has href that looks like a job URL
                    job_indicators = [
                        'apply', 'view job', 'read more', 'details', 'job', 'position',
                        'career', 'vacancy', 'opening', 'opportunity', 'role', 'hiring',
                        'developer', 'engineer', 'manager', 'analyst', 'designer', 'specialist'
                    ]
                    
                    href_indicators = ['/job', '/position', '/career', '/vacancy', '/role', '/opening']
                    
                    # Very lenient matching - accept almost any reasonable link
                    is_potential_job = (
                        any(indicator in text_lower or indicator in href for indicator in job_indicators) or
                        (len(text) > 8 and len(text) < 300 and not text.startswith('http') and not text.startswith('www')) or
                        any(ind in href for ind in href_indicators)
                    )
                    
                    if is_potential_job:
                        if href not in seen_hrefs and not href.startswith('#') and not href.startswith('mailto:') and not href.startswith('javascript:'):
                            seen_hrefs.add(href)
                            parent = link.find_parent(['div', 'article', 'li', 'section', 'tr', 'td'])
                            if parent and parent not in job_cards:
                                job_cards.append(parent)
                            elif not parent:
                                if link not in job_cards:
                                    job_cards.append(link)
                except:
                    continue
            
            if job_cards:
                logger.info(f"Multi-Approach: Found {len(job_cards)} via aggressive link extraction")
        except:
            pass
        
        # APPROACH 7: Find any div/article/li with job-related text - ALWAYS TRY
        logger.debug("Multi-Approach: Trying text-based extraction...")
        try:
            all_elements = soup.find_all(['div', 'article', 'li', 'section', 'tr', 'td'])
            for elem in all_elements[:5000]:  # Significantly increased limit
                try:
                    text = elem.get_text().strip()
                    # ✅ VERY AGGRESSIVE - Accept ANY element with a link and reasonable text
                    # Check if it has a link inside (any link is a potential job)
                    has_link = elem.find('a', href=True)
                    if has_link and len(text) > 5 and len(text) < 1000:  # Very lenient - has link and reasonable text
                        # Skip if it's a navigation or footer element
                        parent_classes = ' '.join(elem.get('class', [])).lower()
                        if 'nav' not in parent_classes and 'footer' not in parent_classes and 'header' not in parent_classes:
                            if elem not in job_cards:
                                job_cards.append(elem)
                except:
                    continue
            
            if job_cards:
                logger.info(f"Multi-Approach: Found {len(job_cards)} via text-based extraction")
        except:
            pass
        
        # Deduplicate by href/id
        unique_cards = []
        seen_ids = set()
        for card in job_cards:
            try:
                # Try to get unique identifier
                card_id = None
                if hasattr(card, 'get'):
                    card_id = card.get('id') or card.get('data-id') or card.get('data-job-id')
                if not card_id and hasattr(card, 'find'):
                    link = card.find('a')
                    if link:
                        card_id = link.get('href', '')
                
                if card_id and card_id in seen_ids:
                    continue
                if card_id:
                    seen_ids.add(card_id)
                
                unique_cards.append(card)
            except:
                unique_cards.append(card)  # Include anyway if we can't check
        
        logger.info(f"Multi-Approach: Total unique job cards found: {len(unique_cards)}")
        return unique_cards[:500]  # Limit to 500 to avoid too many
    
    @staticmethod
    def extract_job_data_from_element(card, base_url: str, keywords: List[str] = None) -> Optional[Dict]:
        """
        Extract job data from a card element (can be HTML element or JSON-LD dict)
        Returns dict with job_title, job_link, company, etc. or None if invalid
        """
        from urllib.parse import urljoin
        
        job_data = {}
        
        # Handle JSON-LD dict
        if isinstance(card, dict):
            job_title = card.get('title') or card.get('name') or ''
            job_link = card.get('url') or card.get('identifier') or ''
            company = ''
            
            hiring_org = card.get('hiringOrganization') or card.get('hiringorganization')
            if isinstance(hiring_org, dict):
                company = hiring_org.get('name') or ''
                job_data['company_url'] = hiring_org.get('sameAs') or hiring_org.get('url') or ''
            
            if job_title and job_link:
                job_data.update({
                    'job_title': job_title,
                    'job_link': job_link,
                    'company': company or 'Unknown',
                    'location': card.get('jobLocation', {}).get('name') if isinstance(card.get('jobLocation'), dict) else '',
                    'job_description': card.get('description') or '',
                    'posted_date': card.get('datePosted') or '',
                })
                return job_data
            return None
        
        # Handle HTML element
        if not hasattr(card, 'find'):
            return None
        
        # Extract title - try multiple methods
        title_elem = None
        title_selectors = [
            ('h2', {}),
            ('h3', {}),
            ('h1', {}),
            ('a', {'class': lambda x: x and 'title' in ' '.join(x).lower()}),
            ('span', {'class': lambda x: x and 'title' in ' '.join(x).lower()}),
            ('div', {'class': lambda x: x and 'title' in ' '.join(x).lower()}),
        ]
        
        for tag, attrs in title_selectors:
            try:
                found = card.find(tag, attrs)
                if found:
                    title_elem = found
                    break
            except:
                continue
        
        # If card is itself a link, use it
        if not title_elem and card.name == 'a':
            title_elem = card
        
        if not title_elem:
            # Try to get any text from card
            text = card.get_text().strip()
            if len(text) > 10 and len(text) < 200:  # Reasonable title length
                title_elem = type('obj', (object,), {'get_text': lambda: text})()
            else:
                return None
        
        job_title = title_elem.get_text().strip() if hasattr(title_elem, 'get_text') else str(title_elem).strip()
        
        # Skip if title is too short or too long
        if not job_title or len(job_title) < 3 or len(job_title) > 200:
            return None
        
        # ✅ REMOVED STRICT KEYWORD MATCHING - Extract ALL jobs, filter later
        # Don't filter here - let the scraper filter later if needed
        # This ensures we get maximum jobs
        
        # Extract job link
        job_link = ''
        if card.name == 'a':
            href = card.get('href', '')
            if href:
                job_link = urljoin(base_url, href) if not href.startswith('http') else href
        else:
            link_elem = card.find('a')
            if link_elem and link_elem.get('href'):
                href = link_elem['href']
                job_link = urljoin(base_url, href) if not href.startswith('http') else href
        
        if not job_link:
            return None
        
        job_data = {
            'job_title': job_title,
            'job_link': job_link,
            'company': '',  # Will be filled from detail page or inferred
            'location': '',
            'job_description': '',
            'posted_date': None,
        }
        
        # Try to extract company from card
        company_selectors = [
            ('a', {'class': lambda x: x and 'company' in ' '.join(x).lower()}),
            ('span', {'class': lambda x: x and 'company' in ' '.join(x).lower()}),
            ('div', {'class': lambda x: x and 'company' in ' '.join(x).lower()}),
        ]
        
        for tag, attrs in company_selectors:
            try:
                found = card.find(tag, attrs)
                if found:
                    company = found.get_text().strip()
                    if company and len(company) > 1:
                        job_data['company'] = company
                        break
            except:
                continue
        
        return job_data

