# Feature: Source Filtering

Filter displayed features by their data source to compare registry vs ML data, focus on specific historical periods, and validate ML detections.

## Overview

The source filter enables users to show/hide features based on their provenance:
- **Registry sources**: SEFRAK, Trondheim Kommune, Matrikkelen (authoritative building dates)
- **ML sources**: Buildings/roads detected from historical maps (kv1880, kv1904, air1947)
- **Modern sources**: OpenStreetMap (current baseline)

This allows:
- Comparing ML detections against known historical buildings
- Isolating features from a specific historical map
- Validating ML performance by toggling confidence overlays
- Focusing on authoritative vs inferred data

## Available Sources

### Buildings

| Source Code | Display Name | Type | Description |
|------------|--------------|------|-------------|
| `sef` | SEFRAK | Registry | Norwegian cultural heritage building registry (pre-1900) |
| `tk` | Trondheim Kommune | Registry | Municipal building records |
| `mat` | Matrikkelen | Registry | Norwegian property cadastre |
| `ml` | ML Detection | ML | AI-detected from historical maps (parent filter) |
| `ml.kv1880` | Kartverket 1880 | ML (sub) | Buildings detected in 1880 topographic map |
| `ml.kv1904` | Kartverket 1904 | ML (sub) | Buildings detected in 1904 topographic map |
| `ml.air1947` | Aerial 1947 | ML (sub) | Buildings detected in 1947 aerial photos |
| `osm` | OpenStreetMap | Modern | Current buildings from OSM |

### Roads

Roads have no registry equivalent, so filtering is simpler:

| Source Code | Display Name | Type | Description |
|------------|--------------|------|-------------|
| `ml_kv1880` | Kartverket 1880 | ML | Roads detected in 1880 map |
| `ml_kv1904` | Kartverket 1904 | ML | Roads detected in 1904 map |
| `ml_air1947` | Aerial 1947 | ML | Roads detected in 1947 aerial |
| `osm` | OpenStreetMap | Modern | Modern OSM roads (baseline) |

## UI Components

### Source Filter Panel (Buildings)

Located in left sidebar below layer toggles:

```
┌─────────────────────────────────┐
│ Filter by Source              ▼ │  <- Collapsible header
├─────────────────────────────────┤
│ [All] [None]                    │  <- Quick actions
│                                 │
│ Registry Sources                │
│ ☑ SEFRAK              [1,234]   │  <- Checkbox, color, name, count
│ ☑ Trondheim Kommune   [5,678]   │
│ ☑ Matrikkelen         [891]     │
│                                 │
│ AI-Detected                     │
│ ☑ ML Detection (all)  [456]     │  <- Parent checkbox
│   ☑ Kartverket 1880             │  <- Indented sub-sources
│   ☑ Kartverket 1904             │
│   ☑ Aerial 1947                 │
│                                 │
│ Modern                          │
│ ☑ OpenStreetMap       [12,345]  │
└─────────────────────────────────┘
```

### Source Counts

Counts are computed from cached GeoJSON data (not live map queries):
- Updated once at startup after data loads
- Shows total features per source across all years
- Display "-" if data not yet loaded

### Source Colors

Each source has a visual indicator (small colored square):
- SEFRAK: `#8b6914` (dark ochre)
- Trondheim Kommune: `#2e7d32` (green)
- Matrikkelen: `#1565c0` (blue)
- ML Detection: `#8b4513` (brown)
- OpenStreetMap: `#d4a373` (tan)

## Filter Logic

### Data Model

Building features have two filter properties:
- `src`: Main source (`'sef'`, `'tk'`, `'mat'`, `'ml'`, `'osm'`)
- `ml_src`: ML sub-source (only present if `src='ml'`; values: `'kv1880'`, `'kv1904'`, `'air1947'`)

Road features have one filter property:
- `ml_src`: Source identifier (`'kv1880'`, `'kv1904'`, `'air1947'`, or absent for OSM roads)

### MapLibre Filter Expressions

**Building filter** (combines main source + ML sub-source):

```javascript
function createBuildingFilter(year) {
  // Main source filter
  const srcFilter = createSourceFilter();  // e.g., ['in', ['get', 'src'], ['literal', ['sef', 'ml', 'osm']]]

  // ML sub-source filter (only applies when ml is enabled)
  const mlSrcFilter = createMlSourceFilter();  // e.g., ['in', ['get', 'ml_src'], ['literal', ['kv1880', 'kv1904']]]

  // Era-based filter (temporal evidence rules)
  const eraFilter = ...; // Pre-1900: strong evidence only, etc.

  // Combine all filters
  return ['all', srcFilter, mlSrcFilter, eraFilter];
}
```

**Road filter**:

```javascript
function createRoadFilter(year) {
  const temporalFilter = ...; // sd <= year, ed >= year
  const srcFilter = createRoadSourceFilter();  // ['in', ['get', 'ml_src'], ['literal', ['kv1880']]]
  const eraFilter = ...; // Evidence rules

  return ['all', temporalFilter, srcFilter, eraFilter];
}
```

### Filter State

JavaScript state objects track enabled sources:

```javascript
// Building sources
let sourceFilter = {
  sef: true,
  tk: true,
  mat: true,
  ml: true,   // Parent toggle
  osm: true
};

// ML sub-sources (only applies when sourceFilter.ml = true)
let mlSourceFilter = {
  kv1880: true,
  kv1904: true,
  air1947: true
};

// Road sources
let roadSourceFilter = {
  ml_kv1880: true,
  ml_kv1904: true,
  ml_air1947: true,
  osm: true
};
```

