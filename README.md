# Trondheim Historical Map System

A web-based system for viewing historical maps of Trondheim and surrounding areas across different time periods. This project uses ML-extracted features from historical maps combined with modern OpenStreetMap data, presented through an interactive time slider interface.

## Overview

This system allows you to:
- View maps of the Trondheim++ region (Trondheim, Malvik, Stjørdal, Meråker, Melhus, Skaun, Klæbu)
- Travel through time from 1850 to present using an interactive slider
- See how buildings, roads, railways, and other features appeared and disappeared over time
- Explore the evolution of urban development in the region

The project combines:
- **Modern data**: OpenStreetMap with temporal attributes
- **Historical data**: ML-extracted features from Kartverket historical maps
- **Interactive frontend**: MapLibre GL JS with time-based filtering
- **Vector tiles**: Efficient PMTiles format for web delivery

## Current Status: Phase 1

Phase 1 provides the infrastructure and frontend for viewing map data with a time slider. The system is ready to display maps, though historical feature extraction (Phases 2-4) is still in development.

## Prerequisites

### Option A: Using Docker (Recommended)
- [Docker Desktop](https://www.docker.com/products/docker-desktop) or Docker Engine
- Docker Compose (included with Docker Desktop)

### Option B: Without Docker
- Python 3.7+ (for running a simple HTTP server)
- A modern web browser (Chrome, Firefox, Safari, Edge)

## Quick Start

### Using Docker

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd historymap
   ```

2. **Ensure data files exist**

   Make sure you have `data/trondheim.pmtiles`. If not, run the data generation scripts:
   ```bash
   # Download OSM data for Trondheim
   ./scripts/download_osm.sh

   # Generate PMTiles (requires tippecanoe or planetiler)
   ./scripts/generate_tiles.sh
   ```

3. **Start the server**
   ```bash
   docker-compose up
   ```

4. **Open in browser**

   Navigate to [http://localhost:8080](http://localhost:8080)

5. **Stop the server**
   ```bash
   # Press Ctrl+C in the terminal, or
   docker-compose down
   ```

### Without Docker (Python HTTP Server)

1. **Navigate to the frontend directory**
   ```bash
   cd frontend
   ```

2. **Start Python's built-in HTTP server**
   ```bash
   # Python 3
   python3 -m http.server 8080

   # or Python 2
   python -m SimpleHTTPServer 8080
   ```

3. **Open in browser**

   Navigate to [http://localhost:8080](http://localhost:8080)

   **Note**: The Python HTTP server method requires the PMTiles file to be accessible from the frontend directory. You may need to create a symlink:
   ```bash
   ln -s ../data data
   ```

## Validation

To verify your Phase 1 setup is working correctly:

```bash
./scripts/validate_phase1.sh
```

This script checks:
- Directory structure and required files
- PMTiles file validity
- Docker/Python availability
- Server startup and response
- Configuration correctness

## Project Structure

```
historymap/
├── README.md                      # This file
├── HISTORICAL_MAP_PROJECT_PLAN.md # Detailed project plan
├── docker-compose.yml             # Docker services configuration
├── nginx.conf                     # Nginx web server configuration
├── frontend/                      # Web application files
│   ├── index.html                 # Main HTML page
│   ├── style.css                  # Styles
│   └── app.js                     # Map and time slider logic
├── data/                          # Map data files
│   └── trondheim.pmtiles          # Vector tile data
└── scripts/                       # Utility scripts
    ├── download_osm.sh            # Download OSM data
    ├── generate_tiles.sh          # Generate PMTiles
    └── validate_phase1.sh         # Validation script
```

## Usage

### Time Slider
- Drag the time slider to select a year between 1850 and present
- Features with temporal attributes will appear/disappear based on their start and end dates
- A feature is visible if: `start_date <= selected_year AND (end_date >= selected_year OR end_date is null)`

### Map Controls
- **Zoom**: Mouse wheel, double-click, or +/- buttons
- **Pan**: Click and drag
- **Tilt**: Right-click and drag (or Ctrl+drag on Mac)
- **Rotate**: Ctrl+click and drag (or Cmd+click on Mac)

## Technical Details

### Data Format
- **PMTiles**: A single-file archive format for vector map tiles
- **Vector tiles**: Efficient, scalable format that renders on the client
- **Temporal attributes**: Each feature can have `start_date` and `end_date` properties

### Server Configuration
The nginx server is configured with:
- **CORS headers**: Allows cross-origin requests for local development
- **Proper MIME types**: Correct content types for `.pmtiles`, `.mvt`, and other map formats
- **Gzip compression**: Reduces bandwidth usage
- **Cache headers**: Optimizes tile delivery (30 days for tiles, 7 days for assets)
- **Range request support**: Enables efficient PMTiles random access

### Browser Support
- Chrome/Edge 79+
- Firefox 70+
- Safari 13.1+
- Any browser with WebGL support

## Troubleshooting

### Port 8080 already in use
```bash
# Change the port in docker-compose.yml
ports:
  - "8081:80"  # Use 8081 instead
```

### PMTiles file not loading
1. Check that `data/trondheim.pmtiles` exists and has a valid size
2. Verify the file isn't corrupted (run `./scripts/validate_phase1.sh`)
3. Check browser console for CORS or network errors

### Docker container won't start
```bash
# View detailed logs
docker-compose logs

# Rebuild the container
docker-compose up --build

# Check if port is in use
lsof -i :8080  # on macOS/Linux
netstat -ano | findstr :8080  # on Windows
```

### Map doesn't load
1. Open browser Developer Tools (F12)
2. Check the Console tab for JavaScript errors
3. Check the Network tab for failed requests
4. Verify your browser supports WebGL

## Development

### File Locations
- Frontend code: `frontend/`
- Map styles: Embedded in `frontend/app.js`
- Server config: `nginx.conf`
- Data files: `data/`

### Adding New Data
1. Generate or obtain GeoJSON with temporal attributes
2. Convert to PMTiles using tippecanoe or planetiler
3. Place in `data/` directory
4. Update `frontend/app.js` to reference the new source

### Customizing Styles
Edit the MapLibre style configuration in `frontend/app.js` to change colors, line widths, or add new feature layers.

## Project Phases

This is a multi-phase project:

1. **Phase 1 (Current)**: Infrastructure + Frontend - Working map viewer with time slider
2. **Phase 2**: Synthetic Data Pipeline - Generate training data from modern vectors
3. **Phase 3**: ML Training - Train U-Net model for feature extraction
4. **Phase 4**: Real Data Integration - Process historical maps from Kartverket
5. **Phase 5**: Production - Deploy complete system with all historical data

For detailed information about the full project plan, see [HISTORICAL_MAP_PROJECT_PLAN.md](HISTORICAL_MAP_PROJECT_PLAN.md).

## Data Sources

- **Modern data**: OpenStreetMap (ODbL license)
- **Historical maps**: Kartverket (Norwegian Mapping Authority)
  - Maps >100 years old: Public domain
  - Maps <100 years old: CC BY 4.0

## License

This project: MIT License

Map data: Depends on sources
- OpenStreetMap derivatives: ODbL
- Kartverket historical maps: CC0/CC-BY

## Contributing

This is a personal project, but feedback and suggestions are welcome. Please note that Phase 1 is focused on infrastructure - the historical feature extraction comes in later phases.

## Links

- Project Plan: [HISTORICAL_MAP_PROJECT_PLAN.md](HISTORICAL_MAP_PROJECT_PLAN.md)
- MapLibre GL JS: https://maplibre.org/
- PMTiles: https://protomaps.com/docs/pmtiles
- OpenStreetMap: https://www.openstreetmap.org/
- Kartverket: https://www.kartverket.no/

## Support

For issues or questions about this project, please refer to the project plan or create an issue in the repository.

---

**Built with Claude Code**
