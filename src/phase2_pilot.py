#!/usr/bin/env python3
"""
Phase 2: Pilot Execution
- Generate scrape plan for pilot corridors (all 70 queries)
- Analyze pilot results after browser_exec scraping
"""

import json
import sys
import yaml
from pathlib import Path
from datetime import datetime
from collections import defaultdict

CONFIG_PATH = Path(__file__).parent.parent / "config" / "browser_config.yaml"
PILOT_SELECTION_PATH = Path(__file__).parent.parent / "config" / "pilot_selection.json"
SAMPLING_POINTS_JSONL = Path(__file__).parent.parent / "config" / "sampling_points.jsonl"
PILOT_SAMPLING_JSONL = Path(__file__).parent.parent / "config" / "pilot_sampling_points.jsonl"
QUERY_CATALOG_PATH = Path(__file__).parent.parent / "config" / "query_catalog.json"
CORRIDORS_JSONL = Path(__file__).parent.parent / "config" / "corridors.jsonl"
BASELINE_CSV = Path(__file__).parent.parent / "config" / "venues_classified.csv"

PILOT_OUTPUT_DIR = Path(__file__).parent.parent / "data" / "pilot"
PILOT_REPORT_PATH = Path(__file__).parent.parent / "outputs" / "pilot_report.json"
SCRAPE_PLAN_PATH = Path(__file__).parent.parent / "data" / "pilot" / "scrape_plan.jsonl"


def load_config():
    with open(CONFIG_PATH, 'r') as f:
        return yaml.safe_load(f)