### Implementation (frontend/app.js)

Key functions:
- `createSourceFilter()` - Line 637: Builds filter expression for main sources
- `createMlSourceFilter()` - Line 660: Builds filter for ML sub-sources
- `createRoadSourceFilter()` - Line 753: Builds filter for road sources
- `initSourceFilterControls()` - Line 1548: Sets up UI event handlers
- `updateSourceCounts()` - Line 1634: Updates count badges from cached data
- `setAllSources(enabled)` - Line 1611: Quick "All" / "None" actions

## Use Cases

### 1. Compare ML vs Registry Data

**Scenario**: Verify ML-detected 1880 buildings against SEFRAK registry.

**Steps**:
1. Set year to 1880
2. Disable all sources except SEFRAK and ML (kv1880)
3. Enable "Show Confidence" overlay
4. Compare SEFRAK buildings (green overlay) vs ML buildings (red-yellow-green by confidence)

**Expected**: SEFRAK buildings should have green confidence (authoritative), ML buildings vary.

### 2. Focus on Single Historical Map

**Scenario**: Examine only features from the 1904 Kartverket map.

**Steps**:
1. Click "None" to clear all sources
2. Enable only "Kartverket 1904" (under ML Detection)
3. Set year to 1904

**Expected**: Only buildings/roads detected in the 1904 map are shown.

### 3. Isolate Modern Changes

**Scenario**: See what's been built since 1947.

**Steps**:
1. Set year to 2024
2. Disable all ML sources and SEFRAK
3. Enable only OpenStreetMap

**Expected**: Only modern buildings (no historical detections) are shown.

### 4. Validate ML Performance

**Scenario**: Count how many SEFRAK buildings were successfully detected by ML.

**Steps**:
1. Load buildings data (happens automatically at startup)
2. Check source counts: SEFRAK shows X buildings, ML (kv1880) shows Y buildings
3. Enable only SEFRAK + ML (kv1880)
4. Visually inspect overlap

**Expected**: High spatial overlap indicates good ML performance.

## Dependencies

### Data Requirements

From **feat_temporal_pipeline**:
- Features must have `src` property (source attribution)
- ML features must have `ml_src` property (which historical map)
- Evidence strength (`ev`) and confidence (`mlc`) for validation

### File Dependencies

- `data/buildings_v2.geojson` - Building features with source attributes
- `data/roads_temporal.geojson` - Road features with source attributes
- `frontend/app.js` - Filter logic implementation
- `frontend/index.html` - Source filter UI panel
- `frontend/style.css` - Filter panel styling

### Data Schema

Buildings must have:
```json
{
  "properties": {
    "src": "sef|tk|mat|ml|osm",     // Required
    "ml_src": "kv1880|kv1904|air1947", // Only if src='ml'
    "sd": 1880,                      // Start date
    "ev": "h|m|l",                   // Evidence level
    "mlc": 0.85                      // ML confidence (if applicable)
  }
}
```

Roads must have:
```json
{
  "properties": {
    "ml_src": "kv1880|kv1904|air1947", // Absent for OSM roads
    "sd": 1880,
    "ev": "h|m|l",
    "mlc": 0.78
  }
}
```

## Performance Considerations

### Optimization: Modern Era Fast Path

For post-1950 years with all sources enabled, use simplified filter:

```javascript
if (year >= 1950 && allSourcesEnabled && allMlSourcesEnabled) {
  // No filtering needed - show everything
  return ['has', '$type'];
}
```

This avoids complex filter evaluation when not needed.

### Source Count Caching

Source counts are computed from cached GeoJSON (not live queries):
- `buildingsDataCache` - Loaded at startup via `loadBuildingsData()`
- Counts updated once after data loads
- Avoids expensive `querySourceFeatures()` calls (doesn't work reliably with GeoJSON)

## Status

- [x] Source filter UI panel (collapsible)
- [x] Checkbox controls for main sources
- [x] ML sub-source checkboxes (hierarchical)
- [x] "All" / "None" quick actions
- [x] Source count badges
- [x] MapLibre filter expressions
- [x] Integration with temporal filtering
- [x] Integration with era-based evidence rules
- [x] Road source filtering
- [x] Performance optimization (fast path for modern era)
- [ ] Source filter persistence (localStorage)
- [ ] Filter presets (e.g., "ML only", "Registry only")
- [ ] Advanced filters (confidence threshold sliders)

## Future Enhancements

### Filter Presets

Predefined filter configurations:
- "Show All" - All sources enabled
- "Registry Only" - SEFRAK + Matrikkelen + TK only
- "ML Only" - All ML sub-sources only
- "Validated Only" - SEFRAK + ML with high confidence
- "Modern Only" - OSM only

### Confidence Threshold Slider

Allow filtering ML features by minimum confidence:
```
ML Confidence: [====|----] 70%
```

Only show ML features where `mlc >= 0.7`.

### Source Statistics Panel

Show detailed stats per source:
- Total features
- Features visible at current year
- Average confidence (for ML sources)
- Date range coverage

### Filter State Persistence

Save filter state to `localStorage`:
- Restore user's last filter selection on page load
- Remember collapsed/expanded state
