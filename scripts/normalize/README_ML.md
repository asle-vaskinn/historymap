# ML Detection Normalizer

This normalizer processes ML-detected building polygons from historical maps and converts them to the unified normalized schema.

## Overview

The ML detection pipeline (ml/predict.py → ml/vectorize.py) produces GeoJSON files with building polygons extracted from historical map rasters. This normalizer converts those raw ML outputs into the standardized schema used across all data sources.

## Input Data Structure

Expected directory structure:
```
data/sources/ml_detected/
├── kartverket_1880/
│   ├── manifest.json
│   ├── raw/
│   │   └── buildings.geojson  (ML vectorized output)
│   └── normalized/
│       └── buildings.geojson  (created by this script)
├── kartverket_1904/
│   └── ...
└── aerial_1947/
    └── ...
```

### Input GeoJSON Format

Expected format from ml/vectorize.py:
```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "properties": {
        "class": "building",
        "class_id": 1,
        "feature_id": "building_0",
        "area": 156.3,
        "confidence": 0.92
      },
      "geometry": {
        "type": "Polygon",
        "coordinates": [...]
      }
    }
  ]
}
```

## Output Schema

Normalized features include:

### Required Fields
- `_src`: Source identifier (e.g., "ml_detected/kartverket_1880")
- `_src_id`: Unique ID (e.g., "kv1880_building_0")
- `_ingested`: Date of normalization (YYYY-MM-DD)

### Temporal Fields
- `sd`: Start date - year of the source map (e.g., 1880)
- `ed`: End date - always null for ML detections
- `ev`: Evidence level based on ML confidence:
  - `h` = high (confidence ≥ 0.9)
  - `m` = medium (0.7 ≤ confidence < 0.9)
  - `l` = low (confidence < 0.7)

### Building Fields
- `bt`: Building type (always "building" for ML detections)
- `nm`: Building name (usually null)

### ML-Specific Fields
- `mlc`: ML confidence score (float 0-1)
- `ml_src`: Short map source code (e.g., "kv1880", "air1947")

### Raw Data Preservation
- `_raw`: Object containing original ML output properties

## Usage

### Normalize Single Map Source
```bash
python3 -m scripts.normalize.normalize_ml --map-source kartverket_1880
```

### Normalize All ML Sources
```bash
python3 -m scripts.normalize.normalize_ml --all
```

### Custom Data Directory
```bash
python3 -m scripts.normalize.normalize_ml --map-source kartverket_1880 --data-dir /path/to/data
```

### Help
```bash
python3 -m scripts.normalize.normalize_ml --help
```

## Map Source Code Mapping

The script automatically generates short map source codes from source IDs:

| Source ID | Map Source Code | Reference Year |
|-----------|----------------|----------------|
| ml_kartverket_1880 | kv1880 | 1880 |
| ml_kartverket_1904 | kv1904 | 1904 |
| ml_aerial_1947 | air1947 | 1947 |

## Manifest Integration

The script reads the manifest.json in each map source directory to extract:
- `coverage.temporal.reference_year`: Year of the source map
- `ml_model.confidence_threshold`: Confidence threshold used during detection

The manifest is updated after normalization with:
- `normalized_at`: Timestamp of normalization
- `normalized_count`: Number of features normalized

## Confidence-Based Evidence Levels

ML confidence scores are mapped to evidence levels:

```python
if confidence >= 0.9:
    ev = 'h'  # High confidence
elif confidence >= 0.7:
    ev = 'm'  # Medium confidence
else:
    ev = 'l'  # Low confidence
```

This allows downstream processing to filter or weight features based on detection confidence.

## Example Output

```json
{
  "type": "Feature",
  "properties": {
    "_src": "ml_detected/kartverket_1880",
    "_src_id": "kv1880_building_0",
    "_ingested": "2025-12-17",
    "sd": 1880,
    "ev": "h",
    "bt": "building",
    "mlc": 0.92,
    "ml_src": "kv1880",
    "_raw": {
      "ml_confidence": 0.92,
      "ml_src": "kv1880",
      "area": 156.3,
      "class_id": 1,
      "class_name": "building",
      "feature_id": "building_0"
    }
  },
  "geometry": {
    "type": "Polygon",
    "coordinates": [...]
  }
}
```

## Implementation Details

### Class: Normalizer(BaseNormalizer)

Extends `BaseNormalizer` with ML-specific logic.

**Key Methods:**
- `normalize()`: Main normalization logic
  - Reads manifest for reference year
  - Processes all GeoJSON files in raw/
  - Filters for building class (class_id=1)
  - Maps confidence to evidence level
  - Creates normalized features

**Helper Functions:**
- `parse_map_date_from_source_id()`: Extract year from source ID
- `parse_map_source_code()`: Generate short map code
- `confidence_to_evidence_level()`: Map confidence to ev level

## Validation

The script validates all normalized features against the base schema:
- Required fields present
- Valid evidence level (h/m/l)
- Valid geometry

## Integration with Data Pipeline

This normalizer is part of the overall data pipeline:

```
Historical Maps (rasters)
  ↓
ML Inference (ml/predict.py) → Segmentation masks
  ↓
Vectorization (ml/vectorize.py) → Raw GeoJSON
  ↓
Normalization (normalize_ml.py) → Normalized GeoJSON ← YOU ARE HERE
  ↓
Merging (scripts/merge/) → Unified temporal dataset
  ↓
Tile Generation → PMTiles for frontend
```

## See Also

- `base.py`: Base normalizer class
- `normalize_osm.py`: OSM data normalizer (implementation reference)
- `ml/vectorize.py`: ML vectorization script
- `CLAUDE.md`: Project overview
