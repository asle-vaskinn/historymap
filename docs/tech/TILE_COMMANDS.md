# Tile Generation Commands

Quick reference for tile generation operations in the Trondheim Historical Map project.

## Vector Tiles (PMTiles)

### Full Pipeline

```bash
# Run complete pipeline (ingest → normalize → merge → export → PMTiles)
PYTHONPATH=scripts python3 scripts/pipeline.py --stage all

# Run for specific feature type
PYTHONPATH=scripts python3 scripts/pipeline.py --stage all --feature-type buildings
PYTHONPATH=scripts python3 scripts/pipeline.py --stage all --feature-type roads
PYTHONPATH=scripts python3 scripts/pipeline.py --stage all --feature-type water
```

### Export Only

```bash
# Export GeoJSON and generate PMTiles
PYTHONPATH=scripts python3 scripts/pipeline.py --stage export

# Export GeoJSON only (skip PMTiles generation)
PYTHONPATH=scripts python3 scripts/pipeline.py --stage export --no-pmtiles
```

### Manual PMTiles Generation

```bash
# Default paths (data/export/buildings.geojson → buildings.pmtiles)
python3 scripts/export/export_pmtiles.py

# Custom paths
python3 scripts/export/export_pmtiles.py \
  --input data/export/buildings.geojson \
  --output data/export/buildings_temporal.pmtiles

# With custom zoom levels
python3 scripts/export/export_pmtiles.py \
  --min-zoom 8 \
  --max-zoom 18

# Force overwrite existing file
python3 scripts/export/export_pmtiles.py --force

# With metadata
python3 scripts/export/export_pmtiles.py \
  --name "Trondheim Buildings" \
  --description "Historical building footprints 1700-2025" \
  --attribution "© Kartverket, OpenStreetMap contributors"
```

### Testing

```bash
# Run PMTiles test suite
python3 scripts/export/test_pmtiles.py

# Check if tippecanoe is installed
which tippecanoe
tippecanoe --version
```

## Raster Tiles (Historical Maps)

### Status: NOT YET IMPLEMENTED

The following commands are recommended for future implementation:

```bash
# Generate XYZ tiles from georeferenced GeoTIFF
python3 scripts/export/export_raster_tiles.py \
  --input data/sources/ml_detected/kartverket_1880/rasters/original.tif \
  --output data/sources/ml_detected/kartverket_1880/rasters/tiles/ \
  --min-zoom 10 \
  --max-zoom 16

# Generate tiles for all sources
python3 scripts/export/export_raster_tiles.py --all

# Test raster tile generation
python3 scripts/export/test_raster_tiles.py
```

### Manual GDAL Approach (Current Workaround)

```bash
# Install GDAL tools
brew install gdal

# Generate XYZ tile pyramid
gdal2tiles.py \
  --zoom=10-16 \
  --processes=4 \
  --xyz \
  --webviewer=none \
  data/sources/ml_detected/kartverket_1880/rasters/original.tif \
  data/sources/ml_detected/kartverket_1880/rasters/tiles/

# Verify tile generation
ls -la data/sources/ml_detected/kartverket_1880/rasters/tiles/10/
```

## ML Training Tiles

### Generate Training Tiles from Georeferenced Maps

```bash
# Single map
python3 scripts/tile_maps.py \
  input.tif \
  --output ../data/kartverket/tiles/ \
  --tile-size 256 \
  --skip-empty

# With overlap (for context)
python3 scripts/tile_maps.py \
  input.tif \
  --output ../data/tiles/ \
  --tile-size 512 \
  --overlap 64

# Batch process directory
python3 scripts/tile_maps.py \
  --input-dir ../data/kartverket/georeferenced/ \
  --output-dir ../data/kartverket/tiles/ \
  --tile-size 256
```

## Development Workflow

### Starting Development Server

```bash
# With Docker (recommended - serves all files correctly)
docker compose up

# Access at: http://localhost:8080

# Restart after frontend changes
docker compose restart web

# Restart after backend changes
docker compose restart backend
```

