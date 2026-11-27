# 2-Day Full Scrape Plan — Optimized for 4 Parallel Browsers

## Summary
- **Target**: 2,478 strategic points across 119 corridors
- **Duration**: ~26 hours with 4 parallel browsers (~6.5 hrs each)
- **Sequential fallback**: ~103 hours (4.3 days)
- **Field coverage**: 100% (venue_url, place_id, cid)
- **Deduplication**: By place_id at merge stage

## Sampling Strategy (2,478 points)

| Tier | Corridors | Points/Corridor | Total |
|------|-----------|-----------------|-------|
| Finish partial (8 corridors) | 8 | 40 | 320 |
| Priority (Tier 1 + major Tier 2) | 50 | 25 | 1,250 |
| Secondary (Tier 2/3) | 60 | 15 | 900 |
| Tertiary | 50 | 8 | 8 |
| Coverage (remaining) | ~50 | 3 | ~0 |
| **Total** | **~119** | — | **2,478** |

## Files Created

```
config/full_scrape_plan_2day.json          # Full 2,478 point plan
config/full_scrape_plan_2day_chunk_0.json  # 620 points → Session scrape_0
config/full_scrape_plan_2day_chunk_1.json  # 620 points → Session scrape_1
config/full_scrape_plan_2day_chunk_2.json  # 620 points → Session scrape_2
config/full_scrape_plan_2day_chunk_3.json  # 618 points → Session scrape_3
subagent_chunk_0.py .. subagent_chunk_3.py  # Standalone runner scripts
orchestrator.py                              # Planning script
```

## Launch: 4 Parallel Terminals (TRUE PARALLELISM)

Open 4 separate terminals and run:

```bash
# Terminal 1
cd C:\Users\Eromo\Downloads\gmaps_sweep_browser
python subagent_chunk_0.py

# Terminal 2
cd C:\Users\Eromo\Downloads\gmaps_sweep_browser
python subagent_chunk_1.py

# Terminal 3
cd C:\Users\Eromo\Downloads\gmaps_sweep_browser
python subagent_chunk_2.py

# Terminal 4
cd C:\Users\Eromo\Downloads\gmaps_sweep_browser
python subagent_chunk_3.py
```

Each script:
- Uses isolated browser session (`scrape_0` .. `scrape_3`)
- Processes points sequentially (2 per browser_exec call)
- Appends to `data/overnight/results/full_scrape_results.jsonl`
- Updates `config/full_scrape_plan.json` status

## Sequential Fallback (Single Terminal)

If parallel not possible, run sequentially:

```bash
cd C:\Users\Eromo\Downloads\gmaps_sweep_browser
# Process in batches via browser_exec tool calls from Hermes
# ~103 hours total
```

## Merge & Deduplicate (Post-Scrape)

```python
import pandas as pd

# Load all sources
df1 = pd.read_json('data/overnight/results/consolidated_ALL_corridors.jsonl', lines=True)
df2 = pd.read_json('data/overnight/results/full_scrape_results.jsonl', lines=True)

# Combine
df = pd.concat([df1, df2], ignore_index=True)

# Deduplicate by place_id (keep most complete record)
df['completeness'] = df[['venue_url','place_id','cid','rating']].notna().sum(axis=1)
df = df.sort_values('completeness', ascending=False).drop_duplicates('place_id', keep='first')

# Save master competitive map
df.to_csv('competitive_map_master.csv', index=False)
print(f"Master map: {len(df)} unique venues")
```

## Progress Tracking

```bash
# Check results count
wc -l data/overnight/results/full_scrape_results.jsonl

# Check plan status
python -c "
import json
with open('config/full_scrape_plan.json') as f:
    p = json.load(f)
done = sum(1 for x in p if x['status']=='done')
print(f'Done: {done}/{len(p)} ({done/len(p)*100:.1f}%)')
"
```

## Resource Requirements

- 4 Chrome/Chromium profiles (or 1 profile with 4 isolated sessions)
- ~20 GB RAM for 4 browser instances
- Stable internet (rate limit: ~1 req/2s per session)
- 20s sleep between sessions per browser (port cleanup)

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| WebSocket failures on 2nd point | Process 1 point per session; re-init page |
| Rate limiting | 20s delay, rotate sessions |
| Crash mid-run | Append-only JSONL + plan status = full recovery |
| Duplicates | place_id deduplication at merge |

## Estimated Output

| Metric | Estimate |
|--------|----------|
| Unique venues | 15,000 - 25,000 |
| Corridors covered | 119/119 (sampled) |
| Field completeness | >95% venue_url, >90% place_id, >85% cid |
| Time (4 parallel) | 26 hours |
| Time (sequential) | 103 hours |