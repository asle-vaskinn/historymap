# Phase 4: Historical Map Processing Scripts

This directory contains scripts for downloading, georeferencing, and tiling historical maps from Kartverket (Norwegian Mapping Authority).

## Scripts Overview

### 1. download_kartverket.py
Download historical maps from Kartverket's map catalog.

**Features:**
- Search maps by bounding box or place name
- Focus on Amtskart, topographic, and cadastral maps
- Resume capability (skip already downloaded files)
- Save metadata JSON for each map
- Progress reporting

**Usage:**
```bash
# Download maps for Trondheim (default bbox)
python download_kartverket.py

# Download with custom bounding box
python download_kartverket.py --bbox 10.0,63.3,10.8,63.5

# Download by place name
python download_kartverket.py --place Trondheim

# Download specific map types only
python download_kartverket.py --types amtskart topographic

# Limit number of downloads for testing
python download_kartverket.py --max 5

# Force re-download (ignore resume state)
python download_kartverket.py --no-resume
```

**Output:**
- Maps saved to: `../data/kartverket/raw/`
- Metadata saved as: `{uuid}_metadata.json`
- Download state: `download_state.json`

### 2. georeference.py
Align historical maps to modern coordinate systems using ground control points (GCPs).

**Features:**
- Support for manual GCPs via JSON file
- Multiple coordinate reference systems (EPSG:4326, EPSG:25832, etc.)
- RMS error calculation for quality assessment
- Various resampling methods
- Quality report generation

**Usage:**

**Step 1: Create GCP template**
```bash
python georeference.py --create-template my_gcps.json
```

**Step 2: Edit GCP file**
Open `my_gcps.json` and add your ground control points. You'll need to identify at least 3-4 points that you can locate on both the historical map (pixel coordinates) and modern map (geographic coordinates).

Example GCP file:
```json
{
  "crs": "EPSG:4326",
  "gcps": [
    {
      "id": "GCP1",
      "pixel_x": 150,
      "pixel_y": 200,
      "geo_x": 10.3951,
      "geo_y": 63.4305,
      "description": "Church tower"
    },
    {
      "id": "GCP2",
      "pixel_x": 850,
      "pixel_y": 220,
      "geo_x": 10.4089,
      "geo_y": 63.4312,
      "description": "Bridge crossing"
    },
    {
      "id": "GCP3",
      "pixel_x": 420,
      "pixel_y": 780,
      "geo_x": 10.3982,
      "geo_y": 63.4198,
      "description": "Road intersection"
    }
  ]
}
```

**Tips for finding GCPs:**
- Use stable features: churches, bridges, road intersections
- Avoid features that may have moved (buildings can be demolished/rebuilt)
- Spread GCPs across the entire map area
- More GCPs = better accuracy (but diminishing returns after ~10)
- Use QGIS or similar tool to identify coordinates

**Step 3: Georeference the map**
```bash
# Basic georeferencing
python georeference.py map.tif --gcps my_gcps.json

# Specify output path and CRS
python georeference.py map.tif --gcps my_gcps.json \
    --output georef.tif \
    --crs EPSG:25832

# Use different resampling method
python georeference.py map.tif --gcps my_gcps.json \
    --resampling lanczos
```

**Output:**
- Georeferenced GeoTIFF: `{input}_georef.tif`
- Quality report: `{input}_georef.quality.json`

**Quality Assessment:**
The script calculates RMS (Root Mean Square) error:
- < 0.0001 (≈10m): Excellent
- < 0.001 (≈100m): Good
- < 0.01 (≈1km): Acceptable
- > 0.01: Poor (add more GCPs or check accuracy)

### 3. tile_maps.py
Cut georeferenced maps into ML-ready tiles.

**Features:**
- Configurable tile size (256×256, 512×512, etc.)
- Optional overlap between tiles
- Skip empty/border tiles automatically
- Save geographic bounds for each tile
- Batch processing mode

**Usage:**

```bash
# Basic tiling (256×256 tiles)
python tile_maps.py georef.tif --output ../data/kartverket/tiles/

# Larger tiles with overlap
python tile_maps.py georef.tif --tile-size 512 --overlap 64 \
    --output ../data/kartverket/tiles/

# Include all tiles (don't skip empty ones)
python tile_maps.py georef.tif --no-skip-empty \
    --output ../data/kartverket/tiles/

# Batch process entire directory
python tile_maps.py --input-dir ../data/kartverket/georeferenced/ \
    --output-dir ../data/kartverket/tiles/ \
    --tile-size 256
```

**Output:**
- Tiles saved as: `{prefix}_0_{row}_{col}.png`
- Tile index: `{prefix}_tiles.json`

**Tile Naming Convention:**
- `{prefix}`: Map name/identifier
- `0`: Zoom level (placeholder)
- `{row}`: Tile row number
- `{col}`: Tile column number

Example: `trondheim_1900_0_5_12.png`

## Installation

### Prerequisites

**GDAL** is the most important (and sometimes tricky) dependency.

**macOS:**
```bash
brew install gdal
pip install gdal==$(gdal-config --version)
```

**Ubuntu/Debian:**
```bash
sudo apt-get update
sudo apt-get install gdal-bin libgdal-dev
pip install gdal==$(gdal-config --version)
```

**Windows:**
Download pre-built wheels from: https://www.lfd.uci.edu/~gohlke/pythonlibs/#gdal

### Install Python dependencies

```bash
cd scripts
pip install -r requirements_phase4.txt
```

Note: If GDAL installation fails, you may need to install it separately before installing other requirements.

## Complete Workflow Example

Here's a complete example of processing a historical map:

