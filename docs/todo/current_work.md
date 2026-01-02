# Current Work: Data Prep Tool v2 + Georeferencing

## Status: IN PROGRESS
## Date: 2026-01-01
## Last Updated: 2026-01-01

## Summary

Simplified Data Prep Tool with two-layer model (Focus + Reference) and integrated georeferencing. Enables georeferencing historical maps with overlay preview, GCP persistence, and automatic image resizing for large files.

---

## Recent Work: Data Prep Tool v2 (2026-01-01)

### Completed

- [x] Simplified two-layer UI: Focus layer (radio buttons) + Reference layer (dropdown)
- [x] WMS integration with nginx proxy (Trondheim Kommune, Geonorge)
- [x] Safari CORS fix using XYZ tile scheme with transformRequest
- [x] Integrated georeferencing workflow:
  - Draggable image overlay for rough positioning
  - Click-click GCP placement (image → map)
  - Affine transform calculation with RMS error
  - Preview using MapLibre image source
  - GDAL-based GeoTIFF generation
- [x] GCP persistence to `data/georeference/gcps/{source_id}.gcp.json`
- [x] Automatic image resizing for large files (>8000px dimension)
- [x] Source catalog auto-update with georeferenced layers

### In Progress

- [ ] Display georeferenced GeoTIFF layers in map viewer
- [ ] "Update GCPs" feature for editing existing georeferencing
- [ ] Research additional historical map sources (finn.no, Norkart)

### Files

| File | Purpose |
|------|---------|
| `frontend/dataprep.html` | Simple two-layer map viewer |
| `frontend/dataprep.js` | Layer switching + georeferencing |
| `frontend/dataprep.css` | UI styling |
| `backend/app.py` | `/api/georeference` endpoint |
| `data/sources/map_sources.json` | Source catalog |

---

## Archived: Water Timeline Pipeline

### Status: PAUSED (ML training low IoU)

Build water feature timeline showing coastal changes 1700-2025, including land reclamation areas like Brattøra (1960-1980), Nedre Elvehavn (1970-1990), and Ilsvika (1950-1970). Integrate water pipeline into main pipeline, ML extraction first, then manual corrections.

---

## Implementation Plan

### Phase 1: Pipeline Integration (COMPLETED)

**Goal:** Integrate water features into main data pipeline.

- [x] Create OSM water fetcher (`scripts/ingest/fetch_osm_water.py`)
- [x] Create water editor tool (`scripts/water_editor.py` on port 5002)
- [x] Create `scripts/merge/merge_water.py` - merge OSM + manual + ML water sources
- [x] Create `scripts/export/export_water.py` - export to GeoJSON/PMTiles
- [x] Update `scripts/pipeline.py` to support `--feature-type water`
- [x] Add water layer to main map with temporal filtering
- [x] Test end-to-end: OSM fetch → merge → export → display

**Scripts:**
- `PYTHONPATH=scripts python3 scripts/ingest/fetch_osm_water.py`
- `python3 scripts/water_editor.py` (port 5002)
- `PYTHONPATH=scripts python3 scripts/pipeline.py --stage all --feature-type water`

### Phase 2: ML Water Extraction (IN PROGRESS)

**Goal:** Automate water extraction from historical maps using ML.

- [x] Create training data prep script (`scripts/ml/prepare_water_training.py`)
- [x] Bootstrap training data from OSM (`scripts/ml/bootstrap_water_training.py`)
  - Generated 100 tiles (50 for 1937, 50 for 1880)
  - Combined into `data/training_water/combined/`
- [ ] Train/fine-tune model with water class
  - Config: `ml/config_water.yaml`
  - Training in progress, early stopping may trigger
  - Current: Low water IoU due to class imbalance
- [x] Create ML water ingest script (`scripts/ingest/ingest_ml_water.py`)
- [x] Create ML water normalize script (`scripts/normalize/normalize_ml_water.py`)
- [ ] Run inference on historical maps
- [ ] Vectorize and integrate into pipeline

**Commands:**
```bash
# Bootstrap training data from OSM
python scripts/ml/bootstrap_water_training.py --year 1937 --tiles 50
python scripts/ml/bootstrap_water_training.py --year 1880 --tiles 50

# Train water model
.venv/bin/python ml/train.py --config ml/config_water.yaml

# Predict water mask (after training)
python ml/predict.py --checkpoint models/checkpoints/water_model.pth --input <map>.tif

# Vectorize
python ml/vectorize.py --input <mask>.png --output water.geojson --class-filter 3
```

