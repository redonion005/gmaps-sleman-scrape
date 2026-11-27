#!/usr/bin/env python3
"""
Browser Scraper Helper - executes scrape plan using Hermes browser_exec tool
Run this via: python -m src.browser_scraper_helper [batch_size]
"""

import json
import sys
import os
from pathlib import Path

SCRAPE_PLAN_PATH = Path(__file__).parent.parent / "data" / "pilot" / "scrape_plan.jsonl"
OUTPUT_DIR = Path(__file__).parent.parent / "data" / "pilot"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

def load_scrape_plan():
    tasks = []
    with open(SCRAPE_PLAN_PATH, 'r', encoding='utf-8') as f:
        for line in f:
            tasks.append(json.loads(line.strip()))
    return tasks

def save_results(results, output_file):
    with open(output_file, 'w', encoding='utf-8') as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')

def load_progress(output_file):
    """Load already completed task IDs"""
    completed = set()
    if output_file.exists():
        with open(output_file, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    r = json.loads(line.strip())
                    completed.add(r.get('task_id'))
                except:
                    pass
    return completed


if __name__ == '__main__':
    batch_size = int(sys.argv[1]) if len(sys.argv) > 1 else 100
    
    tasks = load_scrape_plan()
    print(f"Total tasks: {len(tasks)}")
    
    # Process in batches - output the commands for browser_exec
    for i in range(0, len(tasks), batch_size):
        batch = tasks[i:i+batch_size]
        print(f"\nBatch {i//batch_size + 1}: tasks {batch[0]['task_id']}-{batch[-1]['task_id']}")
        
        # Output the batch for manual browser_exec execution
        batch_file = OUTPUT_DIR / f"batch_{i//batch_size + 1:04d}.jsonl"
        with open(batch_file, 'w', encoding='utf-8') as f:
            for task in batch:
                f.write(json.dumps(task, ensure_ascii=False) + '\n')
        
        print(f"  Saved batch to {batch_file}")
    
    print(f"\nTotal batches: {len(tasks) // batch_size + (1 if len(tasks) % batch_size else 0)}")
    print(f"Run browser_exec for each batch file in {OUTPUT_DIR}")