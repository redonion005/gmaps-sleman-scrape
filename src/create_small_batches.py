#!/usr/bin/env python3
"""
Run pilot scraping in small batches via browser_exec
Each batch: 1 point × 10 queries = 10 tasks
"""

import json
from pathlib import Path

SCRAPE_PLAN = Path(__file__).parent.parent / "data" / "pilot" / "scrape_plan.jsonl"
BATCH_DIR = Path(__file__).parent.parent / "data" / "pilot" / "batches_small"
BATCH_DIR.mkdir(parents=True, exist_ok=True)

def create_small_batches(batch_size=10):
    """Create small batches grouped by point"""
    tasks = []
    with open(SCRAPE_PLAN, 'r', encoding='utf-8') as f:
        for line in f:
            tasks.append(json.loads(line.strip()))
    
    # Group by point
    from collections import defaultdict
    tasks_by_point = defaultdict(list)
    for task in tasks:
        key = (round(task['lat'], 6), round(task['lng'], 6))
        tasks_by_point[key].append(task)
    
    # Create batches: split each point's queries into chunks of batch_size
    batch_num = 0
    for (lat, lng), point_tasks in tasks_by_point.items():
        for i in range(0, len(point_tasks), batch_size):
            batch = point_tasks[i:i+batch_size]
            batch_num += 1
            batch_file = BATCH_DIR / f"batch_{batch_num:04d}.jsonl"
            with open(batch_file, 'w', encoding='utf-8') as f:
                for task in batch:
                    f.write(json.dumps(task, ensure_ascii=False) + '\n')
            print(f"Batch {batch_num}: {len(batch)} tasks at ({lat}, {lng})")
    
    print(f"\nTotal small batches: {batch_num}")
    return batch_num

if __name__ == '__main__':
    create_small_batches(10)