### Phase 3: Manual Corrections (PLANNED)

**Goal:** Use existing source_viewer water editor to fix ML errors.

**Key Areas to Review/Correct:**

| Area | Approx Fill Date | Priority | Notes |
|------|------------------|----------|-------|
| Brattøra | 1960-1980 | HIGH | Railway yard expansion |
| Nedre Elvehavn | 1970-1990 | HIGH | Now Solsiden district |
| Ilsvika | 1950-1970 | MEDIUM | Industrial area |
| Ravnkloa south | 1920-1940 | MEDIUM | Fish market expansion |
| Skansen area | 1900-1920 | LOW | Fortress area |

**Workflow:**
1. Add ML water layer to source_viewer
2. Compare with historical WMS backdrop
3. Delete false positives, draw missed features
4. Adjust boundaries where ML was imprecise
5. Save to `data/sources/manual/water.geojson`
6. Re-run pipeline to merge and export

**Data Schema:**
- `wtype`: river, fjord, lake, canal, harbor
- `sd`: start date (when water existed from)
- `ed`: end date (when filled/removed)
- `ev`: evidence (h=high, m=medium, l=low)
- `name`: feature name if known
- `src`: osm, man, ml

---

## Archive: Pipeline Robustness (COMPLETED 2025-12-23)

### Pain Points (From Debugging Sessions)

### 1. Docker Volume Shadowing
- `./data` mounted over `./frontend/data` in nginx container
- PMTiles rebuilt to `frontend/data/` but Docker served old file from `data/`
- **Fix:** Change mount strategy or always export to `data/export/`

### 2. Inconsistent Export Paths
- Export scripts write to `data/export/buildings.geojson`
- PMTiles generated to `frontend/data/buildings_temporal.pmtiles`
- But Docker serves from `data/buildings_temporal.pmtiles`
- **Fix:** Single canonical path for PMTiles in `data/export/`

### 3. Source Code Mapping Confusion
- `sd_src` values: full names (`sefrak`, `trondheim_kommune`) vs short codes (`sef`, `tk`)
- Export script has `SOURCE_CODES` mapping but inconsistently applied
- Debug legend checkboxes used wrong values (`sef` instead of `sefrak`)
- **Fix:** Single `constants.py` with canonical mappings used everywhere

### 4. Stale Data in Pipeline
- Merged data had old `sd_src: "sefrak"`
- New TK data ingested but needed full re-merge and re-export
- No clear "rebuild everything" command
- **Fix:** New `rebuild.sh` script for full pipeline rebuild

### 5. Missing Fields in Export
- `sd_src` field not initially exported to frontend format
- Had to manually add to `export_geojson.py`
- **Fix:** Required fields manifest + validation script

### 6. Browser/Tile Caching
- Aggressive caching made debugging difficult
- No cache-busting on PMTiles files
- **Fix:** Content hash in filename or query string cache-buster

### 7. Debug UI/Data Mismatch
- Legend showed SEFRAK/Matrikkelen checkboxes but no data had those `sd_src` values
- Checkbox `data-source` values didn't match actual data
- **Fix:** Build-time validation or dynamic legend generation

---

## Implementation Plan

### Phase 1: Rebuild Command & Consistent Paths (Priority: HIGH)

- [ ] Create `rebuild.sh` - single command for full pipeline rebuild
- [ ] Create `scripts/constants.py` with canonical paths and source mappings
- [ ] Update `docker-compose.yml` nginx to serve from `data/export/`
- [ ] Update all export scripts to use `constants.py` paths
- [ ] Add `--fail-fast` default to `pipeline.py` (stop on first error)

### Phase 2: Source Code Consistency (Priority: HIGH)

- [ ] Define `SOURCE_IDS` (full) and `SOURCE_SHORT_CODES` (compact) in `constants.py`
- [ ] Update normalizers to use full IDs consistently
- [ ] Update `export_geojson.py` to convert to short codes at export time
- [ ] Update frontend legend to use short codes matching export

### Phase 3: Validation & Safety (Priority: MEDIUM)

