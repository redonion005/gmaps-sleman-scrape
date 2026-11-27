
import json, time, os

BASE = r"C:\\Users\\Eromo\\Downloads\\gmaps_sweep_browser"
CHUNK_FILE = BASE + "\\config\\full_scrape_plan_2day_chunk_1.json"
RESULTS_FILE = BASE + "\\data\\overnight\\results\\full_scrape_results.jsonl"
MASTER_PLAN_FILE = BASE + "\\config\\full_scrape_plan.json"

with open(CHUNK_FILE) as f:
    chunk = json.load(f)

# Load master plan for status updates
with open(MASTER_PLAN_FILE) as f:
    master_plan = json.load(f)

# Build lookup for master plan
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

print(f"Chunk {chunk_id}: {len(chunk)} points")
completed = 0

for pt in chunk:
    if pt['status'] == 'done':
        continue
    
    print(f"  [{completed+1}/{len(chunk)}] {pt['point_id']} - {pt['corridor_id']}")
    point_results = []
    
    for q_idx, query in enumerate(queries):
        search_url = f"https://www.google.com/maps/search/{query}/@{pt['lat']},{pt['lng']},16z"
        print(f"    Query {q_idx+1}/10: {query}")
        
        try:
            goto_url(search_url)
            wait_for_load()
            time.sleep(3)
            
            for _ in range(4):
                js("window.scrollBy(0, 2000)")
                time.sleep(1.5)
            
            result = js(EXTRACT_JS)
            venues = json.loads(result) if result else []
            
            for v in venues:
                v.update({
                    'query': query,
                    'corridor_id': pt['corridor_id'],
                    'point_id': pt['point_id'],
                    'road_name': pt['road_name'],
                    'tier': pt['tier'],
                    'scraped_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                    'source': 'browser_full_scrape'
                })
                point_results.append(v)
            
            print(f"      Found {len(venues)} venues")
            
        except Exception as e:
            print(f"      ERROR: {e}")
    
    # Append to results file (thread-safe append)
    with open(RESULTS_FILE, 'a', encoding='utf-8') as f:
        for v in point_results:
            f.write(json.dumps(v, ensure_ascii=False) + '\n')
    
    # Update master plan
    key = (pt['corridor_id'], pt['point_id'])
    if key in master_lookup:
        idx = master_lookup[key]
        master_plan[idx]['status'] = 'done'
        master_plan[idx]['queries_done'] = 10
        master_plan[idx]['venues_found'] = len(point_results)
    
    # Save master plan periodically
    if completed % 5 == 0:
        with open(MASTER_PLAN_FILE, 'w') as f:
            json.dump(master_plan, f, indent=2)
    
    pt['status'] = 'done'
    pt['queries_done'] = 10
    pt['venues_found'] = len(point_results)
    completed += 1
    
    # Small delay between points
    time.sleep(2)

# Final save
with open(MASTER_PLAN_FILE, 'w') as f:
    json.dump(master_plan, f, indent=2)

print(f"Chunk {chunk_id} COMPLETE: {completed} points processed")
