#!/usr/bin/env python3
"""
Standalone Optimized Scraper - Chunk 3
Runs directly via browser-use (no Hermes needed)
Usage: python scrape_chunk_3.py
"""

import asyncio
import json
import os
import sys
import time

# Add browser-use to path
sys.path.insert(0, os.path.expanduser("~/.local/lib/python3.11/site-packages"))

from browser_use import Agent, Browser, BrowserConfig
from browser_use.browser.context import BrowserContextConfig

BASE = r"C:\Users\Eromo\Downloads\gmaps_sweep_browser"
CHUNK_FILE = os.path.join(BASE, "config", "full_scrape_plan_2day_chunk_3.json")
RESULTS_FILE = os.path.join(BASE, "data", "overnight", "results", "full_scrape_results.jsonl")
MASTER_PLAN_FILE = os.path.join(BASE, "config", "full_scrape_plan.json")

QUERIES = ['restoran', 'kafe', 'kedai kopi', 'bakery', 'toko roti', 'pujasera']

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

async def scrape_point(browser: Browser, pt: dict) -> list:
    """Scrape one point (6 queries) in a single browser context"""
    context = await browser.new_context()
    page = await context.new_page()
    point_results = []

    try:
        for query in QUERIES:
            search_url = f"https://www.google.com/maps/search/{query}/@{pt['lat']},{pt['lng']},16z"
            await page.goto(search_url, wait_until='networkidle', timeout=30000)
            await page.wait_for_timeout(2000)

            # Fast extract: 1 scroll
            await page.evaluate("window.scrollBy(0, 3000)")
            await page.wait_for_timeout(1500)

            result = await page.evaluate(EXTRACT_JS)
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

            print(f"    {query}: {len(venues)} venues")
            await page.wait_for_timeout(500)

    except Exception as e:
        print(f"    ERROR: {e}")
    finally:
        await context.close()

    return point_results


async def main():
    with open(CHUNK_FILE) as f:
        chunk = json.load(f)

    with open(MASTER_PLAN_FILE) as f:
        master_plan = json.load(f)

    master_lookup = {(p['corridor_id'], p['point_id']): i for i, p in enumerate(master_plan)}

    # Headless browser config (2x density)
    browser = Browser(config=BrowserConfig(
        headless=True,  # HEADLESS = 2x faster
        disable_security=True,
        args=['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu']
    ))

    print(f"Chunk 3: {len(chunk)} points | Headless mode | 6 queries/point")
    completed = 0
    start_time = time.time()

    for pt in chunk:
        if pt['status'] == 'done':
            completed += 1
            continue

        print(f"  [{completed+1}/{len(chunk)}] {pt['point_id']} - {pt['corridor_id']}")

        venues = await scrape_point(browser, pt)

        # Append results (thread-safe)
        with open(RESULTS_FILE, 'a', encoding='utf-8') as f:
            for v in venues:
                f.write(json.dumps(v, ensure_ascii=False) + '\n')

        # Update master plan
        key = (pt['corridor_id'], pt['point_id'])
        if key in master_lookup:
            idx = master_lookup[key]
            master_plan[idx]['status'] = 'done'
            master_plan[idx]['queries_done'] = len(QUERIES)
            master_plan[idx]['venues_found'] = len(venues)

        if completed % 5 == 0:
            with open(MASTER_PLAN_FILE, 'w') as f:
                json.dump(master_plan, f, indent=2)

        pt['status'] = 'done'
        pt['queries_done'] = len(QUERIES)
        pt['venues_found'] = len(venues)
        completed += 1

        # Progress
        if completed % 10 == 0:
            elapsed = time.time() - start_time
            rate = completed / elapsed * 3600
            eta = (len(chunk) - completed) / rate if rate > 0 else 0
            print(f"    Progress: {completed}/{len(chunk)} | {rate:.1f} pts/hr | ETA: {eta:.1f} hrs")

    await browser.close()

    # Final save
    with open(MASTER_PLAN_FILE, 'w') as f:
        json.dump(master_plan, f, indent=2)

    print(f"Chunk 3 COMPLETE: {completed} points, {time.time()-start_time:.0f}s")


if __name__ == "__main__":
    asyncio.run(main())