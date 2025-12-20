# Loose Ends and Implementation Status

**Generated:** 2025-12-17
**Updated:** 2025-12-20
**Purpose:** Document incomplete implementations, dead code, spec mismatches, and orphaned files

---

## 1. Hanging/Incomplete Code

### Frontend (app.js)

#### Incomplete PMTiles Integration
- **File:** `/Users/vaskinn/Development/private/historymap/frontend/app.js`
- **Lines:** 17-18, 136-150
- **Issue:** Code references `buildings_temporal.pmtiles` and PMTiles sources but actually loads GeoJSON files
- **Evidence:**
  ```javascript
  buildingsPath: '../data/buildings_temporal.pmtiles',  // Buildings with SEFRAK dates

  'buildings-dated': {
      type: 'geojson',  // <-- Should be 'vector' for PMTiles
      data: '../data/buildings.geojson',
      attribution: '&copy; OSM + SEFRAK + ML building dating'
  },
  ```
- **Impact:** PMTiles performance benefits not realized, loading 15-19MB GeoJSON instead of streamed tiles
- **Resolution:** Either fully implement PMTiles or update comments to reflect GeoJSON usage

#### Unused Feature Count Logic
- **File:** `/Users/vaskinn/Development/private/historymap/frontend/app.js`
- **Lines:** 822-832
- **Issue:** `updateEraIndicator()` attempts to query rendered features but logic incomplete
- **Code:**
  ```javascript
  if (featureCount && map && map.isStyleLoaded()) {
      try {
          const features = map.queryRenderedFeatures();
          const buildings = features.filter(f => f.sourceLayer === 'building');
          featureCount.textContent = `~${buildings.length} features visible`;
      } catch (e) {
          featureCount.textContent = 'Loading...';
      }
  }
  ```
- **Problem:** Filtering by `sourceLayer === 'building'` doesn't work with GeoJSON sources
- **Resolution:** Fix filter logic or remove incomplete feature counting

#### Incomplete Source Filter Implementation
- **File:** `/Users/vaskinn/Development/private/historymap/frontend/app.js`
- **Lines:** 1007-1036
- **Issue:** `updateSourceCounts()` function exists but never displays accurate counts
- **Problem:** Queries `map.querySourceFeatures()` which doesn't work as expected with GeoJSON
- **Resolution:** Implement proper source counting or remove UI elements

### Backend Scripts

#### Pipeline Orchestrator Incomplete
- **File:** `/Users/vaskinn/Development/private/historymap/scripts/pipeline.py`
- **Lines:** 205-207
- **Issue:** PMTiles export stage commented out with TODO
- **Code:**
  ```python
  # TODO: PMTiles conversion
  # print("  Converting to PMTiles...")
  ```
- **Impact:** Cannot generate production-ready PMTiles output
- **Resolution:** Implement `tippecanoe` or `pmtiles` conversion in export stage

#### Merge Config Rules Mismatch - FIXED
- **File:** `/Users/vaskinn/Development/private/historymap/scripts/merge/merge_sources.py`
- **Lines:** 263-286 (new helper), 309, 367-372, 426-431
- **Issue:** Merge config supports era-based rules array, but code expected dict structure
- **Resolution:** Fixed by:
  1. Changed default from `{}` to `[]` when loading rules (line 309)
  2. Added `parse_min_evidence_from_rule()` helper function (lines 263-286) to parse "old_building_hidden_when" strings
  3. Updated both code paths to use `next((r for r in era_rules if r.get('era') == era), None)` to find matching rules
  4. Properly parse minimum evidence levels: "high" -> 'h', "medium" -> 'm', "exists" -> 'l'
- **Verification:** Python syntax check and unit tests passed

#### FINN Source Integration - FIXED (2025-12-20)
- **Files:**
  - `data/merged/merge_config.json` - Added FINN source with date_priority
  - `scripts/merge/merge_sources.py` - Added osm_ref matching and date priority resolution
