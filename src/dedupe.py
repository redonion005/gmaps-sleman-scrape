#!/usr/bin/env python3
"""
Deduplication Module
Normalizes names and deduplicates by name + 15m coordinate threshold
"""

import re
import math
from typing import List, Dict, Optional
from dataclasses import dataclass, field


@dataclass
class Venue:
    venue_id: str
    name: str
    lat: float
    lng: float
    rating: str = ""
    raw_text: str = ""
    corridors: List[str] = field(default_factory=list)
    source: str = "unknown"
    query_found_by: str = ""
    category: str = ""
    road_name: str = ""
    tier: str = ""


def normalize_name(name: str) -> str:
    """Normalize venue name for comparison"""
    if not name:
        return ""
    # Lowercase, remove non-alphanumeric, collapse whitespace
    normalized = re.sub(r'[^a-z0-9\s]', '', name.lower())
    normalized = re.sub(r'\s+', ' ', normalized).strip()
    return normalized


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance in meters between two points"""
    R = 6371000  # Earth radius in meters
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    
    a = math.sin(dphi/2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c


def is_duplicate(v1: Venue, v2: Venue, name_threshold: float = 0.9, distance_threshold_m: float = 15) -> bool:
    """Check if two venues are duplicates"""
    # Name similarity (exact match after normalization)
    n1 = normalize_name(v1.name)
    n2 = normalize_name(v2.name)
    if n1 != n2:
        return False
    
    # Distance check
    dist = haversine(v1.lat, v1.lng, v2.lat, v2.lng)
    return dist <= distance_threshold_m


def deduplicate_venues(venues: List[Venue], distance_threshold_m: float = 15) -> List[Venue]:
    """Deduplicate list of venues, merging corridor membership"""
    if not venues:
        return []
    
    unique = []
    seen_keys = {}
    
    for venue in venues:
        norm_name = normalize_name(venue.name)
        # Create a grid key for fast lookup (round to ~15m ≈ 0.00015 deg)
        lat_key = round(venue.lat / 0.00015) * 0.00015
        lng_key = round(venue.lng / 0.00015) * 0.00015
        grid_key = (norm_name, lat_key, lng_key)
        
        if grid_key in seen_keys:
            # Merge corridor membership
            existing = seen_keys[grid_key]
            for c in venue.corridors:
                if c not in existing.corridors:
                    existing.corridors.append(c)
            # Keep the one with more info
            if venue.rating and not existing.rating:
                existing.rating = venue.rating
            if venue.raw_text and not existing.raw_text:
                existing.raw_text = venue.raw_text
        else:
            seen_keys[grid_key] = venue
            unique.append(venue)
    
    # Second pass: exact distance check for same-name venues in adjacent grids
    # This catches edge cases where rounding puts them in different grids
    final_unique = []
    for venue in unique:
        is_dup = False
        for existing in final_unique:
            if is_duplicate(venue, existing, distance_threshold_m=distance_threshold_m):
                # Merge
                for c in venue.corridors:
                    if c not in existing.corridors:
                        existing.corridors.append(c)
                is_dup = True
                break
        if not is_dup:
            final_unique.append(venue)
    
    return final_unique


def load_baseline_venues(csv_path: str) -> List[Venue]:
    """Load baseline venues from CSV for deduplication reference"""
    import pandas as pd
    df = pd.read_csv(csv_path)
    venues = []
    for _, row in df.iterrows():
        try:
            venues.append(Venue(
                venue_id=f"baseline_{len(venues)}",
                name=row.get('name', ''),
                lat=float(row['lat']),
                lng=float(row['lng']),
                rating=str(row.get('rating', '')),
                raw_text=row.get('raw_text', ''),
                corridors=[row.get('road_name', '')],
                source="baseline",
                query_found_by=row.get('category', ''),
                category=row.get('category', ''),
                road_name=row.get('road_name', ''),
                tier=row.get('tier', '')
            ))
        except Exception as e:
            continue
    return venues


def filter_new_venues(new_venues: List[Venue], baseline_venues: List[Venue], distance_threshold_m: float = 50) -> List[Venue]:
    """Filter out venues that match baseline (within larger threshold for baseline)"""
    # Create spatial index for baseline
    baseline_by_grid = {}
    for v in baseline_venues:
        norm_name = normalize_name(v.name)
        lat_key = round(v.lat / 0.0005) * 0.0005  # ~50m grid
        lng_key = round(v.lng / 0.0005) * 0.0005
        key = (norm_name, lat_key, lng_key)
        if key not in baseline_by_grid:
            baseline_by_grid[key] = []
        baseline_by_grid[key].append(v)
    
    filtered = []
    for venue in new_venues:
        norm_name = normalize_name(venue.name)
        lat_key = round(venue.lat / 0.0005) * 0.0005
        lng_key = round(venue.lng / 0.0005) * 0.0005
        
        # Check adjacent grids too
        is_match = False
        for dlat in [-0.0005, 0, 0.0005]:
            for dlng in [-0.0005, 0, 0.0005]:
                key = (norm_name, lat_key + dlat, lng_key + dlng)
                if key in baseline_by_grid:
                    for bv in baseline_by_grid[key]:
                        if haversine(venue.lat, venue.lng, bv.lat, bv.lng) <= distance_threshold_m:
                            is_match = True
                            break
                if is_match:
                    break
            if is_match:
                break
        
        if not is_match:
            filtered.append(venue)
    
    return filtered