# Feature: Georeferencing Historical Maps

## Overview

Web-based solution for georeferencing historical maps with an **iterative refinement workflow**. Users place rough control points first, then refine them while seeing live alignment feedback.

## Design Principles

1. **Iterative over perfect** - Start rough, refine as alignment becomes visible
2. **Immediate feedback** - See alignment quality in real-time, not after export
3. **Simple transforms** - Affine/polynomial only, no mesh warping (predictable behavior)
4. **Standard projections** - Auto-detect Norwegian historical projections where possible

## Requirements

### Input
- Historical map images in standard input folder: `data/georeference/input/`
- Manifest file describing available maps: `data/georeference/manifest.json`

### Output
- GCP (Ground Control Point) files: `data/georeference/gcps/{map_id}.gcp.json`
- Georeferenced GeoTIFF files: `data/georeference/output/{map_id}.tif`

## Workflow

### 1. Web-based GCP Editor (`scripts/georef_editor.html`)

**Core Features:**
- Dropdown selector loads maps from manifest (no file upload needed)
- Side-by-side view: historical map + modern OSM reference
- Click-to-place GCPs on historical map
- Click-to-set coordinates on modern map
- Auto-load existing GCPs if present
- Save GCPs to JSON file
- Generate georeferencing command

**Iterative Refinement Features (v2):**

| Feature | Description | Priority |
|---------|-------------|----------|
| **Draggable GCPs** | Drag points on either map to adjust position | High |
| **Live overlay preview** | Semi-transparent historical map over modern, updates in real-time | High |
| **Per-point error display** | Show residual error for each GCP after fitting | High |
| **Undo/redo** | Ctrl+Z/Ctrl+Y for point movements | Medium |
| **Projection hints** | Suggest likely projection based on map date | Medium |

#### Live Overlay Preview

When 3+ GCPs are placed, show the historical map transformed and overlaid on the modern map:

```
┌─────────────────────────────────────────────────┐
│  Modern OSM base map                            │
│  ┌─────────────────────────────────┐            │
│  │  Historical map overlay         │            │
│  │  (50% opacity, affine-warped)   │            │
│  │                                 │            │
│  │  Misaligned areas visible as    │            │
│  │  doubled features               │            │
│  └─────────────────────────────────┘            │
└─────────────────────────────────────────────────┘
```

Controls:
- Opacity slider (0-100%)
- Toggle overlay on/off
- Blend mode options (normal, multiply, difference)

#### Per-Point Error Display

After fitting transform, show residual for each point:

```
GCP List:
├─ GCP1: Nidarosdomen      2.3m ✓
├─ GCP2: Kristiansten      4.1m ✓
├─ GCP3: Gamle Bybro      38.7m ⚠️  ← likely misplaced
└─ GCP4: Torvet            3.2m ✓

Total RMS: 12.4m
```

Color coding:
- Green (✓): < 10m error
- Yellow (⚠️): 10-25m error
- Red (✗): > 25m error

#### Draggable GCPs

Both historical and modern map markers are draggable:

```
Historical map:
  - Drag marker → updates pixel_x, pixel_y
  - Recalculates transform and errors

Modern map:
  - Drag marker → updates geo_x, geo_y
  - Recalculates transform and errors
```

**Usage:**
1. Start server: `python3 -m http.server 8081`
2. Open: `http://localhost:8081/scripts/georef_editor.html`
3. Select map from dropdown
4. Place 3-4 rough GCPs on obvious landmarks
5. Enable overlay preview to see alignment
6. **Drag points** to refine until alignment looks good
7. Add more GCPs if needed for edges/corners
8. Save GCPs and run final georeferencing

### 2. Automated Georeferencing (`scripts/georeference_map.py`)

**Features:**
- GDAL-based polynomial transformation
- Quality metrics (RMS error)
- Multiple CRS support (WGS84, UTM)

**Usage:**
```bash
python scripts/georeference_map.py \
  --input data/georeference/input/trondheim_1909.jpg \
  --gcps data/georeference/gcps/trondheim_1909.gcp.json \
  --output data/georeference/output/trondheim_1909.tif
```

## File Structure

```
data/georeference/
├── manifest.json          # Map catalog
├── input/                 # Raw historical maps
│   ├── trondheim_1868.jpg
│   ├── trondheim_1909.jpg
│   └── ...
├── gcps/                  # Ground Control Points
│   ├── trondheim_1909.gcp.json
│   └── ...
└── output/                # Georeferenced GeoTIFFs
    ├── trondheim_1909.tif
    └── ...
```

## GCP File Format