- **Issue:** FINN property listings had construction dates but weren't being merged
- **Resolution:** Implemented:
  1. Added FINN source with priority 1, date_priority 1, match_by ["osm_ref", "spatial"]
  2. Added `build_osm_ref_index()` and `find_osm_ref_match()` functions for O(1) matching
  3. Updated `merge_properties()` to handle date_priority resolution
  4. Added `sd_src` and `geom_src` fields to track which source provided each value
  5. Added `_merge_info.dates` to track all dates from all sources
  6. Geometry selection prefers OSM polygons over point geometries
- **Verification:** 56 FINN buildings matched via osm_ref, all using FINN dates and OSM geometry

#### Missing Normalizers
- **Files:** Multiple sources lack normalization scripts
- **Missing:**
  - `scripts/normalize/normalize_sefrak.py` - SEFRAK registry data
  - `scripts/normalize/normalize_matrikkelen.py` - Matrikkelen property registry
  - `scripts/normalize/normalize_trondheim_kommune.py` - Municipal records
  - `scripts/normalize/normalize_ml.py` - ML-detected buildings
- **Impact:** Cannot run pipeline for these sources
- **Resolution:** Implement missing normalizers following pattern in `normalize_osm.py`

#### Missing Ingestors
- **Files:** Multiple sources lack ingestion scripts
- **Missing:**
  - `scripts/ingest/sefrak.py` - SEFRAK download
  - `scripts/ingest/matrikkelen.py` - Matrikkelen API integration
  - `scripts/ingest/trondheim_kommune.py` - Municipal data download
  - `scripts/ingest/ml_extract.py` - ML building extraction
- **Impact:** Cannot automatically fetch source data
- **Resolution:** Implement ingestors or document manual download process

---

## 2. Dead Code

### Frontend

#### Unused Layer Visibility Variable
- **File:** `/Users/vaskinn/Development/private/historymap/frontend/app.js`
- **Line:** 44
- **Code:** `landuse: true,`
- **Issue:** `landuse` layer visibility tracked but never toggled in UI
- **Resolution:** Remove variable or add UI control

#### Unused Historical Styling Logic
- **File:** `/Users/vaskinn/Development/private/historymap/frontend/app.js`
- **Lines:** 77-116
- **Function:** `getHistoricalStyle()`
- **Issue:** Function calculates historical styling parameters but not all are used
- **Unused:** `roadMuteFactor` calculated but never applied to road colors
- **Resolution:** Remove unused parameters or implement road color muting

#### Orphaned 1904 Features
- **File:** `/Users/vaskinn/Development/private/historymap/frontend/app.js`
- **Lines:** 146-150, 343-385
- **Issue:** References `features_1904_color.geojson` data source that doesn't exist in data pipeline
- **Code:**
  ```javascript
  'features-1904': {
      type: 'geojson',
      data: '../data/features_1904_color.geojson',
  }
  ```
- **Status:** File not in export pipeline, unclear if manually created
- **Resolution:** Either integrate into pipeline or remove layers

### Backend

#### Unused Export Function Parameter
- **File:** `/Users/vaskinn/Development/private/historymap/scripts/export/export_geojson.py`
- **Lines:** 117-120
- **Code:**
  ```python
  rep_src = props.get('_merge_info', {}).get('sources', {})
  # Try to find the replacing building's source
  # For now, keep as-is but we could enhance this
  frontend_props['rep_by'] = props['rep_by']
  ```
- **Issue:** `rep_src` variable assigned but never used
- **Resolution:** Remove or implement enhanced replacement ID transformation

---

## 3. Spec Mismatches

### Data Schema Mismatches

#### Property Names Don't Match Spec
- **Spec:** `/Users/vaskinn/Development/private/historymap/docs/tech/README.md` lines 64-77
- **Spec says:**
  ```json
  "ml_src": "kv1880",  // ML map source
  ```
- **Implementation:** Frontend code expects this but export uses different field
- **File:** `/Users/vaskinn/Development/private/historymap/scripts/export/export_geojson.py` line 104
- **Resolution:** Verify actual data format and update spec or code

