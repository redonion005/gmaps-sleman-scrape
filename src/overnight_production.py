#!/usr/bin/env python3
"""
Overnight Production Runner
- Runs top 10 queries on 20 corridors (Tier 1 + top Tier 2)
- 5 sample points per corridor (spread along length)
- Batches: 1 point × 10 queries = 10 searches per browser_exec call
- Total: ~100 browser_exec calls = ~1-2 hours
"""

import json
import yaml
import time
from pathlib import Path
from collections import defaultdict

# Config paths
CONFIG_PATH = Path(__file__).parent.parent / "config" / "browser_config.yaml"
CORRIDORS_JSONL = Path(__file__).parent.parent / "config" / "corridors.jsonl"
SAMPLING_POINTS_JSONL = Path(__file__).parent.parent / "config" / "sampling_points.jsonl"
PILOT_REPORT_PATH = Path(__file__).parent.parent / "outputs" / "pilot_report.json"
BASELINE_CSV = Path(__file__).parent.parent / "config" / "venues_classified.csv"

OUTPUT_DIR = Path(__file__).parent.parent / "data" / "overnight"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

def load_config():
    with open(CONFIG_PATH, 'r') as f:
        return yaml.safe_load(f)

def load_corridors():
    corridors = []
    with open(CORRIDORS_JSONL, 'r', encoding='utf-8') as f:
        for line in f:
            corridors.append(json.loads(line.strip()))
    return corridors

def load_sampling_points():
    points = []
    with open(SAMPLING_POINTS_JSONL, 'r', encoding='utf-8') as f:
        for line in f:
            points.append(json.loads(line.strip()))
    return points

def load_production_queries():
    with open(PILOT_REPORT_PATH, 'r', encoding='utf-8') as f:
        report = json.load(f)
    # Top 10 most productive queries
    return report['analysis']['recommended_production_queries'][:10]

def select_corridors_and_points(corridors, points, max_corridors=20, points_per_corridor=5):
    """Select corridors and sample points for overnight run"""
    # Prioritize Tier 1, then Tier 2 by point count
    tier_order = {'Tier 1': 0, 'Tier 2': 1, 'Tier 3': 2, 'digabung': 3}
    corridors_sorted = sorted(corridors, key=lambda c: (tier_order.get(c['tier'], 99), -len([p for p in points if p['corridor_id'] == c['corridor_id']])))
    
    selected = corridors_sorted[:max_corridors]
    
    # For each corridor, select evenly spaced points
    selected_points = []
    for corridor in selected:
        corridor_points = [p for p in points if p['corridor_id'] == corridor['corridor_id']]
        if len(corridor_points) <= points_per_corridor:
            selected_points.extend(corridor_points)
        else:
            # Evenly sample
            step = len(corridor_points) // points_per_corridor
            sampled = [corridor_points[i * step] for i in range(points_per_corridor)]
            selected_points.extend(sampled)
    
    return selected, selected_points

def generate_batches(selected_corridors, selected_points, queries):
    """Generate batch files for browser_exec execution"""
    batches = []
    
    for corridor in selected_corridors:
        corridor_points = [p for p in selected_points if p['corridor_id'] == corridor['corridor_id']]
        
        for pt in corridor_points:
            batch_tasks = []
            for query in queries:
                batch_tasks.append({
                    'lat': pt['lat'],
                    'lng': pt['lng'],
                    'query': query,
                    'corridor_id': corridor['corridor_id'],
                    'point_id': pt['point_id'],
                    'road_name': corridor['road_name'],
                    'tier': corridor['tier']
                })
            
            batches.append({
                'corridor_id': corridor['corridor_id'],
                'road_name': corridor['road_name'],
                'tier': corridor['tier'],
                'point_id': pt['point_id'],
                'lat': pt['lat'],
                'lng': pt['lng'],
                'tasks': batch_tasks
            })
    
    return batches

def save_batches(batches):
    """Save batches as individual JSON files for browser_exec"""
    batch_files = []
    for i, batch in enumerate(batches):
        batch_file = OUTPUT_DIR / f"batch_{i+1:04d}.json"
        with open(batch_file, 'w', encoding='utf-8') as f:
            json.dump(batch, f, ensure_ascii=False, indent=2)
        batch_files.append(batch_file)
    return batch_files

def main():
    config = load_config()
    corridors = load_corridors()
    points = load_sampling_points()
    queries = load_production_queries()
    
    print(f"Total corridors: {len(corridors)}")
    print(f"Total points: {len(points)}")
    print(f"Production queries (top 10): {queries}")
    
    # Select corridors and points
    selected_corridors, selected_points = select_corridors_and_points(
        corridors, points, max_corridors=20, points_per_corridor=5
    )
    
    print(f"\nSelected {len(selected_corridors)} corridors:")
    for c in selected_corridors:
        c_pts = len([p for p in selected_points if p['corridor_id'] == c['corridor_id']])
        print(f"  {c['corridor_id']} ({c['tier']}): {c['road_name']} - {c_pts} points")
    
    print(f"\nTotal sample points: {len(selected_points)}")
    print(f"Queries per point: {len(queries)}")
    print(f"Total searches: {len(selected_points) * len(queries)}")
    
    # Generate batches
    batches = generate_batches(selected_corridors, selected_points, queries)
    print(f"Total batches (browser_exec calls): {len(batches)}")
    
    # Save batch files
    batch_files = save_batches(batches)
    print(f"Batch files saved to {OUTPUT_DIR}")
    
    # Save manifest
    manifest = {
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
        'config': {
            'max_corridors': 20,
            'points_per_corridor': 5,
            'queries': queries
        },
        'selected_corridors': [c['corridor_id'] for c in selected_corridors],
        'total_batches': len(batches),
        'total_searches': len(selected_points) * len(queries),
        'batch_files': [str(f) for f in batch_files]
    }
    
    manifest_file = OUTPUT_DIR / "manifest.json"
    with open(manifest_file, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    
    print(f"\nManifest saved to {manifest_file}")
    print(f"\nReady to run overnight!")
    print(f"Execute browser_exec for each batch file in {OUTPUT_DIR}")
    
    return batches

if __name__ == '__main__':
    main()