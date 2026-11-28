#!/usr/bin/env python3
"""
Container-optimized scraper for GitHub Actions
Uses Playwright directly (no LLM, fast, reliable)
"""

import asyncio
import json
import os
import sys
import time

from playwright.async_api import async_playwright

# Paths (from environment variables, with defaults for local testing)
CHUNK_FILE = os.environ.get('CHUNK_FILE', f"config/full_scrape_plan_2day_chunk_{os.environ.get('CHUNK_ID', '0')}.json")
RESULTS_FILE = os.environ.get('RESULTS_FILE', "data/overnight/results/full_scrape_results.jsonl")
MASTER_PLAN_FILE = os.environ.get('MASTER_PLAN_FILE', "config/full_scrape_plan_2day.json")

# Broad search to capture ALL venue types at location
QUERIES = os.environ.get('QUERIES', 'tempat,wisata,bisnis,layanan,belanja,hiburan,makanan,minuman,olahraga,keagamaan,pendidikan,kesehatan,transportasi,akomodasi').split(',')

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

async def scrape_point(page, pt: dict) -> list:
    point_results = []
    seen_urls = set()

    for query in QUERIES:
        search_url = f"https://www.google.com/maps/search/{query}/@{pt['lat']},{pt['lng']},16z"
        await page.goto(search_url, wait_until='domcontentloaded', timeout=60000)
        await page.wait_for_timeout(3000)

        # Multiple scrolls for broader coverage
        for _ in range(3):
            await page.evaluate("window.scrollBy(0, 3000)")
            await page.wait_for_timeout(2000)

        result = await page.evaluate(EXTRACT_JS)
        venues = json.loads(result) if result else []

        for v in venues:
            # Deduplicate by venue_url
            if v['venue_url'] in seen_urls:
                continue
            seen_urls.add(v['venue_url'])
            
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

        print(f"    {query}: {len(venues)} venues (unique: {len(point_results)})")
        await page.wait_for_timeout(500)

    return point_results


async def main():
    chunk_id = os.environ.get('CHUNK_ID', '0')
    print(f"=== CHUNK {chunk_id} START ===")

    with open(CHUNK_FILE) as f:
        chunk = json.load(f)

    with open(MASTER_PLAN_FILE) as f:
        master_plan = json.load(f)

    master_lookup = {(p['corridor_id'], p['point_id']): i for i, p in enumerate(master_plan)}

    print(f"Points: {len(chunk)} | Queries: {len(QUERIES)}")

    # Ensure results directory exists
    os.makedirs(os.path.dirname(RESULTS_FILE), exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                '--no-sandbox',
                '--disable-dev-shm-usage',
                '--disable-gpu',
                '--disable-blink-features=AutomationControlled',
                '--disable-features=IsolateOrigins,site-per-process',
                '--disable-site-isolation-trials',
            ]
        )
        
        # Anti-detection: realistic context
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            locale='id-ID',
            timezone_id='Asia/Jakarta',
            geolocation={'latitude': -7.8, 'longitude': 110.4},  # Yogyakarta
            permissions=['geolocation'],
        )
        
        # Hide webdriver flag
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            window.chrome = {runtime: {}};
            Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
            Object.defineProperty(navigator, 'languages', {get: () => ['id-ID', 'id', 'en-US', 'en']});
        """)
        
        page = await context.new_page()

        completed = 0
        start_time = time.time()

        for pt in chunk:
            if pt['status'] == 'done':
                completed += 1
                continue

            print(f"  [{completed+1}/{len(chunk)}] {pt['point_id']} - {pt['corridor_id']}")

            venues = await scrape_point(page, pt)

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

            # Random human-like delay between points
            await page.wait_for_timeout(2000 + (hash(str(pt['point_id'])) % 3000))

            if completed % 20 == 0:
                elapsed = time.time() - start_time
                rate = completed / elapsed * 3600
                eta = (len(chunk) - completed) / rate if rate > 0 else 0
                print(f"    Progress: {completed}/{len(chunk)} | {rate:.1f} pts/hr | ETA: {eta:.1f} hrs")

        await context.close()
        await browser.close()

    # Final save
    with open(MASTER_PLAN_FILE, 'w') as f:
        json.dump(master_plan, f, indent=2)

    elapsed = time.time() - start_time
    print(f"=== CHUNK {chunk_id} COMPLETE: {completed} points in {elapsed:.0f}s ===")


if __name__ == "__main__":
    asyncio.run(main())
