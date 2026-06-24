# Quick Start Guide - Trondheim Historical Map

## Setup Commands

### First Time Setup

```bash
# 1. Download OSM data for Trondheim
./scripts/download_osm.sh

# 2. Generate PMTiles from OSM data
./scripts/generate_tiles.sh

# 3. Validate the setup
./scripts/validate_phase1.sh
```

### Start the Server

**Option A: Using Docker (Recommended)**
```bash
# Start the server
docker-compose up

# Start in background (detached mode)
docker-compose up -d

# Stop the server
docker-compose down

# View logs
docker-compose logs -f
```

**Option B: Without Docker**
```bash
cd frontend
python3 -m http.server 8080
# Then open http://localhost:8080
```

## Access the Application

Open your browser and navigate to:
```
http://localhost:8080
```

## Key Features

- **Time Slider**: Drag to select years from 1850 to 2025
- **Map Controls**: 
  - Zoom: Mouse wheel or +/- buttons
  - Pan: Click and drag
  - Tilt: Right-click and drag
  - Rotate: Ctrl+click and drag

## Troubleshooting

### Port Already in Use
```bash
# Check what's using port 8080
lsof -i :8080

# Or change the port in docker-compose.yml to 8081
ports:
  - "8081:80"
```

### Docker Issues
```bash
# Check Docker is running
docker info

# Rebuild container
docker-compose up --build

# View detailed logs
docker-compose logs
```

### PMTiles Not Loading
```bash
# Verify file exists and has data
ls -lh data/trondheim.pmtiles

# Re-run validation
./scripts/validate_phase1.sh
```

## File Locations

```
/Users/vaskinn/Development/private/historymap/
├── docker-compose.yml     # Docker configuration
├── nginx.conf            # Web server config
├── README.md             # Full documentation
├── frontend/             # Web application
├── data/                 # Map data (PMTiles)
└── scripts/              # Utility scripts
```

## Next Steps

1. Generate or obtain real PMTiles data
2. Test the time slider functionality
3. Customize map styles in `frontend/app.js`
4. Move to Phase 2: Synthetic data generation

## More Information

- Full README: [README.md](README.md)
- Project Plan: [HISTORICAL_MAP_PROJECT_PLAN.md](HISTORICAL_MAP_PROJECT_PLAN.md)
- Validation: `./scripts/validate_phase1.sh`
