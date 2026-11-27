#!/usr/bin/env python3
"""
Container-optimized scraper for GitHub Actions
Runs inside browseruse/browser-use Docker image
Mounts: /data (results), /config (plans)
"""

import asyncio
import json
import os
import sys
import time

from browser_use import Agent, Browser

# Paths (from environment variables, with defaults for local testing)
CHUNK_FILE = os.environ.get('CHUNK_FILE', f"config/full_scrape_plan_2day_chunk_{os.environ.get('CHUNK_ID', '0')}.json")
RESULTS_FILE = os.environ.get('RESULTS_FILE', "data/overnight/results/full_scrape_results.jsonl")
MASTER_PLAN_FILE = os.environ.get('MASTER_PLAN_FILE', "config/full_scrape_plan_2day.json")

# 6 core queries (optimized)
QUERIES = os.environ.get('QUERIES', 'restoran,kafe,kedai kopi,bakery,toko roti,pujasera').split(',')

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
    chunk_id = os.environ.get('CHUNK_ID', '0')
    print(f"=== CHUNK {chunk_id} START ===")

    with open(CHUNK_FILE) as f:
        chunk = json.load(f)

    with open(MASTER_PLAN_FILE) as f:
        master_plan = json.load(f)

    master_lookup = {(p['corridor_id'], p['point_id']): i for i, p in enumerate(master_plan)}

    # Headless browser (already in container)
    browser = Browser(
        headless=True,
        disable_security=True,
        args=['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu']
    )

    print(f"Points: {len(chunk)} | Queries: {len(QUERIES)} | Headless: True")
    completed = 0
    start_time = time.time()

    for pt in chunk:
        if pt['status'] == 'done':
            completed += 1
            continue

        print(f"  [{completed+1}/{len(chunk)}] {pt['point_id']} - {pt['corridor_id']}")

        venues = await scrape_point(browser, pt)

        # Append results (atomic append)
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
        if completed % 20 == 0:
            elapsed = time.time() - start_time
            rate = completed / elapsed * 3600
            eta = (len(chunk) - completed) / rate if rate > 0 else 0
            print(f"    Progress: {completed}/{len(chunk)} | {rate:.1f} pts/hr | ETA: {eta:.1f} hrs")

    await browser.close()

    # Final save
    with open(MASTER_PLAN_FILE, 'w') as f:
        json.dump(master_plan, f, indent=2)

    elapsed = time.time() - start_time
    print(f"=== CHUNK {chunk_id} COMPLETE: {completed} points in {elapsed:.0f}s ===")


if __name__ == "__main__":
    asyncio.run(main())
