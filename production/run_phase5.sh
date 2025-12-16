#!/bin/bash
################################################################################
# Phase 5: Complete Workflow Script
#
# Runs the complete Phase 5 workflow:
# 1. Convert OSM PBF to GeoJSON (if needed)
# 2. Merge OSM and historical data
# 3. Generate PMTiles
# 4. Validate output
#
# This is a convenience script that runs all steps in sequence.
#
# Usage:
#   ./run_phase5.sh [--skip-conversion]
#
# Options:
#   --skip-conversion  Skip OSM conversion (assumes GeoJSON already exists)
################################################################################

set -e
set -u
set -o pipefail

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configuration
OSM_PBF="../data/trondheim.osm.pbf"
OSM_GEOJSON="../data/trondheim.geojson"
HISTORICAL_DIR="../data/extracted"
OUTPUT_GEOJSON="../data/final/trondheim_all_eras.geojson"
OUTPUT_PMTILES="../data/final/trondheim_all_eras.pmtiles"

SKIP_CONVERSION=false

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[✓]${NC} $1"
}

log_error() {
    echo -e "${RED}[✗]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_header() {
    local title="$1"
    echo ""
    echo "=================================================="
    echo "  $title"
    echo "=================================================="
    echo ""
}

check_prerequisites() {
    print_header "Checking Prerequisites"

    local missing=false

    # Check Python
    if ! command -v python3 &> /dev/null; then
        log_error "python3 not found"
        missing=true
    else
        log_success "python3 found"
    fi

    # Check tippecanoe
    if ! command -v tippecanoe &> /dev/null; then
        log_error "tippecanoe not found (required for PMTiles generation)"
        echo "  Install: brew install tippecanoe"
        missing=true
    else
        log_success "tippecanoe found"
    fi

    # Check Python dependencies
    if ! python3 -c "import shapely, geojson" 2>/dev/null; then
        log_error "Python dependencies not installed"
        echo "  Run: pip install -r requirements.txt"
        missing=true
    else
        log_success "Python dependencies installed"
    fi

    # Optional: jq
    if ! command -v jq &> /dev/null; then
        log_warning "jq not found (recommended for validation)"
        echo "  Install: brew install jq"
    else
        log_success "jq found"
    fi

    # Optional: pmtiles
    if ! command -v pmtiles &> /dev/null; then
        log_warning "pmtiles CLI not found (recommended for validation)"
        echo "  Install: https://github.com/protomaps/go-pmtiles/releases"
    else
        log_success "pmtiles CLI found"
    fi

    if [[ "$missing" == true ]]; then
        log_error "Missing required dependencies. Please install them first."
        exit 1
    fi

    log_success "All required prerequisites met"
}

step_1_convert_osm() {
    if [[ "$SKIP_CONVERSION" == true ]]; then
        log_info "Skipping OSM conversion (--skip-conversion flag set)"
        return 0
    fi

    print_header "Step 1: Convert OSM PBF to GeoJSON"

    if [[ -f "$OSM_GEOJSON" ]]; then
        log_warning "GeoJSON already exists: $OSM_GEOJSON"
        read -p "Overwrite? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            log_info "Skipping conversion"
            return 0
        fi
    fi

    if [[ ! -f "$OSM_PBF" ]]; then
        log_error "OSM PBF file not found: $OSM_PBF"
        echo ""
        echo "Please run Phase 1 download script first:"
        echo "  cd ../scripts"
        echo "  ./download_osm.sh"
        echo ""
        exit 1
    fi

    ./convert_osm_to_geojson.sh "$OSM_PBF" "$OSM_GEOJSON"

    log_success "Step 1 completed"
}

step_2_merge_data() {
    print_header "Step 2: Merge OSM and Historical Data"

    if [[ ! -f "$OSM_GEOJSON" ]]; then
        log_error "OSM GeoJSON not found: $OSM_GEOJSON"
        echo "Run without --skip-conversion to convert from PBF"
        exit 1
    fi

    if [[ ! -d "$HISTORICAL_DIR" ]]; then
        log_error "Historical data directory not found: $HISTORICAL_DIR"
        echo ""
        echo "Please run Phase 4 extraction first, or create empty directory:"
        echo "  mkdir -p $HISTORICAL_DIR"
        echo ""
        exit 1
    fi

    # Check for historical files
    local historical_count
    historical_count=$(find "$HISTORICAL_DIR" -name "*.geojson" -o -name "*.json" | wc -l)

    if [[ "$historical_count" -eq 0 ]]; then
        log_warning "No historical GeoJSON files found in $HISTORICAL_DIR"
        log_warning "Only OSM data will be included in output"
        read -p "Continue anyway? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 0
        fi
    else
        log_info "Found $historical_count historical GeoJSON file(s)"
    fi

    python3 merge_data.py \
        --osm "$OSM_GEOJSON" \
        --historical "$HISTORICAL_DIR" \
        --output "$OUTPUT_GEOJSON" \
        --verbose

    log_success "Step 2 completed"
}