def load_pilot_selection():
    with open(PILOT_SELECTION_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_corridors():
    corridors = {}
    with open(CORRIDORS_JSONL, 'r', encoding='utf-8') as f:
        for line in f:
            c = json.loads(line.strip())
            corridors[c['corridor_id']] = c
    return corridors


def load_sampling_points(pilot_corridor_ids):
    """Load sampling points for pilot corridors only - uses reduced pilot sampling"""
    points = []
    with open(PILOT_SAMPLING_JSONL, 'r', encoding='utf-8') as f:
        for line in f:
            pt = json.loads(line.strip())
            if pt['corridor_id'] in pilot_corridor_ids:
                points.append(pt)
    return points


def load_all_queries():
    with open(QUERY_CATALOG_PATH, 'r', encoding='utf-8') as f:
        catalog = json.load(f)
    # Flatten all queries
    all_queries = []
    for cat, queries in catalog['query_categories'].items():
        for q in queries:
            all_queries.append({'category': cat, 'query': q})
    return all_queries


def generate_scrape_plan():
    """Generate scrape plan for browser_exec to execute"""
    pilot_selection = load_pilot_selection()
    pilot_corridors = pilot_selection['pilot_corridors']
    pilot_corridor_ids = [info['corridor_id'] for info in pilot_corridors.values()]
    
    corridors = load_corridors()
    points = load_sampling_points(pilot_corridor_ids)
    all_queries = load_all_queries()
    
    print(f"Pilot corridors: {pilot_corridor_ids}")
    print(f"Total sampling points: {len(points)}")
    print(f"Total queries: {len(all_queries)}")
    
    # Generate scrape tasks
    scrape_tasks = []
    task_id = 0
    
    for corridor_id in pilot_corridor_ids:
        corridor = corridors[corridor_id]
        corridor_points = [p for p in points if p['corridor_id'] == corridor_id]
        
        for pt in corridor_points:
            for qinfo in all_queries:
                task_id += 1
                scrape_tasks.append({
                    'task_id': task_id,
                    'corridor_id': corridor_id,
                    'road_name': corridor['road_name'],
                    'tier': corridor['tier'],
                    'point_id': pt['point_id'],
                    'lat': pt['lat'],
                    'lng': pt['lng'],
                    'query': qinfo['query'],
                    'category': qinfo['category'],
                    'source': 'pilot'
                })
    
    SCRAPE_PLAN_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(SCRAPE_PLAN_PATH, 'w', encoding='utf-8') as f:
        for task in scrape_tasks:
            f.write(json.dumps(task, ensure_ascii=False) + '\n')
    
    print(f"\nGenerated {len(scrape_tasks)} scrape tasks")
    print(f"Saved to {SCRAPE_PLAN_PATH}")
    print(f"\nNow run browser_exec to execute the scrape plan.")
    return scrape_tasks


def analyze_pilot_results():
    """Analyze pilot results after browser_exec scraping"""
    # Find all result files
    result_files = list(PILOT_OUTPUT_DIR.glob("*.jsonl"))
    
    if not result_files:
        print("No pilot results found. Run browser_exec scraping first.")
        return None
    
    print(f"Found {len(result_files)} result files")
    
    # Load and analyze results
    all_results = []
    for rf in result_files:
        with open(rf, 'r', encoding='utf-8') as f:
            for line in f:
                all_results.append(json.loads(line.strip()))
    
    print(f"Total scraped results: {len(all_results)}")
    
    # Aggregate query performance
    query_performance = defaultdict(lambda: {'new': 0, 'total': 0, 'corridors': set()})
    
    for r in all_results:
        q = r.get('query', '')
        query_performance[q]['total'] += 1
        query_performance[q]['corridors'].add(r.get('corridor_id', ''))
        if not r.get('is_duplicate', False):
            query_performance[q]['new'] += 1
    
    # Sort by new venues added
    sorted_queries = sorted(
        query_performance.items(),
        key=lambda x: x[1]['new'],
        reverse=True
    )
    
    # Productive vs zero-yield queries
    productive_queries = [q for q, stats in sorted_queries if stats['new'] > 0]
    zero_yield_queries = [q for q, stats in sorted_queries if stats['new'] == 0]
    
    # Recommend production queries: top 80% of productive queries or min 20
    recommended = productive_queries[:max(20, int(len(productive_queries) * 0.8))]
    
    analysis = {
        'query_performance': {q: {'new_venues': s['new'], 'total_results': s['total'], 'corridors': list(s['corridors'])} for q, s in sorted_queries},
        'productive_queries': productive_queries,
        'zero_yield_queries': zero_yield_queries,
        'recommended_production_queries': recommended,
        'summary': {
            'total_queries_tested': len(sorted_queries),
            'productive_queries': len(productive_queries),
            'zero_yield_queries': len(zero_yield_queries),
            'recommended_count': len(recommended),
            'total_scraped_results': len(all_results)
        }
    }
    
    # Save pilot report
    report = {
        'pilot_corridors': list({r.get('corridor_id') for r in all_results}),
        'analysis': analysis,
        'timestamp': datetime.now().isoformat()
    }
    
    PILOT_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(PILOT_REPORT_PATH, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    
    print(f"\n{'='*60}")
    print("PILOT ANALYSIS COMPLETE")
    print(f"{'='*60}")
    print(f"Total scraped results: {analysis['summary']['total_scraped_results']}")
    print(f"Total queries tested: {analysis['summary']['total_queries_tested']}")
    print(f"Productive queries: {analysis['summary']['productive_queries']}")
    print(f"Zero-yield queries: {analysis['summary']['zero_yield_queries']}")
    print(f"Recommended for production: {analysis['summary']['recommended_count']}")
    print(f"\nTop 10 productive queries:")
    for i, (q, stats) in enumerate(list(analysis['query_performance'].items())[:10]):
        print(f"  {i+1}. {q}: {stats['new_venues']} new venues")
    print(f"\nZero-yield queries ({len(zero_yield_queries)}):")
    for q in zero_yield_queries[:20]:
        print(f"  - {q}")
    if len(zero_yield_queries) > 20:
        print(f"  ... and {len(zero_yield_queries) - 20} more")
    print(f"\nPilot report saved to {PILOT_REPORT_PATH}")
    print(f">>> GATE: Review pilot_report.json and approve recommended query list to proceed to Phase 3 <<<")
    
    return analysis


def main():
    if len(sys.argv) > 1 and sys.argv[1] == 'analyze':
        analyze_pilot_results()
    else:
        generate_scrape_plan()


if __name__ == '__main__':
    main()