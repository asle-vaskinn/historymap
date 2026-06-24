#!/bin/bash
#
# Generate raster tiles from georeferenced historical maps
#
# Usage:
#   ./scripts/generate_raster_tiles.sh                    # All maps
#   ./scripts/generate_raster_tiles.sh trondheim_1868     # Specific map
#   ./scripts/generate_raster_tiles.sh --pmtiles          # Also create PMTiles
#   ./scripts/generate_raster_tiles.sh --parallel         # Process maps in parallel
#
# Output:
#   data/export/tiles/{map_name}/     - XYZ tile directory
#   data/export/{map_name}.pmtiles    - PMTiles file (if --pmtiles)
#
# Typically run after georeferencing a new map in source_manager.html
#

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
INPUT_DIR="$PROJECT_DIR/data/georeference/output"
OUTPUT_DIR="$PROJECT_DIR/data/export/tiles"
PMTILES_DIR="$PROJECT_DIR/data/export"

# Tile settings
MIN_ZOOM=10
MAX_ZOOM=17
TILE_SIZE=256
RESAMPLING="lanczos"

# Auto-detect CPU cores for parallelization
if command -v nproc &> /dev/null; then
    CPU_CORES=$(nproc)
elif command -v sysctl &> /dev/null; then
    CPU_CORES=$(sysctl -n hw.ncpu 2>/dev/null || echo 4)
else
    CPU_CORES=4
fi

# Use half the cores for gdal2tiles (it's memory intensive)
PROCESSES=$((CPU_CORES / 2))
[ $PROCESSES -lt 2 ] && PROCESSES=2

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Parse arguments
CREATE_PMTILES=false
PARALLEL_MAPS=false
SPECIFIC_MAP=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --pmtiles)
            CREATE_PMTILES=true
            shift
            ;;
        --parallel|-p)
            PARALLEL_MAPS=true
            shift
            ;;
        --processes|-j)
            PROCESSES="$2"
            shift 2
            ;;
        --min-zoom)
            MIN_ZOOM="$2"
            shift 2
            ;;
        --max-zoom)
            MAX_ZOOM="$2"
            shift 2
            ;;
        --help|-h)
            echo "Usage: $0 [options] [map_name]"
            echo ""
            echo "Options:"
            echo "  --pmtiles       Also create PMTiles files"
            echo "  --parallel, -p  Process multiple maps in parallel"
            echo "  --processes N   CPU cores for tile generation (default: $PROCESSES)"
            echo "  --min-zoom N    Minimum zoom level (default: $MIN_ZOOM)"
            echo "  --max-zoom N    Maximum zoom level (default: $MAX_ZOOM)"
            echo "  --help          Show this help"
            echo ""
            echo "Examples:"
            echo "  $0                          # Process all maps sequentially"
            echo "  $0 --parallel               # Process all maps in parallel"
            echo "  $0 trondheim_1868           # Process specific map"
            echo "  $0 --pmtiles trondheim_1868 # Create tiles + PMTiles"
            echo "  $0 -j 8 trondheim_1868      # Use 8 cores for tile generation"
            exit 0
            ;;
        *)
            SPECIFIC_MAP="$1"
            shift
            ;;
    esac
done