```json
{
  "version": "1.0",
  "map_id": "trondheim_1909",
  "map_date": 1909,
  "crs": "EPSG:4326",
  "source_file": "trondheim_1909.jpg",
  "gcps": [
    {
      "id": "GCP1",
      "pixel_x": 5000,
      "pixel_y": 3000,
      "geo_x": 10.3969,
      "geo_y": 63.4269,
      "description": "Nidarosdomen spire"
    }
  ]
}
```

## Recommended GCP Placement

For Trondheim maps, use these stable landmarks:

| Landmark | Coordinates (lat, lon) |
|----------|------------------------|
| Nidarosdomen | 63.4269, 10.3969 |
| Vår Frue kirke | 63.4308, 10.3952 |
| Kristiansten Festning | 63.4280, 10.4115 |
| Gamle Bybro (north end) | 63.4283, 10.3985 |
| Torvet | 63.4305, 10.3950 |

## Quality Guidelines

- Minimum 4 GCPs required
- 6-10 GCPs recommended for good accuracy
- Spread GCPs across map extent (corners + center)
- Use stable landmarks (churches, bridges, fortifications)
- Target RMS error < 10 meters for city maps

## Projection Detection

Norwegian historical maps used different projections over time. The editor should suggest the likely projection based on map date:

### Norwegian Projection History

| Period | Projection | Prime Meridian | Notes |
|--------|------------|----------------|-------|
| Pre-1845 | Local surveys | Various | Often no consistent projection |
| 1845-1900 | Cassini | Kongsvinger/local | Square-mile maps (kvadratmilkart) |
| 1870-1950 | Cassini | Oslo | Rectangle maps (rektangelkart) |
| 1900-1960 | NGO1948 | Oslo (Christiania) | EPSG:4817 for geographic coords |
| Post-1980 | UTM/ETRS89 | Greenwich | Modern standard EPSG:25832 |

### Projection Hints in Editor

Based on `map_date` in manifest, show suggested projection:

```javascript
function suggestProjection(mapDate) {
  if (mapDate < 1845) return { crs: 'EPSG:4326', note: 'Pre-survey era - use WGS84' };
  if (mapDate < 1900) return { crs: 'EPSG:4326', note: 'Cassini origin - may need local adjustment' };
  if (mapDate < 1960) return { crs: 'EPSG:4817', note: 'NGO1948 - Oslo meridian' };
  return { crs: 'EPSG:4326', note: 'Modern projection' };
}
```

### Handling Oslo Meridian (NGO1948)

Maps from 1900-1960 often use Oslo meridian (10°43'22.5"E from Greenwich). The editor should:

1. Detect if coordinates are relative to Oslo meridian (longitudes near 0° instead of 10°)
2. Offer automatic conversion: `geo_x_wgs84 = geo_x_oslo + 10.7229167`
3. Store original coordinates in `_raw` for reference

### Transform Types

| Type | Min GCPs | Use Case |
|------|----------|----------|
| Affine (1st order) | 3 | Uniform scale/rotation, minimal distortion |
| Polynomial 2nd | 6 | Moderate distortion (paper warping) |
| Polynomial 3rd | 10 | Significant distortion (rarely needed) |

**Default: Affine (1st order)** - Simple, predictable, handles most cases.

Only use higher-order polynomials if:
- Affine gives > 20m RMS error
- Visible systematic distortion pattern
- Sufficient well-distributed GCPs

## Technical Implementation

### Affine Transform Calculation

For live preview, calculate affine transform from GCPs in browser:

```javascript
// Given GCPs: [{pixelX, pixelY, geoX, geoY}, ...]
// Solve for transform matrix [a, b, c, d, e, f] where:
//   geoX = a*pixelX + b*pixelY + c
//   geoY = d*pixelX + e*pixelY + f

function calculateAffineTransform(gcps) {
  // Least squares solution using normal equations
  // Returns: { matrix: [a,b,c,d,e,f], rmsError: number, residuals: [...] }
}
```

### Error Calculation

Per-point residual in meters:

```javascript
function calculateResidual(gcp, transform) {
  const predictedGeo = applyTransform(gcp.pixelX, gcp.pixelY, transform);
  const dx = (predictedGeo.x - gcp.geoX) * 111320 * Math.cos(gcp.geoY * Math.PI/180);
  const dy = (predictedGeo.y - gcp.geoY) * 110540;
  return Math.sqrt(dx*dx + dy*dy);  // meters
}
```

### Canvas Overlay Rendering

For live preview, transform historical image to overlay on Leaflet:

```javascript
// Option 1: CSS transform on image element (fast, approximate)
// Option 2: Canvas with manual pixel transformation (accurate, slower)
// Option 3: Leaflet.imageOverlay with custom bounds (simplest)

// Recommended: Leaflet.imageOverlay with calculated bounds from affine transform
```
