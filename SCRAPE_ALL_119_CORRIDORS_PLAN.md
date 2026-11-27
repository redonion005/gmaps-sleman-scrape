# Scrape All 119 Corridors — Design Plan

## Objective
Scrape all 119 corridors from `config/corridor_point_counts.csv` with quality assurance, auto-retry, and resume capability until 100% complete.

---

## 1. Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    MASTER CONTROLLER                         │
│  (single Python process, runs forever until done)           │
└─────────────────────────────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        ▼                   ▼                   ▼
┌───────────────┐   ┌───────────────┐   ┌───────────────┐
│  Corridor     │   │  Browser      │   │  Quality      │
│  Queue        │──▶│  Workers      │──▶│  Gate         │
│  (SQLite)     │   │  (N parallel) │   │  (validation) │
└───────────────┘   └───────────────┘   └───────────────┘
        ▲                   │                   │
        │                   ▼                   ▼
        │           ┌───────────────┐   ┌───────────────┐
        └───────────│  Checkpoint   │   │  Results      │
                    │  Store        │   │  Sink         │
                    │  (JSONL +     │   │  (JSONL +     │
                    │   SQLite)     │   │   Parquet)    │
                    └───────────────┘   └───────────────┘
```

---

## 2. Data Structures

### 2.1 Corridor Queue (SQLite: `queue.db`)
```sql
CREATE TABLE corridors (
    corridor_id     TEXT PRIMARY KEY,
    road_name       TEXT NOT NULL,
    tier            TEXT NOT NULL,
    lat             REAL NOT NULL,
    lng             REAL NOT NULL,
    status          TEXT DEFAULT 'pending',  -- pending, running, done, failed, skipped
    attempts        INTEGER DEFAULT 0,
    last_attempt    TIMESTAMP,
    started_at      TIMESTAMP,
    completed_at    TIMESTAMP,
    venues_found    INTEGER DEFAULT 0,
    error_msg       TEXT
);
CREATE INDEX idx_status ON corridors(status);
```

### 2.2 Checkpoint Log (JSONL: `checkpoints.jsonl`)
```json
{"corridor_id": "R001_Jalan_Padjajaran", "query": "restoran", "status": "success", "venues": 12, "timestamp": "2026-11-27T02:15:00Z"}
{"corridor_id": "R001_Jalan_Padjajaran", "query": "kafe", "status": "success", "venues": 8, "timestamp": "2026-11-27T02:16:00Z"}
```

### 2.3 Results Sink
- **Primary**: `results/{corridor_id}.jsonl` (one file per corridor, append-only)
- **Consolidated**: `results/consolidated_all.parquet` (rebuilt on each corridor completion)

---

## 3. Browser Worker Design

### 3.1 Session Management
- **Pool size**: 3 concurrent browsers (configurable, default 3)
- **Session reuse**: Each worker keeps a persistent browser session
- **Restart trigger**: After 50 queries OR on critical error (detached frame, context destroyed)
- **Memory guard**: Restart if RSS > 2GB

### 3.2 Extraction Script (hardened)
```python
EXTRACT_JS = r"""
(() => {
    try {
        const articles = document.querySelectorAll('[role=article]');
        const results = [];
        for (const article of articles) {
            const link = article.querySelector('a.hfpxzc') 
                       || article.querySelector('a[href*="/maps/place/"]');
            if (!link) continue;
            
            const name = link.getAttribute('aria-label') || '';
            const href = link.href || '';
            
            let lat = null, lng = null;
            const latMatch = href.match(/!3d(-?[\d.]+)/);
            const lngMatch = href.match(/!4d(-?[\d.]+)/);
            if (latMatch) lat = parseFloat(latMatch[1]);
            if (lngMatch) lng = parseFloat(lngMatch[1]);
            if (lat === null || lng === null) continue;
            
            const text = article.textContent || '';
            const ratingMatch = text.match(/(\d+[,.]\d)/);
            const rating = ratingMatch ? ratingMatch[1].replace(',', '.') : '';
            
            results.push({name, rating, lat, lng});
        }
        return JSON.stringify(results);
    } catch (e) {
        return JSON.stringify({__error: e.message});
    }
})()
"""
```

### 3.3 Scroll & Wait Logic
```python
def scroll_to_bottom(page, max_rounds=10, stall_rounds=3):
    prev = 0
    stalled = 0
    for _ in range(max_rounds):
        page.evaluate("""() => {
            const feed = document.querySelector('[role=feed]');
            if (feed) feed.scrollTop = feed.scrollHeight;
        }""")
        time.sleep(1.2)
        curr = page.evaluate("document.querySelectorAll('[role=article]').length")
        if curr == prev:
            stalled += 1
            if stalled >= stall_rounds:
                break
        else:
            stalled = 0
        prev = curr
    return prev
