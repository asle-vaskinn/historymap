# Water Feature Pipeline

## Overview

Extract and display temporal water features showing coastal changes in Trondheim from 1700 to present. Tracks land reclamation (filled areas) and water feature changes over time.

**Status:** Phase 1 (Pipeline Integration) - IN PROGRESS

## Architecture

```
Data Sources
    ├─ OSM (current baseline, 2024)
    ├─ Manual Tracing (historical fills)
    └─ ML Extraction (future, automated)
            ↓
    Merge (combine sources, resolve conflicts)
            ↓
    Export (GeoJSON + PMTiles)
            ↓
    Frontend (temporal layer with sd/ed filtering)
```

## Data Schema

Water features follow the temporal schema established for buildings/roads:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `wtype` | string | Yes | Water type: `river`, `fjord`, `lake`, `canal`, `harbor` |
| `name` | string | No | Feature name if known |
| `sd` | int | Yes | Start date (year water existed from) |
| `ed` | int/null | No | End date (year filled/removed), null if still exists |
| `ev` | string | Yes | Evidence level: `h` (high/OSM), `m` (medium/manual), `l` (low/ML) |
| `src` | string | Yes | Source: `osm`, `man`, `ml` |
| `_raw` | object | No | Original source properties |

**Example: Filled area at Brattøra**
```json
{
  "type": "Feature",
  "geometry": {"type": "Polygon", "coordinates": [...]},
  "properties": {
    "wtype": "fjord",
    "name": "Brattøra",
    "sd": 1700,
    "ed": 1970,
    "ev": "m",
    "src": "man"
  }
}
```

## Phase 1: Pipeline Integration (IN PROGRESS)

### Goal

Integrate water features into the main data pipeline alongside buildings and roads.

### Components

#### 1. OSM Baseline Ingest

**Script:** `scripts/ingest/fetch_osm_water.py`

Fetches current water features from OpenStreetMap via Overpass API.

**Features:**
- Queries `natural=water`, `waterway=*` in Trondheim bbox
- Converts to normalized schema with `sd=2024`, `ed=null`, `ev=h`
- Classifies into water types (river, fjord, lake, canal, harbor)
- Outputs to `data/sources/osm/water.geojson`

**Usage:**
```bash
PYTHONPATH=scripts python3 scripts/ingest/fetch_osm_water.py
```

#### 2. Manual Tracing Tool

**Script:** `scripts/water_editor.py`

Flask web app for manually tracing historical water features from Kartverket maps.

**Features:**
- Runs on port 5002
- MapboxDraw polygon drawing
- Property form: name, wtype, sd, ed, ev
- Save to `data/sources/manual/water.geojson`
- Import OSM baseline as starting point

**Usage:**
```bash
python3 scripts/water_editor.py
# Open http://localhost:5002
```

#### 3. Merge Script (TODO)

**Script:** `scripts/merge_water.py` (to be created)

Combines OSM, manual, and ML sources with conflict resolution.

**Logic:**
- Load all sources: `data/sources/{osm,manual,ml}/water*.geojson`
- Priority: manual > ML > OSM (manual overrides everything)
- Merge overlapping features (same geometry, different temporal ranges)
- Validate required fields: wtype, sd, ev, src
- Output to `data/merged/water.geojson`

**Conflict Resolution:**
- If manual feature overlaps OSM, use manual
- If temporal ranges conflict, keep both (represents uncertainty)

#### 4. Export Script (TODO)

**Script:** `scripts/export/export_water.py` (to be created)

Exports merged water to frontend-ready formats.

**Outputs:**
- `data/export/water.geojson` - Full GeoJSON with all properties
- `data/export/water_temporal.pmtiles` - Vector tiles with temporal attributes

**Field Mapping:**
```python
# Keep all normalized fields
output_props = {
    'wtype': props['wtype'],
    'name': props.get('name', ''),
    'sd': props['sd'],
    'ed': props.get('ed'),
    'ev': props['ev'],
    'src': props['src']
}
```

#### 5. Pipeline Integration (TODO)

**Script:** `scripts/pipeline.py` (modify existing)

Add water support to main pipeline orchestrator.

**Changes:**
- Accept `--feature-type water` flag
- Run water-specific stages: ingest, normalize, merge, export
- Support `--feature-type all` to run buildings, roads, water

**Usage:**
```bash
# Water only
PYTHONPATH=scripts python3 scripts/pipeline.py --stage all --feature-type water

# All features
PYTHONPATH=scripts python3 scripts/pipeline.py --stage all --feature-type all
```

#### 6. Frontend Integration (TODO)

**Files:** `frontend/app.js`, `frontend/layers.js`

Add water layer to main map with temporal filtering.

**Features:**
- Load `water_temporal.pmtiles`
- Filter by `sd <= year && (ed == null || ed > year)`
- Style by `wtype`: rivers (blue lines), fjords/lakes (blue polygons), harbors (dark blue)
- Add to layer toggle UI

## Phase 2: Manual Tracing (PLANNED)

### Goal

Manually trace historical fill areas from Kartverket maps to populate database.

### Key Fill Areas

Priority areas identified from historical research:

