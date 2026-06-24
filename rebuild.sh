#!/bin/bash
#
# rebuild.sh - Full pipeline rebuild from scratch
#
# Usage:
#   ./rebuild.sh              # Run full pipeline (normalize → merge → export)
#   ./rebuild.sh --clean      # Clean intermediate files first, then rebuild
#   ./rebuild.sh --stage X    # Run specific stage only (normalize, merge, export)
#   ./rebuild.sh --help       # Show this help
#
# This script ensures consistent rebuilds by:
# - Using fail-fast (stops on first error)
# - Running validation after export
# - Restarting Docker to pick up new files
#

set -e  # Exit on first error (fail-fast)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_header() {
    echo ""
    echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}  $1${NC}"
    echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

show_help() {
    echo "Usage: ./rebuild.sh [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --clean         Clean intermediate files before rebuilding"
    echo "  --stage STAGE   Run only a specific stage (normalize, merge, export, all)"
    echo "  --no-restart    Don't restart Docker after rebuild"
    echo "  --no-validate   Skip validation step"
    echo "  --no-pmtiles    Skip PMTiles generation (GeoJSON only)"
    echo "  --help          Show this help message"
    echo ""
    echo "Examples:"
    echo "  ./rebuild.sh                    # Full rebuild with PMTiles"
    echo "  ./rebuild.sh --clean            # Clean and rebuild"
    echo "  ./rebuild.sh --stage merge      # Only run merge stage"
    echo "  ./rebuild.sh --no-pmtiles       # Skip PMTiles generation"
}

# Parse arguments
CLEAN=false
STAGE="all"
RESTART=true
VALIDATE=true
PMTILES=true  # PMTiles generation enabled by default (same as pipeline.py)

while [[ $# -gt 0 ]]; do
    case $1 in
        --clean)
            CLEAN=true
            shift
            ;;
        --stage)
            STAGE="$2"
            shift 2
            ;;
        --no-restart)
            RESTART=false
            shift
            ;;
        --no-validate)
            VALIDATE=false
            shift
            ;;
        --no-pmtiles)
            PMTILES=false
            shift
            ;;
        --help)
            show_help
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            show_help
            exit 1
            ;;
    esac
done

# Start
print_header "PIPELINE REBUILD"
echo "Stage: $STAGE"
echo "Clean: $CLEAN"
echo "PMTiles: $PMTILES"
echo "Timestamp: $(date '+%Y-%m-%d %H:%M:%S')"

