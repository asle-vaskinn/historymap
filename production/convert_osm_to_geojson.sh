#!/bin/bash
################################################################################
# Convert OSM PBF to GeoJSON
#
# Utility script to convert OSM PBF format to GeoJSON for use in merge_data.py
#
# Usage:
#   ./convert_osm_to_geojson.sh <input.osm.pbf> [output.geojson]
#
# Example:
#   ./convert_osm_to_geojson.sh ../data/trondheim.osm.pbf ../data/trondheim.geojson
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

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

check_dependencies() {
    log_info "Checking for conversion tools..."

    local has_tool=false

    # Check for osmium (preferred - fastest)
    if command -v osmium &> /dev/null; then
        log_success "Found osmium-tool (recommended)"
        CONVERTER="osmium"
        has_tool=true
    fi

    # Check for ogr2ogr (GDAL)
    if command -v ogr2ogr &> /dev/null; then
        log_success "Found ogr2ogr (GDAL)"
        if [[ "$has_tool" == false ]]; then
            CONVERTER="ogr2ogr"
            has_tool=true
        fi
    fi

    # Check for osmtogeojson (Node.js based)
    if command -v osmtogeojson &> /dev/null; then
        log_success "Found osmtogeojson"
        if [[ "$has_tool" == false ]]; then
            CONVERTER="osmtogeojson"
            has_tool=true
        fi
    fi

    if [[ "$has_tool" == false ]]; then
        log_error "No OSM conversion tool found"
        echo ""
        echo "Please install one of the following:"
        echo ""
        echo "1. osmium-tool (RECOMMENDED - fastest):"
        echo "   macOS:  brew install osmium-tool"
        echo "   Linux:  apt-get install osmium-tool"
        echo ""
        echo "2. GDAL/ogr2ogr:"
        echo "   macOS:  brew install gdal"
        echo "   Linux:  apt-get install gdal-bin"
        echo ""
        echo "3. osmtogeojson (Node.js):"
        echo "   npm install -g osmtogeojson"
        echo ""
        exit 1
    fi

    log_info "Using converter: $CONVERTER"
}

convert_with_osmium() {
    local input="$1"
    local output="$2"

    log_info "Converting with osmium (fast method)..."

    osmium export \
        --output="$output" \
        --output-format=geojson \
        --overwrite \
        "$input"
}

convert_with_ogr2ogr() {
    local input="$1"
    local output="$2"

    log_info "Converting with ogr2ogr (GDAL method)..."

    ogr2ogr \
        -f GeoJSON \
        "$output" \
        "$input" \
        -overwrite
}

convert_with_osmtogeojson() {
    local input="$1"
    local output="$2"

    log_info "Converting with osmtogeojson (Node.js method)..."

    # osmtogeojson requires OSM XML, so we need to convert PBF to XML first
    log_warning "osmtogeojson requires XML input, converting PBF to XML first..."

    if ! command -v osmium &> /dev/null; then
        log_error "osmium-tool is required to convert PBF to XML"
        log_error "Install with: brew install osmium-tool"
        exit 1
    fi

    local temp_xml="${input%.pbf}.osm"

    log_info "Converting PBF to XML..."
    osmium cat "$input" -o "$temp_xml"

    log_info "Converting XML to GeoJSON..."
    osmtogeojson "$temp_xml" > "$output"

    log_info "Cleaning up temporary file..."
    rm -f "$temp_xml"
}

convert() {
    local input="$1"
    local output="$2"

    case "$CONVERTER" in
        osmium)
            convert_with_osmium "$input" "$output"
            ;;
        ogr2ogr)
            convert_with_ogr2ogr "$input" "$output"
            ;;
        osmtogeojson)
            convert_with_osmtogeojson "$input" "$output"
            ;;
        *)
            log_error "Unknown converter: $CONVERTER"
            exit 1
            ;;
    esac
}

validate_output() {
    local output="$1"

    log_info "Validating output..."

    if [[ ! -f "$output" ]]; then
        log_error "Output file was not created"
        return 1
    fi

    local file_size
    file_size=$(stat -f%z "$output" 2>/dev/null || stat -c%s "$output" 2>/dev/null || echo "0")

    if [[ "$file_size" -eq 0 ]]; then
        log_error "Output file is empty"
        return 1
    fi

    local size_mb=$((file_size / 1024 / 1024))
    log_info "Output file size: ${size_mb} MB"

    # Validate JSON if jq is available
    if command -v jq &> /dev/null; then
        if jq empty "$output" 2>/dev/null; then
            local feature_count
            feature_count=$(jq '.features | length' "$output" 2>/dev/null || echo "unknown")
            log_success "Valid GeoJSON with $feature_count features"
        else
            log_error "Output is not valid JSON"
            return 1
        fi
    else
        log_warning "jq not available, skipping JSON validation"
    fi

    log_success "Output file is valid"
    return 0
}

show_usage() {
    cat << EOF
Usage: $0 <input.osm.pbf> [output.geojson]

Convert OSM PBF format to GeoJSON.

Arguments:
  input.osm.pbf   Path to input OSM PBF file (required)
  output.geojson  Path to output GeoJSON file (optional)
                  Default: input file with .geojson extension

Options:
  -h, --help      Show this help message

Examples:
  $0 trondheim.osm.pbf
  $0 trondheim.osm.pbf trondheim.geojson
  $0 ../data/trondheim.osm.pbf ../data/trondheim.geojson

Supported conversion tools (in order of preference):
  1. osmium-tool  - Fastest, recommended
  2. ogr2ogr      - Part of GDAL, widely available
  3. osmtogeojson - Node.js based, requires XML intermediate

EOF
}

main() {
    if [[ $# -eq 0 ]] || [[ "$1" == "-h" ]] || [[ "$1" == "--help" ]]; then
        show_usage
        exit 0
    fi

    local input_file="$1"
    local output_file="${2:-}"

    # Check input file exists
    if [[ ! -f "$input_file" ]]; then
        log_error "Input file not found: $input_file"
        exit 1
    fi

    # Determine output file
    if [[ -z "$output_file" ]]; then
        output_file="${input_file%.pbf}.geojson"
        output_file="${output_file%.osm.pbf}.geojson"
    fi

    # Convert to absolute paths
    input_file="$(cd "$(dirname "$input_file")" && pwd)/$(basename "$input_file")"
    output_file="$(cd "$(dirname "$output_file")" && pwd)/$(basename "$output_file")" 2>/dev/null || output_file="$(pwd)/$output_file"

    echo ""
    echo "=================================================="
    echo "  OSM PBF to GeoJSON Converter"
    echo "=================================================="
    echo ""
    log_info "Input:  $input_file"
    log_info "Output: $output_file"
    echo ""

    # Check dependencies
    check_dependencies

    # Convert
    echo ""
    local start_time
    start_time=$(date +%s)

    if convert "$input_file" "$output_file"; then
        local end_time
        end_time=$(date +%s)
        local duration=$((end_time - start_time))

        echo ""
        log_success "Conversion completed in ${duration}s"

        # Validate
        if validate_output "$output_file"; then
            echo ""
            echo "=================================================="
            log_success "All done!"
            echo "=================================================="
            echo ""
            echo "Output: $output_file"
            echo ""
            echo "Next step:"
            echo "  python merge_data.py --osm $output_file --historical ../data/extracted/ --output ../data/final/trondheim_all_eras.geojson"
            echo ""
        else
            log_error "Validation failed"
            exit 1
        fi
    else
        log_error "Conversion failed"
        exit 1
    fi
}

main "$@"
