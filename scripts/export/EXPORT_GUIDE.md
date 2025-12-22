# Export Script Guide

This guide explains how to use the export scripts to prepare building data for the frontend.

## Overview

The export stage (Stage 4) transforms merged building data into frontend-ready formats:

```
data/merged/buildings_merged.geojson  →  data/export/buildings.geojson
    (development schema)                     (frontend schema)
```

## Quick Start

### 1. Run the merge first (if not done)

```bash
python3 scripts/merge/merge_sources.py
```

This creates `data/merged/buildings_merged.geojson` from all enabled sources.

### 2. Export to frontend format

```bash
python3 scripts/export/export_geojson.py
```

This creates `data/export/buildings.geojson` ready for the frontend to consume.

### 3. Use in frontend

Update your frontend to point to the exported data:

```javascript
// In frontend/app.js or similar
const dataUrl = '../data/export/buildings.geojson';

map.addSource('buildings', {
  type: 'geojson',
  data: dataUrl
});
```

## Schema Differences

### Development Schema (Merged Data)

The merged data contains full provenance and debugging information:

```json
{
  "type": "Feature",
  "properties": {
    "_src": "sefrak",              // Full source name
    "_src_id": "SEFRAK-12345",     // Original source ID
    "_ingested": "2024-01-20",     // Ingestion timestamp
    "sd": 1850,
    "ev": "h",
    "src_all": ["sefrak", "osm"],  // Full source names
    "_raw": {                      // Original properties
      "byggnr": "12345",
      "...": "..."
    },
    "_merge_info": {               // Merge metadata
      "matched_at": "2024-01-20",
      "sources": {...}
    }
  },
  "geometry": {...}
}
```

### Frontend Schema (Exported Data)

The frontend data is optimized for size and performance:

```json
{
  "type": "Feature",
  "properties": {
    "bid": "sef-12345",           // Compact building ID
    "src": "sef",                 // Short source code
    "src_all": ["sef", "osm"],    // Short source codes
    "sd": 1850,
    "ev": "h"
  },
  "geometry": {...}
}
```

**Benefits:**
- 30-40% smaller file size
- No unnecessary fields in browser
- Clean developer experience
- Standardized field names

## Field Reference

### Core Fields (Always Present)

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `bid` | string | Unique building ID | `"sef-12345"` |
| `src` | string | Primary data source | `"sef"`, `"osm"`, `"ml"` |
| `ev` | string | Evidence strength | `"h"`, `"m"`, `"l"` |

### Temporal Fields

| Field | Type | Description | Required |
|-------|------|-------------|----------|
| `sd` | int | Start date (year built) | Optional |
| `ed` | int | End date (demolished) | Optional |

### Source Fields

| Field | Type | Description | When Present |
|-------|------|-------------|--------------|
| `src_all` | array | All contributing sources | Multiple sources merged |
| `ml_src` | string | ML map identifier | ML-detected buildings |
| `mlc` | float | ML confidence (0-1) | ML-detected buildings |

### Metadata Fields

| Field | Type | Description | Optional |
|-------|------|-------------|----------|
| `bt` | string | Building type | If available |
| `nm` | string | Building name | If available |

### Replacement Fields

| Field | Type | Description | When Present |
|-------|------|-------------|--------------|
| `rep_by` | string | Replacing building ID | Building was replaced |
| `rep_ev` | string | Replacement evidence | Building was replaced |

## Source Code Mappings

### Primary Sources

| Full ID | Short Code | Description |
|---------|------------|-------------|
| `sefrak` | `sef` | SEFRAK cultural heritage registry |
| `trondheim_kommune` | `tk` | Trondheim municipality data |
| `osm` | `osm` | OpenStreetMap |
| `matrikkelen` | `mat` | Norwegian property registry |

### ML Sources

All ML-detected buildings use `src: "ml"`, with the specific map in `ml_src`:

| Full ID | ML Source | Description |
|---------|-----------|-------------|
| `ml_kartverket_1880` | `kv1880` | 1880 topographic map |
| `ml_kartverket_1904` | `kv1904` | 1904 topographic map |
| `ml_aerial_1947` | `air1947` | 1947 aerial photography |
| `ml_aerial_1964` | `air1964` | 1964 aerial photography |

## Evidence Levels

| Code | Name | Meaning |
|------|------|---------|
| `h` | High | Verified historical record or precise detection |
| `m` | Medium | Inferred from style or context |
| `l` | Low | Modern map without date information |

## Command Line Options

### Basic Usage