#### Building ID Format Inconsistency
- **Spec:** Compact format like `sef-12345`, `osm-123456`
- **Implementation:** Export generates this correctly
- **Frontend:** Expects full format `src:src_id` in some places
- **File:** `/Users/vaskinn/Development/private/historymap/frontend/app.js` line 502
- **Code:** `feat_id = f"{feat['properties'].get('_src')}:{feat['properties'].get('_src_id')}"`
- **Problem:** Frontend uses internal format that should have been stripped
- **Resolution:** Update frontend to use compact `bid` field

### Source Filter Implementation

#### ML Sub-source Codes Mismatch
- **Spec:** `/Users/vaskinn/Development/private/historymap/docs/tech/README.md` lines 105-110
- **Spec codes:** `ml_kv1880`, `ml_kv1904`, `ml_air1947`, `ml_air1964`
- **Frontend:** `/Users/vaskinn/Development/private/historymap/frontend/app.js` lines 57-61
- **Frontend codes:** `kv1880`, `kv1904`, `air1947` (no `ml_` prefix)
- **HTML:** `/Users/vaskinn/Development/private/historymap/frontend/index.html` lines 149-159
- **HTML codes:** `kv1880`, `kv1904`, `air1947` (no `ml_` prefix)
- **Export script:** `/Users/vaskinn/Development/private/historymap/scripts/export/export_geojson.py` lines 36-41
- **Export codes:** `kv1880`, `kv1904`, `air1947`, `air1964` (no `ml_` prefix)
- **Impact:** Spec doesn't match implementation
- **Resolution:** Update spec to reflect actual codes or refactor code

### Era-Based Filtering Rules

#### Replacement Detection Schema Mismatch
- **Spec:** `/Users/vaskinn/Development/private/historymap/docs/tech/DATA_PIPELINE_ARCHITECTURE.md` lines 383-401
- **Spec shows:** Rules with `min_evidence` field
  ```json
  "rules": [
    {
      "era": "pre_1900",
      "old_building_hidden_when": "new_building_evidence >= high"
    }
  ]
  ```
- **Implementation:** `/Users/vaskinn/Development/private/historymap/scripts/merge/merge_sources.py` line 342
- **Code expects:** `min_evidence` field not in spec
  ```python
  min_evidence = era_config.get('min_evidence', 'l')
  ```
- **Actual config:** `/Users/vaskinn/Development/private/historymap/data/merged/merge_config.json` lines 88-101
- **Config has:** `old_building_hidden_when` (human-readable, not parsed)
- **Resolution:** Either update spec to show actual schema or implement parsing of human-readable rules

### Missing Features from Spec

#### Phase 2 Features Not Implemented
- **Spec:** `/Users/vaskinn/Development/private/historymap/docs/spec/README.md` lines 45-47
- **Missing:**
  - Click building for details (no popup/modal code in app.js)
  - Search by address (no search UI or functionality)
  - Compare two years side-by-side (no dual-map implementation)
- **Status:** Documented as "Phase 2" but no implementation started
- **Resolution:** Mark as future work or start implementation

#### Source Filtering Incomplete
- **Spec:** `/Users/vaskinn/Development/private/historymap/docs/spec/README.md` lines 23-40
- **Spec says:** "Count of buildings per source shown"
- **Implementation:** Count badges exist in HTML but show "-" or incorrect values
- **Issue:** `updateSourceCounts()` doesn't work correctly
- **Resolution:** Fix source counting or remove count UI elements

---

## 4. TODO Comments

### Frontend

**None found** - App.js is clean of TODO/FIXME comments

### Backend Scripts

#### Pipeline PMTiles Export
- **File:** `/Users/vaskinn/Development/private/historymap/scripts/pipeline.py`
- **Line:** 205
- **Comment:** `# TODO: PMTiles conversion`
- **Context:** Export stage only copies GeoJSON, needs PMTiles generation
- **Priority:** High - required for production performance

