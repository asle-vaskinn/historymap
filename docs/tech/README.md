# Technical Architecture

## System Overview

```
┌─────────────────────────────────────────────────────────────┐
│                      DATA SOURCES                            │
├──────────┬──────────┬──────────┬──────────┬────────────────┤
│  SEFRAK  │   OSM    │ Kartverket│  ML      │  Matrikkelen  │
│ Registry │ Buildings│   Maps    │ Pipeline │    API        │
└────┬─────┴────┬─────┴────┬─────┴────┬─────┴───────┬───────┘
     │          │          │          │             │
     ▼          ▼          ▼          ▼             ▼
┌─────────────────────────────────────────────────────────────┐
│              DATA PROCESSING PIPELINE                        │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐        │
│  │ Ingest  │→ │ Normalize│→ │ Merge   │→ │ Export  │        │
│  └─────────┘  └─────────┘  └─────────┘  └─────────┘        │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    OUTPUT FORMATS                            │
│         GeoJSON (dev)  │  PMTiles (prod)                    │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                     FRONTEND                                 │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │  MapLibre   │  │   Controls  │  │   Filters   │         │
│  │  GL JS      │  │   (Year)    │  │  (Era-based)│         │
│  └─────────────┘  └─────────────┘  └─────────────┘         │
└─────────────────────────────────────────────────────────────┘
```

## Technology Stack

### Frontend
- **MapLibre GL JS**: Vector map rendering
- **PMTiles**: Efficient tile storage/serving
- **Vanilla JS**: No framework dependencies

### Data Processing
- **Python 3.x**: Scripts for data processing
- **GDAL/OGR**: Geospatial operations
- **PyTorch**: ML model inference

### ML Pipeline
- **segmentation-models-pytorch**: U-Net architecture
- **ResNet18**: Encoder backbone
- **Training data**: Synthetic rendered tiles

### Infrastructure
- **Docker**: Containerized deployment
- **Nginx**: Static file serving
- **GitHub Actions**: CI/CD (future)

## Data Schema

### Building Properties (Compact)

```
{
  "bid": 12345,        // Building ID (OSM ID)
  "sd": 1880,          // Start date (year built)
  "ed": 1965,          // End date (year demolished/replaced) - optional
  "ev": "h",           // Evidence: h=high, m=medium, l=low
  "src": "sef",        // Source: sef, tk, ml, osm, mat
  "ml_src": "kv1880",  // ML map source (if src=ml): kv1880, kv1904, air1947
  "mlc": 0.85,         // ML confidence (if applicable)
  "bt": "residential", // Building type
  "nm": "Name",        // Building name (if any)
  "dem": 1,            // Demolished flag (if applicable)
  "rep_by": "osm-567", // ID of replacement building (if replaced)
  "rep_ev": "h"        // Evidence strength for replacement
}
```

### Road Properties (Compact)

Roads use ML-inferred temporal bounds (no authoritative registry exists).

```
{
  "rid": "road-12345", // Road ID (OSM way ID or ML-generated)
  "sd": 1880,          // Start date (earliest ML detection)
  "sd_t": "n",         // Start date type: n=nlt (not-later-than), e=net, s=estimated
  "ed": null,          // End date (if road removed/rerouted) - optional
  "ed_t": null,        // End date type
  "ev": "m",           // Evidence: h=high (multi-map), m=medium (single map), l=low
  "src": "ml",         // Source: always "ml" for roads (no registry)
  "ml_src": "kv1880",  // Which map: kv1880, kv1904, air1947
  "mlc": 0.75,         // ML confidence (0-1)
  "rt": "primary",     // Road type from OSM (primary, secondary, tertiary, residential)
  "nm": "Kongens gate" // Road name (if matched to OSM)
}
```

