# Phase 5: Quick Reference Card

## One-Line Execution

```bash
cd production && ./run_phase5.sh
```

## Prerequisites

```bash
# Python dependencies
pip install -r requirements.txt

# macOS system tools
brew install tippecanoe jq osmium-tool

# Optional: PMTiles CLI
# Download from https://github.com/protomaps/go-pmtiles/releases
```

## File Locations

```
Input Files (from previous phases):
  ../data/trondheim.osm.pbf          # Phase 1: OSM data
  ../data/extracted/*.geojson        # Phase 4: Historical extractions

Output Files (generated):
  ../data/trondheim.geojson          # Converted OSM
  ../data/final/trondheim_all_eras.geojson   # Merged data
  ../data/final/trondheim_all_eras.pmtiles   # Final tiles
```

## Core Commands

### 1. Convert OSM to GeoJSON
```bash
./convert_osm_to_geojson.sh ../data/trondheim.osm.pbf
```

### 2. Merge All Data
```bash
python merge_data.py \
    --osm ../data/trondheim.geojson \
    --historical ../data/extracted/ \
    --output ../data/final/trondheim_all_eras.geojson
```

### 3. Generate PMTiles
```bash
./generate_pmtiles.sh ../data/final/trondheim_all_eras.geojson
```

### 4. Validate Output
```bash
./validate_phase5.sh
```

## Feature Schema

```json
{
  "start_date": 1900,           // Integer year
  "end_date": 1950,             // Integer year or null
  "source": "osm",              // Data source
  "feature_class": "building",  // building|road|water|forest|railway|other
  "confidence": 0.85            // 0-1, ML confidence
}
```

## Troubleshooting

| Problem | Solution |
|---------|----------|
| No features loaded | Check input files exist |
| tippecanoe not found | `brew install tippecanoe` |
| Memory error | Increase `--similarity-threshold 0.9` |
| Output too large | Reduce MAX_ZOOM in generate_pmtiles.sh |

## Test & Debug

```bash
# Test merge logic
python test_merge.py

# Verbose logging
python merge_data.py --verbose ...

# Check feature count
jq '.features | length' ../data/final/trondheim_all_eras.geojson

# Check temporal range
jq '[.features[].properties.start_date | select(. != null)] | min, max' ../data/final/trondheim_all_eras.geojson
```

## Serve Locally

```bash
pmtiles serve ../data/final/trondheim_all_eras.pmtiles
# Open http://localhost:8080
```

## Next Steps

1. Test tiles in frontend
2. Verify time slider works
3. Deploy to production
4. Monitor performance

## Scripts Overview

| Script | Purpose |
|--------|---------|
| `merge_data.py` | Merge OSM + historical data |
| `generate_pmtiles.sh` | Create web-optimized tiles |
| `convert_osm_to_geojson.sh` | Convert OSM PBF format |
| `validate_phase5.sh` | Verify output quality |
| `run_phase5.sh` | Run complete workflow |
| `test_merge.py` | Test merge functionality |

## Performance

| Features | Merge Time | PMTiles Time | Total |
|----------|------------|--------------|-------|
| 50k | 2-3 min | 3-5 min | 6-9 min |
| 100k | 5-7 min | 7-10 min | 13-19 min |

## Documentation

- `README.md` - Complete documentation
- `QUICKSTART.md` - Step-by-step guide
- `PHASE5_COMPLETION_SUMMARY.md` - Overview
- `PHASE5_REFERENCE.md` - This file

## Success Checklist

- [ ] Prerequisites installed
- [ ] OSM data converted to GeoJSON
- [ ] Historical data present in extracted/
- [ ] Merge completes without errors
- [ ] PMTiles generated successfully
- [ ] Validation passes
- [ ] Can serve and view tiles locally

## Support

Check logs for detailed error messages. All scripts include comprehensive error handling and helpful diagnostics.
