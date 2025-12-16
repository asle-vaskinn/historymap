# Start Phase 1: Infrastructure + Frontend

Launch parallel workers to build Phase 1 components concurrently.

## Overview
Phase 1 creates the foundation: OSM data pipeline, MapLibre frontend, and Docker setup.

## Parallel Work Streams

You should spawn **3 parallel agents** to work on these independent tasks:

### Agent 1: Frontend Development
```
Build the MapLibre GL JS frontend with time slider.
- Create frontend/index.html, style.css, app.js
- Time slider range: 1850-2025
- Filter features by start_date/end_date
- Center on Trondheim (63.43°N, 10.39°E)
- Responsive design
- Use PMTiles protocol handler
```

### Agent 2: Data Pipeline Scripts
```
Create scripts to download and process OSM data.
- scripts/download_osm.sh - fetch Trondheim from Geofabrik
- scripts/generate_tiles.sh - convert to PMTiles using tippecanoe or planetiler
- Bounding box: [10.0, 63.3, 10.8, 63.5]
- Preserve temporal attributes (start_date, end_date)
```

### Agent 3: Infrastructure
```
Create Docker and validation setup.
- docker-compose.yml with nginx for static files
- scripts/validate_phase1.sh - verify everything works
- README.md with setup instructions
```

## Coordination Points
After all agents complete:
1. Test that frontend can load the generated PMTiles
2. Verify docker-compose brings up working system
3. Check time slider filters features correctly

## Launch Command
Use the Task tool to spawn 3 agents in parallel, one for each work stream above.
