# Start Phase 5: Production Deployment

Launch parallel workers to prepare for production.

## Prerequisites
Phase 4 must be complete. Verify: `ls data/extracted/*.geojson`

## Overview
Phase 5 merges all data and deploys the complete system.

## Parallel Work Streams

Spawn **3 parallel agents**:

### Agent 1: Data Merging & Tile Generation
```
Merge and prepare final data.
- production/merge_data.py - combine OSM + extracted historical features
- Handle overlapping features across eras
- Consistent schema: start_date, end_date, source, confidence
- production/generate_pmtiles.sh - create optimized tiles
- Output: data/final/trondheim_all_eras.geojson, .pmtiles
```

### Agent 2: Frontend Updates
```
Update frontend for historical data.
- Historical-appropriate styling for old features
- Era indicator showing selected year
- Legend with data sources and confidence levels
- About page with methodology
- Mobile-responsive improvements
- Performance optimization for large datasets
```

### Agent 3: Deployment & Documentation
```
Create deployment infrastructure.
- production/Dockerfile - self-contained deployment
- production/deploy-github-pages.sh
- production/deploy-cloudflare.sh (optional)
- docs/user_guide.md
- docs/methodology.md
- docs/data_sources.md
- Update README.md with final instructions
```

## Coordination
After agents complete:
1. Build and test Docker container
2. Verify all eras display correctly
3. Test time slider filtering
4. Deploy to chosen platform
5. Share the URL!