step_3_generate_pmtiles() {
    print_header "Step 3: Generate PMTiles"

    if [[ ! -f "$OUTPUT_GEOJSON" ]]; then
        log_error "Merged GeoJSON not found: $OUTPUT_GEOJSON"
        echo "Step 2 (merge) must complete successfully first"
        exit 1
    fi

    ./generate_pmtiles.sh "$OUTPUT_GEOJSON" "$OUTPUT_PMTILES"

    log_success "Step 3 completed"
}

step_4_validate() {
    print_header "Step 4: Validate Output"

    ./validate_phase5.sh "$OUTPUT_GEOJSON" "$OUTPUT_PMTILES"

    log_success "Step 4 completed"
}

show_summary() {
    print_header "Phase 5 Complete!"

    echo "Generated files:"
    echo ""

    if [[ -f "$OUTPUT_GEOJSON" ]]; then
        local geojson_size
        geojson_size=$(stat -f%z "$OUTPUT_GEOJSON" 2>/dev/null || stat -c%s "$OUTPUT_GEOJSON" 2>/dev/null || echo "0")
        local geojson_mb=$((geojson_size / 1024 / 1024))
        echo "  GeoJSON: $OUTPUT_GEOJSON"
        echo "    Size: ${geojson_mb} MB"

        if command -v jq &> /dev/null; then
            local feature_count
            feature_count=$(jq '.features | length' "$OUTPUT_GEOJSON" 2>/dev/null || echo "unknown")
            echo "    Features: $feature_count"
        fi
    fi

    echo ""

    if [[ -f "$OUTPUT_PMTILES" ]]; then
        local pmtiles_size
        pmtiles_size=$(stat -f%z "$OUTPUT_PMTILES" 2>/dev/null || stat -c%s "$OUTPUT_PMTILES" 2>/dev/null || echo "0")
        local pmtiles_mb=$((pmtiles_size / 1024 / 1024))
        echo "  PMTiles: $OUTPUT_PMTILES"
        echo "    Size: ${pmtiles_mb} MB"
    fi

    echo ""
    echo "Next steps:"
    echo ""
    echo "1. Test locally:"
    echo "   pmtiles serve $OUTPUT_PMTILES"
    echo ""
    echo "2. Update frontend to use new tiles"
    echo ""
    echo "3. Deploy to production"
    echo ""
}

show_usage() {
    cat << EOF
Usage: $0 [OPTIONS]

Run the complete Phase 5 workflow: merge data and generate tiles.

Options:
  --skip-conversion  Skip OSM PBF to GeoJSON conversion
                     (assumes $OSM_GEOJSON already exists)
  -h, --help        Show this help message

Configuration (edit script to modify):
  OSM_PBF:         $OSM_PBF
  OSM_GEOJSON:     $OSM_GEOJSON
  HISTORICAL_DIR:  $HISTORICAL_DIR
  OUTPUT_GEOJSON:  $OUTPUT_GEOJSON
  OUTPUT_PMTILES:  $OUTPUT_PMTILES

Steps performed:
  1. Convert OSM PBF to GeoJSON (unless --skip-conversion)
  2. Merge OSM and historical data
  3. Generate PMTiles
  4. Validate output

EOF
}

main() {
    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --skip-conversion)
                SKIP_CONVERSION=true
                shift
                ;;
            -h|--help)
                show_usage
                exit 0
                ;;
            *)
                log_error "Unknown option: $1"
                show_usage
                exit 1
                ;;
        esac
    done

    print_header "Phase 5: Data Merging & Tile Generation"

    log_info "Configuration:"
    log_info "  OSM PBF:        $OSM_PBF"
    log_info "  OSM GeoJSON:    $OSM_GEOJSON"
    log_info "  Historical:     $HISTORICAL_DIR"
    log_info "  Output GeoJSON: $OUTPUT_GEOJSON"
    log_info "  Output PMTiles: $OUTPUT_PMTILES"

    # Run workflow
    check_prerequisites

    step_1_convert_osm

    step_2_merge_data

    step_3_generate_pmtiles

    step_4_validate

    # Show summary
    show_summary

    log_success "Phase 5 workflow completed successfully!"
}

main "$@"
