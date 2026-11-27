#!/usr/bin/env python3
"""
GMaps Scraper - browser_exec compatible
Processes all queries at one coordinate before moving to next
"""

import json
import sys
import time
from collections import defaultdict


def scrape_tasks(tasks, output_path):
    """
    Scrape all tasks - grouped by coordinate for efficiency
    This function is called from browser_exec
    """
    # Group by coordinate
    tasks_by_point = defaultdict(list)
    for task in tasks:
        key = (round(task['lat'], 6), round(task['lng'], 6))
        tasks_by_point[key].append(task)
    
    results = []
    
    for (lat, lng), point_tasks in tasks_by_point.items():
        # Navigate to this coordinate once
        # Search all queries for this point
        for task in point_tasks:
            query = task['query']
            
            # Simulate search (replace with actual browser automation)
            # This is a placeholder - actual implementation runs in browser_exec
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
                'venues': [],  # Will be filled by browser
                'status': 'pending',
                'error': None
            }
            results.append(result)
    
    # Save results
    with open(output_path, 'w', encoding='utf-8') as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
    
    return results


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("Usage: python gmaps_scraper.py <batch_file> <output_file>")
        sys.exit(1)
    
    batch_file = sys.argv[1]
    output_file = sys.argv[2]
    
    with open(batch_file, 'r', encoding='utf-8') as f:
        tasks = [json.loads(line) for line in f]
    
    scrape_tasks(tasks, output_file)
    print(f"Processed {len(tasks)} tasks -> {output_file}")