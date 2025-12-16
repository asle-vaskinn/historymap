# Phase 5: Production - Data Merging & Tile Generation

This directory contains scripts for the final phase of the Trondheim Historical Map project: merging all data sources and generating production-ready vector tiles.

## Overview

Phase 5 combines:
- Current OSM data (from Phase 1)
- ML-extracted historical features (from Phase 4)

The output is a single PMTiles file optimized for web delivery with temporal filtering support.

## Files

- `merge_data.py` - Combines and deduplicates all data sources
- `generate_pmtiles.sh` - Converts merged data to PMTiles format
- `requirements.txt` - Python dependencies
- `README.md` - This file

## Prerequisites

### Python Dependencies

Install required Python packages:

```bash
pip install -r requirements.txt
```

Required packages:
- `geojson` - GeoJSON handling
- `shapely` - Geometry operations and deduplication
- `numpy` - Numerical operations

### System Dependencies

#### tippecanoe (required)

**macOS:**
```bash
brew install tippecanoe
```

**Linux:**
```bash
git clone https://github.com/felt/tippecanoe.git
cd tippecanoe
make -j
sudo make install
```

#### pmtiles CLI (optional, for validation)

Download from: https://github.com/protomaps/go-pmtiles/releases

**macOS/Linux:**
```bash
# Download the appropriate binary for your platform
# For macOS ARM64:
curl -LO https://github.com/protomaps/go-pmtiles/releases/latest/download/pmtiles_darwin_arm64
chmod +x pmtiles_darwin_arm64
sudo mv pmtiles_darwin_arm64 /usr/local/bin/pmtiles

# For macOS x86_64:
curl -LO https://github.com/protomaps/go-pmtiles/releases/latest/download/pmtiles_darwin_x86_64
chmod +x pmtiles_darwin_x86_64
sudo mv pmtiles_darwin_x86_64 /usr/local/bin/pmtiles

# For Linux:
curl -LO https://github.com/protomaps/go-pmtiles/releases/latest/download/pmtiles_linux_x86_64
chmod +x pmtiles_linux_x86_64
sudo mv pmtiles_linux_x86_64 /usr/local/bin/pmtiles
```

#### jq (optional, for validation)

**macOS:**
```bash
brew install jq
```

**Linux:**
```bash
sudo apt-get install jq
```

## Usage

### Step 1: Prepare Input Data

Ensure you have:

1. **OSM GeoJSON** - Current map data from Phase 1
   - Usually: `../data/trondheim.geojson` (if converted)
   - Or convert from PBF: See Phase 1 scripts

2. **Historical GeoJSON** - Extracted features from Phase 4
   - Directory: `../data/extracted/`
   - Files: `kartverket_1900.geojson`, `trondheim_1950.geojson`, etc.

If you don't have OSM in GeoJSON format yet, you can convert from PBF:

```bash
# Using ogr2ogr
ogr2ogr -f GeoJSON ../data/trondheim.geojson ../data/trondheim.osm.pbf

# Or using osmtogeojson
npm install -g osmtogeojson
osmtogeojson ../data/trondheim.osm.pbf > ../data/trondheim.geojson
```

### Step 2: Merge Data

Run the merge script to combine all data sources:

```bash
python merge_data.py \
    --osm ../data/trondheim.geojson \
    --historical ../data/extracted/ \
    --output ../data/final/trondheim_all_eras.geojson
```

**Options:**
- `--osm PATH` - Path to OSM GeoJSON file (required)
- `--historical PATH` - Directory with historical GeoJSON files (required)
- `--output PATH` - Output path for merged GeoJSON (required)
- `--similarity-threshold FLOAT` - Geometry similarity threshold (0-1, default: 0.8)
- `--verbose` - Enable verbose logging

**What it does:**
1. Loads OSM features and normalizes properties
2. Loads all historical GeoJSON files from the directory
3. Detects duplicate features using geometry similarity
4. Merges duplicates, keeping:
   - Earliest `start_date`
   - Latest `end_date`
   - Highest `confidence`
   - Combined `source` attribution
