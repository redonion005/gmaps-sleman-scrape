#!/usr/bin/env python3
"""
Phase 0: Corridor Mapping
- Load 119 corridors from gmaps_road_results_all.jsonl
- Fetch road geometry from OSM Overpass (bulk query with timeout)
- Generate sampling points every 300m + baseline venues within 400m
- Fallback: approximate geometry from baseline venue coordinates
"""

import json
import os
import re
import time
from pathlib import Path
from collections import defaultdict

import overpy
import yaml
from shapely.geometry import LineString, Point
from shapely.ops import transform
import pyproj
from tqdm import tqdm

CONFIG_PATH = Path(__file__).parent.parent / "config" / "browser_config.yaml"
CORRIDORS_JSONL = Path(__file__).parent.parent / "config" / "corridors.jsonl"
SAMPLING_POINTS_JSONL = Path(__file__).parent.parent / "config" / "sampling_points.jsonl"
CORRIDOR_GEOJSON = Path(__file__).parent.parent / "config" / "corridors.geojson"
CORRIDOR_POINT_COUNTS = Path(__file__).parent.parent / "config" / "corridor_point_counts.csv"


def load_config():
    with open(CONFIG_PATH, 'r') as f:
        return yaml.safe_load(f)


def load_corridors_from_jsonl(jsonl_path):
    """Extract unique corridors from gmaps_road_results_all.jsonl"""
    corridors = {}
    with open(jsonl_path, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                rec = json.loads(line.strip())
                road_no = rec.get('road_no')
                road_name = rec.get('road_name')
                tier = rec.get('tier')
                key = (road_no, road_name, tier)
                if key not in corridors:
                    corridors[key] = {
                        'road_no': road_no,
                        'road_name': road_name,
                        'tier': tier,
                        'categories': set(),
                        'venue_count': 0
                    }
                corridors[key]['categories'].add(rec.get('category'))
                corridors[key]['venue_count'] += 1
            except:
                pass

    # Convert to list sorted by road_no
    corridor_list = []
    for (road_no, road_name, tier), info in sorted(corridors.items(), key=lambda x: x[0][0]):
        corridor_list.append({
            'road_no': road_no,
            'road_name': road_name,
            'tier': tier,
            'categories': sorted(info['categories']),
            'venue_count': info['venue_count'],
            'corridor_id': f"R{road_no:03d}_{road_name.replace(' ', '_')}"
        })

    return corridor_list


def save_corridors_jsonl(corridors, output_path):
    with open(output_path, 'w', encoding='utf-8') as f:
        for c in corridors:
            f.write(json.dumps(c, ensure_ascii=False) + '\n')


def fetch_all_roads_bulk():
    """Fetch ALL highways in Yogyakarta area - DISABLED due to Overpass API issues"""
    print("  Skipping Overpass API (406/429/timeout errors)")
    return {}


def match_road_to_corridor(road_name, all_roads, corridor_name):
    """Match a corridor name to the best OSM road - always returns None since Overpass disabled"""
    return None


def approximate_geometry_from_baseline(baseline_points):
    """Fallback: create approximate line from baseline venue coordinates"""
    if len(baseline_points) < 2:
        return None

    # Sort points by position along the corridor
    # Use the first coordinate as reference and sort by projection
    pts = [(v['lng'], v['lat']) for v in baseline_points]
    
    try:
        # Fit a line through points using simple approach
        # Sort by latitude (north-south) or longitude (east-west) based on spread
        lats = [p[1] for p in pts]
        lngs = [p[0] for p in pts]
        
        lat_spread = max(lats) - min(lats)
        lng_spread = max(lngs) - min(lngs)
        
        if lng_spread > lat_spread:
            # East-west corridor, sort by longitude
            pts.sort(key=lambda p: p[0])
        else:
            # North-south corridor, sort by latitude
            pts.sort(key=lambda p: p[1])
        
        line = LineString(pts)
        return line
    except:
        return None


def simplify_geometry(line, tolerance=0.0001):
    """Simplify linestring to ~10m tolerance"""
    return line.simplify(tolerance, preserve_topology=True)


def generate_sampling_points(line, interval_m=300, baseline_points=None, buffer_m=400):
    """Generate sampling points along line at interval_m meters"""
    # Project to UTM for accurate distance
    project = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:32749", always_xy=True).transform
    line_utm = transform(project, line)

    points = []
    length = line_utm.length
    num_points = max(2, int(length / interval_m) + 1)

    for i in range(num_points):
        dist = min(i * interval_m, length)
        pt_utm = line_utm.interpolate(dist)
        # Transform back to WGS84
        inv_project = pyproj.Transformer.from_crs("EPSG:32749", "EPSG:4326", always_xy=True).transform
        pt_wgs = transform(inv_project, pt_utm)
        points.append({
            'lat': pt_wgs.y,
            'lng': pt_wgs.x,
            'source': 'interval',
            'distance_along_m': dist
        })

    # Add baseline venue points within buffer
    if baseline_points:
        line_buffer = line.buffer(buffer_m / 111000)  # rough degree conversion
        for bp in baseline_points:
            pt = Point(bp['lng'], bp['lat'])
            if line_buffer.contains(pt):
                # Check if not too close to existing points
                too_close = False
                for ep in points:
                    ep_pt = Point(ep['lng'], ep['lat'])
                    if pt.distance(ep_pt) * 111000 < 50:  # 50m dedupe
                        too_close = True
                        break
                if not too_close:
                    points.append({
                        'lat': bp['lat'],
                        'lng': bp['lng'],
                        'source': 'baseline',
                        'distance_along_m': None
                    })

    return points


def load_baseline_venues(csv_path):
    """Load baseline venues from CSV"""
    import pandas as pd
    df = pd.read_csv(csv_path)
    venues = []
    for _, row in df.iterrows():
        try:
            # road_names is pipe-separated list
            road_names = [r.strip() for r in str(row.get('road_names', '')).split('|')]
            for rn in road_names:
                venues.append({
                    'name': row.get('name', ''),
                    'lat': float(row['lat']),
                    'lng': float(row['lng']),
                    'category': row.get('category', ''),
                    'road_name': rn
                })
        except:
            pass
    return venues


def main():
    config = load_config()

    print("=" * 60)
    print("PHASE 0: CORRIDOR MAPPING")
    print("=" * 60)

    # Step 1: Load corridors
    print("\n[1/4] Loading corridors from JSONL...")
    corridors = load_corridors_from_jsonl(config['CORRIDORS_JSONL'])
    print(f"  Found {len(corridors)} unique corridors")

    # Save corridors JSONL
    save_corridors_jsonl(corridors, CORRIDORS_JSONL)
    print(f"  Saved to {CORRIDORS_JSONL}")

    # Step 2: Load baseline venues
    print("\n[2/4] Loading baseline venues...")
    baseline_venues = load_baseline_venues(config['BASELINE_CSV'])
    print(f"  Loaded {len(baseline_venues)} baseline venues")

    # Group baseline by road_name for faster lookup
    baseline_by_road = defaultdict(list)
    for v in baseline_venues:
        baseline_by_road[v['road_name']].append(v)

    # Step 3: Fetch ALL road geometries in ONE bulk query
    print("\n[3/4] Fetching road geometries (bulk query)...")
    all_osm_roads = fetch_all_roads_bulk()
    print(f"  Found {len(all_osm_roads)} named roads in OSM")

    geojson_features = []
    all_sampling_points = []
    corridor_point_counts = []

    for corridor in tqdm(corridors, desc="Corridors"):
        road_name = corridor['road_name']

        # Match to OSM road
        line = match_road_to_corridor(road_name, all_osm_roads, road_name)
        geometry_source = 'osm'

        # Fallback: approximate from baseline venues
        if line is None:
            baseline_for_road = baseline_by_road.get(road_name, [])
            if len(baseline_for_road) >= 2:
                line = approximate_geometry_from_baseline(baseline_for_road)
                geometry_source = 'baseline_approx'

        if line is None:
            print(f"    WARNING: No geometry for {road_name}")
            corridor['geometry'] = None
            corridor['geometry_status'] = 'failed'
            corridor_point_counts.append({
                'corridor_id': corridor['corridor_id'],
                'road_name': road_name,
                'tier': corridor['tier'],
                'n_interval_points': 0,
                'n_baseline_points': 0,
                'total_points': 0,
                'geometry_status': 'failed',
                'geometry_source': 'none'
            })
            continue

        # Simplify
        line = simplify_geometry(line)
        corridor['geometry'] = line.__geo_interface__
        corridor['geometry_status'] = 'success'

        # Generate sampling points
        baseline_for_road = baseline_by_road.get(road_name, [])
        points = generate_sampling_points(
            line,
            interval_m=config['SAMPLING_INTERVAL_M'],
            baseline_points=baseline_for_road,
            buffer_m=config['BASELINE_BUFFER_M']
        )

        # Assign point IDs and corridor reference
        interval_count = sum(1 for p in points if p['source'] == 'interval')
        baseline_count = sum(1 for p in points if p['source'] == 'baseline')

        for i, pt in enumerate(points):
            pt['corridor_id'] = corridor['corridor_id']
            pt['road_name'] = road_name
            pt['tier'] = corridor['tier']
            pt['point_id'] = f"{corridor['corridor_id']}_P{i:04d}"
            all_sampling_points.append(pt)

        corridor_point_counts.append({
            'corridor_id': corridor['corridor_id'],
            'road_name': road_name,
            'tier': corridor['tier'],
            'n_interval_points': interval_count,
            'n_baseline_points': baseline_count,
            'total_points': len(points),
            'geometry_status': 'success',
            'geometry_source': geometry_source
        })

        # Add to GeoJSON
        geojson_features.append({
            'type': 'Feature',
            'geometry': line.__geo_interface__,
            'properties': {
                'corridor_id': corridor['corridor_id'],
                'road_name': road_name,
                'tier': corridor['tier'],
                'venue_count': corridor['venue_count'],
                'geometry_source': geometry_source
            }
        })

    # Step 4: Save outputs
    print("\n[4/4] Saving outputs...")

    # Sampling points JSONL
    with open(SAMPLING_POINTS_JSONL, 'w', encoding='utf-8') as f:
        for pt in all_sampling_points:
            f.write(json.dumps(pt, ensure_ascii=False) + '\n')
    print(f"  Sampling points: {SAMPLING_POINTS_JSONL} ({len(all_sampling_points)} points)")

    # Corridor GeoJSON
    geojson = {'type': 'FeatureCollection', 'features': geojson_features}
    with open(CORRIDOR_GEOJSON, 'w', encoding='utf-8') as f:
        json.dump(geojson, f, ensure_ascii=False)
    print(f"  Corridor geometries: {CORRIDOR_GEOJSON}")

    # Corridor point counts CSV
    import pandas as pd
    df_counts = pd.DataFrame(corridor_point_counts)
    df_counts.to_csv(CORRIDOR_POINT_COUNTS, index=False)
    print(f"  Point counts: {CORRIDOR_POINT_COUNTS}")

    # Summary
    total_interval = sum(c['n_interval_points'] for c in corridor_point_counts)
    total_baseline = sum(c['n_baseline_points'] for c in corridor_point_counts)
    osm_count = sum(1 for c in corridor_point_counts if c['geometry_source'] == 'osm')
    approx_count = sum(1 for c in corridor_point_counts if c['geometry_source'] == 'baseline_approx')

    print(f"\n{'='*60}")
    print("PHASE 0 COMPLETE")
    print(f"{'='*60}")
    print(f"Total corridors: {len(corridors)}")
    print(f"Total sampling points: {len(all_sampling_points)}")
    print(f"  - Interval points: {total_interval}")
    print(f"  - Baseline points: {total_baseline}")
    print(f"Corridors with OSM geometry: {osm_count}")
    print(f"Corridors with baseline approximation: {approx_count}")
    print(f"Corridors missing geometry: {sum(1 for c in corridor_point_counts if c['geometry_status'] == 'failed')}")
    print(f"\nNext: Review corridor_point_counts.csv and approve to proceed to Phase 1")


if __name__ == '__main__':
    main()