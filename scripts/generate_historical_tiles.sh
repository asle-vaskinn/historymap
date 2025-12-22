#!/bin/bash
# Generate PMTiles from the temporal building GeoJSON

set -e

DATA_DIR="$(dirname "$0")/../data"
cd "$DATA_DIR"

echo "Converting buildings_temporal.geojson to PMTiles..."

# Check if tippecanoe is available
if command -v tippecanoe &> /dev/null; then
    # Use tippecanoe for best results
    tippecanoe \
        -o buildings_temporal.pmtiles \
        -Z 10 -z 16 \
        --drop-densest-as-needed \
        --extend-zooms-if-still-dropping \
        -l buildings \
        buildings_temporal.geojson

    echo "Created buildings_temporal.pmtiles"
    ls -lh buildings_temporal.pmtiles
else
    echo "tippecanoe not found. Install with: brew install tippecanoe"
    echo ""
    echo "Alternative: Use the GeoJSON directly in the frontend"
    echo "The file is at: $DATA_DIR/buildings_temporal.geojson"
fi