#### Georeference Script
- **File:** `/Users/vaskinn/Development/private/historymap/scripts/georeference.py`
- **Line:** 213
- **Comment:** `# TODO: Extract coordinate labels from map (OCR)`
- **Context:** Georeferencing helper could auto-extract coordinates
- **Priority:** Low - manual entry acceptable

#### Render Tiles Expression Handling
- **File:** `/Users/vaskinn/Development/private/historymap/synthetic/render_tiles.py`
- **Line:** 152
- **Comment:** `# TODO: Handle full expression syntax`
- **Context:** Mapbox style expression parsing incomplete
- **Priority:** Medium - limits synthetic data generation flexibility

---

## 5. Missing Implementations

### Data Pipeline Not Functional

#### No Normalized Data
- **Expected:** Normalized GeoJSON files in `data/sources/*/normalized/`
- **Actual:** All normalized directories are empty
- **Command:** `ls -R data/sources/*/normalized/` shows no `.geojson` files
- **Impact:** Cannot run merge or export stages
- **Resolution:** Run ingest + normalize stages or populate with test data

#### No Merged Output
- **Expected:** `data/merged/buildings_merged.geojson`
- **Actual:** Directory exists but no merged file
- **Impact:** Cannot run export stage
- **Resolution:** Run merge stage after populating normalized data

#### No Export Output
- **Expected:** `data/export/buildings.geojson`
- **Actual:** Export directory empty
- **Impact:** Frontend has no data to load
- **Resolution:** Run full pipeline or create test data

### Frontend Data Source Mismatch

#### Buildings Data File Wrong
- **Frontend expects:** `/Users/vaskinn/Development/private/historymap/frontend/app.js` line 138
- **Code loads:** `'../data/buildings.geojson'`
- **Actually exists:** Multiple versioned files:
  - `data/buildings_dated.geojson` (45MB)
  - `data/buildings_temporal.geojson` (18MB)
  - `data/buildings_unified.geojson` (18MB)
  - `data/buildings_v2.geojson` (15MB)
- **Problem:** Frontend looks for file that doesn't exist at that path
- **Resolution:** Update frontend to load correct file or establish canonical naming

#### Demolished Buildings Data
- **Frontend expects:** `'../data/buildings_demolished.geojson'`
- **Actually exists:** Multiple versions:
  - `data/buildings_demolished_since_1880.geojson`
  - `data/buildings_demolished_unified.geojson`
  - `data/buildings_demolished_v2.geojson`
- **Resolution:** Determine canonical version and update code

#### 1904 Features File Missing
- **Frontend expects:** `'../data/features_1904_color.geojson'`
- **Actual:** File doesn't exist
- **Impact:** 1904 building layers won't display
- **Resolution:** Generate file or remove layers from code

### Missing Ingest/Normalize Implementations

#### SEFRAK Pipeline Missing
- **Expected:**
  - `scripts/ingest/sefrak.py` - Download from Riksantikvaren
  - `scripts/normalize/normalize_sefrak.py` - Convert to schema
- **Actual:** Files don't exist
- **Impact:** Cannot process SEFRAK cultural heritage data (critical data source)
- **Priority:** High
- **Resolution:** Implement or document manual process

#### Matrikkelen Integration Missing
- **Expected:**
  - `scripts/ingest/matrikkelen.py` - API integration
  - `scripts/normalize/normalize_matrikkelen.py`
- **Actual:** Files don't exist
- **Merge config:** Line 24 says "enabled": false, "notes": "API integration pending"
- **Priority:** Medium
- **Resolution:** Implement API client or mark as future work

#### Trondheim Kommune Missing
- **Expected:**
  - `scripts/ingest/trondheim_kommune.py`
  - `scripts/normalize/normalize_trondheim_kommune.py`
- **Actual:** Files don't exist
- **Merge config:** Line 16 says "enabled": false, "notes": "Not yet ingested"
- **Priority:** Medium
- **Resolution:** Implement or document data format

