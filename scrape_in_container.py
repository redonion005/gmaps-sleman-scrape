#!/usr/bin/env python3
"""
Container-optimized scraper for GitHub Actions
Uses browser-use 1.0 Agent API
"""

import asyncio
import json
import os
import re
import sys
import time

from browser_use import Agent
from langchain_openai import ChatOpenAI

# Paths (from environment variables, with defaults for local testing)
CHUNK_FILE = os.environ.get('CHUNK_FILE', f"config/full_scrape_plan_2day_chunk_{os.environ.get('CHUNK_ID', '0')}.json")
RESULTS_FILE = os.environ.get('RESULTS_FILE', "data/overnight/results/full_scrape_results.jsonl")
MASTER_PLAN_FILE = os.environ.get('MASTER_PLAN_FILE', "config/full_scrape_plan_2day.json")

# 6 core queries (optimized)
QUERIES = os.environ.get('QUERIES', 'restoran,kafe,kedai kopi,bakery,toko roti,pujasera').split(',')

# Use a dummy LLM - we'll use the agent's built-in extraction
llm = ChatOpenAI(model="gpt-4o-mini", api_key=os.environ.get("OPENAI_API_KEY", "dummy"))

async def scrape_point(pt: dict) -> list:
    point_results = []

    for query in QUERIES:
        search_url = f"https://www.google.com/maps/search/{query}/@{pt['lat']},{pt['lng']},16z"
        
        task = f"""
        Go to {search_url}
        Wait for the map results to load completely
        Scroll down once to load more listings
        Extract all business listings from the page as JSON with these fields:
        name, venue_url, place_id, cid, lat, lng, rating
        Return ONLY a JSON array of objects.
        """
        
        agent = Agent(
            task=task,
            llm=llm,
        )
        
        try:
            result = await agent.run()
            # Parse result - extract JSON array
            venues = []
            if result:
                json_match = re.search(r'\[.*\]', str(result), re.DOTALL)
                if json_match:
                    venues = json.loads(json_match.group())
            
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
            
        except Exception as e:
            print(f"    ERROR {query}: {e}")
        
        await asyncio.sleep(1)  # Rate limiting

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
    completed = 0
    start_time = time.time()

    for pt in chunk:
        if pt['status'] == 'done':
            completed += 1
            continue

        print(f"  [{completed+1}/{len(chunk)}] {pt['point_id']} - {pt['corridor_id']}")

        venues = await scrape_point(pt)

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

    # Final save
    with open(MASTER_PLAN_FILE, 'w') as f:
        json.dump(master_plan, f, indent=2)

    elapsed = time.time() - start_time
    print(f"=== CHUNK {chunk_id} COMPLETE: {completed} points in {elapsed:.0f}s ===")


if __name__ == "__main__":
    asyncio.run(main())