### Rebuilding Data

```bash
# Full rebuild (all stages)
PYTHONPATH=scripts python3 scripts/pipeline.py --stage all

# Copy to frontend directory (if needed)
cp data/export/*.pmtiles frontend/data/
cp data/export/*.geojson frontend/data/
```

### Quick Iteration

```bash
# 1. Edit normalized data
vim data/sources/manual/normalized/buildings.geojson

# 2. Run merge only
PYTHONPATH=scripts python3 scripts/pipeline.py --stage merge

# 3. Export to frontend
PYTHONPATH=scripts python3 scripts/pipeline.py --stage export

# 4. Restart Docker
docker compose restart web

# 5. Refresh browser (Ctrl+Shift+R to bypass cache)
```

## Verification

### Check PMTiles Files

```bash
# List PMTiles in export directory
ls -lh data/export/*.pmtiles

# List PMTiles in frontend directory
ls -lh frontend/data/*.pmtiles

# Check file manifest
cat frontend/data/manifest.json
```

### Test PMTiles Loading

```bash
# Start local server
cd frontend
python3 -m http.server 8080

# Open browser to http://localhost:8080
# Check browser console for errors

# Test range requests
curl -I -H "Range: bytes=0-100" http://localhost:8080/data/buildings_temporal.pmtiles
# Should see: HTTP/1.0 206 Partial Content
```

### Check Raster Sources

```bash
# Check sources manifest
cat frontend/data/sources_manifest.json

# List configured raster sources
jq '.sources | keys' frontend/data/sources_manifest.json

# Check if raster files exist
ls -la data/sources/ml_detected/kartverket_1880/rasters/
```

## Troubleshooting

### PMTiles Not Loading

```bash
# 1. Check if file exists
ls -lh frontend/data/buildings_temporal.pmtiles

# 2. Verify file size (should be ~12MB)
du -h frontend/data/buildings_temporal.pmtiles

# 3. Test with tippecanoe-decode (if installed)
tippecanoe-decode frontend/data/buildings_temporal.pmtiles 14 8425 5140

# 4. Check browser console for errors
# Look for: "Failed to load PMTiles", "Range request failed", etc.

# 5. Regenerate PMTiles
rm frontend/data/buildings_temporal.pmtiles
python3 scripts/export/export_pmtiles.py --force
```

### Tippecanoe Not Found

```bash
# Install on macOS
brew install tippecanoe

# Verify installation
which tippecanoe
tippecanoe --version

# If still not found, check PATH
echo $PATH
```

### WMS Proxy Not Working

```bash
# Test WMS endpoint directly
curl -I "https://wms.geonorge.no/skwms1/wms.historiskekart?service=WMS&version=1.1.1&request=GetCapabilities"

# Test via nginx proxy
curl -I "http://localhost:8080/wms/geonorge/wms.historiskekart?service=WMS&version=1.1.1&request=GetCapabilities"

# Check nginx logs
docker compose logs web | grep wms

# Restart nginx
docker compose restart web
```

### Large File Size

```bash
# Check current size
ls -lh data/export/*.pmtiles

# Reduce max zoom (fewer detail levels)
python3 scripts/export/export_pmtiles.py --max-zoom 14

# Or filter features before export
# Edit merge_config.json to exclude certain sources
```

## Performance Tips

1. **Use Docker for development**: Ensures correct MIME types and range request support
2. **Enable browser caching**: PMTiles are immutable, safe to cache aggressively
3. **Monitor tile requests**: Check Network tab in browser DevTools
4. **Use local tiles for offline**: Generate XYZ raster tiles instead of WMS
5. **Parallel generation**: Use `--processes` flag with GDAL tools

## Next Steps

See `/Users/vaskinn/Development/private/historymap/docs/tech/TILE_ARCHITECTURE_ANALYSIS.md` for:
- Detailed architecture analysis
- Recommendations for raster tile generation
- Implementation plan for offline development
- Technical considerations and storage estimates