**Key Differences from Buildings:**
- `src` is always "ml" (no SEFRAK/Matrikkelen equivalent for roads)
- `sd_t` field indicates date type (buildings often have exact dates, roads don't)
- Evidence levels based on ML confidence and multi-map detection, not registry presence

### Temporal Visibility Logic

A building or road is visible at year Y if:
- `sd <= Y` (built/existed by this year)
- AND (`ed` is null OR `ed > Y`) (not yet demolished/replaced/removed)

**Note:** For roads with `sd_t: "n"` (not-later-than), the road definitely existed by `sd` but may have existed earlier. For roads with `sd_t: "e"` (not-earlier-than), the road definitely didn't exist before `sd`.

### Evidence Levels

**Buildings:**
| Code | Name | Sources | Use |
|------|------|---------|-----|
| `h` | High | SEFRAK, Matrikkelen, ML detection, OSM+date | Filter pre-1900 |
| `m` | Medium | Style inference, statistical | Filter 1900-1950 |
| `l` | Low | OSM without date | Only post-1950 |

**Roads:**
| Code | Name | Criteria | Use |
|------|------|----------|-----|
| `h` | High | Detected in 2+ historical maps with confidence > 0.8 | Show in all eras |
| `m` | Medium | Detected in 1 map OR confidence 0.5-0.8 | Show 1900+ |
| `l` | Low | OSM only (no historical detection) | Show post-1950 only |

### Source Codes

| Code | Full Name | Description |
|------|-----------|-------------|
| `sef` | SEFRAK | Norwegian cultural heritage registry |
| `tk` | Trondheim Kommune | Municipal records and data |
| `osm` | OpenStreetMap | Community map data |
| `mat` | Matrikkelen | Official property registry |
| `ml` | ML Detection | Model-detected from historical maps |

#### ML Sub-Sources (Map Origins)

When `src` is `ml`, the `ml_src` field identifies which historical map was used:

| Code | Map Source | Year |
|------|------------|------|
| `kv1880` | Kartverket topographic | ~1880 |
| `kv1904` | Kartverket topographic | ~1904 |
| `air1947` | Aerial photography | 1947 |
| `air1964` | Aerial photography | 1964 |

## File Structure

```
historymap/
├── data/
│   ├── buildings_v2.geojson      # Main building data
│   ├── buildings_demolished_v2.geojson
│   ├── roads_temporal.geojson    # Road data with ML-inferred dates
│   ├── trondheim.pmtiles         # OSM base layers
│   ├── kartverket/               # Historical map images
│   └── sefrak/                   # SEFRAK data
├── frontend/
│   ├── index.html
│   ├── app.js
│   ├── style.css
│   └── data/ → ../data/          # Symlinks
├── ml/
│   ├── train.py
│   ├── predict.py
│   └── models/
├── scripts/
│   ├── normalize_with_evidence.py
│   ├── compare_buildings.py
│   └── download_kartverket.py
├── synthetic/
│   ├── render_tiles.py
│   └── styles/
└── docs/
    ├── need/
    ├── spec/
    ├── tech/
    └── todo/
```

## Key Algorithms

### Era-Based Filtering

```javascript
filter: [
  'any',
  // Post-1950: show all
  ['>=', year, 1950],
  // 1900-1950: strong evidence OR modern
  ['all', ['>=', year, 1900], ['<', year, 1950],
    ['any', ['!', ['has', 'sd']],
            ['all', ['==', ['get', 'ev'], 'h'], ['<=', ['get', 'sd'], year]]]],
  // Pre-1900: strong evidence only
  ['all', ['<', year, 1900],
          ['==', ['get', 'ev'], 'h'],
          ['has', 'sd'],
          ['<=', ['get', 'sd'], year]]
]
```

### ML Building Matching

```python
def match_buildings(ml_buildings, osm_buildings):
    # For each ML-detected building:
    # 1. Find OSM buildings with overlapping bounding box
    # 2. Check centroid containment
    # 3. Score overlap (0-1)
    # 4. Match if score > 0.5
```

## Performance Considerations

### Current (Development)
- GeoJSON: ~19MB for 44k buildings
- Initial load: 2-3 seconds
- Acceptable for development

### Production (Future)
- Convert to PMTiles for streaming
- Only load visible tiles
- Target: <500ms initial load
