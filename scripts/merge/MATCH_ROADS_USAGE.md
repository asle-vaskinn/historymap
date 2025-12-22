# Road Matching Script - Usage Guide

## Overview

`match_roads.py` matches historical road segments to modern OSM roads using **LSS-Hausdorff matching**, a robust algorithm that combines geometric similarity with distance-based metrics.

## Algorithm

### LSS (Longest Similar Subsequence)

1. Sample points along both lines at regular intervals (default: 5m)
2. Find longest subsequence where point-to-point distance < threshold (default: 10m)
3. Return ratio of LSS length to shorter line length

### Hausdorff Distance

- Uses shapely's `hausdorff_distance()` method
- Converts from degrees to meters for Trondheim latitude (~63°N)

### Change Classification

The algorithm classifies each match into one of six categories:

| Change Type | LSS Ratio | Hausdorff | Description |
|-------------|-----------|-----------|-------------|
| **same** | >= 0.9 | <= 5m | Minimal change, essentially same road |
| **widened** | >= 0.8 | <= 10m | Road widened (width difference detected) |
| **rerouted** | >= 0.5 | <= 20m | Partial match, route changed |
| **replaced** | < 0.5 | > 20m | Same endpoints, completely different path |
| **removed** | N/A | N/A | Historical road with no OSM match |
| **new** | N/A | N/A | OSM road with no historical match |

## Usage

### Basic Usage

```bash
python3 scripts/merge/match_roads.py \
  --historical data/roads_historical.geojson \
  --osm data/roads_osm.geojson \
  --output data/roads_matched.geojson
```

### With Custom Thresholds

```bash
python3 scripts/merge/match_roads.py \
  --historical data/kartverket/1880/roads.geojson \
  --osm data/sources/osm/roads.geojson \
  --output data/merged/roads_temporal.geojson \
  --lss-threshold 0.6 \
  --hausdorff-max 30 \
  --sample-interval 10 \
  --match-threshold 15
```

## Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--historical` | (required) | Path to historical roads GeoJSON |
| `--osm` | (required) | Path to OSM roads GeoJSON |
| `--output` | (required) | Path to output merged GeoJSON |
| `--lss-threshold` | 0.7 | Minimum LSS ratio for match (0-1) |
| `--hausdorff-max` | 20 | Maximum Hausdorff distance (meters) |
| `--sample-interval` | 5 | Point sampling interval (meters) |
| `--match-threshold` | 10 | Point matching threshold (meters) |

## Output Format

The output GeoJSON includes these properties for each road:

```json
{
  "type": "Feature",
  "properties": {
    "src": "ml_1880",
    "sd": 1880,
    "ed": null,
    "ev": "m",
    "nm": "Kongens gate",
    "change": "widened",
    "match_score": 0.852,
    "hausdorff": 8.3,
    "src_all": ["ml_1880", "osm"]
  },
  "geometry": { ... }
}
```

### Output Properties

| Field | Type | Description |
|-------|------|-------------|
| `src` | string | Primary source (from historical data) |
| `sd` | int | Start date (construction year) |
| `ed` | int/null | End date (demolition year, null if still exists) |
| `ev` | string | Evidence level: h/m/l |
| `nm` | string | Road name (from OSM if matched) |
| `change` | string | Change type: same/widened/rerouted/replaced/removed/new |
| `match_score` | float | LSS ratio (0-1, higher = better match) |
| `hausdorff` | float | Hausdorff distance in meters |
| `src_all` | array | All contributing sources |

## Report Output

A JSON report is generated alongside the output file:

```json
{
  "input": {
    "historical": "data/roads_historical.geojson",
    "osm": "data/roads_osm.geojson",
    "historical_count": 450,
    "osm_count": 1250
  },
  "parameters": {
    "lss_threshold": 0.7,
    "hausdorff_max": 20.0,
    "sample_interval_m": 5.0,
    "match_threshold_m": 10.0
  },
  "output": {
    "total_roads": 1520,
    "statistics": {
      "same": 320,
      "widened": 85,
      "rerouted": 25,
      "replaced": 10,
      "removed": 10,
      "new": 800
    }
  }
}
```

## Example Workflow

### 1. Extract historical roads from 1880 map

```bash
python3 ml/predict.py --input data/kartverket/1880/map.png --output data/kartverket/1880/roads.geojson --type roads
```

### 2. Download modern OSM roads

```bash
# (Use Overpass API or similar)
# Save to data/sources/osm/roads.geojson
```

### 3. Match historical to modern

```bash
python3 scripts/merge/match_roads.py \
  --historical data/kartverket/1880/roads.geojson \
  --osm data/sources/osm/roads.geojson \
  --output data/roads_temporal.geojson
```

### 4. Visualize results

The output can be visualized in the frontend using the `change` property:

```javascript
map.addLayer({
  id: 'roads',
  type: 'line',
  source: 'roads',
  paint: {
    'line-color': [
      'match',
      ['get', 'change'],
      'same', '#2c5aa0',
      'widened', '#4a90e2',
      'rerouted', '#e8b339',
      'replaced', '#e85d75',
      'removed', '#999',
      'new', '#4caf50',
      '#ccc'
    ],
    'line-width': 2
  }
});
```

## Performance

- **O(n log n)** spatial indexing using shapely's STRtree
- **O(n²)** LSS calculation for matched pairs (unavoidable)
- Typical processing time: ~1-2 minutes for 1000 roads

## Dependencies

- Python 3.7+
- shapely >= 1.8.0

Install with:

```bash
pip install shapely
```

## Notes

- The script uses approximate coordinate-to-meter conversions for Trondheim latitude (~63°N)
- For other locations, adjust the conversion factors in `point_distance_m()` and `calculate_hausdorff_m()`
- Tuning parameters (`lss-threshold`, `hausdorff-max`) may be needed for different map qualities
