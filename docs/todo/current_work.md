# Current Work: Building Replacement Detection + Architecture Cleanup

## Status: APPROVED
## Date: 2025-12-22

## Summary

Implement building replacement detection to identify demolished buildings and inherit demolition dates from their replacements. Most historical demolitions in Trondheim were replacements - old building demolished, new building constructed on same site. Also includes architecture cleanup to consolidate scattered magic numbers and make code actually read from config.

## Key Insight

```
Building A (1880 map) overlaps Building B (modern OSM)
Building B's sd = 1950 (from SEFRAK or estimation)
→ Building A's ed = 1950 (inherited from replacement)
```

SEFRAK provides 289 buildings with `status=0` (demolished) but NO demolition dates. These dates must be inherited from replacement buildings.

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Matching method | Centroid containment | Handles rebuilt larger/smaller/shifted |
| SEFRAK demolished | Flag only, dates from replacements | SEFRAK has no demolition dates |
| Date inheritance | `old.ed = new.sd` | Replacement's construction = demolition |
| Architecture | Constants file + read config | Fix 5+ hardcoded `1960` values |

## Schema Additions

```python
# Existing fields (already in DATA_SCHEMA.md)
ed          # End date (demolition year)
ed_t        # 'x' exact, 's' estimated
ed_s        # 'sef' (SEFRAK), 'repl' (from replacement), 'map' (ML)

# New fields
demolished  # boolean - known to be demolished (from SEFRAK status=0)
repl_by     # ID of building that replaced this one
repl_of     # ID of building this replaced
```

## Tasks

### Phase 1: Architecture Cleanup

- [ ] Create `scripts/constants.py` with centralized magic numbers:
  - DATE_FALLBACK = 1960
  - MEDIAN_RADIUS_M = 2000
  - ML_CONFIDENCE_HIGH = 0.9
  - ML_CONFIDENCE_MEDIUM = 0.7
  - ERA_BOUNDS = [1900, 1950]
- [ ] Update `merge_sources.py` to read `fallback_year` from config (currently ignored)
- [ ] Extract `determine_era(year)` function (duplicated at lines 879-884, 944-949)
- [ ] Extract `check_evidence_threshold(ev, min_ev)` function
- [ ] Create `scripts/normalize/date_utils.py` for shared date parsing

### Phase 2: SEFRAK Demolished Integration

- [ ] Update `normalize_sefrak.py` to set `demolished=true` for status=0
- [ ] Ensure SEFRAK demolished buildings flow through merge pipeline
- [ ] Add SEFRAK demolished to candidate list for date inheritance

### Phase 3: Replacement Detection Enhancement

- [ ] Implement centroid-containment matching:
  - New building centroid inside old footprint → same location
  - OR old building centroid inside new footprint → same location
  - Overlap ratio >30% confirms replacement vs adjacent
- [ ] Inherit `ed` from replacement's `sd` for demolished buildings
- [ ] Track replacement chain: `repl_by`, `repl_of` fields
- [ ] Update quality report with replacement statistics

## Date Inference Rules

| Scenario | Old Building `ed` | Evidence |
|----------|-------------------|----------|
| SEFRAK has demolition date | SEFRAK date | `h` (high) |
| Overlaps modern building with known `sd` | Modern building's `sd` | `m` (medium) |
| Overlaps modern building, `sd` estimated | Modern building's estimated `sd` | `l` (low) |
| No overlap (truly removed, rare) | Map where last seen + buffer | `l` (low) |

## Files to Modify

| File | Changes |
|------|---------|
| `scripts/constants.py` | NEW - centralized magic numbers |
| `scripts/normalize/date_utils.py` | NEW - shared date parsing |
| `scripts/normalize/normalize_sefrak.py` | Add demolished flag |
| `scripts/merge/merge_sources.py` | Read config, extract functions, centroid matching |
| `scripts/merge/merge_config.json` | Add date_inference section |
| `docs/tech/DATA_SCHEMA.md` | Document new fields |

## Architecture Issues to Fix

| Issue | File:Line | Fix |
|-------|-----------|-----|
| `1960` hardcoded 5+ times | merge_sources.py:431,465,523 | Use constants.DATE_FALLBACK |
| Config `fallback_year` ignored | merge_sources.py | Read from osm_centric config |
| Duplicate era logic | merge_sources.py:879-884,944-949 | Extract to function |
| ML thresholds hardcoded | normalize_ml.py:76-78 | Use constants |
| Date parsing duplicated | normalize_*.py | Use date_utils.py |

## Expected Yield

| Source | Demolished Buildings | With Dates |
|--------|---------------------|------------|
| SEFRAK status=0 | 289 | 0 → ~200 (via replacement) |
| ML 1880 absent in modern | ~100-500 | ~80% (via replacement) |
| **Total** | **~400-800** | **~300-600** |

## Success Criteria

- [ ] `scripts/constants.py` exists with all magic numbers
- [ ] `merge_sources.py` reads `fallback_year` from config
- [ ] No duplicate era determination logic
- [ ] SEFRAK demolished buildings have `demolished=true`
- [ ] Replacement detection finds overlapping buildings
- [ ] Demolished buildings inherit `ed` from replacements
- [ ] `repl_by`/`repl_of` fields track replacement chains
- [ ] Quality report shows replacement statistics

---

## Archive

### Year Step Buttons (2025-12-22) - APPROVED (pending)

Add forward/back step buttons (◀ ▶) next to the play button to allow single-year navigation.

### Road Temporal Network (2025-12-22) - IMPLEMENTED

Segment-based road tracking with LSS-Hausdorff matching and building-based date inference.
See `scripts/extract/extract_roads.py`, `scripts/merge/match_roads.py`, `scripts/merge/infer_road_dates.py`.

### UI Reorganization + Manual Edit Mode (2025-12-22) - IMPLEMENTED

Reorganized toggle buttons to Background/Debug/Edit. Added Edit mode for manually setting building construction/demolition dates.

### Semi-Manual FINN Data Entry (2025-12-22) - IMPLEMENTED

CLI script for adding FINN listings manually. See `scripts/ingest/finn_manual.py`.

### Multi-Layer Date Inheritance (2025-12-22) - IMPLEMENTED

Three-tier building date fallback: median within 2km → nearest any distance → 1960.
See `scripts/merge/merge_sources.py:inherit_dates_from_neighbors()`

### OSM-Centric Building Model (2025-12-20) - IMPLEMENTED

OSM buildings as canonical geometry, dates attached from SEFRAK/FINN/MANUAL.