| Area | Approx Fill Date | Priority | Map Source |
|------|------------------|----------|------------|
| Brattøra | 1960-1980 | HIGH | Kartverket 1950, 1980 |
| Nedre Elvehavn | 1970-1990 | HIGH | Kartverket 1960, 1990 |
| Ilsvika | 1950-1970 | MEDIUM | Kartverket 1940, 1970 |
| Ravnkloa south | 1920-1940 | MEDIUM | Kartverket 1910, 1950 |
| Skansen area | 1900-1920 | LOW | Kartverket 1880, 1920 |

### Workflow

1. **Start water editor**
   ```bash
   python3 scripts/water_editor.py
   ```

2. **Load historical map**
   - Open http://localhost:5002
   - Select Kartverket map for target year
   - Toggle OSM overlay to see current state

3. **Trace filled area**
   - Click "Draw Polygon" in water mode
   - Draw boundary around area that is currently land but was water
   - Click "Finish"

4. **Set properties**
   - `wtype`: Usually `fjord` for coastal fills
   - `name`: Area name (e.g., "Brattøra")
   - `sd`: Early date when water existed (e.g., 1700)
   - `ed`: Year when filled (e.g., 1970)
   - `ev`: Always `m` for manual tracing

5. **Save and export**
   - Click "Save" (writes to `data/sources/manual/water.geojson`)
   - Run merge and export:
     ```bash
     PYTHONPATH=scripts python3 scripts/merge_water.py
     PYTHONPATH=scripts python3 scripts/export/export_water.py
     ```

6. **Verify on main map**
   - Refresh main map
   - Toggle water layer
   - Use timeline to verify feature appears/disappears correctly

### Quality Guidelines

- **Temporal Accuracy:** Use map dates, not estimates
- **Geometry Precision:** Trace actual water boundary, not approximate
- **Evidence Level:** Always `m` for manual, document source in notes
- **Water Type:** Use specific types (harbor > fjord for port areas)

## Phase 3: ML Extraction (PLANNED)

### Goal

Automate water extraction from historical Kartverket maps using machine learning.

### Approach

#### 1. U-Net Segmentation (Primary Method)

The existing U-Net model is already trained on water features (class 3).

**Model:** `ml/model.py` - U-Net with ResNet34 encoder
**Classes:** 0=background, 1=building, 2=road, **3=water**, 4=forest

**Steps:**

1. **Predict water mask**
   ```bash
   python ml/predict.py \
     --input data/kartverket/1960.tif \
     --output masks/1960_water.png \
     --class-filter 3 \
     --checkpoint models/checkpoints/best_model.pth
   ```

2. **Vectorize to polygons**
   ```bash
   python ml/vectorize.py \
     --input masks/1960_water.png \
     --output data/sources/ml/water_1960.geojson \
     --class-filter 3 \
     --simplify 1.0
   ```

3. **Assign temporal metadata**
   - `sd`: Infer from map date and earlier maps
   - `ed`: Infer from later maps showing fill
   - `ev`: Always `l` for ML extraction
   - `src`: Always `ml`

**Challenges:**
- Water varies by map style (blue shading vs crosshatch)
- Harbors often marked differently than natural water
- Rivers may be thin and hard to detect

#### 2. HSV Color Detection (Fallback)

For maps where ML struggles, use color-based detection.

**Algorithm:**
1. Convert map to HSV color space
2. Define blue water thresholds: H=200-240, S=30-100, V=40-80
3. Apply morphological operations (close, open) to clean noise
4. Extract connected components as water polygons
5. Filter by area (remove tiny artifacts)

**Implementation:** To be added to `ml/color_detect.py`

#### 3. Vectorization Pipeline

**Tool:** `ml/vectorize.py` (existing, supports class filtering)

**Process:**
1. Load binary mask (water = white, background = black)
2. Use `rasterio.features.shapes()` to extract polygons
3. Simplify with Douglas-Peucker (tolerance=1.0m)
4. Merge adjacent polygons with `shapely.unary_union()`
5. Convert to GeoJSON with normalized schema

**Output Schema:**
```json
{
  "type": "Feature",
  "geometry": {"type": "Polygon", "coordinates": [...]},
  "properties": {
    "wtype": "fjord",
    "sd": 1960,
    "ed": null,
    "ev": "l",
    "src": "ml",
    "confidence": 0.85
  }
}
```

#### 4. Integration with Pipeline

**Workflow:**

1. **Batch prediction** across all Kartverket maps
   ```bash
   for map in data/kartverket/*.tif; do
     year=$(basename $map .tif)
     python ml/predict.py --input $map --output masks/${year}_water.png --class-filter 3
     python ml/vectorize.py --input masks/${year}_water.png --output data/sources/ml/water_${year}.geojson
   done
   ```

2. **Temporal inference**
   - Compare consecutive years to detect fills
   - If feature present in 1960 but gone in 1970, set `ed=1965` (midpoint)
   - If feature absent in 1950 but present in 1960, set `sd=1955`

3. **Quality filtering**
   - Confidence threshold: Only keep features with `confidence > 0.7`
   - Size threshold: Remove polygons < 100 sq meters
   - Manual review: Flag ambiguous cases for manual verification

