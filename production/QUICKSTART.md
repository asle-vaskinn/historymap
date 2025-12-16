# Phase 5: Quick Start Guide

Get your historical map data merged and deployed in minutes.

## Prerequisites Check

```bash
# Python dependencies
pip install -r requirements.txt

# System tools (macOS)
brew install tippecanoe jq

# Optional: PMTiles CLI for validation
# Download from https://github.com/protomaps/go-pmtiles/releases
```

## Step-by-Step

### 1. Prepare OSM Data (if needed)

If you don't have OSM in GeoJSON format yet:

```bash
# Option A: Using ogr2ogr
ogr2ogr -f GeoJSON ../data/trondheim.geojson ../data/trondheim.osm.pbf

# Option B: Using osmium (faster for large files)
# brew install osmium-tool
osmium export ../data/trondheim.osm.pbf -o ../data/trondheim.geojson
```

### 2. Merge All Data Sources

```bash
python merge_data.py \
    --osm ../data/trondheim.geojson \
    --historical ../data/extracted/ \
    --output ../data/final/trondheim_all_eras.geojson
```

Expected output:
```
[INFO] Loading OSM data from ../data/trondheim.geojson
[INFO] Loaded 45123 features from OSM
[INFO] Loading historical data from ../data/extracted/
[INFO] Loaded 12456 features from kartverket_1900.geojson
[INFO] Loaded 8734 features from trondheim_1950.geojson
[INFO] Loaded 21190 total historical features
[INFO] Total features before merging: 66313
[INFO] Finding duplicates among 66313 features...
[INFO] Found 3421 duplicate groups
[INFO] Result: 62892 unique features after merging
[INFO] Writing merged data to ../data/final/trondheim_all_eras.geojson
[INFO] Validating output...
[INFO] Validation results:
  Total features: 62892
  By class: {'building': 45234, 'road': 12456, 'water': 3421, 'railway': 1234, 'other': 547}
  With start_date: 58456
  With end_date: 12234
  Year range: 1890 - 2024
✓ Merge completed successfully
```

### 3. Generate PMTiles

```bash
./generate_pmtiles.sh ../data/final/trondheim_all_eras.geojson
```

Expected output:
```
==================================================
  PMTiles Generator - Phase 5
  Trondheim Historical Map Project
==================================================

[INFO] Checking dependencies...
✓ Dependencies checked
[INFO] Validating input file: ../data/final/trondheim_all_eras.geojson
[INFO] Found 62892 features in input file
✓ Input file is valid
[INFO] Generating PMTiles...
  Input:     ../data/final/trondheim_all_eras.geojson
  Output:    ../data/final/trondheim_all_eras.pmtiles
  Zoom:      8 - 16
[INFO] Running tippecanoe...
✓ PMTiles generation completed
[INFO] Validating output file: ../data/final/trondheim_all_eras.pmtiles
[INFO] Output file size: 45.2 MiB
✓ PMTiles structure is valid
✓ Output file is valid

==================================================
✓ PMTiles generation completed successfully!
==================================================

Output file: ../data/final/trondheim_all_eras.pmtiles

To serve locally for testing:
  pmtiles serve ../data/final/trondheim_all_eras.pmtiles
```

### 4. Validate Output

```bash
./validate_phase5.sh
```

Expected output shows all checks passing:
```
==================================================
  Phase 5 Validation
  Trondheim Historical Map Project
==================================================

✓ Merged GeoJSON exists
✓ PMTiles file exists
✓ Valid GeoJSON FeatureCollection
✓ Feature count: 62892
✓ Temporal attributes validated
✓ Feature classes validated
✓ Temporal range validated
✓ Metadata present
✓ PMTiles structure is valid
✓ PMTiles file validated

==================================================
  Validation Summary
==================================================
✓ All checks passed!
==================================================
```

### 5. Test Locally

Serve the PMTiles file:

```bash
pmtiles serve ../data/final/trondheim_all_eras.pmtiles
```

Then open http://localhost:8080 in your browser.

Or integrate with your frontend:

```bash
cd ../frontend
# Update the tile source URL in app.js
# Then serve:
python3 -m http.server 8080
```

## Troubleshooting

### Merge script fails with "No features loaded"

Check your input files:

```bash
# Check OSM file
jq '.features | length' ../data/trondheim.geojson

# Check historical files
ls -lh ../data/extracted/*.geojson
```

If OSM file doesn't exist or is in wrong format, convert from PBF (see Step 1).

### PMTiles generation fails

Check tippecanoe is installed:

```bash
tippecanoe --version
```

If not installed:

```bash
brew install tippecanoe  # macOS
```

### Output file is too large

Reduce detail by editing `generate_pmtiles.sh`:

```bash
# Change these lines:
MAX_ZOOM=14          # Instead of 16
SIMPLIFICATION_INCREASE=2.0  # Instead of 1.5
```

Then regenerate:

```bash
./generate_pmtiles.sh ../data/final/trondheim_all_eras.geojson
```

### Memory errors during merge

Process with higher similarity threshold to reduce comparisons:

```bash
python merge_data.py \
    --osm ../data/trondheim.geojson \
    --historical ../data/extracted/ \
    --output ../data/final/trondheim_all_eras.geojson \
    --similarity-threshold 0.9  # Stricter matching
```

## Next Steps

1. **Update frontend** to use the new PMTiles file
2. **Test time slider** functionality with real historical data
3. **Deploy** to production (see deployment guide)
4. **Share** with users and gather feedback

## File Locations

After completion, you should have:

```
data/final/
├── trondheim_all_eras.geojson  (~100-500 MB)
└── trondheim_all_eras.pmtiles  (~20-100 MB)
```

## Performance Benchmarks

Typical execution times on modern hardware:

| Step | Features | Time |
|------|----------|------|
| Merge | 50k | 2-3 min |
| Merge | 100k | 5-7 min |
| PMTiles | 50k | 3-5 min |
| PMTiles | 100k | 7-10 min |

## Questions?

See the full README.md in this directory for detailed documentation.
