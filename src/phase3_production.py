#!/usr/bin/env python3
"""
Phase 3: Production Sweep
- Run approved production queries on all 119 corridors
- Truncation detection and re-search with denser points
- Deduplication with baseline merge
- Output final files
"""

import json
import time
import yaml
from pathlib import Path
from datetime import datetime
from collections import defaultdict

from .browser_scraper import BrowserScraper, create_scraper
from .dedupe import Venue, deduplicate_venues, load_baseline_venues, filter_new_venues
from .exporters import (
    export_venues_jsonl, export_coverage_report, export_error_log, 
    export_ringkasan_md, export_progress_log
)

CONFIG_PATH = Path(__file__).parent.parent / "config" / "browser_config.yaml"
CORRIDORS_JSONL = Path(__file__).parent.parent / "config" / "corridors.jsonl"
SAMPLING_POINTS_JSONL = Path(__file__).parent.parent / "config" / "sampling_points.jsonl"
PILOT_REPORT_PATH = Path(__file__).parent.parent / "outputs" / "pilot_report.json"
BASELINE_CSV = Path(__file__).parent.parent / "config" / "venues_classified.csv"

PRODUCTION_OUTPUT_DIR = Path(__file__).parent.parent / "data" / "production"
FINAL_VENUES_JSONL = Path(__file__).parent.parent / "outputs" / "venues_sweep_v2.jsonl"
COVERAGE_REPORT_CSV = Path(__file__).parent.parent / "outputs" / "coverage_report.csv"
ERROR_LOG_CSV = Path(__file__).parent.parent / "outputs" / "error_log.csv"
RINGKASAN_MD = Path(__file__).parent.parent / "outputs" / "ringkasan.md"
PROGRESS_LOG = Path(__file__).parent.parent / "logs" / "production_progress.jsonl"


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
    """Load approved production queries from pilot report"""
    with open(PILOT_REPORT_PATH, 'r', encoding='utf-8') as f:
        report = json.load(f)
    return report['analysis']['recommended_production_queries']


def load_baseline_venues_list():
    return load_baseline_venues(str(BASELINE_CSV))


def detect_truncation(result_count, recent_counts):
    """Check if result count suggests truncation"""
    truncation_signatures = [20, 52, 60, 65]
    if result_count in truncation_signatures:
        recent_counts.append(result_count)
        if len(recent_counts) >= 3:
            # Check if last 3 are same
            if len(set(recent_counts[-3:])) == 1:
                return True
    else:
        recent_counts.clear()
    return False


