# Feature: Timeline UI

Interactive timeline interface for navigating Trondheim's historical map from 1700-2025.

## Overview

The timeline UI enables temporal navigation through historical map data, showing features (buildings, roads, water) as they existed at any selected year. Users can scrub through time via a slider or animate through years automatically.

## Components

### 1. Year Slider
- **Range**: 1700-2025
- **Step**: 1 year increments
- **Default**: 2020 (modern baseline)
- **Key markers**: 1700, 1800, 1850, 1900, 1950, 2000, 2025
- **Behavior**: Updates map on `change` event, shows preview on `input` event

### 2. Year Display
- **Location**: Prominent header position
- **Format**: Large numeric display (e.g., "1880")
- **Update**: Real-time as slider moves or animation plays

### 3. Play/Pause Control
- **Function**: Auto-advances through years
- **Speed**: 5 years per second (configurable)
- **Behavior**:
  - Stops at `maxYear` (2025)
  - Manual slider interaction pauses animation
  - Resets to `minYear` if played from end

### 4. Era Indicator
Contextual information about the selected time period:
- **Era name**: "Early 19th Century", "Late 20th Century", etc.
- **Data sources**: "SEFRAK + Kartverket Historical", "OpenStreetMap", etc.
- **Feature count**: "~142 buildings visible" (approximate, based on rendered features)

### 5. Layer Toggles
- Buildings (temporal, filtered)
- Roads (OSM modern)
- Roads Historical (ML-detected)
- Water bodies
- Confidence overlay (evidence strength visualization)

### 6. Source Filter
Drill down by data source:
- Registry: SEFRAK, Trondheim Kommune, Matrikkelen
- AI-Detected: ML (with sub-filters: Kartverket 1880/1904, Aerial 1947)
- Modern: OpenStreetMap

Shows feature counts per source for transparency.

## Filtering Logic

### Core Temporal Filter

Features are visible if:
```
start_date <= selectedYear AND (end_date is null OR end_date > selectedYear)
```

- `start_date`: Year feature first appeared
- `end_date`: Year demolished (null = still exists)
- Properties stored in GeoJSON as `sd` (start_date), `ed` (end_date)

### Implementation (MapLibre Expression)
```javascript
[
  'all',
  ['any', ['!has', 'sd'], ['<=', 'sd', year]],
  ['any', ['!has', 'ed'], ['>=', 'ed', year]]
]
```

## Era-Based Rules

Stricter evidence requirements for older dates to avoid false positives:

| Era | Rule | Rationale |
|-----|------|-----------|
| **Post-1950** | Show all buildings | Modern OSM baseline is reliable |
| **1900-1950** | Strong evidence OR undated modern | Registry + ML verification available |
| **Pre-1900** | Strong evidence ONLY with date | Require SEFRAK date or high-confidence ML |

### Evidence Levels

| Level | Code | Criteria |
|-------|------|----------|
| **High** | `ev='h'` | SEFRAK registry OR multiple ML sources agree |
| **Medium** | `ev='m'` | Single ML source |
| **Low** | `ev='l'` | OSM only, no historical verification |

### Implementation (MapLibre Expression)
```javascript
// Pre-1900 filter (strictest)
[
  'all',
  ['==', ['get', 'ev'], 'h'],
  ['has', 'sd'],
  ['<=', ['get', 'sd'], year]
]

// 1900-1950 filter
[
  'any',
  ['!has', 'sd'],  // Undated modern buildings
  ['all', ['==', ['get', 'ev'], 'h'], ['<=', ['get', 'sd'], year]]
]

// Post-1950 filter (no era restriction)
true
```

## Visual Feedback

### Current Year
- Large, clear numeric display
- Updates in real-time during animation
- Color emphasis on era transitions (e.g., crossing 1900 threshold)

