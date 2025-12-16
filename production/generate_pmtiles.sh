#!/bin/bash
################################################################################
# Phase 5: PMTiles Generation Script
#
# Converts merged GeoJSON data into optimized PMTiles format for web delivery.
#
# This script:
# 1. Takes merged GeoJSON as input
# 2. Converts to PMTiles using tippecanoe
# 3. Optimizes for web delivery with appropriate zoom levels
# 4. Includes temporal attributes for time-based filtering
# 5. Validates the output
#
# Usage:
#   ./generate_pmtiles.sh <input_geojson> [output_pmtiles]
#
# Example:
#   ./generate_pmtiles.sh ../data/final/trondheim_all_eras.geojson
#   ./generate_pmtiles.sh ../data/final/trondheim_all_eras.geojson custom_output.pmtiles
################################################################################

set -e  # Exit on error
set -u  # Exit on undefined variable
set -o pipefail  # Exit on pipe failure

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
MIN_ZOOM=8
MAX_ZOOM=16
DROP_SMALLEST_AS_NEEDED=true
SIMPLIFICATION_INCREASE=1.5

################################################################################
# Helper Functions
################################################################################

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_dependencies() {
    log_info "Checking dependencies..."

    if ! command -v tippecanoe &> /dev/null; then
        log_error "tippecanoe is not installed"
        echo ""
        echo "Installation instructions:"
        echo "  macOS:    brew install tippecanoe"
        echo "  Linux:    git clone https://github.com/felt/tippecanoe.git && cd tippecanoe && make -j && sudo make install"
        echo ""
        exit 1
    fi

    if ! command -v jq &> /dev/null; then
        log_warning "jq is not installed (recommended for validation)"
        echo "  Install with: brew install jq (macOS) or apt-get install jq (Linux)"
    fi

    if ! command -v pmtiles &> /dev/null; then
        log_warning "pmtiles CLI is not installed (recommended for validation)"
        echo "  Install from: https://github.com/protomaps/go-pmtiles"
    fi

    log_success "Dependencies checked"
}

validate_input() {
    local input_file="$1"

    log_info "Validating input file: $input_file"

    if [[ ! -f "$input_file" ]]; then
        log_error "Input file does not exist: $input_file"
        exit 1
    fi

    # Check if file is valid JSON
    if command -v jq &> /dev/null; then
        if ! jq empty "$input_file" 2>/dev/null; then
            log_error "Input file is not valid JSON"
            exit 1
        fi

        # Check if it's a valid GeoJSON FeatureCollection
        local type
        type=$(jq -r '.type' "$input_file" 2>/dev/null || echo "")
        if [[ "$type" != "FeatureCollection" ]]; then
            log_error "Input file is not a GeoJSON FeatureCollection (type: $type)"
            exit 1
        fi

        # Count features
        local feature_count
        feature_count=$(jq '.features | length' "$input_file" 2>/dev/null || echo "0")
        log_info "Found $feature_count features in input file"

        if [[ "$feature_count" -eq 0 ]]; then
            log_error "Input file contains no features"
            exit 1
        fi
    else
        log_warning "Cannot validate JSON structure (jq not installed)"
    fi

    log_success "Input file is valid"
}

validate_output() {
    local output_file="$1"

    log_info "Validating output file: $output_file"

    if [[ ! -f "$output_file" ]]; then
        log_error "Output file was not created"
        return 1
    fi

    local file_size
    file_size=$(stat -f%z "$output_file" 2>/dev/null || stat -c%s "$output_file" 2>/dev/null || echo "0")

    if [[ "$file_size" -eq 0 ]]; then
        log_error "Output file is empty"
        return 1
    fi

    log_info "Output file size: $(numfmt --to=iec-i --suffix=B $file_size 2>/dev/null || echo $file_size bytes)"

    # Validate with pmtiles if available
    if command -v pmtiles &> /dev/null; then
        log_info "Validating PMTiles structure..."
        if pmtiles show "$output_file" > /dev/null 2>&1; then
            log_success "PMTiles structure is valid"

            # Show metadata
            log_info "PMTiles metadata:"
            pmtiles show "$output_file" | head -20
        else
            log_error "PMTiles validation failed"
            return 1
        fi
    else
        log_warning "Cannot validate PMTiles structure (pmtiles CLI not installed)"
    fi

    log_success "Output file is valid"
    return 0
}

