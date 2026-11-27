#!/usr/bin/env python3
"""
Full corridor scrape - runs 1 point per session, checkpoints after each.
Usage: python scrape_all_points.py [point_index]
"""
import json, time, sys, os

# Load plan
PLAN_PATH = r"C:\Users\Eromo\Downloads\gmaps_sweep_browser\config\full_scrape_plan.json"
OUTPUT_PATH = r"C:\Users\Eromo\Downloads\gmaps_sweep_browser\data\overnight\results\full_scrape_results.jsonl"

with open(PLAN_PATH, 'r', encoding='utf-8') as f:
    plan = json.load(f)

# Find next pending point
start_idx = int(sys.argv[1]) if len(sys.argv) > 1 else 0
point = None
for i, p in enumerate(plan):
    if i >= start_idx and p['status'] == 'pending':
        point = p
        point_idx = i
        break

if not point:
    print("All points completed!")
    sys.exit(0)

print(f"Scraping point {point_idx+1}/{len(plan)}: {point['point_id']}")

# This script is imported by browser_exec - the actual browser code runs in browser_exec
# We just print the point info for the browser script to use
print(json.dumps({'point': point, 'point_idx': point_idx, 'total': len(plan)}))