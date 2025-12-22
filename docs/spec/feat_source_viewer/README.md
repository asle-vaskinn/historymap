# Feature: Data Source Viewer

## Problem

When debugging data quality issues, it's difficult to:
- See the original raw data before processing
- Understand what normalization did to the data
- Verify that features are correctly georeferenced
- Isolate issues to a specific source

## Solution

A standalone debug page for inspecting individual data sources with three views:

| View | Purpose |
|------|---------|
| **Raw** | See original source data (raster map for ML sources) |
| **Normalized** | See ML output overlaid on source, colored by confidence |
| **Rendered** | See final styled output on base map to verify placement |

## Scope (Phase 1)

Single source: **Kartverket 1880 (kv1880)**

Future phases can add: kv1904, air1947, sefrak, osm, manual

## User Interface

```
┌─────────────────────────────────────────────────────┐
│  Source: [kv1880 ▼]                    260 buildings │
├─────────────────────────────────────────────────────┤
│  [Raw] [Normalized] [Rendered]                      │
├─────────────────────────────────────────────────────┤
│                                                     │
│                   Map View                          │
│                                                     │
└─────────────────────────────────────────────────────┘
```

## View Details

### Raw View
- Shows the original 1880 Kartverket map raster
- No overlays
- Allows inspection of source material quality

### Normalized View
- Raster background (same as Raw)
- ML-detected building polygons overlaid
- Polygons colored by confidence: red (low) → yellow (medium) → green (high)
- Helps identify false positives and missed detections

### Rendered View
- Minimal base map (Carto Positron) for geographic context
- Building polygons styled as they appear in production
- Verifies correct georeferencing and placement

## Technical Implementation

### Files
- `frontend/source_viewer.html` - standalone page
- `frontend/source_viewer.js` - map logic and view switching
- `frontend/source_viewer.css` - styling

### Data Loading
- Direct GeoJSON fetch (no PMTiles)
- Raster tiles from source manifest

### Dependencies
- MapLibre GL JS (same version as main app)
- Source manifest: `data/sources_manifest.json`

## Acceptance Criteria

- [ ] Page loads at `frontend/source_viewer.html`
- [ ] Dropdown shows kv1880 (single option for now)
- [ ] Raw tab shows 1880 raster map
- [ ] Normalized tab shows raster + confidence-colored polygons
- [ ] Rendered tab shows base map + production-styled polygons
- [ ] Stats bar shows building count
- [ ] Map centers on Trondheim with appropriate zoom

## Future Extensions

- Add source selector with all sources
- Feature table with click-to-inspect
- Diff view showing raw vs normalized properties
- Processing log showing transformation steps
- Side-by-side comparison of two sources
