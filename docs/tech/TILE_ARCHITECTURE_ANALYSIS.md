# Tile Generation Architecture Analysis

**Date**: 2026-01-04
**Author**: GIS Architecture Agent

## Executive Summary

This document analyzes the current tile generation architecture for the Trondheim Historical Map project and provides recommendations for improvements, particularly for offline/local development needs.

## Current Architecture

### 1. Vector Tiles (PMTiles)

**Technology**: PMTiles (cloud-optimized vector tiles)
**Tool**: Tippecanoe
**Status**: Fully implemented and working

#### Vector Data Sources

| Data Type | Source File | Output PMTiles | Size | Status |
|-----------|-------------|----------------|------|--------|
| Buildings (temporal) | data/export/buildings.geojson | buildings_temporal.pmtiles | 12 MB | Active |
| Buildings (legacy) | data/export/buildings.geojson | buildings.pmtiles | 12 MB | Legacy |
| Base map (OSM) | - | trondheim.pmtiles | 24 MB | Active |
| Water features | data/export/water.geojson | water.pmtiles | 4.8 KB | Active |

#### Generation Pipeline

```
GeoJSON (normalized)
    ↓
[export_pmtiles.py] → Uses tippecanoe
    ↓
PMTiles (vector tiles archive)
    ↓
Served via nginx with range request support
    ↓
MapLibre GL JS + PMTiles protocol
```

**Key Features**:
- Zoom levels: 10-16 (city to building detail)
- Temporal attributes preserved: `sd`, `ed`, `ev`, `src`
- Full detail at max zoom (no simplification)
- Drop-densest-as-needed for tile size management
- Cache busting via manifest.json with file hashes

**Configuration** (from export_pmtiles.py):
```bash
tippecanoe
  --minimum-zoom 10
  --maximum-zoom 16
  --full-detail 16
  --drop-densest-as-needed
  --extend-zooms-if-still-dropping
  --attribute-type=sd:int
  --attribute-type=ed:int
  --attribute-type=mlc:float
  --accumulate-attribute=src:comma
  --maximum-tile-features 200000
  --maximum-tile-bytes 500000
  --buffer 5
```

### 2. Raster Tiles (Historical Maps)

**Technology**: WMS (Web Map Service) via proxy
**Status**: Partially implemented

#### Raster Data Sources

| Source | Type | Year | Implementation | Status |
|--------|------|------|----------------|--------|
| Kartverket 1880 | Mosaic (PNG images) | 1880 | ImageOverlay (MapLibre) | Configured |
| Kartverket 1904 | Single image | 1904 | ImageOverlay (MapLibre) | Configured |
| Aerial 1947 | XYZ Tiles | 1947 | Tile source | Configured |
| Geonorge WMS | WMS service | Various | Proxied via nginx | Active |
| Trondheim Kommune WMS | WMS service | Various | Proxied via nginx | Active |

#### WMS Configuration (nginx.conf)

```nginx
# Geonorge historical maps
location /wms/geonorge/ {
    proxy_pass https://wms.geonorge.no/skwms1/;
    proxy_cache_valid 200 1d;
}

# Trondheim Kommune rasters
location /wms/trondheim/ {
    proxy_pass https://kart.trondheim.kommune.no/geoserver/;
    proxy_cache_valid 200 1d;
}
```

**Frontend Usage** (app.js):
```javascript
// WMS sources converted to XYZ tiles via transformRequest
const wmsUrl = `${baseUrl}?service=WMS&version=1.1.1&request=GetMap` +
    `&layers=${layers}&styles=&srs=EPSG:4326` +
    `&bbox={bbox-epsg-4326}&width=256&height=256&format=image/png`;
```

**Issue**: WMS sources are external services, not suitable for offline use.

#### Local Raster Storage

**Sources Manifest** (frontend/data/sources_manifest.json):
```json
{
  "kv1880": {
    "raster": {
      "type": "mosaic",
      "images": [
        {"url": "../data/sources/ml_detected/kartverket_1880/rasters/tile_000_000.png", ...}
      ]
    }
  },
  "air1947": {
    "raster": {
      "type": "tiles",
      "url": "../data/sources/ml_detected/aerial_1947/rasters/tiles/{z}/{x}/{y}.png"
    }
  }
}
```

**Issue**: Raster directories exist in config but not on filesystem.

### 3. Serving Architecture

**Current Setup**:
```
nginx (port 8080)
├── /               → frontend/ (HTML, JS, CSS)
├── /data/          → frontend/data/ (symlink to data/export/)
├── /wms/geonorge/  → WMS proxy (external)
├── /wms/trondheim/ → WMS proxy (external)
└── /api/           → backend:5000 (FastAPI)
```

