# Extract Scripts

Scripts for extracting vector features from raster data sources.

## extract_roads.py

Extracts road centerlines from ML prediction images using skeletonization and vectorization.

### Features

- Loads grayscale prediction images (road confidence maps)
- Thresholds to binary mask (default 0.5)
- Skeletonizes to 1-pixel width centerlines using scikit-image
- Traces connected components as LineStrings
- Simplifies using Douglas-Peucker algorithm
- Splits at intersections for segment-based tracking
- Outputs GeoJSON with temporal properties

### Georeferencing Support

The script supports three methods for georeferencing (in priority order):

1. **World files** (.jgw, .pgw, .tfw) - Automatically detected next to image
2. **Explicit bounds** - Via `--bounds` parameter
3. **Pixel coordinates** - Falls back if no georeferencing available

### Usage Examples

```bash
# Basic usage with world file
python scripts/extract/extract_roads.py \
    --input data/kartverket/prediction.png \
    --output data/roads_1880.geojson

# With explicit bounds
python scripts/extract/extract_roads.py \
    --input prediction.png \
    --output roads.geojson \
    --bounds 10.37,63.42,10.44,63.44

# Adjust extraction parameters
python scripts/extract/extract_roads.py \
    --input prediction.png \
    --output roads.geojson \
    --threshold 0.6 \
    --simplify-tolerance 3 \
    --min-length 10

# Add temporal metadata
python scripts/extract/extract_roads.py \
    --input data/kartverket/prediction_1880.png \
    --output data/roads_1880.geojson \
    --year 1880 \
    --source ml80 \
    --evidence m
```

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `--input` | Path | Required | Path to prediction image |
| `--output` | Path | Required | Path to output GeoJSON |
| `--threshold` | Float | 0.5 | Confidence threshold (0.0-1.0) |
| `--simplify-tolerance` | Float | 2.0 | Douglas-Peucker tolerance in pixels |
| `--min-length` | Float | 5.0 | Minimum line length in pixels |
| `--bounds` | String | None | Geographic bounds "west,south,east,north" |
| `--source` | String | 'ml' | Source identifier |
| `--evidence` | String | 'm' | Evidence level: h/m/l |
| `--year` | Integer | None | Year of source map |

### Output Schema

The output GeoJSON follows the road temporal data schema from `docs/tech/DATA_SCHEMA.md`:

```json
{
  "type": "FeatureCollection",
  "metadata": {
    "feature_type": "road",
    "feature_count": 123,
    "source": "ml",
    "reference_year": 1880,
    "georeferenced": true
  },
  "features": [
    {
      "type": "Feature",
      "geometry": {
        "type": "LineString",
        "coordinates": [[10.38, 63.42], [10.39, 63.43], ...]
      },
      "properties": {
        "rid": "ml_road_0",
        "src": "ml",
        "ev": "m",
        "length": 125.3,
        "sd": 1880,
        "sd_t": "n",
        "sd_s": "ml1880"
      }
    }
  ]
}
```

### Dependencies

- PIL/Pillow - Image loading
- numpy - Array operations
- scikit-image - Skeletonization (`skimage.morphology.skeletonize`)
- shapely - Geometry operations
- cv2 (OpenCV) - Connected components

All dependencies are listed in `requirements.txt`.

### Processing Pipeline

1. **Load** - Load prediction image and threshold to binary mask
2. **Skeletonize** - Reduce road areas to 1-pixel centerlines
3. **Trace** - Convert skeleton pixels to LineStrings using connected components
4. **Simplify** - Apply Douglas-Peucker simplification
5. **Split** - Split at intersections for segment-based tracking (TODO)
6. **Transform** - Convert from pixel to geographic coordinates
7. **Export** - Save as GeoJSON with temporal properties

### Known Limitations

- **Intersection splitting** is not yet fully implemented (currently returns unsplit lines)
- **Complex intersections** may not be handled optimally
- **Very thin roads** (<3 pixels wide) may not skeletonize well

### Integration

This script is designed to work with:

- ML prediction outputs from `ml/predict.py`
- Historical map processing from `scripts/extract_from_map.py`
- Data pipeline from `scripts/pipeline.py`
- Normalization scripts in `scripts/normalize/`

The output can be ingested into the temporal database using `scripts/ingest/` scripts.
