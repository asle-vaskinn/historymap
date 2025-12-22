# Current Work: Road Fallback Layer System

## Status: IMPLEMENTED
## Date: 2025-12-22

## Summary

Add a multi-layer road fallback system aligned with building fallback. Roads get dates from multiple sources with confidence-based merging: ML detection (medium/high evidence) takes precedence, building-based inference (low evidence) fills gaps, and year 2000 is the final fallback.

## Date Priority Logic

| Scenario | Result |
|----------|--------|
| ML: detected in 1880, Buildings: earliest 1920 | `sd=1880, ev=m` (ML wins) |
| ML: NOT in 1880, detected in 1904, Buildings: earliest 1870 | `sd=1868, ev=l` (building wins) |
| ML: none, Buildings: earliest 1950 | `sd=1948, ev=l` (building - 2 years) |
| ML: none, Buildings: none | `sd=2000, ev=l, sd_method=fallback` |

## Key Rules

1. **Buffer distance**: 50m from road centerline
2. **Building selection**: Earliest building date within buffer
3. **Offset**: Subtract 2 years (roads built before houses)
4. **Evidence**: Building-inferred dates get `ev='l'` (low)
5. **Override**: Building date can override ML only if ML evidence isn't 'h'

## Properties Added to Roads

| Field | Type | Description |
|-------|------|-------------|
| `sd_method` | string | 'ml', 'building', 'building_override', 'fallback' |
| `sd_buildings` | int | Number of buildings used for inference |
| `sd_offset` | int | Years subtracted (typically -2) |
| `sd_inherited` | bool | True if date came from buildings |

## Tasks

### Phase 1: Constants & Schema

- [x] Add constants to `scripts/constants.py`:
  - `ROAD_FALLBACK_YEAR = 2000`
  - `ROAD_BUILDING_OFFSET = 2`
  - `ROAD_BUFFER_M = 50`

- [x] Update `docs/tech/DATA_SCHEMA.md` with road fallback documentation

### Phase 2: Backend - Date Inference

- [x] Update `scripts/merge/infer_road_dates.py`:
  - Load buildings with dates
  - For each road, find buildings within 50m buffer
  - Get earliest building `sd`, subtract 2 years
  - Apply priority logic (ML vs building)
  - Set `sd_method`, `sd_buildings`, `sd_offset`, `sd_inherited`

### Phase 3: Frontend - Filter Update

- [x] Update `frontend/app.js` `createRoadFilter(year)`:
  - Roads without `sd` shown only when `year >= 2000`
  - Match building filter pattern

### Phase 4: Pipeline Re-run

- [x] Re-run road merge pipeline with new inference
- [x] Verify output in `roads_temporal.geojson`
- [ ] Test in frontend with timeline slider

## Files to Modify

| File | Changes |
|------|---------|
| `scripts/constants.py` | Add ROAD_FALLBACK_YEAR, ROAD_BUILDING_OFFSET, ROAD_BUFFER_M |
| `scripts/merge/infer_road_dates.py` | Building-based date inference logic |
| `frontend/app.js` | Update createRoadFilter() with 2000 fallback |
| `docs/tech/DATA_SCHEMA.md` | Document road fallback logic |

## Success Criteria

- [x] Roads without dates hidden before year 2000
- [x] Roads near old buildings get earlier dates (building.sd - 2)
- [x] ML-detected roads keep their dates unless building contradicts
- [x] `sd_method` field tracks how date was determined
- [ ] Frontend timeline correctly filters roads (needs manual verification)

---

## Archive

### Water Diff-Comparison Workflow (2025-12-22) - ON HOLD

Enhance water editor with diff-comparison mode. See previous version for details.

### Building Replacement Detection (2025-12-22) - IMPLEMENTED

Centroid-containment matching, `repl_by`/`repl_of` tracking, `demolished` flag.

### Road Temporal Network (2025-12-22) - IMPLEMENTED

LSS-Hausdorff matching, building-based date inference.

### Year Step Buttons (2025-12-22) - IMPLEMENTED

Timeline navigation with ◀ ▶ buttons.
