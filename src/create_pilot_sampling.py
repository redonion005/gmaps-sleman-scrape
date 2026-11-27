#!/usr/bin/env python3
"""
Create reduced pilot sampling - ~50 points per corridor
"""

import json
from pathlib import Path

SAMPLING_POINTS_JSONL = Path(__file__).parent.parent / "config" / "sampling_points.jsonl"
PILOT_SELECTION_PATH = Path(__file__).parent.parent / "config" / "pilot_selection.json"
OUTPUT_PATH = Path(__file__).parent.parent / "config" / "pilot_sampling_points.jsonl"

PILOT_CORRIDORS = ['R053_Jalan_Teknika_Utara', 'R066_Jalan_Pandega_Marta', 'R055_Jalan_Sawit_Sari']
TARGET_POINTS_PER_CORRIDOR = 50

def main():
    # Load all pilot points
    pilot_points = {cid: [] for cid in PILOT_CORRIDORS}
    with open(SAMPLING_POINTS_JSONL, 'r', encoding='utf-8') as f:
        for line in f:
            pt = json.loads(line.strip())
            if pt['corridor_id'] in PILOT_CORRIDORS:
                pilot_points[pt['corridor_id']].append(pt)
    
    # Sample ~50 points per corridor - evenly spaced along the corridor
    reduced_points = []
    for cid, points in pilot_points.items():
        n = len(points)
        if n <= TARGET_POINTS_PER_CORRIDOR:
            selected = points
        else:
            # Evenly sample
            step = n / TARGET_POINTS_PER_CORRIDOR
            indices = [int(i * step) for i in range(TARGET_POINTS_PER_CORRIDOR)]
            selected = [points[i] for i in indices]
        
        print(f"{cid}: {n} -> {len(selected)} points")
        reduced_points.extend(selected)
    
    # Save reduced pilot sampling
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        for pt in reduced_points:
            f.write(json.dumps(pt, ensure_ascii=False) + '\n')
    
    print(f"\nTotal reduced points: {len(reduced_points)}")
    print(f"Saved to {OUTPUT_PATH}")

if __name__ == '__main__':
    main()