- [ ] Create `scripts/validate_export.py` for build-time validation
- [ ] Add `REQUIRED_EXPORT_FIELDS` manifest to `constants.py`
- [ ] Validate legend sources match exported data
- [ ] Add atomic writes (temp file + rename) to export scripts

### Phase 4: Cache Busting (Priority: MEDIUM)

- [ ] Add content hash to PMTiles filename or use manifest.json
- [ ] Update frontend to load tiles via manifest or cache-busted URL
- [ ] Add `?v=timestamp` fallback for development

### Phase 5: Error Handling (Priority: LOW)

- [ ] Replace bare `except:` blocks with specific exception handling
- [ ] Add logging for all suppressed errors
- [ ] Add `--continue-on-error` flag for batch processing

---

## Files to Create/Modify

| File | Action | Purpose |
|------|--------|---------|
| `rebuild.sh` | CREATE | Single rebuild command |
| `scripts/constants.py` | CREATE | Canonical paths and mappings |
| `scripts/validate_export.py` | CREATE | Build-time validation |
| `docker-compose.yml` | MODIFY | Fix nginx volume mounts |
| `scripts/pipeline.py` | MODIFY | Add `--fail-fast` default |
| `scripts/export/export_geojson.py` | MODIFY | Use constants, add fields |
| `scripts/export/export_pmtiles.py` | MODIFY | Use constants, add hash |
| `frontend/app.js` | MODIFY | Load via manifest/cache-bust |

---

## Success Criteria

- [ ] `./rebuild.sh` runs full pipeline without manual intervention
- [ ] All exports go to `data/export/` (single canonical location)
- [ ] Source codes consistent: full IDs in pipeline, short codes in frontend
- [ ] `validate_export.py` catches missing fields before deployment
- [ ] PMTiles changes visible immediately after rebuild (no stale cache)
- [ ] Legend checkboxes match actual `sd_src` values in data


## Success Criteria

- [ ] Water features integrated into `pipeline.py` (buildings, roads, water)
- [ ] OSM current water baseline loaded and visible on map
- [ ] Manual tracing workflow documented and tested
- [ ] At least 2 key areas traced (Brattøra, Nedre Elvehavn)
- [ ] Water layer shows temporal changes (appears/disappears by year)
- [ ] ML extraction approach documented for future implementation

---

## Archive

### Data Prep Tool Modularization (2025-12-23) - IMPLEMENTED

Refactored `source_viewer.*` into modular `data_prep/` structure:
- `core.js` - Config, state, initialization
- `layers.js` - Map layer management
- `buildings.js` - Building annotation workflow
- `water.js` - Water tracing workflow
- `ml_pipeline.js` - ML training jobs

Default source changed to OpenStreetMap (current state), chronological order.

### Data Overlays & Alignment Tools (2025-12-23) - IMPLEMENTED

- Data overlay toggles (Buildings, Roads, Water from merged database)
- Georeferencing alignment UI with TPS/TIN/Affine method selection
- Smoothing and min IoU parameters exposed in UI
- Backend API: `/api/align`, `/api/alignment-report/{source}`
- Real-time job logging via WebSocket

### Water Editor Tooling (2025-12-23) - IMPLEMENTED

- OSM water import via Overpass API
- Water editor mode in Data Prep Tool
- Polygon drawing with MapboxDraw
- Property form (name, wtype, sd, ed)
- Backend API: `/api/water/add`, `/api/water/update`, `/api/water/delete`
- Main map integration with temporal filtering

### Iterative Georeferencing Alignment (2025-12-23) - IMPLEMENTED

OSM-based alignment using IoU matching, TPS/TIN transforms, train/test validation.
Script: `scripts/align_to_osm.py`

### Road Fallback Layer System (2025-12-22) - IMPLEMENTED

Multi-layer road fallback: ML detection → building inference → year 2000 fallback.

### Building Replacement Detection (2025-12-22) - IMPLEMENTED

Centroid-containment matching, `repl_by`/`repl_of` tracking, `demolished` flag.

### Road Temporal Network (2025-12-22) - IMPLEMENTED

LSS-Hausdorff matching, building-based date inference.

### Year Step Buttons (2025-12-22) - IMPLEMENTED

Timeline navigation with ◀ ▶ buttons.