**Docker Volumes**:
```yaml
web:
  volumes:
    - ./frontend:/usr/share/nginx/html:ro
    - ./data:/usr/share/nginx/html/data:ro
    - ./nginx.conf:/etc/nginx/conf.d/default.conf:ro
```

**PMTiles Support**:
- Range request headers enabled
- MIME type: `application/octet-stream`
- Cache headers: 30 days (immutable)
- gzip disabled (required for byte-range)

### 4. ML Training Tile Generation

**Tool**: tile_maps.py
**Purpose**: Cut georeferenced GeoTIFFs into training tiles
**Status**: Separate from production pipeline

```python
# For ML training only - not used in frontend
MapTiler(
    tile_size=256,
    overlap=0,
    skip_empty=True,
    empty_threshold=0.95
)
```

**Output**: Individual PNG tiles with geotransform metadata
**Use Case**: ML model training data preparation

## Data Flow

### Vector Data Pipeline

```
1. INGEST
   ├── OSM → data/sources/osm/raw/
   ├── SEFRAK → data/sources/sefrak/raw/
   └── ML detections → data/sources/ml_detected/*/raw/

2. NORMALIZE
   ├── → data/sources/*/normalized/buildings.geojson
   ├── → data/sources/*/normalized/roads.geojson
   └── → data/sources/*/normalized/water.geojson

3. MERGE
   └── → data/merged/buildings_merged.geojson
        (merge_config.json defines rules)

4. EXPORT
   ├── → data/export/buildings.geojson
   ├── → data/export/buildings_temporal.pmtiles (tippecanoe)
   └── → frontend/data/ (symlink or copy)

5. SERVE
   └── nginx → http://localhost:8080/data/*.pmtiles
```

### Raster Data Pipeline

```
1. DOWNLOAD/GEOREFERENCE
   └── Historical maps (GeoTIFF or WMS)

2. TILING (if needed)
   ├── tile_maps.py → ML training tiles (256x256 PNG)
   └── gdal2tiles.py → Web tiles (XYZ pyramid) [NOT IMPLEMENTED]

3. SERVE
   ├── WMS proxy (external services)
   ├── ImageOverlay (single georeferenced images)
   └── XYZ tiles (local file tree) [NOT IMPLEMENTED]
```

## Issues and Gaps

### 1. Raster Tile Generation Missing

**Problem**: No automated pipeline for converting georeferenced historical maps to XYZ tiles.

**Current State**:
- sources_manifest.json references raster files that don't exist
- WMS proxies depend on external services (unreliable for offline)
- No local tile generation for historical maps

**Impact**:
- Cannot work offline with historical map overlays
- Dependent on external WMS services
- No control over raster tile quality/zoom levels

### 2. Raster File Organization

**Problem**: Unclear where georeferenced rasters should live.

**Current State**:
```
data/sources/ml_detected/kartverket_1880/
├── rasters/           # CONFIGURED but EMPTY
├── normalized/        # Vector features (exists)
└── raw/              # ML predictions (exists)
```

**Questions**:
- Where are original georeferenced TIFFs?
- Should rasters be in source directories or separate?
- How to version raster tiles vs vector data?

### 3. Mixed Serving Strategy

**Problem**: Inconsistent approach to raster data.

**Current State**:
- Some rasters via WMS proxy (external)
- Some via ImageOverlay (single images)
- Some via XYZ tiles (configured but not implemented)

**Impact**:
- Confusing architecture
- Different caching strategies
- Hard to debug issues

### 4. Offline Development

**Problem**: Cannot develop offline due to WMS dependencies.

**Current State**:
- WMS services require internet connection
- No local fallback for historical maps
- Development workflow requires external services

**Impact**:
- Cannot work on planes, trains, remote locations
- Dependent on third-party service availability
- Slow development iteration (network latency)

## Recommendations

### Priority 1: Local Raster Tile Generation

**Add**: `scripts/export/export_raster_tiles.py`

```python
#!/usr/bin/env python3
"""
Export georeferenced rasters to XYZ tile pyramid.

Uses GDAL gdal2tiles.py or similar to generate:
- Mercator projection tiles (Web Mercator EPSG:3857)
- Zoom levels 10-16 (matching vector tiles)
- PNG format with transparency
"""

def export_raster_tiles(
    input_geotiff: Path,
    output_dir: Path,
    min_zoom: int = 10,
    max_zoom: int = 16,
    profile: str = 'mercator'
):
    """
    Generate XYZ tile pyramid from georeferenced raster.

    Uses gdal2tiles.py or similar tooling.
    """
    pass
```

**Integration**: Add to pipeline.py export stage

