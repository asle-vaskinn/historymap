# Phase 1 Scripts - Data Download and Tile Generation

This directory contains scripts for downloading OSM data and generating PMTiles for the Trondheim Historical Map project.

## Overview

The Phase 1 scripts set up the data pipeline:

1. **download_osm.sh** - Downloads OpenStreetMap data for the Trondheim area
2. **generate_tiles.sh** - Converts OSM PBF to PMTiles format
3. **validate_phase1.sh** - Validates the complete Phase 1 setup

## Quick Start

```bash
# 1. Download OSM data
./download_osm.sh

# 2. Generate tiles
./generate_tiles.sh

# 3. Validate setup
./validate_phase1.sh
```

## Detailed Documentation

### 1. download_osm.sh

Downloads OpenStreetMap data for the Trondheim area using the Overpass API.

**Configuration:**
- **Bounding box**: [10.0, 63.3, 10.8, 63.5] (minlon, minlat, maxlon, maxlat)
- **Coverage**: Trondheim and surrounding municipalities (~3,000 km²)
- **Output**: `../data/trondheim.osm.pbf`

**Requirements:**
- `curl` - For downloading data
- `osmium-tool` - For PBF conversion

**Installation (osmium-tool):**

macOS:
```bash
brew install osmium-tool
```

Ubuntu/Debian:
```bash
sudo apt-get install osmium-tool
```

**Usage:**
```bash
./download_osm.sh
```

**Features:**
- Automatic retry on failure (3 attempts)
- Progress indicators
- File validation
- Error handling
- Skips download if file exists (with confirmation prompt)

**Expected runtime:** 3-10 minutes (depending on server load)

**Output file size:** Approximately 50-150 MB (compressed PBF format)

---

### 2. generate_tiles.sh

Converts OSM PBF data to PMTiles format for web display.

**Configuration:**
- **Input**: `../data/trondheim.osm.pbf`
- **Output**: `../data/trondheim.pmtiles` (or `.mbtiles` if PMTiles conversion unavailable)
- **Zoom levels**: z10-z16 (city viewing)
- **Layers**: buildings, roads, water, landuse, places

**Requirements:**

Choose one of the following tools:

**Option 1: Tilemaker (Recommended for macOS/Linux)**

macOS:
```bash
brew install tilemaker
```

Ubuntu/Debian:
```bash
sudo apt-get install tilemaker
```

From source:
```bash
git clone https://github.com/systemed/tilemaker.git
cd tilemaker
make
sudo make install
```

**Option 2: Planetiler (Cross-platform Java)**

Requires Java 17+:

macOS:
```bash
brew install openjdk@17
```

Ubuntu/Debian:
```bash
sudo apt-get install openjdk-17-jdk
```

The script will automatically download Planetiler JAR if Java is available.

**Optional: PMTiles CLI (for .pmtiles format)**

```bash
npm install -g pmtiles
```

Without this, the output will be in `.mbtiles` format (still usable with maplibre-gl-js).

**Usage:**
```bash
./generate_tiles.sh
```

**Features:**
- Auto-detection of available tools (tilemaker or planetiler)
- Preserves temporal attributes (start_date, end_date)
- Automatic MBTiles → PMTiles conversion (if pmtiles CLI available)
- Progress indicators
- File validation
- Cleanup of temporary files

**Expected runtime:**
- Tilemaker: 5-15 minutes
- Planetiler: 10-20 minutes

**Output file size:** Approximately 20-100 MB (depending on compression)

**Temporal Attributes:**

The script preserves OSM temporal tags:
- `start_date` → `start_year` (numeric)
- `end_date` → `end_year` (numeric)

These attributes enable time-based filtering in the frontend.

**Supported date formats:**
- `YYYY` (e.g., 1850)
- `YYYY-MM-DD` (e.g., 1850-06-15)
- `YYYY-MM` (e.g., 1850-06)

**Layers:**

| Layer | Min Zoom | Max Zoom | Features |
|-------|----------|----------|----------|
| building | 13 | 16 | Buildings with type, name, dates |
| road | 10 | 16 | Roads/highways with class, name, dates |
| water | 10 | 16 | Water bodies and waterways |
| landuse | 10 | 14 | Land use polygons |
| place | 10 | 16 | Place names and labels |

---

### 3. validate_phase1.sh

Validates that Phase 1 setup is complete and working.

**Checks:**
1. Directory structure (frontend/, data/, scripts/)
2. Required files (index.html, docker-compose.yml, etc.)
3. PMTiles file existence and validity
4. Docker availability and status
5. Python availability (alternative runtime)
6. Server startup test
7. nginx configuration validation