# Clean if requested
if [ "$CLEAN" = true ]; then
    print_header "CLEANING INTERMEDIATE FILES"

    if [ -d "data/merged" ]; then
        echo "Cleaning data/merged/*.geojson..."
        rm -f data/merged/*.geojson
        rm -f data/merged/*.json
    fi

    if [ -d "data/export" ]; then
        echo "Cleaning data/export/*..."
        rm -f data/export/*.geojson
        rm -f data/export/*.pmtiles
        rm -f data/export/*.json
    fi

    print_success "Clean complete"
fi

# Ensure export directory exists
mkdir -p data/export

# Run pipeline stages
run_stage() {
    local stage=$1
    local stage_upper=$(echo "$stage" | tr '[:lower:]' '[:upper:]')
    print_header "STAGE: $stage_upper"

    local cmd="PYTHONPATH=scripts python3 scripts/pipeline.py --stage $stage"

    # pipeline.py generates PMTiles by default; only add --no-pmtiles if disabled
    if [ "$PMTILES" = false ] && [ "$stage" = "export" ]; then
        cmd="$cmd --no-pmtiles"
    fi

    echo "Running: $cmd"
    if eval "$cmd"; then
        print_success "Stage $stage complete"
        return 0
    else
        print_error "Stage $stage FAILED"
        return 1
    fi
}

case $STAGE in
    all)
        run_stage normalize
        run_stage merge
        run_stage export
        ;;
    normalize|merge|export)
        run_stage "$STAGE"
        ;;
    *)
        print_error "Unknown stage: $STAGE"
        echo "Valid stages: normalize, merge, export, all"
        exit 1
        ;;
esac

# Generate export manifest for cache-busting
print_header "GENERATING EXPORT MANIFEST"
if PYTHONPATH=scripts python3 scripts/export/export_manifest.py; then
    print_success "Manifest generated"
else
    print_warning "Manifest generation failed (non-fatal)"
fi

# Validate output
if [ "$VALIDATE" = true ]; then
    print_header "VALIDATING OUTPUT"

    # Check that output files exist
    if [ -f "data/export/buildings.geojson" ]; then
        BUILDING_COUNT=$(python3 -c "import json; print(len(json.load(open('data/export/buildings.geojson'))['features']))" 2>/dev/null || echo "0")
        print_success "buildings.geojson: $BUILDING_COUNT features"
    else
        print_warning "buildings.geojson not found"
    fi

    if [ -f "data/export/roads_temporal.geojson" ]; then
        ROAD_COUNT=$(python3 -c "import json; print(len(json.load(open('data/export/roads_temporal.geojson'))['features']))" 2>/dev/null || echo "0")
        print_success "roads_temporal.geojson: $ROAD_COUNT features"
    else
        print_warning "roads_temporal.geojson not found"
    fi

    if [ -f "data/export/buildings_temporal.pmtiles" ]; then
        PMTILES_SIZE=$(ls -lh data/export/buildings_temporal.pmtiles | awk '{print $5}')
        print_success "buildings_temporal.pmtiles: $PMTILES_SIZE"
    elif [ "$PMTILES" = true ]; then
        print_warning "PMTiles not generated (is tippecanoe installed?)"
    fi

    # Run validation script if it exists
    if [ -f "scripts/validate_export.py" ]; then
        echo ""
        echo "Running validation script..."
        if PYTHONPATH=scripts python3 scripts/validate_export.py; then
            print_success "Validation passed"
        else
            print_error "Validation FAILED"
            exit 1
        fi
    fi
fi

# Ensure base tiles are in data/export (Docker serves from here)
print_header "ENSURING BASE TILES"
if [ -f "frontend/data/trondheim.pmtiles" ] && [ ! -f "data/export/trondheim.pmtiles" ]; then
    echo "Copying base map tiles to data/export/..."
    cp frontend/data/trondheim.pmtiles data/export/
    print_success "Base tiles copied"
elif [ -f "data/export/trondheim.pmtiles" ]; then
    echo "Base tiles already present in data/export/"
else
    print_warning "trondheim.pmtiles not found - base map may not work"
fi

# Copy to frontend data directory (for non-Docker development)
print_header "COPYING TO FRONTEND"
if [ -d "frontend/data" ]; then
    cp -v data/export/buildings.geojson frontend/data/ 2>/dev/null || true
    cp -v data/export/roads_temporal.geojson frontend/data/ 2>/dev/null || true
    cp -v data/export/water.geojson frontend/data/ 2>/dev/null || true
    cp -v data/export/buildings_temporal.pmtiles frontend/data/ 2>/dev/null || true
    cp -v data/export/water.pmtiles frontend/data/ 2>/dev/null || true
    cp -v data/export/manifest.json frontend/data/ 2>/dev/null || true
    print_success "Copied to frontend/data/"
else
    print_warning "frontend/data/ not found, skipping copy"
fi

# Restart Docker
if [ "$RESTART" = true ]; then
    print_header "RESTARTING DOCKER"
    if command -v docker &> /dev/null && docker compose ps &> /dev/null; then
        echo "Recreating web container to pick up new files..."
        # Use --force-recreate to ensure volume mounts are refreshed
        # This is necessary because 'restart' doesn't update bind mounts
        docker compose up -d --force-recreate web 2>/dev/null || \
            docker-compose up -d --force-recreate web 2>/dev/null || \
            docker compose restart 2>/dev/null || true
        print_success "Docker containers updated"
    else
        print_warning "Docker not running, skipping restart"
    fi
fi

# Summary
print_header "REBUILD COMPLETE"
echo ""
echo "Output files:"
echo "  - data/export/buildings.geojson"
echo "  - data/export/roads_temporal.geojson"
echo "  - data/export/water.geojson"
[ "$PMTILES" = true ] && echo "  - data/export/buildings_temporal.pmtiles"
[ "$PMTILES" = true ] && echo "  - data/export/water.pmtiles"
[ "$PMTILES" = false ] && echo "  (PMTiles skipped - use default or remove --no-pmtiles to generate)"
echo ""
echo "Frontend files:"
echo "  - frontend/data/buildings.geojson"
echo "  - frontend/data/roads_temporal.geojson"
echo "  - frontend/data/water.geojson"
[ "$PMTILES" = true ] && echo "  - frontend/data/buildings_temporal.pmtiles"
[ "$PMTILES" = true ] && echo "  - frontend/data/water.pmtiles"
echo ""
print_success "Done! $(date '+%Y-%m-%d %H:%M:%S')"