5. Ensures consistent schema for all features
6. Validates temporal consistency
7. Outputs merged GeoJSON with metadata

**Output Schema:**

Each feature has standardized properties:
```json
{
  "type": "Feature",
  "geometry": { ... },
  "properties": {
    "start_date": 1900,           // Year (integer) or null
    "end_date": 1950,             // Year (integer) or null if still exists
    "source": "osm",              // "osm" | "kartverket_1900" | combined
    "feature_class": "building",  // building | road | water | forest | railway | other
    "confidence": 0.85,           // 0-1 (ML confidence for extracted features)
    "merged_count": 3,            // Number of features merged (if applicable)
    "original_props": { ... }     // Original OSM/source properties
  }
}
```

### Step 3: Generate PMTiles

Convert the merged GeoJSON to PMTiles format:

```bash
./generate_pmtiles.sh ../data/final/trondheim_all_eras.geojson
```

Or specify custom output path:

```bash
./generate_pmtiles.sh ../data/final/trondheim_all_eras.geojson ../data/final/trondheim_historical.pmtiles
```

**What it does:**
1. Validates input GeoJSON
2. Runs tippecanoe with optimized settings:
   - Zoom levels: 8-16
   - Layer name: `historical_features`
   - Feature simplification at low zooms
   - Drops small features at low zooms
   - Preserves all temporal attributes
3. Validates output PMTiles structure
4. Reports file size and metadata

**Configuration:**

Edit the script to adjust these settings:
- `MIN_ZOOM=8` - Minimum zoom level
- `MAX_ZOOM=16` - Maximum zoom level
- `SIMPLIFICATION_INCREASE=1.5` - Geometry simplification factor

### Step 4: Validate Output

The scripts include automatic validation, but you can manually check:

```bash
# Check PMTiles metadata
pmtiles show ../data/final/trondheim_all_eras.pmtiles

# Serve locally for testing
pmtiles serve ../data/final/trondheim_all_eras.pmtiles
# Then open: http://localhost:8080
```

## Data Flow

```
Phase 1: OSM Data                Phase 4: Historical Extraction
     │                                      │
     ├─ trondheim.osm.pbf                  ├─ kartverket_1900.geojson
     └─ trondheim.geojson                  ├─ trondheim_1920.geojson
              │                            └─ trondheim_1950.geojson
              │                                      │
              └──────────┬─────────────────────────┘
                         ▼
                  merge_data.py
                         │
                         ├─ Normalize schemas
                         ├─ Detect duplicates
                         ├─ Merge temporal data
                         └─ Validate consistency
                         │
                         ▼
          trondheim_all_eras.geojson
                         │
                         ▼
              generate_pmtiles.sh
                         │
                         ├─ Optimize for web
                         ├─ Multi-zoom levels
                         ├─ Feature simplification
                         └─ Preserve attributes
                         │
                         ▼
          trondheim_historical.pmtiles
                         │
                         ▼
                   Frontend Map Viewer
```

## Feature Deduplication

The merge script detects duplicates using geometry similarity (Intersection over Union):

- **Threshold:** 0.8 by default (80% overlap)
- **Method:** Spatial index (STRtree) for efficiency
- **Merge strategy:**
  - Earliest `start_date` wins
  - Latest `end_date` wins (null = still exists)
  - Highest `confidence` wins
  - Sources are combined

**Example:**

If the same building appears in:
- OSM (current): `start_date=null, end_date=null, confidence=1.0`
- 1900 map: `start_date=1895, end_date=null, confidence=0.85`

Merged result:
- `start_date=1895` (earliest)
- `end_date=null` (latest/still exists)
- `confidence=1.0` (highest)
- `source="osm, kartverket_1900"` (combined)

## Troubleshooting

### "No features loaded from any source"

**Cause:** Input files are empty or in wrong format

**Solution:**
1. Check OSM file exists and is valid GeoJSON:
   ```bash
   jq '.features | length' ../data/trondheim.geojson
   ```
