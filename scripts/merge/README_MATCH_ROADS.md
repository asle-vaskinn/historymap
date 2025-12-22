# Road Matching with LSS-Hausdorff Algorithm

## Overview

`match_roads.py` implements **LSS-Hausdorff matching** to correlate historical road segments with modern OSM roads. This algorithm classifies road changes over time into six categories: same, widened, rerouted, replaced, removed, and new.

## Key Features

1. **Longest Similar Subsequence (LSS)** - Geometric similarity metric
   - Samples points at regular intervals along both roads
   - Finds longest matching subsequence where points are within threshold
   - Returns ratio relative to shorter road

2. **Hausdorff Distance** - Maximum point separation metric
   - Uses shapely's built-in `hausdorff_distance()`
   - Converts degrees to meters for Trondheim latitude

3. **Change Classification** - Six-way categorization
   - Same, widened, rerouted, replaced, removed, new
   - Based on LSS ratio, Hausdorff distance, and endpoint matching

4. **Temporal Integration** - Preserves historical dates
   - Keeps `sd` (start date) from historical data
   - Infers `ed` (end date) for removed roads
   - Adds metadata (`match_score`, `hausdorff`, `change`)

## Algorithm Details

### LSS (Longest Similar Subsequence)

```python
def calculate_lss_ratio(line1, line2, sample_interval=5m, match_threshold=10m):
    """
    1. Sample points every 5m along both lines
    2. Use dynamic programming to find longest subsequence
       where corresponding points are < 10m apart
    3. Return: lss_length / min(len(points1), len(points2))
    """
```

**Time Complexity:** O(n²) where n = number of sample points per road

### Hausdorff Distance

```python
def calculate_hausdorff_m(line1, line2):
    """
    1. Use shapely's hausdorff_distance() (in degrees)
    2. Convert to meters: dist_m = dist_deg * 80000
       (approximation for 63°N latitude)
    """
```

### Change Classification Rules

| Type | Condition | Description |
|------|-----------|-------------|
| **same** | LSS >= 0.9 AND Hausdorff <= 5m | Virtually identical roads |
| **widened** | LSS >= 0.8 AND Hausdorff <= 10m AND width_change | Road expanded laterally |
| **rerouted** | LSS >= 0.5 | Partial match, route modified |
| **replaced** | LSS < 0.5 BUT endpoints_match | Same origin/destination, new path |
| **removed** | No match found | Historical road no longer exists |
| **new** | OSM with no historical match | Road built after historical period |

## Usage

### Basic Command

```bash
python3 scripts/merge/match_roads.py \
  --historical data/kartverket/1880/roads.geojson \
  --osm data/sources/osm/roads.geojson \
  --output data/roads_matched.geojson
```

### Full Options

```bash
python3 scripts/merge/match_roads.py \
  --historical <historical_roads.geojson> \
  --osm <osm_roads.geojson> \
  --output <output.geojson> \
  --lss-threshold 0.7      # Minimum LSS ratio (0-1)
  --hausdorff-max 20       # Max Hausdorff distance (meters)
  --sample-interval 5      # Point sampling interval (meters)
  --match-threshold 10     # Point match threshold (meters)
```

## Output Schema

Each road feature includes:

```json
{
  "type": "Feature",
  "geometry": { "type": "LineString", "coordinates": [...] },
  "properties": {
    "src": "ml_1880",           // Primary source
    "sd": 1880,                 // Start date (construction)
    "ed": null,                 // End date (null = still exists)
    "ev": "m",                  // Evidence: h/m/l
    "nm": "Kongens gate",       // Name (from OSM)
    "rt": "primary",            // Road type (from OSM)
    "change": "widened",        // Change type
    "match_score": 0.852,       // LSS ratio
    "hausdorff": 8.3,           // Hausdorff distance (m)
    "src_all": ["ml_1880", "osm"]  // All sources
  }
}
```

## Report Output

Generated as `<output>.report.json`:

```json
{
  "input": {
    "historical": "...",
    "osm": "...",
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

## Integration with Pipeline

The script fits into the data pipeline as follows:

```
Historical Maps (1880, 1904, etc.)
         │
         ▼
   ML Extraction (roads)
         │
         ▼
   Vectorization → historical_roads.geojson
         │
         ▼
   LSS-Hausdorff Matching ──► match_roads.py ◄── OSM roads.geojson
         │
         ▼
   roads_temporal.geojson
         │
         ▼
   PMTiles conversion → frontend visualization
```

## Tuning Parameters

### For High-Quality Historical Maps

```bash
--lss-threshold 0.8       # Stricter matching
--hausdorff-max 15        # Tighter tolerance
--sample-interval 3       # Finer sampling
--match-threshold 8       # Closer points
```

### For Low-Quality Historical Maps

```bash
--lss-threshold 0.6       # More lenient
--hausdorff-max 30        # Wider tolerance
--sample-interval 10      # Coarser sampling
--match-threshold 15      # Looser points
```

## Performance

- **Spatial complexity:** O(n log n) using shapely STRtree
- **Matching complexity:** O(m × k × p²) where:
  - m = historical roads
  - k = OSM candidates per historical road (usually 1-5)
  - p = points per road (~20-100)
- **Typical runtime:** 1-2 minutes for 1000 roads

## Dependencies

```bash
pip install shapely>=1.8.0
```

## Testing

```bash
# Validate Python syntax
python3 -m py_compile scripts/merge/match_roads.py

# Show help
python3 scripts/merge/match_roads.py --help

# Test with sample data (if available)
python3 scripts/merge/match_roads.py \
  --historical data/test/roads_historical_sample.geojson \
  --osm data/test/roads_osm_sample.geojson \
  --output data/test/roads_matched.geojson
```

## Limitations

1. **Coordinate conversion is approximate** - Assumes Trondheim latitude (~63°N)
   - For other locations, modify conversion factors in the code

2. **No topological awareness** - Treats each segment independently
   - Doesn't consider road networks or connectivity

3. **Width detection is heuristic** - May not catch all widenings
   - Samples perpendicular distances at fixed intervals

4. **Single best match** - Each historical road matches at most one OSM road
   - Road splits/merges may need manual review

## Future Enhancements

- [ ] Network-aware matching (consider connectivity)
- [ ] Multi-match support (one historical → multiple OSM)
- [ ] Attribute-based boosting (match score += name_similarity)
- [ ] Confidence scoring (probabilistic classification)
- [ ] Interactive review tool for borderline cases

## References

- Hausdorff distance: https://en.wikipedia.org/wiki/Hausdorff_distance
- Longest common subsequence: https://en.wikipedia.org/wiki/Longest_common_subsequence_problem
- Shapely documentation: https://shapely.readthedocs.io/

## See Also

- `MATCH_ROADS_USAGE.md` - Detailed usage guide
- `merge_roads.py` - Alternative merge approach using buffer overlap
- `../normalize/` - Data normalization scripts
- `../../docs/tech/DATA_SCHEMA.md` - Road temporal schema
