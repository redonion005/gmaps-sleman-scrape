# HANDOVER: Full 119 Corridor Scrape (All Corridors, All Points, All Categories)

## Goal
Scrape **all 119 corridors** × all points × 10 categories → complete venue dataset with `venue_url`, `place_id`, `cid` for later Places API enrichment.

## Current State

### Data Sources
| File | Description |
|------|-------------|
| `config/corridor_point_counts.csv` | 119 corridors, point counts per corridor |
| `config/full_scrape_plan.json` | Working plan (183 points for 14 corridors with existing data) |
| `data/overnight/results/consolidated_ALL_corridors.jsonl` | 1,886 venues from 14 corridors (no URLs) |
| `data/overnight/results/full_scrape_results.jsonl` | New scrape results (append-only) |
| `SCRAPE_ALL_119_CORRIDORS_PLAN.md` | Original design doc |

### Progress
- **14 corridors** have existing overnight data (183 points, 1,886 venues)
- **4/183 points** re-scraped with URLs (R003 Godean: P0000, P0038, P0076, P0114)
- **105 corridors** have **zero data** — need full initial scrape
- **Next point index:** 4 (R003_Jalan_Godean_P0152)

## Full Scope

### Corridors with Existing Data (14)
| Corridor | Points | Status |
|----------|--------|--------|
| R003_Jalan_Godean | 19 | 4 done, 15 pending |
| R011_Jalan_Magelang | 23 | 0 done |
| R015_Jalan_Nyi_Tjondro_Loekito | 5 | 0 done |
| R029_Jalan_Kaliurang | 11 | 0 done |
| R036_Jalan_Wonosari | 23 | 0 done |
| R041_Jalan_Cornelis_Simanjuntak | 7 | 0 done |
| R052_Jalan_Teknika_Selatan | 5 | 0 done |
| R053_Jalan_Teknika_Utara | 5 | 0 done |
| R064_Jalan_Solo | 24 | 0 done |
| R070_Jalan_Laksda_Adisutjipto | 26 | 0 done |
| R095_Selokan_Mataram | 20 | 0 done |
| R104_Jalan_Kahar_Muzakir | 5 | 0 done |
| R105_Jalan_Yacaranda | 5 | 0 done |
| R108_Jalan_Kemuning | 5 | 0 done |

### Corridors Needing Initial Scrape (105)
From `config/corridor_point_counts.csv` — all corridors not in above list. Each has 5-30 points.

**Total estimated points:** ~1,500-2,000 across 119 corridors
**Total queries:** ~15,000-20,000 (10 categories × points)

## Resume Instructions

### 1. Continue 14 Corridors Re-scrape (Current Plan)
```bash
cd C:\Users\Eromo\Downloads\gmaps_sweep_browser
# Run browser_exec with start_idx = 4
```

### 2. Build Plan for Remaining 105 Corridors
```python
# Load corridor_point_counts.csv
# For each corridor not in existing 14:
#   Generate points from corridor geometry (or use CSV point counts)
#   Add to full_scrape_plan.json with status=pending
```

### 3. Scrape Loop (Crash-Safe Pattern)
```python
# Per browser_exec session: MAX 2 points (≈20 queries)
# Per point: 10 queries × scroll feed × EXTRACT_JS
# After EACH point: append to results + update plan status
# Save plan after every point
# New session picks up from next pending
```

## Required Output Schema (per venue)
```json
{
  "name": "string",
  "venue_url": "https://www.google.com/maps/place/...",
  "place_id": "ChIJ...",
  "cid": "hex",
  "rating": 4.5,
  "lat": -7.759,
  "lng": 110.345,
  "address": "string",
  "category": "restoran|warung makan|kafe|...",
  "query": "restoran",
  "corridor_id": "R003_Jalan_Godean",
  "point_id": "R003_Jalan_Godean_P0000",
  "road_name": "Jalan Godean",
  "tier": "Tier 1",
  "scraped_at": "2026-11-27T...",
  "source": "browser_full_scrape"
}
```

## Extraction JS (Copy Exact)
```javascript
const EXTRACT_JS = r\"\"\"
(() => {
    const articles = document.querySelectorAll('[role=article]');
    const results = [];
    for (const article of articles) {
        const link = article.querySelector('a.hfpxzc') || article.querySelector('a[href*="/maps/place/"]');
        if (!link) continue;
        const name = link.getAttribute('aria-label') || '';
        const href = link.href || '';
        let lat = null, lng = null, place_id = null, cid = null;
        if (href) {
            const latMatch = href.match(/!3d(-?[\\d.]+)/);
            const lngMatch = href.match(/!4d(-?[\\d.]+)/);
            const placeMatch = href.match(/19s(ChIJ[^!&?]+)/);
            const cidMatch = href.match(/1s0x[^:]+:0x([0-9a-f]+)/);
            if (latMatch) lat = parseFloat(latMatch[1]);
            if (lngMatch) lng = parseFloat(lngMatch[1]);
            if (placeMatch) place_id = placeMatch[1];
            if (cidMatch) cid = cidMatch[1];
        }
        if (lat === null || lng === null) continue;
        const text = article.textContent || '';
        const ratingMatch = text.match(/(\\d+[,.]\\d)/);
        const rating = ratingMatch ? ratingMatch[1].replace(',', '.') : '';
        results.push({name, venue_url: href, place_id, cid, rating: rating ? parseFloat(rating) : null, rating_raw: ratingMatch ? ratingMatch[1] : '', lat, lng});
    }
    return JSON.stringify(results);
})()
\"\"\"
```

## Queries (10 Categories)
```python
queries = ['restoran', 'warung makan', 'rumah makan', 'kafe', 'kedai kopi', 'bakery', 'toko roti', 'toko kue', 'donat', 'pujasera']
```

## Quality Gates
- [ ] Every point has 10 query results saved
- [ ] Every venue has `venue_url`, `place_id`, `cid`, `lat`, `lng`
- [ ] Deduplication: dedupe by (name, lat, lng) across all queries
- [ ] Final merge: enrich original 1,886 + new venues into master dataset
- [ ] Export: `master_venues_all_119_corridors.jsonl` with 100% URL coverage

## Crash Recovery
- Plan file is source of truth — `status: pending/done`
- Results file is append-only — never overwritten
- On crash: re-read plan, find next `pending`, continue
- No manual cleanup needed

## Estimated Effort
- 183 points × 20 queries = 3,660 queries (14 corridors re-scrape)
- ~1,500 points × 10 queries = 15,000 queries (105 new corridors)
- ~18,660 total queries
- At 2 points/session = ~840 browser sessions
- Run overnight, resume each morning

## Next Immediate Action
1. Continue current plan from index 4 (R003_P0152)
2. After 14 corridors done, generate plan for 105 remaining corridors from CSV
3. Run until `pending == 0` for all 119 corridors