# Check dependencies
check_dependencies() {
    local missing=()

    if ! command -v gdal2tiles.py &> /dev/null; then
        if ! command -v gdal2tiles &> /dev/null; then
            missing+=("gdal2tiles.py (install: brew install gdal)")
        fi
    fi

    if ! command -v gdalinfo &> /dev/null; then
        missing+=("gdalinfo (install: brew install gdal)")
    fi

    if $CREATE_PMTILES; then
        if ! command -v pmtiles &> /dev/null && ! command -v rio &> /dev/null; then
            echo -e "${YELLOW}Warning: Neither 'pmtiles' nor 'rio' found. PMTiles creation will be skipped.${NC}"
            echo "Install with: brew install pmtiles  OR  pip install rio-pmtiles"
            CREATE_PMTILES=false
        fi
    fi

    if [ ${#missing[@]} -ne 0 ]; then
        echo -e "${RED}Error: Missing dependencies:${NC}"
        for dep in "${missing[@]}"; do
            echo "  - $dep"
        done
        exit 1
    fi
}

# Get gdal2tiles command (handles different installations)
get_gdal2tiles_cmd() {
    if command -v gdal2tiles.py &> /dev/null; then
        echo "gdal2tiles.py"
    elif command -v gdal2tiles &> /dev/null; then
        echo "gdal2tiles"
    else
        echo ""
    fi
}

# Generate tiles for a single GeoTIFF
generate_tiles() {
    local input_file="$1"
    local map_name=$(basename "$input_file" .tif)
    local output_subdir="$OUTPUT_DIR/$map_name"

    echo -e "${BLUE}Processing: $map_name${NC}"

    # Check if input is georeferenced
    if ! gdalinfo "$input_file" 2>/dev/null | grep -q "Coordinate System is"; then
        echo -e "${YELLOW}  Skipping: Not georeferenced${NC}"
        return 1
    fi

    # Get CRS info
    local crs=$(gdalinfo "$input_file" 2>/dev/null | grep "EPSG" | head -1 || echo "Unknown")
    echo -e "  CRS: $crs"

    # Check file size
    local size=$(du -h "$input_file" | cut -f1)
    echo -e "  Size: $size"

    # Create output directory
    mkdir -p "$output_subdir"

    # Get gdal2tiles command
    local gdal2tiles=$(get_gdal2tiles_cmd)

    # Generate tiles
    echo -e "  Generating tiles (zoom $MIN_ZOOM-$MAX_ZOOM)..."

    $gdal2tiles \
        --profile=mercator \
        --zoom="$MIN_ZOOM-$MAX_ZOOM" \
        --resampling="$RESAMPLING" \
        --tiledriver=PNG \
        --processes="$PROCESSES" \
        --webviewer=none \
        "$input_file" \
        "$output_subdir" 2>&1 | while read line; do
            # Show progress dots
            if [[ "$line" == *"Generating"* ]] || [[ "$line" == *"%"* ]]; then
                echo -ne "."
            fi
        done

    echo ""

    # Count generated tiles
    local tile_count=$(find "$output_subdir" -name "*.png" 2>/dev/null | wc -l | tr -d ' ')
    local dir_size=$(du -sh "$output_subdir" 2>/dev/null | cut -f1)
    echo -e "  ${GREEN}Generated $tile_count tiles ($dir_size)${NC}"

    # Create PMTiles if requested
    if $CREATE_PMTILES; then
        create_pmtiles "$input_file" "$map_name"
    fi

    # Create metadata file
    create_metadata "$input_file" "$map_name" "$tile_count"

    return 0
}

# Create PMTiles from GeoTIFF
create_pmtiles() {
    local input_file="$1"
    local map_name="$2"
    local output_file="$PMTILES_DIR/${map_name}_raster.pmtiles"

    echo -e "  Creating PMTiles..."

    if command -v rio &> /dev/null; then
        # Use rio-pmtiles (better quality)
        rio pmtiles "$input_file" "$output_file" \
            --format PNG \
            --tile-size $TILE_SIZE \
            --resampling bilinear \
            --minzoom $MIN_ZOOM \
            --maxzoom $MAX_ZOOM 2>/dev/null || {
            echo -e "${YELLOW}  PMTiles creation failed (rio)${NC}"
            return 1
        }
    elif command -v pmtiles &> /dev/null; then
        # Convert from tile directory (less efficient)
        local tile_dir="$OUTPUT_DIR/$map_name"
        if [ -d "$tile_dir" ]; then
            # pmtiles doesn't directly support tile directories
            echo -e "${YELLOW}  PMTiles CLI doesn't support tile directories. Use rio-pmtiles.${NC}"
            return 1
        fi
    fi

    if [ -f "$output_file" ]; then
        local pmtiles_size=$(du -h "$output_file" | cut -f1)
        echo -e "  ${GREEN}PMTiles: $output_file ($pmtiles_size)${NC}"
    fi
}

# Create metadata JSON file
create_metadata() {
    local input_file="$1"
    local map_name="$2"
    local tile_count="$3"
    local meta_file="$OUTPUT_DIR/$map_name/metadata.json"

    # Get bounds from gdalinfo
    local bounds=$(gdalinfo -json "$input_file" 2>/dev/null | python3 -c "
import sys, json
try:
    info = json.load(sys.stdin)
    if 'wgs84Extent' in info:
        coords = info['wgs84Extent']['coordinates'][0]
        lons = [c[0] for c in coords]
        lats = [c[1] for c in coords]
        print(f'{min(lons)},{min(lats)},{max(lons)},{max(lats)}')
except:
    print('')
" 2>/dev/null || echo "")

    # Extract year from filename if possible
    local year=$(echo "$map_name" | grep -oE '[0-9]{4}' | head -1 || echo "unknown")

    cat > "$meta_file" << EOF
{
  "name": "$map_name",
  "description": "Historical map tiles for $map_name",
  "version": "1.0",
  "format": "png",
  "minzoom": $MIN_ZOOM,
  "maxzoom": $MAX_ZOOM,
  "bounds": "$bounds",
  "year": "$year",
  "tile_count": $tile_count,
  "generated": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
  "source": "$(basename "$input_file")"
}
EOF

    echo -e "  Metadata: $meta_file"
}

# Process a single map (for parallel execution)
process_single_map() {
    local tif="$1"
    local logfile="$2"

    if generate_tiles "$tif" > "$logfile" 2>&1; then
        echo "SUCCESS: $(basename "$tif")"
    else
        echo "FAILED: $(basename "$tif")"
    fi
}

# Export functions for parallel subshells
export -f generate_tiles process_single_map create_pmtiles create_metadata get_gdal2tiles_cmd
export INPUT_DIR OUTPUT_DIR PMTILES_DIR MIN_ZOOM MAX_ZOOM RESAMPLING PROCESSES TILE_SIZE
export CREATE_PMTILES RED GREEN YELLOW BLUE NC

# Main execution
main() {
    echo -e "${BLUE}=== Raster Tile Generator ===${NC}"
    echo -e "Using $PROCESSES CPU cores for tile generation"
    echo ""

    check_dependencies

    # Create output directory
    mkdir -p "$OUTPUT_DIR"
    mkdir -p "$PMTILES_DIR"

    # Find input files
    local processed=0
    local skipped=0

    if [ -n "$SPECIFIC_MAP" ]; then
        # Process specific map
        local input_file="$INPUT_DIR/${SPECIFIC_MAP}.tif"
        if [ ! -f "$input_file" ]; then
            echo -e "${RED}Error: File not found: $input_file${NC}"
            echo "Available maps:"
            ls -1 "$INPUT_DIR"/*.tif 2>/dev/null | xargs -I{} basename {} .tif | sed 's/^/  - /'
            exit 1
        fi

        if generate_tiles "$input_file"; then
            ((processed++))
        else
            ((skipped++))
        fi
    elif $PARALLEL_MAPS; then
        # Process all TIFFs in parallel
        echo "Input directory: $INPUT_DIR"
        echo "Output directory: $OUTPUT_DIR"
        echo -e "${YELLOW}Running in PARALLEL mode${NC}"
        echo ""

        # Collect valid TIFFs
        local tifs_to_process=()
        for tif in "$INPUT_DIR"/*.tif; do
            if [ -f "$tif" ]; then
                local basename=$(basename "$tif")
                if [[ "$basename" != *"_warped"* ]] && [[ "$basename" != *"_georef"* ]]; then
                    tifs_to_process+=("$tif")
                else
                    echo -e "${YELLOW}Skipping intermediate: $basename${NC}"
                    ((skipped++))
                fi
            fi
        done

        if [ ${#tifs_to_process[@]} -eq 0 ]; then
            echo "No maps to process"
            return
        fi

        echo "Processing ${#tifs_to_process[@]} maps in parallel..."
        echo ""

        # Create temp directory for logs
        local log_dir=$(mktemp -d)
        local pids=()

        # Start background jobs
        for tif in "${tifs_to_process[@]}"; do
            local map_name=$(basename "$tif" .tif)
            local logfile="$log_dir/$map_name.log"

            echo -e "${BLUE}Starting: $map_name${NC}"
            generate_tiles "$tif" > "$logfile" 2>&1 &
            pids+=($!)
        done

        # Wait for all jobs and collect results
        echo ""
        echo "Waiting for ${#pids[@]} parallel jobs..."
        for i in "${!pids[@]}"; do
            local pid=${pids[$i]}
            local tif="${tifs_to_process[$i]}"
            local map_name=$(basename "$tif" .tif)
            local logfile="$log_dir/$map_name.log"

            if wait $pid; then
                echo -e "${GREEN}✓ $map_name${NC}"
                ((processed++))
            else
                echo -e "${RED}✗ $map_name (see $logfile)${NC}"
                ((skipped++))
            fi
        done

        # Show logs location
        echo ""
        echo "Logs: $log_dir/"
    else
        # Process all TIFFs sequentially
        echo "Input directory: $INPUT_DIR"
        echo "Output directory: $OUTPUT_DIR"
        echo ""

        for tif in "$INPUT_DIR"/*.tif; do
            if [ -f "$tif" ]; then
                # Skip intermediate files
                local basename=$(basename "$tif")
                if [[ "$basename" == *"_warped"* ]] || [[ "$basename" == *"_georef"* ]]; then
                    echo -e "${YELLOW}Skipping intermediate: $basename${NC}"
                    ((skipped++))
                    continue
                fi

                if generate_tiles "$tif"; then
                    ((processed++))
                else
                    ((skipped++))
                fi
                echo ""
            fi
        done
    fi

    echo -e "${GREEN}=== Complete ===${NC}"
    echo "Processed: $processed maps"
    echo "Skipped: $skipped maps"
    echo ""
    echo "Tiles location: $OUTPUT_DIR/"

    if $CREATE_PMTILES; then
        echo "PMTiles location: $PMTILES_DIR/"
    fi
}

main "$@"