```bash
# 1. Download historical maps
python download_kartverket.py --place Trondheim --max 5

# 2. Create GCP template for the first map
python georeference.py --create-template trondheim_map_gcps.json

# 3. Edit GCP file (use QGIS to find coordinates)
# Open trondheim_map_gcps.json and add your GCPs

# 4. Georeference the map
python georeference.py ../data/kartverket/raw/abc123.tif \
    --gcps trondheim_map_gcps.json \
    --output ../data/kartverket/georeferenced/trondheim_1900.tif \
    --crs EPSG:25832

# 5. Check quality report
cat ../data/kartverket/georeferenced/trondheim_1900.quality.json

# 6. If quality is good, tile the map
python tile_maps.py ../data/kartverket/georeferenced/trondheim_1900.tif \
    --output ../data/kartverket/tiles/trondheim_1900/ \
    --tile-size 256 \
    --overlap 32

# 7. Check tiles
ls -l ../data/kartverket/tiles/trondheim_1900/
cat ../data/kartverket/tiles/trondheim_1900/trondheim_1900_tiles.json
```

## Directory Structure

After running these scripts, your data directory will look like:

```
data/kartverket/
├── raw/                          # Downloaded original maps
│   ├── abc123.tif               # Map image
│   ├── abc123_metadata.json     # Map metadata
│   ├── def456.jp2
│   ├── def456_metadata.json
│   └── download_state.json      # Resume state
├── georeferenced/                # Georeferenced maps
│   ├── trondheim_1900.tif       # GeoTIFF with coordinates
│   └── trondheim_1900.quality.json  # Quality report
└── tiles/                        # Tiled maps
    ├── trondheim_1900/
    │   ├── trondheim_1900_0_0_0.png
    │   ├── trondheim_1900_0_0_1.png
    │   ├── ...
    │   └── trondheim_1900_tiles.json  # Tile index
    └── trondheim_1920/
        └── ...
```

## Tips and Best Practices

### Downloading Maps

1. **Start small**: Use `--max 5` to test before downloading everything
2. **Check metadata**: Review the JSON files to understand what you downloaded
3. **Resume capability**: If download is interrupted, just run again with same parameters

### Georeferencing

1. **Choose good GCPs**:
   - Use stable landmarks (churches, bridges, major intersections)
   - Avoid temporary features
   - Spread across entire map area
   - Include corners if possible

2. **How many GCPs?**:
   - Minimum: 3 (affine transformation)
   - Recommended: 6-10 (good accuracy)
   - More than 15: diminishing returns

3. **Finding coordinates**:
   - Use QGIS with modern basemap (OpenStreetMap)
   - Use norgeskart.no for Norwegian coordinates
   - Google Maps for quick reference (but verify!)

4. **CRS selection**:
   - EPSG:4326 (WGS84): Global, lat/lon, good for web maps
   - EPSG:25832 (UTM 32N): Norwegian standard, meters, good for accuracy
   - EPSG:25833 (UTM 33N): Eastern Norway
   - Use UTM zones for better accuracy in Norway

### Tiling

1. **Tile size**:
   - 256×256: Standard for ML, fast processing
   - 512×512: More context, good for complex features
   - Use powers of 2

2. **Overlap**:
   - 0: No overlap, no duplication
   - 32-64: Good for edge features
   - Too much overlap = more data, slower training

3. **Empty tiles**:
   - Default (skip): Faster, less data
   - Include all: Better for training (if you have negative examples)

## Troubleshooting

### GDAL Import Error
```
ImportError: No module named 'osgeo'
```
**Solution**: Install GDAL properly (see Installation section above)

### Georeferencing RMS Error Too High
**Symptoms**: Quality report shows "poor" or RMS > 0.01

**Solutions**:
1. Check GCP coordinates are correct
2. Add more GCPs, especially in corners
3. Ensure GCPs are well-distributed
4. Verify CRS matches your coordinates

### No Maps Found
**Symptoms**: `download_kartverket.py` finds 0 maps

**Solutions**:
1. Check bounding box is correct (west, south, east, north)
2. Try broader search without bbox
3. Check Kartverket API is accessible
4. Try `--verbose` flag for debugging

### Tiles Are All Black/White
**Symptoms**: All tiles skipped or tiles are blank

**Solutions**:
1. Check input GeoTIFF is valid: `gdalinfo georef.tif`
2. Try `--no-skip-empty` flag
3. Adjust `--empty-threshold`
4. Verify image has data: `gdal_translate -of PNG georef.tif test.png`

## Next Steps

After processing your historical maps:

1. **Manual Annotation** (Phase 4 continued):
   - Select diverse tiles for annotation
   - Use QGIS, Label Studio, or custom tool
   - Annotate 30-50 tiles for fine-tuning

2. **Fine-tuning** (Phase 4):
   - Train model on annotated tiles
   - Use `ml/train.py` with `--fine-tune` flag
   - Lower learning rate for fine-tuning

3. **Batch Extraction**:
   - Run inference on all tiles
   - Vectorize results
   - Merge into GeoJSON

4. **Integration** (Phase 5):
   - Merge with OSM data
   - Generate final PMTiles
   - Deploy to web viewer

## Resources

- **Kartverket Map Catalog**: https://kartkatalog.geonorge.no/
- **Historical Maps**: https://www.kartverket.no/en/order-historical-maps
- **GDAL Documentation**: https://gdal.org/
- **QGIS**: https://qgis.org/ (Free GIS software for finding GCPs)
- **norgeskart.no**: Norwegian national map portal

## License

These scripts are part of the Trondheim Historical Map project.

Historical maps from Kartverket:
- Maps >100 years old: Public domain
- Maps <100 years old: CC BY 4.0

See project LICENSE file for details.