4. **Merge with manual sources**
   - Manual overrides ML for same area
   - Keep ML for areas not manually traced
   - Use ML to suggest areas for manual review

### Validation

- Compare ML output with manual traces (IoU score)
- Visual inspection of random samples
- Test on known fill areas (Brattøra, Nedre Elvehavn)

## Data Sources

### OSM (Current Baseline)

- **Source:** OpenStreetMap via Overpass API
- **Coverage:** Current state only (2024)
- **Evidence:** High (h) - actively maintained, GPS-verified
- **Types:** Rivers, fjords, lakes, harbors
- **Usage:** Baseline for comparison, shows current water extent

### Manual Tracing (Historical Fills)

- **Source:** Kartverket historical maps (1700-2020)
- **Coverage:** Key fill areas only (incomplete)
- **Evidence:** Medium (m) - human interpretation of maps
- **Focus:** Land reclamation, harbor expansion, coastal changes
- **Usage:** High-priority areas, overrides other sources

### ML Extraction (Future)

- **Source:** Automated extraction from Kartverket maps
- **Coverage:** Complete (all maps)
- **Evidence:** Low (l) - automated, needs validation
- **Usage:** Fill gaps, suggest areas for manual review

## Testing Strategy

### Unit Tests

- Validate normalized schema (required fields, valid types)
- Test water type classification logic
- Test temporal conflict resolution in merge

### Integration Tests

- End-to-end: OSM fetch → merge → export → load in map
- Verify temporal filtering (features appear/disappear by year)
- Check geometry validity (no self-intersections, valid polygons)

### Manual QA

- Load Brattøra example (should disappear around 1970)
- Check Nedre Elvehavn (should disappear around 1980)
- Verify timeline navigation shows correct features per year

## File Structure

```
data/
  sources/
    osm/
      water.geojson          # Current OSM water features
    manual/
      water.geojson          # Hand-traced historical fills
    ml/
      water_1960.geojson     # ML-extracted from 1960 map
      water_1970.geojson     # ML-extracted from 1970 map
      ...
  merged/
    water.geojson            # Combined from all sources
  export/
    water.geojson            # Frontend-ready GeoJSON
    water_temporal.pmtiles   # Vector tiles

scripts/
  ingest/
    fetch_osm_water.py       # OSM baseline fetcher
  merge_water.py             # Merge all sources
  export/
    export_water.py          # Export to frontend formats
  water_editor.py            # Manual tracing tool (port 5002)
  pipeline.py                # Main orchestrator (add water support)

ml/
  predict.py                 # U-Net inference (--class-filter 3)
  vectorize.py               # Mask to polygon conversion
  color_detect.py            # HSV fallback (future)

frontend/
  app.js                     # Main map (add water layer)
  layers.js                  # Layer management
```

## Commands Reference

### Phase 1 (Pipeline Integration)

```bash
# Fetch OSM baseline
PYTHONPATH=scripts python3 scripts/ingest/fetch_osm_water.py

# Start manual editor
python3 scripts/water_editor.py

# Run full pipeline (once merge/export scripts exist)
PYTHONPATH=scripts python3 scripts/pipeline.py --stage all --feature-type water

# Run all feature types
PYTHONPATH=scripts python3 scripts/pipeline.py --stage all --feature-type all
```

### Phase 2 (Manual Tracing)

```bash
# Start editor and trace in browser
python3 scripts/water_editor.py
# Then open http://localhost:5002

# After tracing, merge and export
PYTHONPATH=scripts python3 scripts/merge_water.py
PYTHONPATH=scripts python3 scripts/export/export_water.py
```

### Phase 3 (ML Extraction)

```bash
# Single map
python ml/predict.py --input data/kartverket/1960.tif --output masks/1960_water.png --class-filter 3
python ml/vectorize.py --input masks/1960_water.png --output data/sources/ml/water_1960.geojson

# Batch all maps
for map in data/kartverket/*.tif; do
  year=$(basename $map .tif)
  python ml/predict.py --input $map --output masks/${year}_water.png --class-filter 3
  python ml/vectorize.py --input masks/${year}_water.png --output data/sources/ml/water_${year}.geojson
done
```

## Next Steps

1. **Immediate (Phase 1):**
   - Create `scripts/merge_water.py`
   - Create `scripts/export/export_water.py`
   - Update `scripts/pipeline.py` to support water
   - Add water layer to frontend

2. **Short-term (Phase 2):**
   - Trace Brattøra fill area (1960-1980)
   - Trace Nedre Elvehavn (1970-1990)
   - Document tracing workflow with screenshots

3. **Medium-term (Phase 3):**
   - Test U-Net on sample Kartverket maps
   - Implement temporal inference logic
   - Run batch extraction on all historical maps

## References

- Data schema: `docs/tech/DATA_SCHEMA.md`
- Building pipeline: `scripts/merge_buildings.py` (template for water merge)
- Road pipeline: `scripts/merge_roads.py` (similar temporal logic)
- ML model: `ml/model.py` (U-Net with water class 3)
