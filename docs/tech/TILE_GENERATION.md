# Tile Generation Guide

This document covers generating map tiles for local/offline use in the Trondheim Historical Map project.

## Overview

The project uses two types of tiles:

| Type | Format | Tool | Use Case |
|------|--------|------|----------|
| **Vector** | PMTiles | Tippecanoe | Buildings, roads, water (temporal data) |
| **Raster** | XYZ/PMTiles | gdal2tiles | Historical scanned maps |

## Quick Start

```bash
# Vector tiles (buildings, roads, water)
./rebuild.sh

# Raster tiles (historical maps)
./scripts/generate_raster_tiles.sh
```

---

## Vector Tiles

### Standard Workflow

The build pipeline automatically generates vector PMTiles:

```bash
# Full rebuild
./rebuild.sh

# Export stage only
PYTHONPATH=scripts python3 scripts/pipeline.py --stage export

# Skip PMTiles (GeoJSON only)
./rebuild.sh --no-pmtiles
```

### Output Files

| File | Size | Content |
|------|------|---------|
| `data/export/buildings_temporal.pmtiles` | ~12 MB | Building footprints with temporal attributes |
| `data/export/trondheim.pmtiles` | ~24 MB | OSM base map |
| `data/export/water.pmtiles` | ~5 KB | Water features |

### Manual Tippecanoe Usage

```bash
tippecanoe \
  -o output.pmtiles \
  -l buildings \
  -Z 10 -z 16 \
  --drop-densest-as-needed \
  --extend-zooms-if-still-dropping \
  -y sd -y ed -y ev -y src -y nm \
  --attribute-type=sd:int \
  --attribute-type=ed:int \
  input.geojson
```

### Key Options

| Option | Purpose |
|--------|---------|
| `-Z`, `-z` | Min/max zoom levels |
| `-l` | Layer name |
| `-y` | Include only specified attributes |
| `--drop-densest-as-needed` | Smart feature dropping |
| `--attribute-type` | Type hints for filtering |

---

## Raster Tiles

### Prerequisites

```bash
# Install GDAL (includes gdal2tiles)
brew install gdal

# Optional: rio-pmtiles for PMTiles output
pip install rio-pmtiles

# Optional: pmtiles CLI
brew install pmtiles
```

### Generate Tiles

```bash
# All georeferenced maps
./scripts/generate_raster_tiles.sh

# Specific map
./scripts/generate_raster_tiles.sh trondheim_1868

# With PMTiles output
./scripts/generate_raster_tiles.sh --pmtiles trondheim_1868

# Custom zoom levels
./scripts/generate_raster_tiles.sh --min-zoom 8 --max-zoom 18 trondheim_1868
```

### Output Structure

```
data/export/tiles/
├── trondheim_1868/
│   ├── 10/
│   │   ├── 541/
│   │   │   ├── 282.png
│   │   │   └── ...
│   │   └── ...
│   ├── 11/
│   ├── ...
│   └── metadata.json
├── trondheim_1909/
└── ...
```

### Manual gdal2tiles Usage

```bash
gdal2tiles.py \
  --profile=mercator \
  --zoom=10-17 \
  --resampling=lanczos \
  --tiledriver=PNG \
  --processes=4 \
  --webviewer=none \
  input.tif \
  output_directory/
```

### Key Options

| Option | Purpose |
|--------|---------|
| `--profile` | `mercator` (web maps), `geodetic` (WGS84), `raster` (local) |
| `--zoom` | Zoom range (e.g., `10-17`) |
| `--resampling` | `lanczos` (sharp), `bilinear` (smooth), `average` (fast) |
| `--tiledriver` | `PNG` (transparency), `WEBP` (smaller), `JPEG` (photos) |
| `--processes` | Parallel processing |

---

## Serving Tiles Locally

### PMTiles (Recommended)

No server needed - works directly with MapLibre:

```javascript
import * as pmtiles from 'pmtiles';

const protocol = new pmtiles.Protocol();
maplibregl.addProtocol('pmtiles', protocol.tile);

// Vector tiles
map.addSource('buildings', {
  type: 'vector',
  url: 'pmtiles://data/buildings_temporal.pmtiles'
});

// Raster tiles (if converted to PMTiles)
map.addSource('historical', {
  type: 'raster',
  url: 'pmtiles://data/trondheim_1868_raster.pmtiles'
});
```

### XYZ Tile Directory

For directory-based tiles:

```javascript
map.addSource('historical', {
  type: 'raster',
  tiles: ['/data/tiles/trondheim_1868/{z}/{x}/{y}.png'],
  tileSize: 256,
  minzoom: 10,
  maxzoom: 17
});
```

### Docker/nginx

The project's nginx config serves tiles from `data/export/`:

```nginx
location /data/tiles/ {
    alias /usr/share/nginx/html/data/tiles/;
    expires 30d;
    add_header Cache-Control "public, immutable";
}
```

---

## Input Requirements

### For Vector Tiles

- **Format**: GeoJSON (FeatureCollection)
- **CRS**: EPSG:4326 (WGS84)
- **Properties**: Any JSON-serializable attributes

### For Raster Tiles

- **Format**: GeoTIFF (georeferenced)
- **CRS**: Any (converted to Web Mercator)
- **Bit depth**: 8-bit recommended (16-bit will be scaled)

### Checking GeoTIFF

```bash
# Check if georeferenced
gdalinfo input.tif | grep "Coordinate System"

# Check CRS
gdalinfo input.tif | grep "EPSG"

# Check bounds
gdalinfo -json input.tif | jq '.wgs84Extent'
```

---

## Troubleshooting

### "GeoTIFF not georeferenced"

The input file lacks spatial reference. Use the Source Manager to add GCPs and run georeferencing first.

### "Black edges on tiles"

Use PNG format (not JPEG) to preserve transparency:
```bash
gdal2tiles.py --tiledriver=PNG ...
```

### "Tiles look pixelated"

Increase max zoom or use better resampling:
```bash
gdal2tiles.py --zoom=10-18 --resampling=lanczos ...
```

### "Out of memory"

Reduce parallel processes:
```bash
gdal2tiles.py --processes=2 ...
```

### "PMTiles not loading"

1. Check protocol is registered before map init
2. Verify file path is correct
3. Check browser console for CORS errors

---

## File Sizes (Estimates)

| Map | XYZ Tiles (z10-17) | PMTiles |
|-----|-------------------|---------|
| trondheim_1868 (428 MB TIF) | ~200 MB | ~150 MB |
| trondheim_1909 (109 MB TIF) | ~80 MB | ~60 MB |
| trondheim_1936 (65 MB TIF) | ~50 MB | ~40 MB |

Actual sizes depend on map detail and zoom levels.

---

## Related Documentation

- [DATA_PIPELINE_ARCHITECTURE.md](./DATA_PIPELINE_ARCHITECTURE.md) - Full pipeline overview
- [scripts/export/README.md](../../scripts/export/README.md) - Export scripts
- [scripts/export/QUICKSTART_PMTILES.md](../../scripts/export/QUICKSTART_PMTILES.md) - PMTiles quick start