```

---

## 4. Quality Assurance Gates

### 4.1 Per-Query Validation
| Check | Threshold | Action |
|-------|-----------|--------|
| Venues extracted | ≥ 1 | Pass |
| All venues have lat/lng | 100% | Pass |
| Duplicate rate (name+coord) | < 20% | Pass |
| Rating parse rate | > 50% | Warn only |
| Extraction JS error | None | Fail → retry |

### 4.2 Per-Corridor Validation (after 10 queries)
| Metric | Minimum | Action |
|--------|---------|--------|
| Total unique venues | ≥ 5 | Pass |
| Queries successful | 10/10 | Pass (else retry failed queries) |
| Coverage (queries with results) | ≥ 8/10 | Pass |

### 4.3 Global Validation (on completion)
- All 119 corridors status = `done`
- Consolidated venues > 5,000 (sanity)
- No corridor with 0 venues (investigate)

---

## 5. Retry & Recovery Policy

| Failure Type | Max Retries | Backoff | Escalation |
|--------------|-------------|---------|------------|
| Network timeout | 3 | 5s, 15s, 45s | Mark query failed, continue |
| Extraction JS error | 2 | 10s, 30s | Restart browser session |
| No venues found | 2 | 30s, 60s | Try alternate queries |
| Browser crash | 3 | 10s, 30s, 60s | Restart worker process |
| Rate limit (429) | 5 | 60s, 120s, 300s, 600s, 1800s | Pause all workers |

**Circuit breaker**: If 5 consecutive corridors fail → pause 10 min, alert.

---

## 6. Checkpoint & Resume Logic

### 6.1 On Startup
```python
def resume():
    # 1. Load queue.db
    # 2. For each corridor with status 'running':
    #    - Check checkpoints.jsonl for completed queries
    #    - Mark those queries as done in memory
    #    - Set corridor status = 'pending' (will re-pick unfinished queries)
    # 3. For corridors with status 'done': verify results file exists & non-empty
    # 4. Resume from first 'pending' corridor
```

### 6.2 Checkpoint Frequency
- After **every query** (append to `checkpoints.jsonl`)
- After **every corridor** (update `queue.db`, rebuild consolidated parquet)
- **Atomic writes**: write to `.tmp` then rename

---

## 7. Monitoring & Observability

### 7.1 Progress File (updated every 30s)
`progress.json`:
```json
{
  "total_corridors": 119,
  "done": 14,
  "running": 3,
  "pending": 102,
  "failed": 0,
  "total_venues": 1886,
  "started_at": "2026-11-27T01:00:00Z",
  "eta": "2026-11-27T08:30:00Z",
  "workers_alive": 3,
  "last_update": "2026-11-27T03:15:00Z"
}
```

### 7.2 Log Format (structured JSON)
```json
{"level": "INFO", "corridor_id": "R001_Jalan_Padjajaran", "query": "restoran", "phase": "extract", "venues": 12, "duration_ms": 4200, "timestamp": "..."}
{"level": "WARN", "corridor_id": "R001_Jalan_Padjajaran", "query": "bakery", "phase": "validate", "msg": "Only 2 venues found", "timestamp": "..."}
{"level": "ERROR", "corridor_id": "R002_Jalan_Siliwangi", "query": "restoran", "phase": "navigate", "error": "Timeout", "attempt": 2, "timestamp": "..."}
```

### 7.3 Health Endpoints (optional HTTP)
- `GET /health` → worker status
- `GET /progress` → progress.json
- `GET /queue?status=failed` → failed corridors

---

## 8. Implementation Plan

### Phase 1: Core Engine (Day 1)
- [ ] `queue.db` schema + init from CSV
- [ ] BrowserWorker class with session management
- [ ] Extraction + scroll logic
- [ ] Checkpoint writer (JSONL + SQLite)
- [ ] Single-corridor end-to-end test

### Phase 2: Quality Gates (Day 1-2)
- [ ] Per-query validator
- [ ] Per-corridor validator
- [ ] Retry logic with backoff
- [ ] Circuit breaker

### Phase 3: Orchestration (Day 2)
- [ ] Master controller (asyncio + process pool)
- [ ] Worker pool management (3 workers)
- [ ] Progress reporter (30s interval)
- [ ] Resume logic on startup

### Phase 4: Hardening (Day 2-3)
- [ ] Memory leak guard (restart workers periodically)
- [ ] Rate limit detection + adaptive delay
- [ ] Browser crash recovery
- [ ] Disk space monitor

### Phase 5: Run & Monitor (Day 3+)
- [ ] Start full 119-corridor run
- [ ] Monitor progress.json
- [ ] Investigate any failed corridors manually
- [ ] Final validation + consolidated export

---

## 9. Configuration (config.yaml)
```yaml
browser:
  pool_size: 3
  headless: true
  restart_after_queries: 50
  max_memory_mb: 2048
  timeout_navigate: 30
  timeout_extract: 15

scraping:
  queries: 
    - restoran
    - warung makan
    - rumah makan
    - kafe
    - kedai kopi
    - bakery
    - toko roti
    - toko kue
    - donat
    - pujasera
  zoom: 16
  scroll_max_rounds: 10
  scroll_stall_rounds: 3

quality:
  min_venues_per_corridor: 5
  min_successful_queries: 8
  max_duplicate_rate: 0.2

retry:
  max_attempts: 3
  base_backoff_sec: 5
  max_backoff_sec: 1800
  rate_limit_backoff: [60, 120, 300, 600, 1800]

monitoring:
  progress_interval_sec: 30
  checkpoint_every_query: true
  rebuild_parquet_every_corridor: true
```

---

## 10. Entry Points

```bash
# Initialize queue from CSV
python -m scrape.init_queue

# Run master controller (blocks until done)
python -m scrape.master --config config.yaml

# Resume after interruption (auto-detects)
python -m scrape.master --config config.yaml --resume

# Check progress
python -m scrape.status

# Validate final output
python -m scrape.validate
```

---

## 11. Success Criteria

1. **All 119 corridors** status = `done` in `queue.db`
2. **Consolidated venues** > 5,000 unique (after dedup)
3. **Zero corridors** with 0 venues
4. **Checkpoint coverage**: every query logged in `checkpoints.jsonl`
5. **Resumable**: kill at any point, restart → continues from last checkpoint