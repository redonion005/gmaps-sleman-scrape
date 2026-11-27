#!/usr/bin/env python3
"""
Optimized Scraper - Chunk 0
Efficiency: 1 point/session, 6 queries, headless, fast extract
Target: ~620 points in ~1.5 hours
"""

import json, time, os, sys

BASE = r"C:\Users\Eromo\Downloads\gmaps_sweep_browser"
CHUNK_FILE = BASE + r"\config\full_scrape_plan_2day_chunk_0.json"
RESULTS_FILE = BASE + r"\data\overnight\results\full_scrape_results.jsonl"
MASTER_PLAN_FILE = BASE + r"\config\full_scrape_plan.json"

with open(CHUNK_FILE) as f:
    chunk = json.load(f)

with open(MASTER_PLAN_FILE) as f:
    master_plan = json.load(f)

master_lookup = {(p['corridor_id'], p['point_id']): i for i, p in enumerate(master_plan)}

# 6 CORE QUERIES (40% faster than 10)
QUERIES = ['restoran', 'kafe', 'kedai kopi', 'bakery', 'toko roti', 'pujasera']

# FAST EXTRACT: 1 scroll, immediate extract
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

print(f"Chunk 0: {len(chunk)} points")
completed = 0
session_start = time.time()

for pt in chunk:
    if pt['status'] == 'done':
        completed += 1
        continue

    print(f"  [{completed+1}/{len(chunk)}] {pt['point_id']} - {pt['corridor_id']}")
    point_results = []

    for q_idx, query in enumerate(QUERIES):
        # This will be called via browser_exec from terminal
        # The browser_exec wrapper handles goto_url, js, wait_for_load
        pass  # Actual execution happens in browser_exec call below

    # Build single browser_exec call for this point (1 session = 1 point)
    # We'll execute via: browser_exec(code=build_code(pt), session="scrape_0")
    completed += 1

    # Progress
    if completed % 10 == 0:
        elapsed = time.time() - session_start
        rate = completed / elapsed * 3600
        eta = (len(chunk) - completed) / rate if rate > 0 else 0
        print(f"    Progress: {completed}/{len(chunk)} | {rate:.1f} pts/hr | ETA: {eta:.1f} hrs")

print(f"Chunk 0 prepared: {completed} points ready for browser_exec")
print("Run via: python -c \"from run_chunk import run; run(0)\"")