# Phase 4 Quick Start Guide

## Historical Map Processing Pipeline

This guide walks you through downloading, georeferencing, and tiling historical maps from Kartverket.

### Prerequisites

Install Phase 4 dependencies:

```bash
cd scripts
pip install -r requirements_phase4.txt
```

**Note**: GDAL can be tricky to install. See `scripts/PHASE4_README.md` for platform-specific instructions.

### Quick Test (5 minutes)

Test the complete pipeline with a single map:

```bash
cd scripts

# 1. Download a few test maps
python download_kartverket.py --place Trondheim --max 2

# 2. Create GCP template
python georeference.py --create-template test_gcps.json

# 3. Edit test_gcps.json with your GCPs (use QGIS to find coordinates)
# You'll need to open one of the downloaded maps and identify at least 3 points

# 4. Georeference (replace abc123.tif with your actual file)
python georeference.py ../data/kartverket/raw/abc123.tif \
    --gcps test_gcps.json \
    --output ../data/kartverket/georeferenced/test.tif

# 5. Check quality
cat ../data/kartverket/georeferenced/test.quality.json

# 6. Tile the map
python tile_maps.py ../data/kartverket/georeferenced/test.tif \
    --output ../data/kartverket/tiles/test/ \
    --tile-size 256
```

### Full Pipeline

#### Step 1: Download Historical Maps

```bash
# Download maps for Trondheim area
python download_kartverket.py --place Trondheim

# Or use bounding box
python download_kartverket.py --bbox 10.0,63.3,10.8,63.5

# Download specific map types
python download_kartverket.py --types amtskart topographic
```

**Output**: Maps saved to `../data/kartverket/raw/`

#### Step 2: Georeference Maps

For each downloaded map, you need to create ground control points (GCPs).

**A. Create GCP file:**

```bash
python georeference.py --create-template map_gcps.json
```

**B. Find GCP coordinates:**

1. Open QGIS (free GIS software)
2. Add modern basemap (OpenStreetMap or similar)
3. Open your historical map as raster layer
4. Find identifiable features on both maps:
   - Churches (often unchanged for centuries)
   - Bridges
   - Road intersections
   - Coastline features

5. For each feature:
   - Note pixel coordinates on historical map (x, y from top-left)
   - Note geographic coordinates from modern map (longitude, latitude)

**C. Edit GCP file:**

```json
{
  "crs": "EPSG:4326",
  "gcps": [
    {
      "id": "church_tower",
      "pixel_x": 234,
      "pixel_y": 567,
      "geo_x": 10.3951,
      "geo_y": 63.4305
    },
    {
      "id": "bridge",
      "pixel_x": 789,
      "pixel_y": 456,
      "geo_x": 10.4089,
      "geo_y": 63.4312
    },
    {
      "id": "intersection",
      "pixel_x": 456,
      "pixel_y": 890,
      "geo_x": 10.3982,
      "geo_y": 63.4198
    }
  ]
}
```

**D. Run georeferencing:**

```bash
python georeference.py ../data/kartverket/raw/MAP_FILE.tif \
    --gcps map_gcps.json \
    --output ../data/kartverket/georeferenced/MAP_NAME.tif \
    --crs EPSG:25832
```

**E. Check quality:**

```bash
cat ../data/kartverket/georeferenced/MAP_NAME.quality.json
```

- **Excellent**: RMS error < 0.0001
- **Good**: RMS error < 0.001
- **Acceptable**: RMS error < 0.01
- **Poor**: RMS error > 0.01 (add more GCPs)

#### Step 3: Tile Maps

Cut georeferenced maps into training-size tiles:

```bash
# Single map
python tile_maps.py ../data/kartverket/georeferenced/MAP_NAME.tif \
    --output ../data/kartverket/tiles/MAP_NAME/ \
    --tile-size 256 \
    --overlap 32

# Batch process all georeferenced maps
python tile_maps.py \
    --input-dir ../data/kartverket/georeferenced/ \
    --output-dir ../data/kartverket/tiles/ \
    --tile-size 256 \
    --overlap 32
```

