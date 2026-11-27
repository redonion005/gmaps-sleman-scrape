#!/usr/bin/env python3
"""
Robust batch processor for browser_exec
Processes many queries in one browser session with tab recycling
"""

import json
import urllib.parse
import time
from pathlib import Path
from collections import defaultdict

BATCH_DIR = Path(__file__).parent.parent / "data" / "pilot" / "batches_small"
RESULTS_DIR = Path(__file__).parent.parent / "data" / "pilot" / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

def get_batch_files():
    """Get sorted list of batch files"""
    return sorted(BATCH_DIR.glob("batch_*.jsonl"))

def process_batches_in_browser(start_idx, count, session_name="pilot_run"):
    """Generate code for browser_exec to process N batches"""
    batch_files = get_batch_files()[start_idx:start_idx+count]
    
    # Load all tasks
    all_tasks = []
    for bf in batch_files:
        with open(bf, 'r', encoding='utf-8') as f:
            for line in f:
                all_tasks.append(json.loads(line.strip()))
    
    # Group by coordinate
    tasks_by_point = defaultdict(list)
    for task in all_tasks:
        key = (round(task['lat'], 6), round(task['lng'], 6))
        tasks_by_point[key].append(task)
    
    # Generate browser code
    code = f'''# Process {len(all_tasks)} tasks across {len(tasks_by_point)} points
import json
import time
import urllib.parse
from collections import defaultdict

tasks_by_point = {json.dumps({f"{k[0]},{k[1]}": v for k, v in tasks_by_point.items()}, ensure_ascii=False)}

results = []
total_points = len(tasks_by_point)
queries_done = 0
TAB_RECYCLE_EVERY = 20

for point_idx, (point_key, point_tasks) in enumerate(tasks_by_point.items()):
    lat, lng = map(float, point_key.split(','))
    print(f"Point {{point_idx+1}}/{{total_points}}: {{lat}}, {{lng}} ({{len(point_tasks)}} queries)")
    
    # Open new tab for this point
    base_url = f"https://www.google.com/maps/@{{lat}},{{lng}},16z"
    new_tab(base_url)
    wait_for_load()
    time.sleep(2)
    
    for task in point_tasks:
        query = task['query']
        encoded_query = urllib.parse.quote(query)
        search_url = f"https://www.google.com/maps/search/{{encoded_query}}/@{{lat}},{{lng}},16z"
        
        try:
            goto_url(search_url)
            wait_for_load()
            time.sleep(2.5)
            
            venues = js("""
                const results = [];
                const links = document.querySelectorAll('a[href*="/place/"]');
                links.forEach(link => {{
                    try {{
                        const name = link.getAttribute('aria-label') || link.textContent?.trim();
                        const href = link.href;
                        if (name && name.length > 1 && name.length < 200) {{
                            results.push({{name: name, href: href}});
                        }}
                    }} catch (e) {{}}
                }});
                return results.slice(0, 20);
            """)
            
            for v in venues:
                results.append({{
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
                    'venue_rating': '',
                    'status': 'success',
                    'error': None
                }})
            
            print(f"  {{query}}: {{len(venues)}} venues")
            
        except Exception as e:
            print(f"  Error on {{query}}: {{e}}")
            results.append({{
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
            }})
        
        queries_done += 1
        
        # Recycle tab periodically to prevent crash
        if queries_done % TAB_RECYCLE_EVERY == 0:
            print(f"  Recycling tab at query {{queries_done}}")
            # Close current tab by opening a new one
            new_tab("about:blank")
            wait_for_load()
            time.sleep(1)
            base_url = f"https://www.google.com/maps/@{{lat}},{{lng}},16z"
            new_tab(base_url)
            wait_for_load()
            time.sleep(2)
        
        time.sleep(1.5)

# Save results
output_file = f"C:\\\\Users\\\\Eromo\\\\Downloads\\\\gmaps_sweep_browser\\\\data\\\\pilot\\\\results\\\\results_{{start_idx}}_{{count}}.jsonl"
with open(output_file, 'w', encoding='utf-8') as f:
    for r in results:
        f.write(json.dumps(r, ensure_ascii=False) + '\\n')

print(f"\\nSaved {{len(results)}} results to {{output_file}}")
'''
    return code

if __name__ == '__main__':
    # Test: first 50 batches
    code = process_batches_in_browser(0, 50)
    print(f"Generated code length: {len(code)} chars")
    print("First 2000 chars:")
    print(code[:2000])