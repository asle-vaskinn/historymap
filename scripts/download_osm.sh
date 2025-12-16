#!/bin/bash

################################################################################
# Download OSM Data for Trondheim Area
################################################################################
#
# This script downloads OpenStreetMap data for the Trondheim area using the
# Overpass API. The bounding box covers Trondheim and surrounding municipalities.
#
# Bounding box: [10.0, 63.3, 10.8, 63.5] (minlon, minlat, maxlon, maxlat)
# Output: ../data/trondheim.osm.pbf
#
# Requirements:
#   - curl
#   - osmium-tool (for PBF conversion)
#
# Install osmium-tool:
#   macOS: brew install osmium-tool
#   Ubuntu/Debian: sudo apt-get install osmium-tool
#
################################################################################

set -euo pipefail  # Exit on error, undefined vars, pipe failures

# Color output for better readability
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA_DIR="${SCRIPT_DIR}/../data"
OUTPUT_FILE="${DATA_DIR}/trondheim.osm.pbf"
TEMP_DIR="${DATA_DIR}/temp"

# Bounding box for Trondheim area (minlon, minlat, maxlon, maxlat)
MIN_LON=10.0
MIN_LAT=63.3
MAX_LON=10.8
MAX_LAT=63.5

# Overpass API endpoint
OVERPASS_URL="https://overpass-api.de/api/interpreter"

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

    if ! command -v curl &> /dev/null; then
        log_error "curl is not installed. Please install curl first."
        exit 1
    fi

    if ! command -v osmium &> /dev/null; then
        log_error "osmium-tool is not installed."
        echo "Install with:"
        echo "  macOS: brew install osmium-tool"
        echo "  Ubuntu/Debian: sudo apt-get install osmium-tool"
        exit 1
    fi

    log_success "All dependencies are installed."
}

create_directories() {
    log_info "Creating directories..."
    mkdir -p "${DATA_DIR}"
    mkdir -p "${TEMP_DIR}"
}

cleanup_temp() {
    if [ -d "${TEMP_DIR}" ]; then
        log_info "Cleaning up temporary files..."
        rm -rf "${TEMP_DIR}"
    fi
}

download_overpass() {
    local osm_file="${TEMP_DIR}/trondheim.osm"

    log_info "Downloading OSM data from Overpass API..."
    log_info "Bounding box: [${MIN_LON}, ${MIN_LAT}, ${MAX_LON}, ${MAX_LAT}]"

    # Create Overpass QL query
    # This query fetches all nodes, ways, and relations within the bounding box
    # and includes full geometry (out geom) for complete data
    local query="[out:xml][timeout:300][bbox:${MIN_LAT},${MIN_LON},${MAX_LAT},${MAX_LON}];
(
  node;
  way;
  relation;
);
out meta;
>;
out skel qt;"

    log_info "Query size: Trondheim and surrounding municipalities (~3,000 km²)"
    log_warning "This may take 3-10 minutes depending on server load..."

    # Download with progress bar and retry logic
    local max_retries=3
    local retry_count=0

    while [ ${retry_count} -lt ${max_retries} ]; do
        if curl -f --progress-bar \
            --data-urlencode "data=${query}" \
            "${OVERPASS_URL}" \
            -o "${osm_file}"; then
            log_success "Download completed successfully."
            return 0
        else
            retry_count=$((retry_count + 1))
            if [ ${retry_count} -lt ${max_retries} ]; then
                log_warning "Download failed. Retrying (${retry_count}/${max_retries})..."
                sleep 5
            else
                log_error "Download failed after ${max_retries} attempts."
                return 1
            fi
        fi
    done
}

convert_to_pbf() {
    local osm_file="${TEMP_DIR}/trondheim.osm"

    log_info "Converting OSM XML to PBF format..."

    if [ ! -f "${osm_file}" ]; then
        log_error "OSM file not found: ${osm_file}"
        return 1
    fi

    # Check file size
    local file_size=$(du -h "${osm_file}" | cut -f1)
    log_info "OSM XML file size: ${file_size}"

    # Convert using osmium
    if osmium cat "${osm_file}" -o "${OUTPUT_FILE}" -f pbf; then
        log_success "Conversion to PBF completed."
        return 0
    else
        log_error "PBF conversion failed."
        return 1
    fi
}

verify_output() {
    log_info "Verifying output file..."

    if [ ! -f "${OUTPUT_FILE}" ]; then
        log_error "Output file not created: ${OUTPUT_FILE}"
        return 1
    fi

    # Get file size
    local file_size=$(du -h "${OUTPUT_FILE}" | cut -f1)
    log_info "PBF file size: ${file_size}"

    # Check if file is valid using osmium
    if osmium fileinfo "${OUTPUT_FILE}" > /dev/null 2>&1; then
        log_success "PBF file is valid."

        # Show file info
        log_info "File information:"
        osmium fileinfo "${OUTPUT_FILE}"
        return 0
    else
        log_error "PBF file validation failed."
        return 1
    fi
}

################################################################################
# Main Execution
################################################################################

main() {
    log_info "Starting OSM data download for Trondheim area"
    echo "========================================"

    # Check if output already exists
    if [ -f "${OUTPUT_FILE}" ]; then
        log_warning "Output file already exists: ${OUTPUT_FILE}"
        read -p "Do you want to re-download? (y/N) " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            log_info "Skipping download. Using existing file."
            exit 0
        fi
        rm -f "${OUTPUT_FILE}"
    fi

    # Trap to ensure cleanup on exit
    trap cleanup_temp EXIT

    # Execute pipeline
    check_dependencies
    create_directories

    if download_overpass; then
        if convert_to_pbf; then
            if verify_output; then
                cleanup_temp
                echo "========================================"
                log_success "OSM data download complete!"
                log_info "Output file: ${OUTPUT_FILE}"
                echo ""
                log_info "Next step: Run ./generate_tiles.sh to create PMTiles"
                exit 0
            fi
        fi
    fi

    # If we get here, something failed
    log_error "OSM data download failed. Check the errors above."
    exit 1
}

# Run main function
main "$@"