**Output**:
- Tiles: `{map_name}_0_{row}_{col}.png`
- Index: `{map_name}_tiles.json`

### Workflow Automation

Once you have GCPs for your maps, you can process them in batch:

```bash
#!/bin/bash
# process_all_maps.sh

for map in ../data/kartverket/raw/*.tif; do
    basename=$(basename "$map" .tif)

    # Georeference
    python georeference.py "$map" \
        --gcps "gcps/${basename}_gcps.json" \
        --output "../data/kartverket/georeferenced/${basename}_georef.tif" \
        --crs EPSG:25832

    # Tile
    python tile_maps.py "../data/kartverket/georeferenced/${basename}_georef.tif" \
        --output "../data/kartverket/tiles/${basename}/" \
        --tile-size 256 \
        --overlap 32
done
```

### Directory Structure After Processing

```
data/kartverket/
├── raw/
│   ├── map1.tif
│   ├── map1_metadata.json
│   ├── map2.jp2
│   └── map2_metadata.json
├── georeferenced/
│   ├── map1_georef.tif
│   ├── map1_georef.quality.json
│   ├── map2_georef.tif
│   └── map2_georef.quality.json
└── tiles/
    ├── map1/
    │   ├── map1_0_0_0.png
    │   ├── map1_0_0_1.png
    │   ├── ...
    │   └── map1_tiles.json
    └── map2/
        └── ...
```

### Next: Annotation & Fine-tuning

After tiling, proceed with Phase 4 annotation workflow:

1. **Select tiles for annotation** (30-50 diverse tiles)
2. **Annotate features** (buildings, roads, water)
3. **Fine-tune model** on annotated tiles
4. **Batch extract** features from all tiles
5. **Merge results** into GeoJSON

See `scripts/ANNOTATION_README.md` for annotation workflow.

### Validation Script

Test your Phase 4 setup:

```bash
cd scripts
./validate_phase4.sh
```

This will check:
- All scripts are executable
- Dependencies are installed
- Directory structure exists
- Sample processing works

### Common Issues

**1. GDAL import error**
```bash
# macOS
brew install gdal
pip install gdal==$(gdal-config --version)

# Ubuntu
sudo apt-get install gdal-bin libgdal-dev
pip install gdal==$(gdal-config --version)
```

**2. No maps found**
- Check Kartverket API is accessible
- Verify bounding box coordinates (west, south, east, north)
- Try `--verbose` flag for debugging

**3. Poor georeferencing quality**
- Add more GCPs (6-10 recommended)
- Ensure GCPs are well-distributed across map
- Verify GCP coordinates are accurate
- Use stable features (churches, not temporary buildings)

**4. All tiles skipped**
- Try `--no-skip-empty` flag
- Verify input GeoTIFF has data: `gdalinfo file.tif`
- Adjust `--empty-threshold`

### Resources

- **Full Documentation**: `scripts/PHASE4_README.md`
- **Annotation Guide**: `scripts/ANNOTATION_README.md`
- **Kartverket Map Catalog**: https://kartkatalog.geonorge.no/
- **QGIS Download**: https://qgis.org/
- **Norwegian Maps**: https://norgeskart.no/

### Time Estimates

- **Download maps**: 30 min - 2 hours (depends on number)
- **Create GCPs per map**: 15-30 minutes
- **Georeference per map**: 1-2 minutes
- **Tile per map**: 2-5 minutes
- **Annotate tiles**: 10-20 hours (30-50 tiles)
- **Fine-tune model**: 2-4 hours
- **Batch extract**: 3-8 hours (depends on map count)

**Total Phase 4 estimate**: 15-30 hours active work + 5-12 hours compute time

### Getting Help

If you encounter issues:

1. Check `scripts/PHASE4_README.md` troubleshooting section
2. Verify dependencies: `pip list | grep -E "gdal|rasterio|Pillow"`
3. Test individual scripts with `--help` flag
4. Check log files for detailed error messages

---

**Ready to start?** Begin with the Quick Test above, then proceed to the Full Pipeline!