```python
# pipeline.py
def run_export(data_dir, pmtiles=True, raster_tiles=True):
    # ... existing vector export

    if raster_tiles:
        # Generate raster tiles for each historical map source
        export_historical_map_tiles(data_dir)
```

### Priority 2: Raster Data Organization

**Proposed Structure**:
```
data/sources/ml_detected/kartverket_1880/
├── rasters/
│   ├── original.tif              # Original georeferenced raster
│   ├── tiles/                    # XYZ tile pyramid
│   │   ├── 10/                   # Zoom level
│   │   │   ├── 512/              # X coordinate
│   │   │   │   └── 350.png       # Y coordinate
│   │   ├── 11/
│   │   └── ...
│   └── manifest.json             # Tile metadata
├── normalized/                   # Vector features
│   ├── buildings.geojson
│   └── roads.geojson
└── manifest.json                 # Source metadata
```

**Raster Manifest** (rasters/manifest.json):
```json
{
  "source_id": "ml_kartverket_1880",
  "raster_type": "xyz_tiles",
  "generated_at": "2026-01-04T12:00:00Z",
  "original_file": "original.tif",
  "projection": "EPSG:3857",
  "bounds": [10.35, 63.38, 10.45, 63.46],
  "zoom_levels": {
    "min": 10,
    "max": 16
  },
  "tile_count": 1024,
  "total_size_mb": 45.2
}
```

### Priority 3: Unified Raster Serving

**Recommendation**: Standardize on XYZ tiles for all raster sources.

**nginx Configuration**:
```nginx
# Serve raster tiles from source directories
location ~ ^/data/sources/.*/rasters/tiles/ {
    alias /usr/share/nginx/html/data/sources/;
    expires 30d;
    add_header Cache-Control "public, immutable";
    add_header Access-Control-Allow-Origin "*" always;
}
```

**Frontend Code**:
```javascript
// Unified raster tile source
map.addSource('historical-1880', {
  type: 'raster',
  tiles: ['data/sources/ml_detected/kartverket_1880/rasters/tiles/{z}/{x}/{y}.png'],
  tileSize: 256,
  minzoom: 10,
  maxzoom: 16,
  bounds: [10.35, 63.38, 10.45, 63.46]
});
```

**Benefits**:
- Works offline
- Consistent caching
- Better performance
- No external dependencies

### Priority 4: Offline Development Mode

**Add**: Environment variable for development mode

```javascript
// frontend/app.js
const CONFIG = {
    offlineMode: window.location.hostname === 'localhost',

    // Use local tiles in offline mode, WMS in production
    useWMS: !offlineMode,

    rasterSources: offlineMode
        ? 'data/sources/ml_detected/{source}/rasters/tiles/{z}/{x}/{y}.png'
        : '/wms/geonorge/...'
};
```

**Docker Compose Override**:
```yaml
# docker-compose.override.yml (for development)
services:
  web:
    environment:
      - OFFLINE_MODE=true
```

### Priority 5: Documentation

**Create**: `docs/tech/RASTER_TILE_PIPELINE.md`

Document:
- How to add new historical map sources
- Georeferencing process (GDAL tools)
- Tile generation commands
- Testing raster tiles
- Troubleshooting common issues

## Implementation Plan

### Phase 1: Prototype (1-2 days)

1. Test GDAL gdal2tiles.py with one historical map
2. Verify tiles load in MapLibre GL JS
3. Measure tile size and generation time
4. Document process

### Phase 2: Automation (2-3 days)

1. Create `export_raster_tiles.py` script
2. Integrate into pipeline.py
3. Add raster tile generation to rebuild.sh
4. Update sources_manifest.json generation

### Phase 3: Migration (1-2 days)

1. Generate tiles for existing historical maps
2. Update frontend to use local tiles
3. Keep WMS as fallback option
4. Test offline mode

### Phase 4: Documentation (1 day)

1. Write raster tile pipeline docs
2. Update QUICKSTART guides
3. Add troubleshooting section
4. Document performance characteristics

## Commands Reference

### Current Commands

**Generate Vector Tiles**:
```bash
# Full pipeline (includes PMTiles generation)
python scripts/pipeline.py --stage all

# Export only
python scripts/pipeline.py --stage export

# Manual PMTiles generation
python scripts/export/export_pmtiles.py \
  -i data/export/buildings.geojson \
  -o data/export/buildings.pmtiles \
  --min-zoom 10 --max-zoom 16
```

**Start Development Server**:
```bash
# With Docker (serves PMTiles correctly)
docker compose up

# Without Docker (for frontend-only development)
cd frontend && python -m http.server 8080
```

**Test PMTiles**:
```bash
python scripts/export/test_pmtiles.py
```

### Recommended New Commands

