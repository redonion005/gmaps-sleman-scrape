#!/usr/bin/env python3
"""
2-Day Orchestrator - Runs 4 browser sessions in pipelined parallel
Uses execute_code to make browser_exec calls with different session names
"""

import json
import time

BASE = r"C:\Users\Eromo\Downloads\gmaps_sweep_browser"

# Load chunks
chunks = []
for i in range(4):
    with open(f"{BASE}\\config\\full_scrape_plan_2day_chunk_{i}.json") as f:
        chunks.append(json.load(f))

print(f"Chunks loaded: {[len(c) for c in chunks]}")

# Load master plan for updates
with open(f"{BASE}\\config\\full_scrape_plan.json") as f:
    master_plan = json.load(f)

master_lookup = {(p['corridor_id'], p['point_id']): i for i, p in enumerate(master_plan)}

queries = ['restoran', 'warung makan', 'rumah makan', 'kafe', 'kedai kopi', 'bakery', 'toko roti', 'toko kue', 'donat', 'pujasera']

EXTRACT_JS = r"""
(() => {
    const articles = document.querySelectorAll('[role=article]');
    const results = [];
    for (const article of articles) {
        const link = article.querySelector('a.hfpxzc') || article.querySelector('a[href*="/maps/place/"]');
        if (!link) continue;
        const name = link.getAttribute('aria-label') || '';
        const href = link.href || '';
        let lat = null, lng = null, place_id = null, cid = null;
        if (href) {
            const latMatch = href.match(/!3d(-?[\d.]+)/);
            const lngMatch = href.match(/!4d(-?[\d.]+)/);
            const placeMatch = href.match(/19s(ChIJ[^!&?]+)/);
            const cidMatch = href.match(/1s0x[^:]+:0x([0-9a-f]+)/);
            if (latMatch) lat = parseFloat(latMatch[1]);
            if (lngMatch) lng = parseFloat(lngMatch[1]);
            if (placeMatch) place_id = placeMatch[1];
            if (cidMatch) cid = cidMatch[1];
        }
        if (lat === null || lng === null) continue;
        const text = article.textContent || '';
        const ratingMatch = text.match(/(\d+[,.]\d)/);
        const rating = ratingMatch ? ratingMatch[1].replace(',', '.') : '';
        results.push({name, venue_url: href, place_id, cid, rating: rating ? parseFloat(rating) : null, rating_raw: ratingMatch ? ratingMatch[1] : '', lat, lng});
    }
    return JSON.stringify(results);
})()
"""

# Session names for 4 parallel browsers
SESSIONS = ['scrape_0', 'scrape_1', 'scrape_2', 'scrape_3']

# Build work queue: each item is (chunk_idx, point_idx_in_chunk)
work_queue = []
for chunk_idx, chunk in enumerate(chunks):
    for pt_idx, pt in enumerate(chunk):
        if pt['status'] != 'done':
            work_queue.append((chunk_idx, pt_idx))

print(f"Total pending points: {len(work_queue)}")

# Process in round-robin across 4 sessions
# Each browser_exec call handles 1 point (10 queries)
# We'll pipeline: launch session 0, then session 1, etc., then wait for results

def build_browser_code(session_name, pt, q_start=0, q_end=10):
    """Build browser_exec code for a point"""
    code = f'''# Session {session_name}: {pt['point_id']} queries {q_start}-{q_end}
import time
import json

goto_url("https://www.google.com/maps")
wait_for_load()
time.sleep(2)

point_results = []
for q_idx in range({q_start}, {q_end}):
    query = "{queries[q_start]}".replace("'", "\\\\'") if q_start < 10 else ""
    if q_idx >= len({queries}):
        break
    query = {queries}[q_idx]
    search_url = f"https://www.google.com/maps/search/{{query}}/@{{pt['lat']}},{{pt['lng']}},16z"
    goto_url(search_url)
    wait_for_load()
    time.sleep(3)
    for _ in range(4):
        js("window.scrollBy(0, 2000)")
        time.sleep(1.5)
    result = js("""{EXTRACT_JS}""")
    venues = json.loads(result) if result else []
    for v in venues:
        v.update({{
            'query': query,
            'corridor_id': '{pt['corridor_id']}',
            'point_id': '{pt['point_id']}',
            'road_name': '{pt['road_name']}',
            'tier': '{pt['tier']}',
            'scraped_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            'source': 'browser_full_scrape'
        }})
        point_results.append(v)
    time.sleep(1)

print(json.dumps({{'venues': point_results, 'point_id': '{pt['point_id']}', 'session': '{session_name}'}}))
'''
    return code

# For now, just print the plan - we'll run via execute_code in batches
print("\n=== EXECUTION PLAN ===")
print(f"Total points: {len(work_queue)}")
print(f"4 sessions: {SESSIONS}")
print(f"Estimated time: {len(work_queue) * 2.5 / 4 / 60:.1f} hours")

# Save work queue for execute_code to process
with open(f"{BASE}\\config\\work_queue.json", 'w') as f:
    json.dump(work_queue, f)

print("\nWork queue saved. Ready for execute_code orchestration.")