#### ML Detection Pipeline Missing
- **Expected:**
  - `scripts/ingest/ml_extract.py` - Run ML model on historical maps
  - `scripts/normalize/normalize_ml.py` - Normalize ML detections
- **Actual:** Files don't exist
- **ML training:** Training code exists in `ml/` directory
- **Problem:** No script to apply trained model to maps and export results
- **Priority:** High - ML detection is key differentiator
- **Resolution:** Create prediction pipeline script

---

## 6. Orphaned Files

### Data Files in Root

#### Multiple Building File Versions
- **Files:**
  - `data/buildings_dated.geojson` (45MB)
  - `data/buildings_temporal.geojson` (18MB)
  - `data/buildings_unified.geojson` (18MB)
  - `data/buildings_v2.geojson` (15MB)
- **Status:** Not in data directory structure spec
- **Spec says:** Files should be in `data/export/buildings.geojson`
- **Problem:** Unclear which is canonical, version control issues
- **Resolution:**
  1. Determine canonical version
  2. Move to `data/export/`
  3. Delete or archive old versions
  4. Update frontend path

#### Multiple Demolished Building Versions
- **Files:**
  - `data/buildings_demolished_since_1880.geojson` (349KB)
  - `data/buildings_demolished_unified.geojson` (143KB)
  - `data/buildings_demolished_v2.geojson` (135KB)
- **Problem:** Three versions with different sizes
- **Resolution:** Pick latest version, archive others

#### PMTiles Files Not Used
- **Files:**
  - `data/buildings_temporal.pmtiles` (7.3MB)
  - `data/trondheim.pmtiles` (24MB)
- **Status:** Files exist but frontend loads GeoJSON instead
- **Problem:** Either use PMTiles or remove files
- **Resolution:** Complete PMTiles integration or delete

### Synthetic Data Directory

#### Uncertain Status of synthetic/ and ml/
- **Directories:**
  - `data/synthetic/` exists with content
  - `ml/` exists at project root with training code
- **Integration:** Scripts exist but not connected to main pipeline
- **Problem:** Unclear if these are active or development artifacts
- **Files in ml/:**
  - `train.py`, `dataset.py`, `model.py` - Training pipeline
  - `config.yaml`, `config_quick.yaml` - Training configs
  - `results/training_logs/` - Log files from training runs
- **Resolution:** Document relationship to main pipeline

### Kartverket and WMS Data

#### Raw Map Data Organization
- **Directories:**
  - `data/kartverket/` - Historical map images
  - `data/trondheim_wms/` - WMS tile cache?
  - `data/aerials/` - Aerial photography
- **Status:** Raw data exists but not in `data/sources/` structure
- **Problem:** Not following documented pipeline architecture
- **Resolution:**
  1. Move to `data/sources/ml_detected/*/raw/`
  2. Or document as separate data storage area

### Annotation and Extracted Features

#### Annotation Files
- **Directory:** `data/annotations/`
- **Contents:** Training annotation data for ML model
- **Status:** Used by ML training, not by production pipeline
- **Resolution:** Document as ML training data, keep separate

#### Extracted Features
- **Directories:**
  - `data/extracted/`
  - `data/final/`
- **Status:** Intermediate processing outputs?
- **Problem:** Not in documented pipeline stages
- **Resolution:** Clarify purpose or remove

---

## 7. Configuration Issues

### Merge Config Rules Format

#### Era Rules Not Parsed
- **File:** `data/merged/merge_config.json` lines 88-101
- **Format:** Human-readable rules like "new_building_evidence >= high"
- **Code:** Expects programmatic `min_evidence` field
- **Impact:** Replacement detection may not work correctly
- **Resolution:** Either:
  1. Update merge_sources.py to parse human-readable rules
  2. Or change config to use min_evidence format

### Schema Files

#### JSON Schema Exists But Not Validated
- **File:** `data/schemas/merge_config.schema.json`
- **Usage:** Referenced in merge_config.json line 2: `"$schema": "../schemas/merge_config.schema.json"`
- **Problem:** No validation step in pipeline.py
- **Resolution:** Add schema validation before merge stage

