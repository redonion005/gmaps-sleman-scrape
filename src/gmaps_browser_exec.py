#!/usr/bin/env python3
"""
GMaps Scraper - browser_exec version
Real browser automation for Google Maps scraping
"""

# This script runs inside browser_exec tool
# It uses the browser helpers (new_tab, goto_url, js, etc.)

SCRAPE_CODE = '''
import json
import time
from collections import defaultdict

# Load batch file
batch_file = "{{BATCH_FILE}}"
output_file = "{{OUTPUT_FILE}}"

with open(batch_file, 'r', encoding='utf-8') as f:
    tasks = [json.loads(line) for line in f]

# Group by coordinate
tasks_by_point = defaultdict(list)
for task in tasks:
    key = (round(task['lat'], 6), round(task['lng'], 6))
    tasks_by_point[key].append(task)

results = []

# Process each point
for (lat, lng), point_tasks in tasks_by_point.items():
    # Navigate to Google Maps at this coordinate
    search_url = f"https://www.google.com/maps/@{lat},{lng},16z"
    new_tab(search_url)
    wait_for_load()
    time.sleep(2)
    
    # For each query at this point
    for task in point_tasks:
        query = task['query']
        
        try:
            # Find search box and enter query
            search_box = js("""
                const box = document.querySelector('input[aria-label="Search Google Maps"]') 
                    || document.querySelector('input[name="q"]')
                    || document.querySelector('input#searchboxinput');
                return box ? true : false;
            """)
            
            if search_box:
                js(f'''
                    const box = document.querySelector('input[aria-label="Search Google Maps"]') 
                        || document.querySelector('input[name="q"]')
                        || document.querySelector('input#searchboxinput');
                    box.value = "{query.replace('"', '\\"')}";
                    box.dispatchEvent(new Event('input', {{bubbles: true}}));
                    box.dispatchEvent(new KeyboardEvent('keydown', {{key: 'Enter', bubbles: true}}));
                ''')
                time.sleep(3)
                
                # Wait for results to load
                wait_for_load()
                time.sleep(2)
                
                # Extract results
                venues = js('''
                    const results = [];
                    const cards = document.querySelectorAll('[role="article"], .Nv2PK, .hfpxzc');
                    cards.forEach(card => {
                        try {
                            const nameEl = card.querySelector('[aria-label], .qBF1Pd, .fontHeadlineSmall');
                            const name = nameEl ? nameEl.getAttribute('aria-label') || nameEl.textContent : '';
                            
                            const linkEl = card.querySelector('a.hfpxzc, a[href*="/place/"]');
                            const href = linkEl ? linkEl.href : '';
                            
                            const ratingEl = card.querySelector('[role="img"][aria-label*="star"], .MW4etd');
                            const rating = ratingEl ? ratingEl.getAttribute('aria-label') : '';
                            
                            if (name && name.length > 1) {
                                results.push({name: name.trim(), href: href, rating: rating});
                            }
                        } catch (e) {}
                    });
                    return results.slice(0, 20);
                ''')
                
                for v in venues:
                    result = {
                        'task_id': task['task_id'],
                        'corridor_id': task['corridor_id'],
                        'road_name': task['road_name'],
                        'tier': task['tier'],
                        'point_id': task['point_id'],
                        'lat': task['lat'],
                        'lng': task['lng'],
                        'query': query,
                        'category': task['category'],
                        'source': task['source'],
                        'venue_name': v.get('name', ''),
                        'venue_url': v.get('href', ''),
                        'venue_rating': v.get('rating', ''),
                        'status': 'success',
                        'error': None
                    }
                    results.append(result)
                
                print(f"  {query}: {len(venues)} venues")
            else:
                print(f"  Search box not found for {query}")
                results.append({
                    'task_id': task['task_id'],
                    'corridor_id': task['corridor_id'],
                    'road_name': task['road_name'],
                    'tier': task['tier'],
                    'point_id': task['point_id'],
                    'lat': task['lat'],
                    'lng': task['lng'],
                    'query': query,
                    'category': task['category'],
                    'source': task['source'],
                    'venue_name': '',
                    'venue_url': '',
                    'venue_rating': '',
                    'status': 'error',
                    'error': 'Search box not found'
                })
            
            time.sleep(1)  # Rate limiting
            
        except Exception as e:
            print(f"  Error on {query}: {e}")
            results.append({
                'task_id': task['task_id'],
                'corridor_id': task['corridor_id'],
                'road_name': task['road_name'],
                'tier': task['tier'],
                'point_id': task['point_id'],
                'lat': task['lat'],
                'lng': task['lng'],
                'query': query,
                'category': task['category'],
                'source': task['source'],
                'venue_name': '',
                'venue_url': '',
                'venue_rating': '',
                'status': 'error',
                'error': str(e)
            })

# Save results
with open(output_file, 'w', encoding='utf-8') as f:
    for r in results:
        f.write(json.dumps(r, ensure_ascii=False) + '\\n')

print(f"Saved {len(results)} results to {output_file}")
'''

if __name__ == '__main__':
    print(SCRAPE_CODE)