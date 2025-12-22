# Quickstart Guide

Get the Trondheim Historical Map running in 5 minutes.

## Prerequisites

- **Python 3.11+** (for data processing)
- **Node.js** (optional, for local server)
- **Web browser** (Chrome, Firefox, or Safari)

## Quick Start: View the Frontend

The fastest way to see the map is to use the existing data files.

### Option 1: Python HTTP Server (Recommended)

```bash
# From project root
cd frontend
python3 -m http.server 8080
```

Open http://localhost:8080 in your browser.

### Option 2: Docker

```bash
# From project root
docker-compose up
```

Open http://localhost:8080 in your browser.

### Option 3: Direct File Access

Open `frontend/index.html` directly in your browser. Note: Some browsers restrict local file access, so a server is recommended.

## What You'll See

- **Time slider**: 1700-2025 range showing building construction/demolition
- **Source filters**: Toggle data sources (SEFRAK, OSM, ML-detected buildings)
- **Confidence overlay**: Shows evidence strength for historical dates
- **Era indicator**: Current period context

## Data Files

The frontend loads these files from `data/`:

### Current Production Files

| File | Size | Description | Status |
|------|------|-------------|--------|
| `buildings_v2.geojson` | 15MB | Main building dataset | ✅ Most recent |
| `buildings_demolished_v2.geojson` | 135KB | Demolished buildings | ✅ Most recent |
| `buildings_temporal.pmtiles` | 7.3MB | PMTiles format (unused) | ⚠️ Not integrated |

**Note**: The frontend currently loads GeoJSON files, not PMTiles. This is acceptable for development but should be migrated to PMTiles for production.

### Where Data Files Come From

```
Data Pipeline Stages:
1. Ingest    → data/sources/{source}/raw/
2. Normalize → data/sources/{source}/normalized/
3. Merge     → data/merged/buildings_merged.geojson
4. Export    → data/export/buildings.geojson (NOT YET IMPLEMENTED)
```

**Current situation**: The files in `data/` root are manually created from earlier pipeline runs. The full automated pipeline is not yet complete.

## Running the Data Pipeline

### Stage 1: Ingest Data Sources

#### OSM Buildings (Modern Baseline)

```bash
# Download current OSM data for Trondheim
./scripts/download_osm.sh

# Output: data/sources/osm/raw/trondheim.osm.pbf
```

#### SEFRAK Cultural Heritage Registry

SEFRAK data must be downloaded manually from [Riksantikvaren](https://www.riksantikvaren.no/):

1. Visit https://sefrak.ra.no/
2. Filter for Trondheim municipality
3. Export as CSV or GeoJSON
4. Place in `data/sources/sefrak/raw/`

**File format expected**:
- Building coordinates (WGS84)
- Construction year (`byggeaar` or similar field)
- Building name/description

#### ML-Detected Buildings (Historical Maps)

**Not yet implemented**. To extract buildings from historical maps:

1. Train the ML model: `python ml/train.py --config ml/config.yaml`
2. Run inference on historical maps (script TODO)
3. Place output in `data/sources/ml_detected/{map_source}/raw/`

### Stage 2: Normalize Data

Convert each source to common schema:

```bash
# Normalize OSM data
python scripts/normalize/normalize_osm.py

# Normalize SEFRAK (when ingestion is implemented)
# python scripts/normalize/normalize_sefrak.py

# Output: data/sources/*/normalized/buildings.geojson
```

### Stage 3: Merge Sources

Combine normalized sources according to `data/merged/merge_config.json`:

```bash
python scripts/merge/merge_sources.py \
  --config data/merged/merge_config.json \
  --output data/merged/buildings_merged.geojson
```

**Configuration**: Edit `data/merged/merge_config.json` to:
- Enable/disable sources
- Set priority order (higher priority wins conflicts)
- Configure replacement detection rules

### Stage 4: Export for Frontend

Transform merged data to frontend format:

```bash
python scripts/export/export_geojson.py \
  --input data/merged/buildings_merged.geojson \
  --output data/export/buildings.geojson
```

**Frontend symlinks**: Update `frontend/data/` symlinks to point to export directory:

```bash
cd frontend/data
ln -sf ../../data/export/buildings.geojson buildings.geojson
```

## Troubleshooting

### Frontend shows no buildings

**Cause**: Data files not found or wrong path.

**Fix**:
1. Check that `data/buildings_v2.geojson` exists
2. Update `frontend/app.js` line 138 to point to correct file:
   ```javascript
   data: '../data/buildings_v2.geojson'
   ```

### "Failed to load GeoJSON" error

**Cause**: CORS policy blocking local file access.

**Fix**: Use a local server (Python or Docker) instead of opening `index.html` directly.

### Slider moves but no buildings appear

**Cause**: Frontend temporal filter may be too restrictive.

**Fix**:
1. Check browser console for errors
2. Try year 2020+ (modern OSM buildings should always show)
3. Disable confidence overlay to see all buildings

### Pipeline fails at merge stage

**Cause**: No normalized data files.

**Fix**: Run normalize stage first for at least one source (OSM is easiest).

## Next Steps

### For Frontend Development

- **Modify styles**: Edit `frontend/style.css`
- **Change time range**: Edit `frontend/app.js` lines 700-750
- **Add features**: See `docs/spec/README.md` for Phase 2 features

### For Data Pipeline Development

- **Add new source**: Follow `docs/tech/DATA_PIPELINE_ARCHITECTURE.md` Section "Adding a New Source"
- **Improve ML detection**: Train model with more data in `ml/`
- **Vectorization**: Convert ML raster masks to GeoJSON polygons

### For ML Model Training

```bash
# Quick training run (for testing)
python ml/train.py --config ml/config_quick.yaml

# Full training run
python ml/train.py --config ml/config.yaml

# Resume from checkpoint
python ml/train.py --config ml/config.yaml --resume models/checkpoints/last_checkpoint.pth
```

## Getting Historical Map Data

### Kartverket Historical Maps

1. Visit [Kartverket Historiske Kart](https://www.kartverket.no/kart/historiske-kart)
2. Search for "Trondheim"
3. Download maps from ~1880, ~1904 (topographic series)
4. Place georeferenced TIFFs in `data/kartverket/`

**License**: Public domain for maps >100 years old, CC BY 4.0 for newer maps.

### Historical Aerial Photography

1. Visit [Norgeibilder.no](https://norgeibilder.no/)
2. Filter for Trondheim, year range 1945-1970
3. Download aerial photos
4. Georeference using `scripts/georeference.py`
5. Place in `data/aerials/`

**License**: Varies by source, check individual image metadata.

## Key Configuration Files

| File | Purpose |
|------|---------|
| `ml/config.yaml` | ML training parameters |
| `data/merged/merge_config.json` | Source merging rules |
| `frontend/app.js` (lines 17-62) | Data source paths and filters |

## Resources

- **Full architecture**: See `docs/tech/DATA_PIPELINE_ARCHITECTURE.md`
- **Technical details**: See `docs/tech/README.md`
- **Feature spec**: See `docs/spec/README.md`
- **Project instructions**: See `CLAUDE.md`

## Known Limitations

1. **No automated SEFRAK ingestion**: Must download manually
2. **ML extraction incomplete**: Training works, but no inference pipeline
3. **PMTiles not integrated**: Frontend uses GeoJSON (slower for large datasets)
4. **Phase 2 features missing**: No building popups, search, or comparison view
5. **Source counting inaccurate**: UI shows "-" or incorrect counts

See `docs/tech/IMPLEMENTATION_STATUS.md` for complete list of implementation gaps.
