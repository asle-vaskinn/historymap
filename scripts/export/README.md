# Export Scripts

This directory contains scripts for transforming merged building data to frontend-ready formats.

## export_geojson.py

Transforms merged building data from `data/merged/buildings_merged.geojson` to a compact, frontend-optimized GeoJSON format.

### Usage

```bash
# Basic usage (uses default paths)
python scripts/export/export_geojson.py

# Custom input/output paths
python scripts/export/export_geojson.py \
  --input data/merged/buildings_merged.geojson \
  --output data/export/buildings.geojson

# Disable statistics output
python scripts/export/export_geojson.py --no-stats
```

### Transformations

The script performs the following transformations:

1. **Compact source codes**: `sefrak` → `sef`, `osm` → `osm`, `ml_*` → `ml`
2. **Generate building IDs**: Combines source and source ID into compact `bid` field
3. **Filter fields**: Keeps only frontend-required fields
4. **Strip metadata**: Removes `_raw`, `_merge_info`, `_ingested` (development-only fields)
5. **Add source arrays**: Creates `src_all` array when multiple sources contributed

### Field Mapping

#### Input (Merged Schema)

```json
{
  "type": "Feature",
  "properties": {
    "_src": "sefrak",
    "_src_id": "SEFRAK-12345",
    "_ingested": "2024-01-20",
    "sd": 1850,
    "ed": null,
    "ev": "h",
    "bt": "residential",
    "nm": "Stiftsgården",
    "src_all": ["sefrak", "osm"],
    "_raw": {...},
    "_merge_info": {...}
  },
  "geometry": {...}
}
```

#### Output (Frontend Schema)

```json
{
  "type": "Feature",
  "properties": {
    "bid": "sef-12345",
    "src": "sef",
    "src_all": ["sef", "osm"],
    "sd": 1850,
    "ev": "h",
    "bt": "residential",
    "nm": "Stiftsgården"
  },
  "geometry": {...}
}
```

### Frontend Fields

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `bid` | string | Compact building ID | `"sef-12345"` |
| `src` | string | Primary source code | `"sef"`, `"osm"`, `"ml"` |
| `src_all` | array | All contributing sources (optional) | `["sef", "osm"]` |
| `sd` | int | Start date (year built) | `1850` |
| `ed` | int | End date (year demolished) - optional | `1965` |
| `ev` | string | Evidence level: `h`, `m`, `l` | `"h"` |
| `ml_src` | string | ML map source (if ML-detected) | `"kv1880"`, `"air1947"` |
| `mlc` | float | ML confidence score (if applicable) | `0.85` |
| `bt` | string | Building type | `"residential"` |
| `nm` | string | Building name (optional) | `"Stiftsgården"` |
| `rep_by` | string | ID of replacement building (optional) | `"osm-567890"` |
| `rep_ev` | string | Evidence strength for replacement | `"h"` |

### Source Codes

| Full Name | Short Code |
|-----------|------------|
| `sefrak` | `sef` |
| `trondheim_kommune` | `tk` |
| `osm` | `osm` |
| `matrikkelen` | `mat` |
| `ml_kartverket_1880` | `ml` |
| `ml_kartverket_1904` | `ml` |
| `ml_aerial_1947` | `ml` |
| `ml_aerial_1964` | `ml` |

### ML Source Codes

For ML-detected buildings, the `ml_src` field specifies which historical map:

| Full Name | Map Code |
|-----------|----------|
| `ml_kartverket_1880` | `kv1880` |
| `ml_kartverket_1904` | `kv1904` |
| `ml_aerial_1947` | `air1947` |
| `ml_aerial_1964` | `air1964` |

### Output Files

The script creates two files:

1. **buildings.geojson**: Frontend-ready GeoJSON
2. **buildings.meta.json**: Export metadata and statistics

### Statistics Output

When statistics are enabled (default), the script prints:

- Total feature count
- Count by source (with percentages)
- Temporal data coverage (buildings with dates)
- Evidence level distribution
- ML-detected building count (by map source)
- Multi-source building count
- Replaced/demolished building count
- Date range (min/max years)

Example output:

```
============================================================
EXPORT STATISTICS
============================================================

Total features: 45123

By source:
  sef       :   2847 (  6.3%)
  osm       :  41250 ( 91.4%)
  ml        :   1026 (  2.3%)

Temporal data:
  With start date:   3873 (  8.6%)
  With end date:      127 (  0.3%)

By evidence level:
  h (high/med/low):   3873 (  8.6%)
  m (high/med/low):      0 (  0.0%)
  l (high/med/low):  41250 ( 91.4%)

ML-detected buildings: 1026
  By map source:
    kv1880    :   1026

Multi-source buildings: 834
Replaced buildings: 127

Date range: 1650 - 2024
============================================================
```

### Integration with Pipeline

This script is Stage 4 of the data pipeline:

```
Stage 1: Ingest    → data/sources/{source}/raw/
Stage 2: Normalize → data/sources/{source}/normalized/
Stage 3: Merge     → data/merged/buildings_merged.geojson
Stage 4: Export    → data/export/buildings.geojson  ← THIS SCRIPT
```

Run after merge:

```bash
# Full pipeline
python scripts/merge/merge_sources.py
python scripts/export/export_geojson.py
```

### Error Handling

The script includes error handling for:

- Missing input file
- Invalid feature data
- Missing required fields
- File write errors

Failed features are logged but don't stop the export process.

## export_pmtiles.py

Converts frontend-ready GeoJSON to PMTiles format for efficient web serving. PMTiles is a cloud-optimized format that allows serving vector tiles without a tile server.

### Requirements

**tippecanoe** must be installed:

```bash
# macOS
brew install tippecanoe

# Linux (build from source)
git clone https://github.com/felt/tippecanoe.git
cd tippecanoe
make -j
sudo make install

# Docker (alternative)
docker run -v $(pwd):/data felt/tippecanoe [args]
```

Verify installation:

```bash
tippecanoe --version
```

### Usage

```bash
# Basic usage (uses default paths)
python scripts/export/export_pmtiles.py

# Custom input/output paths
python scripts/export/export_pmtiles.py \
  -i data/export/buildings.geojson \
  -o data/export/buildings.pmtiles

# Adjust zoom levels
python scripts/export/export_pmtiles.py --min-zoom 8 --max-zoom 18

# With metadata
python scripts/export/export_pmtiles.py \
  --name "Trondheim Historical Buildings" \
  --description "Building footprints 1700-present" \
  --attribution "© Kartverket, OpenStreetMap contributors"

# Force overwrite existing file
python scripts/export/export_pmtiles.py --force
```

### Configuration

Default settings optimized for building data:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--min-zoom` | 10 | City-level view |
| `--max-zoom` | 16 | Individual building detail |
| `--layer` | buildings | Layer name in tiles |
| `--force` | false | Overwrite existing output |

### Tippecanoe Optimizations

The script uses these tippecanoe settings optimized for building data:

```bash
--full-detail 16               # Preserve full detail at max zoom
--no-simplification-of-shared-nodes  # Keep accurate shared walls
--drop-densest-as-needed       # Manage tile size by dropping dense features
--extend-zooms-if-still-dropping  # Add zoom levels if needed
--maximum-tile-features 200000  # Reasonable limit for buildings
--maximum-tile-bytes 500000    # ~500KB max tile size
--buffer 5                     # Edge buffer for seamless tiles
```

### Attribute Handling

Temporal and metadata attributes are preserved with proper types:

- `sd` (start_date): Integer year
- `ed` (end_date): Integer year
- `mlc` (ML confidence): Float 0.0-1.0
- `src`: String, combined with comma for multi-source buildings

### Output Files

The script creates two files:

1. **buildings.pmtiles**: PMTiles archive with vector tiles
2. **buildings.meta.json**: Export metadata and configuration

Example metadata:

```json
{
  "exported_at": "2024-01-20T14:30:00Z",
  "source_file": "data/export/buildings.geojson",
  "format": "pmtiles",
  "feature_count": 45123,
  "size_mb": 12.4,
  "zoom_levels": {
    "min": 10,
    "max": 16
  },
  "layer_name": "buildings",
  "name": "Trondheim Historical Buildings",
  "description": "Building footprints from 1700 to present with temporal attributes",
  "attribution": "© Kartverket, SEFRAK, OpenStreetMap contributors"
}
```

### Frontend Integration

Using PMTiles with MapLibre GL JS:

```javascript
// 1. Install pmtiles library
// npm install pmtiles