2. Check historical directory has GeoJSON files:
   ```bash
   ls -lh ../data/extracted/*.geojson
   ```

### "tippecanoe is not installed"

**Cause:** tippecanoe not found in PATH

**Solution:**
1. Install tippecanoe (see Prerequisites)
2. Verify installation:
   ```bash
   tippecanoe --version
   ```

### "Output file is empty"

**Cause:** tippecanoe failed or no features passed filters

**Solution:**
1. Check tippecanoe output for errors
2. Verify input GeoJSON has features with valid geometries:
   ```bash
   jq '.features[] | .geometry.type' ../data/final/trondheim_all_eras.geojson | sort | uniq -c
   ```

### "Memory error during merge"

**Cause:** Too many features for available RAM

**Solution:**
1. Process in batches (modify script to process regions separately)
2. Increase similarity threshold to reduce matching:
   ```bash
   python merge_data.py ... --similarity-threshold 0.9
   ```

### PMTiles file is very large

**Cause:** Too many features or detailed geometries

**Solution:**
1. Increase simplification:
   ```bash
   # Edit generate_pmtiles.sh
   SIMPLIFICATION_INCREASE=2.0  # More aggressive
   ```
2. Reduce max zoom:
   ```bash
   # Edit generate_pmtiles.sh
   MAX_ZOOM=14  # Instead of 16
   ```
3. Filter low-confidence features before merging

## Performance

### merge_data.py

- **Time:** 1-5 minutes for ~100k features
- **Memory:** 1-4 GB depending on feature count
- **Bottleneck:** Geometry similarity calculations

### generate_pmtiles.sh

- **Time:** 2-10 minutes for ~100k features
- **Memory:** 2-8 GB depending on zoom levels and features
- **Output size:** Typically 10-100 MB for city-scale data

## Output Quality Checks

After generation, verify:

1. **Feature count is reasonable:**
   ```bash
   jq '.features | length' ../data/final/trondheim_all_eras.geojson
   ```

2. **Temporal coverage:**
   ```bash
   jq '.metadata' ../data/final/trondheim_all_eras.geojson
   ```

3. **Feature classes distribution:**
   ```bash
   jq -r '.features[].properties.feature_class' ../data/final/trondheim_all_eras.geojson | sort | uniq -c
   ```

4. **Year range:**
   ```bash
   jq -r '.features[].properties.start_date' ../data/final/trondheim_all_eras.geojson | sort | uniq
   ```

5. **PMTiles is valid:**
   ```bash
   pmtiles show ../data/final/trondheim_all_eras.pmtiles
   ```

## Next Steps

After successful tile generation:

1. **Update frontend** to use new PMTiles file
2. **Test time slider** with real historical data
3. **Deploy** to production (see deployment options in main project plan)
4. **Monitor** performance and user feedback

## Integration with Frontend

Update your MapLibre GL JS configuration:

```javascript
// In frontend/app.js or similar
const map = new maplibregl.Map({
  container: 'map',
  style: {
    version: 8,
    sources: {
      'historical': {
        type: 'vector',
        url: 'pmtiles://path/to/trondheim_historical.pmtiles',
        attribution: '© OpenStreetMap contributors, Kartverket'
      }
    },
    layers: [
      {
        id: 'buildings',
        type: 'fill',
        source: 'historical',
        'source-layer': 'historical_features',
        filter: ['==', 'feature_class', 'building'],
        paint: {
          'fill-color': '#ff0000',
          'fill-opacity': 0.5
        }
      }
      // Add more layers for roads, water, etc.
    ]
  }
});

// Time slider filtering
function updateMapForYear(year) {
  map.setFilter('buildings', [
    'all',
    ['==', 'feature_class', 'building'],
    ['<=', 'start_date', year],
    ['any',
      ['>=', 'end_date', year],
      ['==', 'end_date', null]
    ]
  ]);
}
```

## License

See main project LICENSE file.

## Support

For issues or questions:
1. Check this README
2. Review Phase 5 section in HISTORICAL_MAP_PROJECT_PLAN.md
3. Check script output for detailed error messages