**Generate Raster Tiles** (not yet implemented):
```bash
# Generate tiles for a single source
python scripts/export/export_raster_tiles.py \
  --source ml_kartverket_1880 \
  --input data/sources/ml_detected/kartverket_1880/rasters/original.tif \
  --min-zoom 10 --max-zoom 16

# Generate tiles for all sources
python scripts/export/export_raster_tiles.py --all

# Integrate with pipeline
python scripts/pipeline.py --stage export --raster-tiles
```

**Test Raster Tiles**:
```bash
# Verify tile generation
python scripts/export/test_raster_tiles.py --source ml_kartverket_1880

# Check tile coverage
python scripts/export/verify_tile_pyramid.py \
  data/sources/ml_detected/kartverket_1880/rasters/tiles/
```

## Technical Considerations

### Tile Format Selection

| Format | Pros | Cons | Recommendation |
|--------|------|------|----------------|
| **PNG** | Transparency support, lossless | Large file size | Use for historical maps (preserves quality) |
| **JPEG** | Smaller file size | No transparency, lossy | Avoid (need transparency for overlays) |
| **WebP** | Small + transparency | Browser support varies | Future consideration |

**Decision**: Use PNG for historical map tiles (transparency essential for overlays).

### Zoom Level Strategy

**Current Vector Tiles**: Z10-Z16
**Recommended Raster Tiles**: Z10-Z16 (match vector tiles)

**Rationale**:
- Z10: City-level view
- Z13: Street-level view
- Z16: Building-level detail
- Matches existing vector tile zoom range
- Keeps tile count manageable

### Projection Considerations

**Vector Tiles**: EPSG:4326 (WGS84) → converted to Web Mercator by MapLibre
**Raster Tiles**: Should be EPSG:3857 (Web Mercator) for XYZ tiles

**Important**: Historical maps must be georeferenced in EPSG:4326, then reprojected to EPSG:3857 for tiling.

### Storage Estimates

**Per Historical Map Source** (rough estimates):
- Original GeoTIFF: 50-200 MB
- XYZ tiles (Z10-Z16): 30-100 MB
- Total per source: ~100-300 MB

**Total for 3 sources**: ~300-900 MB

**Current disk usage**:
- Vector PMTiles: ~50 MB total
- Raster tiles: 0 MB (not generated)
- **Estimated total with rasters**: ~350-950 MB

**Conclusion**: Storage is acceptable for local development.

### Performance Considerations

**Tile Loading**:
- Local XYZ tiles: <10ms per tile (SSD)
- WMS proxy: 100-500ms per tile (network)
- PMTiles: <5ms per tile (single file, range requests)

**Generation Time**:
- Vector PMTiles: ~30 seconds (tippecanoe)
- Raster XYZ tiles: ~5-10 minutes per source (gdal2tiles)
- Total pipeline: ~30-45 minutes with raster tiles

**Caching**:
- Browser caches tiles aggressively (30 days)
- nginx caches WMS responses (1 day)
- Local tiles don't need caching (instant)

## Conclusion

The current tile architecture is well-designed for vector data (PMTiles) but lacks proper raster tile generation. Key improvements needed:

1. **Add raster tile generation pipeline** (gdal2tiles.py integration)
2. **Organize raster files** (clear directory structure)
3. **Standardize on XYZ tiles** (remove WMS dependency for offline)
4. **Document raster workflow** (georeferencing → tiling → serving)

These improvements will enable:
- Fully offline development
- Faster map loading
- Better control over historical map quality
- Consistent architecture across data types

## References

**File Paths**:
- Vector tile generation: `/Users/vaskinn/Development/private/historymap/scripts/export/export_pmtiles.py`
- Pipeline orchestration: `/Users/vaskinn/Development/private/historymap/scripts/pipeline.py`
- Frontend tile loading: `/Users/vaskinn/Development/private/historymap/frontend/app.js`
- nginx configuration: `/Users/vaskinn/Development/private/historymap/nginx.conf`
- Docker setup: `/Users/vaskinn/Development/private/historymap/docker-compose.yml`

**Documentation**:
- PMTiles quickstart: `/Users/vaskinn/Development/private/historymap/scripts/export/QUICKSTART_PMTILES.md`
- Pipeline architecture: `/Users/vaskinn/Development/private/historymap/docs/tech/DATA_PIPELINE_ARCHITECTURE.md`
- Data sources: `/Users/vaskinn/Development/private/historymap/docs/tech/data_sources.md`

**External Tools**:
- Tippecanoe: https://github.com/felt/tippecanoe
- PMTiles: https://github.com/protomaps/PMTiles
- GDAL: https://gdal.org/programs/gdal2tiles.html
- MapLibre GL JS: https://maplibre.org/maplibre-gl-js-docs/