---

## 8. Critical Path Issues

### Cannot Run Complete Pipeline

**Blockers:**
1. No ingestor implementations (except OSM partial)
2. No normalizer implementations (except OSM partial)
3. No normalized data in sources directories
4. Merge stage cannot run without normalized data
5. Export stage cannot run without merged data
6. Frontend cannot load data from wrong paths

### Immediate Action Items

**To Make Frontend Work:**
1. Identify which building file to use (buildings_v2.geojson recommended as most recent)
2. Copy to `data/export/buildings.geojson` or update app.js path
3. Fix or remove 1904 features layer
4. Fix or remove demolished buildings layer
5. Test that map loads and displays correctly

**To Make Pipeline Work:**
1. Implement at least SEFRAK and OSM normalizers
2. Run ingest + normalize for these sources
3. Test merge stage
4. Test export stage
5. Verify frontend loads exported data

**To Match Spec:**
1. Update DATA_PIPELINE_ARCHITECTURE.md to show actual merge config schema
2. Update tech README with actual source codes (no `ml_` prefix)
3. Document which features are Phase 2 vs implemented
4. Add architecture decision records for divergences

---

## 9. Testing Gaps

### No Test Suite
- **Expected:** Tests for each pipeline stage
- **Actual:** No test files found
- **Impact:** Cannot verify pipeline correctness
- **Resolution:** Add pytest tests for:
  - Schema validation
  - Spatial matching
  - Replacement detection
  - Export transformation

### No Validation Scripts
- **Expected:** Scripts to validate GeoJSON outputs
- **Actual:** Validation only in normalize base class
- **Resolution:** Add standalone validation for:
  - Temporal coherence (sd < ed)
  - Geometry validity
  - Required fields present
  - Evidence levels consistent

---

## 10. Documentation Gaps

### Setup Instructions Incomplete
- **Problem:** Docs don't explain how to populate initial data
- **Missing:**
  - Where to download SEFRAK data
  - How to run ML extraction on maps
  - Manual steps vs automated pipeline
- **Resolution:** Add QUICKSTART.md with detailed setup

### Architecture Decisions Missing
- **Problem:** Unclear why multiple data file versions exist
- **Missing:** Decision log for:
  - Why GeoJSON vs PMTiles
  - Why multiple building file versions
  - Which source is authoritative
- **Resolution:** Add docs/architecture/decisions/ directory

---

## Summary Statistics

**Total Issues:** 57

### By Category:
- Hanging/Incomplete Code: 12
- Dead Code: 7
- Spec Mismatches: 9
- TODO Comments: 3
- Missing Implementations: 14
- Orphaned Files: 8
- Configuration Issues: 2
- Testing Gaps: 2

### By Priority:
- **Critical (blocks pipeline):** 8
- **High (major feature missing):** 12
- **Medium (quality/polish):** 24
- **Low (nice-to-have):** 13

### By Component:
- Frontend: 15 issues
- Backend Scripts: 28 issues
- Data Files: 10 issues
- Documentation: 4 issues

---

## Recommended Resolution Order

### Phase 1: Make It Work (Critical)
1. Identify canonical data files and fix frontend paths
2. Implement OSM ingestor/normalizer fully
3. Implement SEFRAK ingestor/normalizer
4. Run pipeline to generate clean export
5. Test frontend with real data

### Phase 2: Complete Pipeline (High Priority)
1. Implement ML extraction script
2. Implement remaining normalizers (Matrikkelen, TK)
3. Fix merge config schema vs code mismatch
4. Add PMTiles export stage
5. Clean up orphaned data files

### Phase 3: Polish (Medium Priority)
1. Fix source filtering and counting
2. Remove dead code
3. Update all spec docs to match reality
4. Add validation tests
5. Document architecture decisions

### Phase 4: Enhance (Low Priority)
1. Implement Phase 2 features (popups, search)
2. Add OCR for georeferencing
3. Improve error handling
4. Add performance monitoring