// 2. Add PMTiles protocol
import { Protocol } from 'pmtiles';
let protocol = new Protocol();
maplibregl.addProtocol('pmtiles', protocol.tile);

// 3. Add source
map.addSource('buildings', {
  type: 'vector',
  url: 'pmtiles://https://example.com/buildings.pmtiles',
  // Or for local testing:
  // url: 'pmtiles:///buildings.pmtiles'
});

// 4. Add layer with temporal filtering
map.addLayer({
  id: 'buildings-fill',
  type: 'fill',
  source: 'buildings',
  'source-layer': 'buildings',
  filter: [
    'all',
    ['<=', ['get', 'sd'], currentYear],
    ['any',
      ['>=', ['get', 'ed'], currentYear],
      ['!', ['has', 'ed']]
    ]
  ],
  paint: {
    'fill-color': '#888',
    'fill-opacity': 0.8
  }
});
```

### Hosting Options

PMTiles files can be served from:

1. **Object Storage**: S3, Cloudflare R2, Google Cloud Storage
2. **Static Hosting**: GitHub Pages, Netlify, Vercel
3. **CDN**: Cloudflare, AWS CloudFront
4. **Local Development**: Any HTTP server with range request support

Requirements:
- HTTP Range Request support (for partial file access)
- CORS headers enabled (for cross-origin access)

Example nginx configuration:

```nginx
location /tiles/ {
    root /var/www;
    add_header Access-Control-Allow-Origin *;
    add_header Access-Control-Allow-Methods 'GET, HEAD, OPTIONS';
    add_header Access-Control-Allow-Headers 'Range';
}
```

### Performance

PMTiles advantages over traditional tile servers:

- **No tile server required**: Serve directly from static storage
- **Efficient caching**: Browser and CDN caching work naturally
- **Low latency**: Only downloads needed tiles via range requests
- **Cost effective**: Pay only for storage and bandwidth
- **Scalable**: Automatically scales with CDN

Typical file sizes (Trondheim building data):

- 40,000 buildings: ~10-15 MB
- 100,000 buildings: ~25-35 MB
- Includes all zoom levels 10-16

### Integration with Pipeline

PMTiles export is Stage 4b of the data pipeline:

```
Stage 1: Ingest    → data/sources/{source}/raw/
Stage 2: Normalize → data/sources/{source}/normalized/
Stage 3: Merge     → data/merged/buildings_merged.geojson
Stage 4: Export    → data/export/buildings.geojson
Stage 4b: PMTiles  → data/export/buildings.pmtiles  ← THIS SCRIPT
```

Run as part of export stage:

```bash
# Using pipeline (automatic)
python scripts/pipeline.py --stage export

# Manual (after GeoJSON export)
python scripts/export/export_geojson.py
python scripts/export/export_pmtiles.py

# Skip PMTiles in pipeline
python scripts/pipeline.py --stage export --no-pmtiles
```

### Testing

Run the test suite to verify the export works:

```bash
python scripts/export/test_pmtiles.py
```

The test creates a minimal GeoJSON file and converts it to PMTiles, validating:

- Tippecanoe availability
- File creation
- Metadata generation
- Attribute preservation
- Zoom level configuration

### Troubleshooting

**"tippecanoe not found"**

Install tippecanoe (see Requirements section above).

**"Output file exists"**

Use `--force` to overwrite, or delete the existing file.

**Large file sizes**

- Reduce `--max-zoom` (fewer detail levels)
- Increase `--maximum-tile-bytes` (larger tiles, fewer files)
- Filter source data to reduce feature count

**Tiles not loading in browser**

- Verify server supports HTTP Range requests
- Check CORS headers are set correctly
- Use browser dev tools to inspect network requests
- Test with `curl -H "Range: bytes=0-1023" https://example.com/buildings.pmtiles`

**Attributes missing or wrong type**

Check the `--attribute-type` flags in the script. Temporal attributes should be integers:
- `sd` (start_date): int
- `ed` (end_date): int
- `mlc` (confidence): float

## Future Scripts

Planned export scripts:

- **apply_filters.py**: Apply spatial/temporal filters before export