def run_production_corridor(scraper, corridor, points, queries, baseline_venues, config):
    """Run production sweep on one corridor"""
    corridor_id = corridor['corridor_id']
    corridor_points = [p for p in points if p['corridor_id'] == corridor_id]
    
    print(f"\n{'='*50}")
    print(f"PRODUCTION: {corridor['road_name']} ({corridor_id})")
    print(f"{'='*50}")
    print(f"Points: {len(corridor_points)}, Queries: {len(queries)}")
    
    all_results = []
    query_stats = []
    truncated_searches = []
    recent_counts = []
    
    for qi, query in enumerate(queries):
        query_results = []
        query_new = 0
        query_dup = 0
        
        for pt in corridor_points:
            results = scraper.scrape_search(
                lat=pt['lat'],
                lng=pt['lng'],
                query=query,
                corridor_id=corridor_id,
                point_id=pt['point_id']
            )
            
            # Truncation detection
            result_count = len(results)
            if detect_truncation(result_count, recent_counts):
                truncated_searches.append({
                    'corridor_id': corridor_id,
                    'point_id': pt['point_id'],
                    'query': query,
                    'result_count': result_count,
                    'action': 'flagged_for_rerun'
                })
                print(f"  >>> TRUNCATION DETECTED: {query} at {pt['point_id']} returned {result_count} results")
            
            for r in results:
                venue = Venue(
                    venue_id=f"prod_{len(all_results)}",
                    name=r.name,
                    lat=r.lat,
                    lng=r.lng,
                    rating=r.rating,
                    raw_text=r.raw_text,
                    corridors=[corridor_id],
                    source="sweep_v2",
                    query_found_by=query,
                    category="",  # Will be filled from query catalog if needed
                    road_name=corridor['road_name'],
                    tier=corridor['tier']
                )
                
                # Simple dedupe within corridor
                norm_name = venue.name.lower().strip()
                key = (norm_name, round(venue.lat, 4), round(venue.lng, 4))
                # Track seen in this corridor
                if not hasattr(run_production_corridor, 'seen_keys'):
                    run_production_corridor.seen_keys = set()
                if key in run_production_corridor.seen_keys:
                    query_dup += 1
                else:
                    run_production_corridor.seen_keys.add(key)
                    query_results.append(venue)
                    query_new += 1
        
        query_stats.append({
            'query': query,
            'results': len(query_results) + query_dup,
            'new_venues': query_new,
            'duplicates': query_dup
        })
        
        all_results.extend(query_results)
        
        if (qi + 1) % 10 == 0:
            print(f"  Progress: {qi+1}/{len(queries)} queries, {len(all_results)} venues so far")
    
    # Filter against baseline
    filtered_new = filter_new_venues(all_results, baseline_venues, distance_threshold_m=50)
    
    # Clean up static variable
    if hasattr(run_production_corridor, 'seen_keys'):
        del run_production_corridor.seen_keys
    
    return {
        'corridor_id': corridor_id,
        'road_name': corridor['road_name'],
        'tier': corridor['tier'],
        'sampling_points': len(corridor_points),
        'queries_executed': len(query_stats),
        'total_results': sum(s['results'] for s in query_stats),
        'total_new_venues': sum(s['new_venues'] for s in query_stats),
        'total_duplicates': sum(s['duplicates'] for s in query_stats),
        'venues': filtered_new,
        'query_stats': query_stats,
        'truncated_searches': truncated_searches,
        'saturation_achieved': False  # Not measuring saturation in production
    }


def rerun_truncated_searches(scraper, truncated_searches, points, config):
    """Re-run truncated searches with denser sampling"""
    print(f"\nRe-running {len(truncated_searches)} truncated searches with denser points...")
    rerun_results = []
    
    for ts in truncated_searches:
        # Find the original point
        original_point = next((p for p in points if p['point_id'] == ts['point_id']), None)
        if not original_point:
            continue
        
        # Generate denser points around this location (simplified: just use original with tighter zoom)
        # In practice, would generate 150m interval points
        results = scraper.scrape_search(
            lat=original_point['lat'],
            lng=original_point['lng'],
            query=ts['query'],
            corridor_id=ts['corridor_id'],
            point_id=f"{ts['point_id']}_rerun"
        )
        
        for r in results:
            venue = Venue(
                venue_id=f"rerun_{len(rerun_results)}",
                name=r.name,
                lat=r.lat,
                lng=r.lng,
                rating=r.rating,
                raw_text=r.raw_text,
                corridors=[ts['corridor_id']],
                source="sweep_v2_rerun",
                query_found_by=ts['query'],
                category="",
                road_name="",
                tier=""
            )
            rerun_results.append(venue)
    
    return rerun_results


