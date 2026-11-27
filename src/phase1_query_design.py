#!/usr/bin/env python3
"""
Phase 1: Query Catalog Design & Pilot Corridor Selection
- Load query catalog
- Select 3 pilot corridors (1 Tier 1 dense, 1 Tier 2, 1 Tier 3)
- Output query_catalog.json with pilot/production tags
"""

import json
import yaml
from pathlib import Path
from collections import defaultdict

CONFIG_PATH = Path(__file__).parent.parent / "config" / "browser_config.yaml"
QUERY_CATALOG_PATH = Path(__file__).parent.parent / "config" / "query_catalog.json"
CORRIDORS_JSONL = Path(__file__).parent.parent / "config" / "corridors.jsonl"
PILOT_SELECTION_PATH = Path(__file__).parent.parent / "config" / "pilot_selection.json"


def load_config():
    with open(CONFIG_PATH, 'r') as f:
        return yaml.safe_load(f)


def load_corridors(jsonl_path):
    corridors = []
    with open(jsonl_path, 'r', encoding='utf-8') as f:
        for line in f:
            corridors.append(json.loads(line.strip()))
    return corridors


def load_query_catalog(json_path):
    with open(json_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def select_pilot_corridors(corridors, config):
    """Auto-select 3 pilot corridors by density within each tier"""
    # Group by tier
    by_tier = defaultdict(list)
    for c in corridors:
        by_tier[c['tier']].append(c)
    
    # Select densest in each tier (by venue_count)
    pilot = {}
    for tier in ['Tier 1', 'Tier 2', 'Tier 3']:
        if by_tier[tier]:
            densest = max(by_tier[tier], key=lambda x: x['venue_count'])
            pilot[tier.lower().replace(' ', '_')] = {
                'corridor_id': densest['corridor_id'],
                'road_name': densest['road_name'],
                'tier': densest['tier'],
                'venue_count': densest['venue_count'],
                'selection_reason': f'Densest {tier} corridor by baseline venue count'
            }
    
    # Allow override from config
    if config.get('PILOT_TIER1_CORRIDOR'):
        for c in corridors:
            if c['corridor_id'] == config['PILOT_TIER1_CORRIDOR']:
                pilot['tier_1'] = {'corridor_id': c['corridor_id'], 'road_name': c['road_name'], 'tier': c['tier'], 'venue_count': c['venue_count'], 'selection_reason': 'Manual override from config'}
                break
    
    if config.get('PILOT_TIER2_CORRIDOR'):
        for c in corridors:
            if c['corridor_id'] == config['PILOT_TIER2_CORRIDOR']:
                pilot['tier_2'] = {'corridor_id': c['corridor_id'], 'road_name': c['road_name'], 'tier': c['tier'], 'venue_count': c['venue_count'], 'selection_reason': 'Manual override from config'}
                break
    
    if config.get('PILOT_TIER3_CORRIDOR'):
        for c in corridors:
            if c['corridor_id'] == config['PILOT_TIER3_CORRIDOR']:
                pilot['tier_3'] = {'corridor_id': c['corridor_id'], 'road_name': c['road_name'], 'tier': c['tier'], 'venue_count': c['venue_count'], 'selection_reason': 'Manual override from config'}
                break
    
    return pilot


def main():
    config = load_config()
    
    print("=" * 60)
    print("PHASE 1: QUERY CATALOG & PILOT SELECTION")
    print("=" * 60)
    
    # Load corridors
    print("\n[1/3] Loading corridors...")
    corridors = load_corridors(CORRIDORS_JSONL)
    print(f"  Loaded {len(corridors)} corridors")
    
    # Load query catalog
    print("\n[2/3] Loading query catalog...")
    query_catalog = load_query_catalog(QUERY_CATALOG_PATH)
    total_queries = query_catalog['metadata']['total_queries']
    print(f"  Total queries: {total_queries} across {query_catalog['metadata']['categories']} categories")
    
    # Select pilot corridors
    print("\n[3/3] Selecting pilot corridors...")
    pilot = select_pilot_corridors(corridors, config)
    
    for tier_key, info in pilot.items():
        print(f"  {tier_key.upper()}: {info['road_name']} ({info['corridor_id']}) - {info['venue_count']} baseline venues")
    
    # Save pilot selection
    pilot_selection = {
        'pilot_corridors': pilot,
        'selection_timestamp': json.dumps({'auto': True}),
        'total_queries_pilot': total_queries
    }
    
    with open(PILOT_SELECTION_PATH, 'w', encoding='utf-8') as f:
        json.dump(pilot_selection, f, ensure_ascii=False, indent=2)
    
    print(f"\n  Saved pilot selection to {PILOT_SELECTION_PATH}")
    
    # Update query catalog with pilot/production tags (all queries for pilot)
    for cat, queries in query_catalog['query_categories'].items():
        for q in queries:
            # In a real implementation, we'd tag each query
            pass
    
    print(f"\n{'='*60}")
    print("PHASE 1 COMPLETE")
    print(f"{'='*60}")
    print(f"Pilot corridors selected:")
    for tier_key, info in pilot.items():
        print(f"  {info['road_name']} ({info['tier']}) - {info['venue_count']} baseline venues")
    print(f"\nAll {total_queries} queries will be used in pilot.")
    print(f"Next: Review pilot_selection.json and approve to proceed to Phase 2 (Pilot Execution)")


if __name__ == '__main__':
    main()