generate_tiles() {
    local input_file="$1"
    local output_file="$2"

    log_info "Generating PMTiles..."
    log_info "  Input:     $input_file"
    log_info "  Output:    $output_file"
    log_info "  Zoom:      $MIN_ZOOM - $MAX_ZOOM"

    # Build tippecanoe command
    local tippecanoe_cmd=(
        tippecanoe
        --output="$output_file"
        --force  # Overwrite if exists

        # Zoom levels
        --minimum-zoom=$MIN_ZOOM
        --maximum-zoom=$MAX_ZOOM

        # Layer configuration
        --layer=historical_features

        # Feature handling
        --read-parallel  # Faster processing
        --simplification=$SIMPLIFICATION_INCREASE

        # Drop features at low zooms based on size
        --drop-smallest-as-needed

        # Coalesce densely packed features
        --coalesce-densest-as-needed

        # Extend tiles at lower zooms to include neighboring features
        --extend-zooms-if-still-dropping

        # Preserve all attributes for filtering
        --preserve-properties

        # Temporal attributes (critical for time slider)
        --preserve-input-order

        # Name the layer
        --name="Trondheim Historical Map"

        # Attribution
        --attribution="OSM Contributors, Kartverket"

        # Description
        --description="Historical map features for Trondheim area across multiple time periods"

        # Input file
        "$input_file"
    )

    log_info "Running tippecanoe..."
    log_info "Command: ${tippecanoe_cmd[*]}"

    # Run tippecanoe with progress
    if "${tippecanoe_cmd[@]}" 2>&1 | while IFS= read -r line; do
        echo "  $line"
    done; then
        log_success "PMTiles generation completed"
        return 0
    else
        log_error "tippecanoe failed"
        return 1
    fi
}

show_usage() {
    cat << EOF
Usage: $0 <input_geojson> [output_pmtiles]

Generates optimized PMTiles from merged historical GeoJSON data.

Arguments:
  input_geojson    Path to input GeoJSON file (required)
  output_pmtiles   Path to output PMTiles file (optional)
                   Default: input file with .pmtiles extension

Options:
  -h, --help       Show this help message

Examples:
  $0 ../data/final/trondheim_all_eras.geojson
  $0 input.geojson output.pmtiles

Configuration (edit script to modify):
  MIN_ZOOM:        $MIN_ZOOM
  MAX_ZOOM:        $MAX_ZOOM
  SIMPLIFICATION:  $SIMPLIFICATION_INCREASE

EOF
}

################################################################################
# Main
################################################################################

main() {
    # Parse arguments
    if [[ $# -eq 0 ]] || [[ "$1" == "-h" ]] || [[ "$1" == "--help" ]]; then
        show_usage
        exit 0
    fi

    local input_file="$1"
    local output_file="${2:-}"

    # Convert to absolute paths
    input_file="$(cd "$(dirname "$input_file")" && pwd)/$(basename "$input_file")"

    # Determine output file if not provided
    if [[ -z "$output_file" ]]; then
        output_file="${input_file%.geojson}.pmtiles"
        output_file="${output_file%.json}.pmtiles"
    else
        output_file="$(cd "$(dirname "$output_file")" && pwd)/$(basename "$output_file")"
    fi

    # Print header
    echo ""
    echo "=================================================="
    echo "  PMTiles Generator - Phase 5"
    echo "  Trondheim Historical Map Project"
    echo "=================================================="
    echo ""

    # Check dependencies
    check_dependencies

    # Validate input
    validate_input "$input_file"

    # Generate tiles
    if ! generate_tiles "$input_file" "$output_file"; then
        log_error "Failed to generate PMTiles"
        exit 1
    fi

    # Validate output
    if ! validate_output "$output_file"; then
        log_error "Output validation failed"
        exit 1
    fi

    # Success summary
    echo ""
    echo "=================================================="
    log_success "PMTiles generation completed successfully!"
    echo "=================================================="
    echo ""
    echo "Output file: $output_file"
    echo ""

    if command -v pmtiles &> /dev/null; then
        echo "To serve locally for testing:"
        echo "  pmtiles serve $output_file"
        echo ""
    fi

    echo "To use in frontend, update the tile source URL to:"
    echo "  pmtiles://$output_file"
    echo ""
}

# Run main function
main "$@"
