# Feature: Georeferencing Historical Maps

## Overview

Web-based solution for georeferencing historical maps, with automated or guided workflow.

## Requirements

### Input
- Historical map images in standard input folder: `data/georeference/input/`
- Manifest file describing available maps: `data/georeference/manifest.json`

### Output
- GCP (Ground Control Point) files: `data/georeference/gcps/{map_id}.gcp.json`
- Georeferenced GeoTIFF files: `data/georeference/output/{map_id}.tif`

## Workflow

### 1. Web-based GCP Editor (`scripts/georef_editor.html`)

**Features:**
- Dropdown selector loads maps from manifest (no file upload needed)
- Side-by-side view: historical map + modern OSM reference
- Click-to-place GCPs on historical map
- Click-to-set coordinates on modern map
- Auto-load existing GCPs if present
- Save GCPs to JSON file
- Generate georeferencing command

**Usage:**
1. Start server: `python3 -m http.server 8081`
2. Open: `http://localhost:8081/scripts/georef_editor.html`
3. Select map from dropdown
4. Place 4+ GCPs (Ground Control Points)
5. Save GCPs and run georeferencing

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