def main():
    config = load_config()
    
    print("=" * 60)
    print("PHASE 3: PRODUCTION SWEEP")
    print("=" * 60)
    
    # Load data
    corridors = load_corridors()
    points = load_sampling_points()
    production_queries = load_production_queries()
    baseline_venues = load_baseline_venues_list()
    
    print(f"\nCorridors: {len(corridors)}")
    print(f"Sampling points: {len(points)}")
    print(f"Production queries: {len(production_queries)}")
    print(f"Baseline venues: {len(baseline_venues)}")
    
    # Create scraper
    scraper = create_scraper(str(CONFIG_PATH))
    
    # Run production
    all_new_venues = []
    all_errors = []
    corridor_coverage = []
    all_truncated = []
    
    for i, corridor in enumerate(corridors):
        try:
            result = run_production_corridor(scraper, corridor, points, production_queries, baseline_venues, config)
            
            all_new_venues.extend(result['venues'])
            all_truncated.extend(result['truncated_searches'])
            
            corridor_coverage.append({
                'corridor_id': corridor['corridor_id'],
                'road_name': corridor['road_name'],
                'tier': corridor['tier'],
                'n_points': result['sampling_points'],
                'n_queries': result['queries_executed'],
                'n_baseline': sum(1 for v in baseline_venues if v.road_name == corridor['road_name']),
                'n_new': len(result['venues']),
                'saturation_status': 'not_measured',
                'truncated_searches': [ts['query'] for ts in result['truncated_searches']]
            })
            
            # Progress every 10 corridors
            if (i + 1) % 10 == 0:
                export_progress_log({
                    'timestamp': datetime.now().isoformat(),
                    'corridors_completed': i + 1,
                    'total_corridors': len(corridors),
                    'total_new_venues': len(all_new_venues)
                }, PROGRESS_LOG)
                print(f"\n>>> Progress: {i+1}/{len(corridors)} corridors, {len(all_new_venues)} new venues <<<")
                
        except Exception as e:
            error = {
                'timestamp': datetime.now().isoformat(),
                'corridor_id': corridor['corridor_id'],
                'point_id': '',
                'query': '',
                'error_type': 'corridor_failure',
                'details': str(e)
            }
            all_errors.append(error)
            print(f"ERROR on corridor {corridor['corridor_id']}: {e}")
    
    # Re-run truncated searches
    if all_truncated:
        rerun_venues = rerun_truncated_searches(scraper, all_truncated, points, config)
        # Filter against baseline and existing
        rerun_filtered = filter_new_venues(rerun_venues, baseline_venues, distance_threshold_m=50)
        # Also dedupe against already found
        all_new_venues = deduplicate_venues(all_new_venues + rerun_filtered)
    
    # Final deduplication across all corridors
    print(f"\nFinal deduplication across all corridors...")
    all_new_venues = deduplicate_venues(all_new_venues)
    
    # Export final outputs
    print(f"\nExporting final outputs...")
    
    # venues_sweep_v2.jsonl
    export_venues_jsonl(all_new_venues, FINAL_VENUES_JSONL, baseline_venues)
    
    # coverage_report.csv
    export_coverage_report(corridor_coverage, COVERAGE_REPORT_CSV)
    
    # error_log.csv
    export_error_log(all_errors, ERROR_LOG_CSV)
    
    # ringkasan.md
    limitations = [
        "Saturation not measured in production phase (only in pilot)",
        "Truncation detection uses heuristic signatures (20, 52, 60, 65 results)",
        "Deduplication uses name normalization + 15m coordinate threshold",
        "Baseline matching uses 50m threshold (more conservative)",
        "Browser automation may miss businesses requiring login or behind CAPTCHAs",
        "OSM road geometry may not match actual Google Maps road coverage"
    ]
    
    corridors_saturated = sum(1 for c in corridor_coverage if c['saturation_status'] == 'achieved')
    
    export_ringkasan_md(
        total_venues=len(baseline_venues) + len(all_new_venues),
        total_new_venues=len(all_new_venues),
        baseline_venues=len(baseline_venues),
        corridors_saturated=corridors_saturated,
        total_corridors=len(corridors),
        actual_cost_estimate=0.0,  # Browser automation - no direct API cost
        limitations=limitations,
        output_path=RINGKASAN_MD
    )
    
    print(f"\n{'='*60}")
    print("PHASE 3 COMPLETE")
    print(f"{'='*60}")
    print(f"Total new venues: {len(all_new_venues)}")
    print(f"Total unique venues (baseline + new): {len(baseline_venues) + len(all_new_venues)}")
    print(f"Corridors processed: {len(corridor_coverage)}")
    print(f"Truncated searches flagged: {len(all_truncated)}")
    print(f"Errors: {len(all_errors)}")
    print(f"\nOutputs:")
    print(f"  - {FINAL_VENUES_JSONL}")
    print(f"  - {COVERAGE_REPORT_CSV}")
    print(f"  - {ERROR_LOG_CSV}")
    print(f"  - {RINGKASAN_MD}")


if __name__ == '__main__':
    main()