```bash
# Use default paths
python3 scripts/export/export_geojson.py

# Custom input
python3 scripts/export/export_geojson.py \
  --input data/merged/custom_merge.geojson

# Custom output
python3 scripts/export/export_geojson.py \
  --output data/export/trondheim_buildings.geojson

# Both custom
python3 scripts/export/export_geojson.py \
  --input data/merged/test_merge.geojson \
  --output data/export/test_output.geojson
```

### Options

| Flag | Description | Default |
|------|-------------|---------|
| `--input`, `-i` | Input merged GeoJSON | `data/merged/buildings_merged.geojson` |
| `--output`, `-o` | Output frontend GeoJSON | `data/export/buildings.geojson` |
| `--no-stats` | Disable statistics output | Statistics enabled |

## Output Files

The script creates two files:

### 1. buildings.geojson

The main export file containing frontend-ready GeoJSON.

```bash
data/export/buildings.geojson
```

### 2. buildings.meta.json

Export metadata and statistics:

```json
{
  "exported_at": "2024-01-20T15:30:00Z",
  "source_file": "data/merged/buildings_merged.geojson",
  "feature_count": 45123,
  "size_mb": 15.8,
  "statistics": {
    "by_source": {
      "sef": 2847,
      "osm": 41250,
      "ml": 1026
    },
    "with_dates": {
      "start_date": 3873,
      "end_date": 127
    },
    "ml_detected": 1026,
    "multi_source": 834,
    "replaced": 127,
    "date_range": {
      "min": 1650,
      "max": 2024
    }
  }
}
```

## Statistics Output

When running with statistics (default), you'll see:

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

## Frontend Integration

### Loading the Data

```javascript
// Method 1: Direct URL
map.addSource('buildings', {
  type: 'geojson',
  data: '../data/export/buildings.geojson'
});

// Method 2: Fetch first
const response = await fetch('../data/export/buildings.geojson');
const data = await response.json();
map.addSource('buildings', {
  type: 'geojson',
  data: data
});
```

### Filtering by Year

```javascript
// Show buildings that existed in 1880
map.setFilter('buildings-layer', [
  'all',
  ['<=', ['get', 'sd'], 1880],  // Built by 1880
  ['any',
    ['!', ['has', 'ed']],        // Still exists
    ['>', ['get', 'ed'], 1880]   // Or demolished after 1880
  ]
]);
```

### Filtering by Source

```javascript
// Show only SEFRAK buildings
map.setFilter('buildings-layer', [
  '==', ['get', 'src'], 'sef'
]);

// Show high-evidence buildings only
map.setFilter('buildings-layer', [
  '==', ['get', 'ev'], 'h'
]);
```

### Styling by Evidence

```javascript
map.addLayer({
  id: 'buildings',
  type: 'fill',
  source: 'buildings',
  paint: {
    'fill-color': [
      'match',
      ['get', 'ev'],
      'h', '#2563eb',  // Blue for high evidence
      'm', '#f59e0b',  // Orange for medium
      'l', '#94a3b8',  // Gray for low
      '#cbd5e1'        // Default
    ],
    'fill-opacity': 0.6
  }
});
```

## Troubleshooting

### Error: Input file not found

Make sure you've run the merge step first:

```bash
python3 scripts/merge/merge_sources.py
```

### Error: Failed to transform feature

Check the merged data schema matches expected format. Run with debugging:

```bash
python3 -u scripts/export/export_geojson.py 2>&1 | tee export.log
```

### Output is too large

Consider:
1. Filtering to specific area before export
2. Converting to PMTiles format (future script)
3. Removing optional fields like `nm` if not needed

## Testing

Run the test suite to verify the export script:

```bash
python3 scripts/export/test_export.py
```

This tests:
- Building ID generation
- Feature transformation
- Full export process
- Schema validation

## Performance

### File Sizes

Typical size reduction from merged to exported:

| Dataset | Merged | Exported | Reduction |
|---------|--------|----------|-----------|
| 45k buildings | 24 MB | 16 MB | 33% |
| 10k buildings | 6 MB | 4 MB | 33% |

### Processing Speed

- ~5,000 buildings/second
- 45k buildings in ~9 seconds
- Memory usage: ~200 MB peak

## Next Steps

After exporting:

1. **Test in frontend**: Verify data loads and displays correctly
2. **Check statistics**: Review source distribution and date coverage
3. **PMTiles export** (future): For production deployment
4. **Filters** (future): Apply spatial/temporal filters before export

## Related Documentation

- [Data Pipeline Architecture](../../docs/tech/DATA_PIPELINE_ARCHITECTURE.md)
- [Technical README](../../docs/tech/README.md)
- [Merge Sources Guide](../merge/README.md)