### Era Name
Provides historical context:
- 1700-1749: Early 18th Century
- 1750-1799: Late 18th Century
- 1800-1849: Early 19th Century
- 1850-1899: Late 19th Century
- 1900-1949: Early 20th Century
- 1950-1999: Late 20th Century
- 2000+: 21st Century

### Data Sources
Shows which sources contribute to current view:
- Pre-1900: "SEFRAK (Riksantikvaren)"
- 1800-1950: "SEFRAK + Kartverket Historical"
- 1950+: "SEFRAK + Kartverket + OpenStreetMap"

### Feature Counts
- **Method**: Query rendered features via `map.queryRenderedFeatures({ layers: ['buildings'] })`
- **Display**: "~142 buildings visible"
- **Note**: Approximate count (viewport-dependent), but gives scale of data

### Historical Styling
Visual feedback indicating distance from present:

| Period | Style |
|--------|-------|
| **Modern (1950+)** | Standard colors, full opacity |
| **Historical (pre-1950)** | Sepia tones, varied by age |
| **Very old (pre-1850)** | Dark sepia (#b89968) |

Colors interpolate based on `start_date`:
```javascript
'fill-color': [
  'interpolate', ['linear'],
  ['coalesce', ['get', 'start_date'], year],
  1850, '#b89968',  // Dark sepia
  1900, '#c9a876',  // Medium sepia
  1950, '#d4a373',  // Light tan
  2000, '#d4a373'   // Modern
]
```

## Animation

### Play Mode
- **Trigger**: Click "Play Timeline" button
- **Speed**: 5 years/second (configurable in code)
- **Frame rate**: Uses `requestAnimationFrame` for smooth updates
- **Stop conditions**:
  - Reaches `maxYear` (2025)
  - User clicks "Pause"
  - User manually moves slider

### Performance Optimization
- **Modern era (1950+)**: Simplified filter (no era rules) when all sources enabled
- **Debouncing**: Map style updates on slider `change`, not `input` (preview only)
- **Style replacement**: Full `setStyle` call ensures clean state (filters, colors, etc.)

## Dependencies

### Upstream
- **feat_temporal_pipeline**: Consumes temporal dataset
  - Requires `buildings_v2.geojson` with temporal attributes (`sd`, `ed`, `ev`, `src`)
  - Requires `roads_temporal.geojson` with historical roads
  - Requires `sources_manifest.json` for inspection mode

### Downstream
None (consumer feature)

### Technical
- **MapLibre GL JS** 3.x: Vector map rendering
- **PMTiles**: Efficient tile serving (for OSM base layers)
- **Modern JavaScript**: ES6+ features (no build step)

## File References

Implementation in:
- `/Users/vaskinn/Development/private/historymap/frontend/app.js`
  - Lines 609-630: `createTemporalFilter()` - core filtering logic
  - Lines 699-747: `createBuildingFilter()` - era-based rules
  - Lines 1351-1397: `startAnimation()` / `stopAnimation()` - play controls
  - Lines 1401-1438: `updateEraIndicator()` - visual feedback
- `/Users/vaskinn/Development/private/historymap/frontend/index.html`
  - Lines 61-77: Year slider UI
  - Lines 79-84: Play/pause button
  - Lines 47-59: Era indicator panel
- `/Users/vaskinn/Development/private/historymap/frontend/style.css`
  - Styling for timeline controls

## Status

- [x] Year slider with temporal filtering
- [x] Play/pause animation
- [x] Era indicator with context
- [x] Layer toggles
- [x] Source filtering with counts
- [x] Era-based evidence rules (pre-1900 strictness)
- [x] Historical styling (sepia tones)
- [x] Confidence overlay mode
- [x] Feature count display
- [x] Inspection mode (single-source view)
- [ ] Keyboard shortcuts (space = play/pause, arrow keys = step)
- [ ] Speed control (2x, 5x, 10x)
- [ ] Bookmark/permalink for specific years
- [ ] Mobile-responsive timeline UI
