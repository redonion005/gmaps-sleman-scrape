#!/usr/bin/env python3
"""
Browser Scraper Module
Wraps Hermes browser_exec tool for Google Maps scraping
"""

import json
import time
import random
import asyncio
from typing import List, Dict, Optional
from dataclasses import dataclass
from pathlib import Path

from hermes_tools import browser_exec


@dataclass
class SearchResult:
    name: str
    rating: str
    lat: Optional[float]
    lng: Optional[float]
    raw_text: str
    source_query: str
    corridor_id: str
    point_id: str


class BrowserScraper:
    def __init__(self, session_name: str = "gmaps_sweep", config: dict = None):
        self.session_name = session_name
        self.config = config or {}
        self.min_delay = self.config.get('MIN_DELAY_BETWEEN_SEARCHES', 5)
        self.max_delay = self.config.get('MAX_DELAY_BETWEEN_SEARCHES', 10)
        self.scroll_rounds = self.config.get('SCROLL_ROUNDS', 20)
        self.scroll_wait = self.config.get('SCROLL_WAIT', 1.5)
        self.initial_wait = self.config.get('INITIAL_WAIT', 3)
        self.search_zoom = self.config.get('SEARCH_ZOOM', 16)
    
    def build_search_url(self, lat: float, lng: float, query: str) -> str:
        """Build Google Maps search URL"""
        import urllib.parse
        encoded = urllib.parse.quote(query)
        return f"https://www.google.com/maps/search/{encoded}/@{lat},{lng},{self.search_zoom}z"
    
    def _rate_limit(self):
        """Random delay between searches"""
        delay = random.uniform(self.min_delay, self.max_delay)
        time.sleep(delay)
    
    def scrape_search(self, lat: float, lng: float, query: str, corridor_id: str, point_id: str) -> List[SearchResult]:
        """Execute a single search and extract results"""
        url = self.build_search_url(lat, lng, query)
        
        # Build browser automation code
        code = f'''
# Navigate to Google Maps search
goto_url("{url}")
wait_for_load()
time.sleep({self.initial_wait})

# Scroll to load all results
prev = 0
for _ in range({self.scroll_rounds}):
    js("var feed = document.querySelector('[role=feed]'); if (feed) feed.scrollTop = feed.scrollHeight;")
    time.sleep({self.scroll_wait})
    curr = js("document.querySelectorAll('[role=article]').length")
    if curr == prev:
        break
    prev = curr

# Extract
EXTRACT_JS = r\"\"\"
(() => {{
    var articles = document.querySelectorAll('[role=article]');
    var results = [];
    for (var i = 0; i < articles.length; i++) {{
        var article = articles[i];
        var link = article.querySelector('a.hfpxzc') || article.querySelector('a[href*="/maps/place/"]');
        var name = link ? (link.getAttribute('aria-label') || '') : '';
        var href = link ? link.href : '';
        var lat = null, lng = null;
        if (href) {{
            var latMatch = href.match(/!3d(-?[\\d.]+)/);
            var lngMatch = href.match(/!4d(-?[\\d.]+)/);
            if (latMatch) lat = parseFloat(latMatch[1]);
            if (lngMatch) lng = parseFloat(lngMatch[1]);
        }}
        var text = article.textContent || '';
        var ratingMatch = text.match(/(\\d+[,.]\\d)/);
        var rating = ratingMatch ? ratingMatch[1] : '';
        var cleanText = text;
        if (name && text.indexOf(name) === 0) {{
            cleanText = text.substring(name.length);
        }}
        results.push({{name: name, rating: rating, lat: lat, lng: lng, raw_text: cleanText.substring(0, 300)}});
    }}
    return JSON.stringify(results);
}})()
\"\"\"
raw = js(EXTRACT_JS)
print(raw)
'''
        
        self._rate_limit()
        
        try:
            result = browser_exec(code=code, session=self.session_name, timeout_s=120)
            raw_output = result.get('stdout', '').strip()
            
            if not raw_output:
                return []
            
            # Parse JSON array from output
            businesses = json.loads(raw_output)
            
            results = []
            for b in businesses:
                if b.get('name') and b.get('lat') is not None and b.get('lng') is not None:
                    results.append(SearchResult(
                        name=b['name'],
                        rating=b.get('rating', ''),
                        lat=b['lat'],
                        lng=b['lng'],
                        raw_text=b.get('raw_text', ''),
                        source_query=query,
                        corridor_id=corridor_id,
                        point_id=point_id
                    ))
            
            return results
            
        except Exception as e:
            print(f"  ERROR scraping {query} at ({lat}, {lng}): {e}")
            return []
    
    def scrape_batch(self, searches: List[Dict]) -> List[SearchResult]:
        """Scrape multiple searches sequentially"""
        all_results = []
        for search in searches:
            results = self.scrape_search(
                lat=search['lat'],
                lng=search['lng'],
                query=search['query'],
                corridor_id=search['corridor_id'],
                point_id=search['point_id']
            )
            all_results.extend(results)
            print(f"    [{search['point_id']}] {search['query']}: {len(results)} results")
        return all_results


def create_scraper(config_path: str = None) -> BrowserScraper:
    """Factory function to create scraper with config"""
    config = {}
    if config_path:
        import yaml
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
    return BrowserScraper(config=config)