**Usage:**
```bash
./validate_phase1.sh
```

**Expected output:**
```
Trondheim Historical Map - Phase 1 Validation

======================================
1. Directory Structure
======================================
[PASS] frontend/ directory exists
[PASS] data/ directory exists
[PASS] scripts/ directory exists

...

======================================
Validation Summary
======================================

Passed: 15/15
Failed: 0/15

All checks passed! Phase 1 setup is complete.
```

---

## Directory Structure

After running the scripts, your directory structure will look like:

```
historymap/
├── data/
│   ├── trondheim.osm.pbf          # Downloaded OSM data
│   └── trondheim.pmtiles          # Generated tiles
├── scripts/
│   ├── download_osm.sh            # This script
│   ├── generate_tiles.sh          # This script
│   ├── validate_phase1.sh         # Validation script
│   ├── README.md                  # This file
│   └── tilemaker_config/          # Generated by generate_tiles.sh
│       ├── config.json
│       └── process.lua
└── frontend/
    └── ... (created separately)
```

---

## Troubleshooting

### download_osm.sh

**Problem: "osmium: command not found"**
- Install osmium-tool (see requirements above)

**Problem: Download timeout or failure**
- The Overpass API may be overloaded
- Wait a few minutes and try again
- The script will automatically retry 3 times

**Problem: "curl: (28) Operation timed out"**
- Your internet connection may be slow
- The Overpass API may be rate-limiting
- Try again later

### generate_tiles.sh

**Problem: "No suitable tile generation tool found"**
- Install either tilemaker or planetiler (see requirements above)

**Problem: "Java version is too old"**
- Planetiler requires Java 17+
- Install a newer Java version or use tilemaker instead

**Problem: Tilemaker fails with "unknown option"**
- Your tilemaker version may be outdated
- Update with: `brew upgrade tilemaker` (macOS) or install from source

**Problem: Planetiler runs out of memory**
- Increase Java heap size by editing the script:
  ```bash
  java -Xmx4g -jar ...  # Change 2g to 4g or higher
  ```
- Close other applications to free up RAM

**Problem: Output is .mbtiles instead of .pmtiles**
- Install pmtiles CLI: `npm install -g pmtiles`
- Or use .mbtiles format (maplibre-gl-js supports both)

---

## Advanced Usage

### Custom Bounding Box

To change the download area, edit `download_osm.sh`:

```bash
# Find these lines and modify:
MIN_LON=10.0
MIN_LAT=63.3
MAX_LON=10.8
MAX_LAT=63.5
```

### Custom Zoom Levels

To change tile zoom levels, edit `generate_tiles.sh`:

```bash
# Find these lines and modify:
MIN_ZOOM=10
MAX_ZOOM=16
```

Higher max zoom = more detail but larger file size.

### Adding Custom Layers

To add custom layers to the tiles, edit the Tilemaker configuration:

1. After running `generate_tiles.sh` once, find: `scripts/tilemaker_config/`
2. Edit `config.json` to add layers
3. Edit `process.lua` to define layer processing logic
4. Re-run `generate_tiles.sh`

---

## Performance Notes

**Download speed:**
- Depends on Overpass API server load
- Typical: 1-5 MB/s
- Peak times (weekday afternoons UTC): slower

**Tile generation speed:**
- Depends on CPU and disk speed
- Tilemaker: Generally faster, lower memory usage
- Planetiler: Slower, higher memory usage, but more features

**Recommended hardware:**
- CPU: 2+ cores
- RAM: 2GB minimum, 4GB recommended
- Disk: 1GB free space

---

## Next Steps

After successfully running these scripts:

1. Verify output with:
   ```bash
   ./validate_phase1.sh
   ```

2. Set up the frontend:
   - Follow instructions in `../frontend/README.md`

3. Start the development server:
   ```bash
   docker-compose up
   # or
   cd frontend && python3 -m http.server 8080
   ```

4. Open http://localhost:8080 in your browser

---

## Reference

- **Overpass API**: https://overpass-api.de/
- **Tilemaker**: https://github.com/systemed/tilemaker
- **Planetiler**: https://github.com/onthegomap/planetiler
- **PMTiles**: https://github.com/protomaps/PMTiles
- **OSM Wiki - Temporal Data**: https://wiki.openstreetmap.org/wiki/Key:start_date

---

## License

Scripts: MIT License
OSM Data: ODbL (OpenStreetMap Open Database License)
