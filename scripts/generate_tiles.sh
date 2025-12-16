#!/bin/bash

################################################################################
# Generate PMTiles from OSM Data
################################################################################
#
# This script converts OSM PBF data to PMTiles format for web display.
# It uses tilemaker (preferred) or planetiler to generate vector tiles.
#
# Input: ../data/trondheim.osm.pbf
# Output: ../data/trondheim.pmtiles
#
# Features:
#   - Preserves temporal attributes (start_date, end_date) if present
#   - Generates appropriate zoom levels for city viewing (z10-z16)
#   - Includes buildings, roads, water bodies, and other features
#
# Requirements:
#   - tilemaker OR planetiler
#   - Java 17+ (for planetiler)
#
# Installation:
#
#   Option 1: Tilemaker (recommended for macOS/Linux)
#     macOS: brew install tilemaker
#     Ubuntu: sudo apt-get install tilemaker
#     From source: https://github.com/systemed/tilemaker
#
#   Option 2: Planetiler (cross-platform Java)
#     Download: https://github.com/onthegomap/planetiler/releases
#     Requires: Java 17+
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
INPUT_FILE="${DATA_DIR}/trondheim.osm.pbf"
OUTPUT_FILE="${DATA_DIR}/trondheim.pmtiles"
TEMP_DIR="${DATA_DIR}/temp_tiles"

# Tilemaker configuration
TILEMAKER_CONFIG_DIR="${SCRIPT_DIR}/tilemaker_config"
TILEMAKER_CONFIG="${TILEMAKER_CONFIG_DIR}/config.json"
TILEMAKER_PROCESS="${TILEMAKER_CONFIG_DIR}/process.lua"

# Planetiler configuration
PLANETILER_JAR="${DATA_DIR}/planetiler.jar"
PLANETILER_VERSION="0.7.0"
PLANETILER_URL="https://github.com/onthegomap/planetiler/releases/download/v${PLANETILER_VERSION}/planetiler.jar"

# Zoom level configuration
MIN_ZOOM=10
MAX_ZOOM=16

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

check_input() {
    log_info "Checking input file..."

    if [ ! -f "${INPUT_FILE}" ]; then
        log_error "Input file not found: ${INPUT_FILE}"
        echo "Please run ./download_osm.sh first to download OSM data."
        exit 1
    fi

    local file_size=$(du -h "${INPUT_FILE}" | cut -f1)
    log_info "Input PBF file size: ${file_size}"
    log_success "Input file found."
}

detect_tool() {
    log_info "Detecting available tile generation tools..."

    if command -v tilemaker &> /dev/null; then
        log_success "Found tilemaker"
        echo "tilemaker"
        return 0
    fi

    if command -v java &> /dev/null; then
        local java_version=$(java -version 2>&1 | head -n 1 | cut -d'"' -f2 | cut -d'.' -f1)
        if [ "${java_version}" -ge 17 ] 2>/dev/null; then
            log_success "Found Java ${java_version}"
            echo "planetiler"
            return 0
        else
            log_warning "Java version is too old (need 17+, found ${java_version})"
        fi
    fi

    log_error "No suitable tile generation tool found."
    echo ""
    echo "Please install one of the following:"
    echo ""
    echo "  Option 1: Tilemaker (recommended)"
    echo "    macOS: brew install tilemaker"
    echo "    Ubuntu: sudo apt-get install tilemaker"
    echo "    From source: https://github.com/systemed/tilemaker"
    echo ""
    echo "  Option 2: Planetiler"
    echo "    Requires Java 17+"
    echo "    macOS: brew install openjdk@17"
    echo "    Ubuntu: sudo apt-get install openjdk-17-jdk"
    echo "    Then re-run this script to download Planetiler automatically"
    echo ""
    exit 1
}

create_tilemaker_config() {
    log_info "Creating Tilemaker configuration..."

    mkdir -p "${TILEMAKER_CONFIG_DIR}"

    # Create config.json
    cat > "${TILEMAKER_CONFIG}" <<'EOF'
{
  "layers": {
    "building": {
      "minzoom": 13,
      "maxzoom": 16,
      "source": "buildings"
    },
    "road": {
      "minzoom": 10,
      "maxzoom": 16,
      "source": "roads"
    },
    "water": {
      "minzoom": 10,
      "maxzoom": 16,
      "source": "water"
    },
    "landuse": {
      "minzoom": 10,
      "maxzoom": 14,
      "source": "landuse"
    },
    "place": {
      "minzoom": 10,
      "maxzoom": 16,
      "source": "places"
    }
  },
  "settings": {
    "minzoom": 10,
    "maxzoom": 16,
    "basezoom": 14,
    "name": "Trondheim Historical Map",
    "version": "1.0",
    "description": "Vector tiles for Trondheim with temporal attributes",
    "attribution": "© OpenStreetMap contributors",
    "compress": "gzip",
    "filemetadata": {
      "type": "baselayer"
    }
  }
}
EOF

    # Create process.lua
    cat > "${TILEMAKER_PROCESS}" <<'EOF'
-- Tilemaker processing script for historical map features
-- Preserves temporal attributes (start_date, end_date)

-- Define layers
node_keys = { "place", "natural", "amenity" }

-- Initialize
function init_function()
end

-- Process nodes
function node_function(node)
    local place = node:Find("place")
    if place ~= "" then
        node:Layer("place", false)
        node:Attribute("class", place)
        node:Attribute("name", node:Find("name"))

        -- Temporal attributes
        local start_date = node:Find("start_date")
        local end_date = node:Find("end_date")
        if start_date ~= "" then
            node:AttributeNumeric("start_year", parse_year(start_date))
        end
        if end_date ~= "" then
            node:AttributeNumeric("end_year", parse_year(end_date))
        end
    end
end

-- Process ways
function way_function(way)
    local highway = way:Find("highway")
    local building = way:Find("building")
    local natural = way:Find("natural")
    local landuse = way:Find("landuse")
    local waterway = way:Find("waterway")

    -- Temporal attributes (will be added to all features)
    local start_date = way:Find("start_date")
    local end_date = way:Find("end_date")
    local start_year = nil
    local end_year = nil

    if start_date ~= "" then
        start_year = parse_year(start_date)
    end
    if end_date ~= "" then
        end_year = parse_year(end_date)
    end

    -- Buildings
    if building ~= "" then
        way:Layer("building", true)
        way:Attribute("type", building)
        way:Attribute("name", way:Find("name"))

        if start_year then way:AttributeNumeric("start_year", start_year) end
        if end_year then way:AttributeNumeric("end_year", end_year) end
    end

    -- Roads
    if highway ~= "" then
        way:Layer("road", false)
        way:Attribute("class", highway)
        way:Attribute("name", way:Find("name"))
        way:AttributeNumeric("oneway", way:Find("oneway") == "yes" and 1 or 0)

        if start_year then way:AttributeNumeric("start_year", start_year) end
        if end_year then way:AttributeNumeric("end_year", end_year) end
    end

    -- Water (natural=water or waterway=*)
    if natural == "water" or waterway ~= "" then
        way:Layer("water", true)
        way:Attribute("class", waterway ~= "" and waterway or "water")
        way:Attribute("name", way:Find("name"))

        if start_year then way:AttributeNumeric("start_year", start_year) end
        if end_year then way:AttributeNumeric("end_year", end_year) end
    end

    -- Landuse
    if landuse ~= "" then
        way:Layer("landuse", true)
        way:Attribute("class", landuse)

        if start_year then way:AttributeNumeric("start_year", start_year) end
        if end_year then way:AttributeNumeric("end_year", end_year) end
    end
end

-- Helper function to parse year from date string
-- Handles formats: YYYY, YYYY-MM-DD, YYYY-MM, etc.
function parse_year(date_str)
    if date_str == nil or date_str == "" then
        return nil
    end

    -- Extract first 4 digits (year)
    local year = string.match(date_str, "^(%d%d%d%d)")
    if year then
        return tonumber(year)
    end

    return nil
end
EOF

    log_success "Tilemaker configuration created."
}

generate_with_tilemaker() {
    log_info "Generating tiles with Tilemaker..."

    create_tilemaker_config

    # Run tilemaker
    # Note: Tilemaker outputs .mbtiles by default, we'll convert to .pmtiles after
    local mbtiles_file="${DATA_DIR}/trondheim.mbtiles"

    log_info "Running tilemaker (this may take 5-15 minutes)..."

    if tilemaker \
        --input "${INPUT_FILE}" \
        --output "${mbtiles_file}" \
        --config "${TILEMAKER_CONFIG}" \
        --process "${TILEMAKER_PROCESS}" \
        --verbose; then

        log_success "Tilemaker completed successfully."

        # Convert MBTiles to PMTiles
        if command -v pmtiles &> /dev/null; then
            log_info "Converting MBTiles to PMTiles..."
            if pmtiles convert "${mbtiles_file}" "${OUTPUT_FILE}"; then
                log_success "Conversion to PMTiles completed."
                rm -f "${mbtiles_file}"
                return 0
            else
                log_warning "PMTiles conversion failed, keeping MBTiles format."
                mv "${mbtiles_file}" "${OUTPUT_FILE%.pmtiles}.mbtiles"
                log_info "Output: ${OUTPUT_FILE%.pmtiles}.mbtiles"
                return 0
            fi
        else
            log_warning "pmtiles tool not found. Keeping MBTiles format."
            log_info "To convert to PMTiles, install: npm install -g pmtiles"
            mv "${mbtiles_file}" "${OUTPUT_FILE%.pmtiles}.mbtiles"
            log_info "Output: ${OUTPUT_FILE%.pmtiles}.mbtiles"
            return 0
        fi
    else
        log_error "Tilemaker failed."
        return 1
    fi
}

download_planetiler() {
    if [ -f "${PLANETILER_JAR}" ]; then
        log_info "Planetiler already downloaded."
        return 0
    fi

    log_info "Downloading Planetiler ${PLANETILER_VERSION}..."

    if curl -L --progress-bar \
        "${PLANETILER_URL}" \
        -o "${PLANETILER_JAR}"; then
        log_success "Planetiler downloaded successfully."
        return 0
    else
        log_error "Failed to download Planetiler."
        return 1
    fi
}

generate_with_planetiler() {
    log_info "Generating tiles with Planetiler..."

    # Download Planetiler if needed
    if ! download_planetiler; then
        return 1
    fi

    mkdir -p "${TEMP_DIR}"

    log_info "Running Planetiler (this may take 10-20 minutes)..."
    log_warning "Planetiler requires significant memory. Ensure you have at least 2GB free RAM."

    # Run planetiler
    # Note: Planetiler outputs .mbtiles, we'll need to convert to .pmtiles
    local mbtiles_file="${DATA_DIR}/trondheim.mbtiles"

    if java -Xmx2g -jar "${PLANETILER_JAR}" \
        --osm-path="${INPUT_FILE}" \
        --output="${mbtiles_file}" \
        --area=trondheim \
        --bounds="${MIN_LON},${MIN_LAT},${MAX_LON},${MAX_LAT}" \
        --minzoom=${MIN_ZOOM} \
        --maxzoom=${MAX_ZOOM}; then

        log_success "Planetiler completed successfully."

        # Convert MBTiles to PMTiles
        if command -v pmtiles &> /dev/null; then
            log_info "Converting MBTiles to PMTiles..."
            if pmtiles convert "${mbtiles_file}" "${OUTPUT_FILE}"; then
                log_success "Conversion to PMTiles completed."
                rm -f "${mbtiles_file}"
                return 0
            else
                log_warning "PMTiles conversion failed, keeping MBTiles format."
                mv "${mbtiles_file}" "${OUTPUT_FILE%.pmtiles}.mbtiles"
                return 0
            fi
        else
            log_warning "pmtiles tool not found. Keeping MBTiles format."
            log_info "To convert to PMTiles, install: npm install -g pmtiles"
            mv "${mbtiles_file}" "${OUTPUT_FILE%.pmtiles}.mbtiles"
            return 0
        fi
    else
        log_error "Planetiler failed."
        return 1
    fi
}

verify_output() {
    log_info "Verifying output file..."

    # Check for either .pmtiles or .mbtiles
    local actual_output
    if [ -f "${OUTPUT_FILE}" ]; then
        actual_output="${OUTPUT_FILE}"
    elif [ -f "${OUTPUT_FILE%.pmtiles}.mbtiles" ]; then
        actual_output="${OUTPUT_FILE%.pmtiles}.mbtiles"
    else
        log_error "No output file found."
        return 1
    fi

    # Get file size
    local file_size=$(du -h "${actual_output}" | cut -f1)
    log_info "Output file size: ${file_size}"

    # Basic validation
    if [ -s "${actual_output}" ]; then
        log_success "Output file created successfully."
        log_info "Output: ${actual_output}"
        return 0
    else
        log_error "Output file is empty."
        return 1
    fi
}

cleanup_temp() {
    if [ -d "${TEMP_DIR}" ]; then
        log_info "Cleaning up temporary files..."
        rm -rf "${TEMP_DIR}"
    fi
}

################################################################################
# Main Execution
################################################################################

main() {
    log_info "Starting PMTiles generation for Trondheim"
    echo "========================================"

    # Check if output already exists
    if [ -f "${OUTPUT_FILE}" ] || [ -f "${OUTPUT_FILE%.pmtiles}.mbtiles" ]; then
        log_warning "Output file already exists."
        read -p "Do you want to regenerate? (y/N) " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            log_info "Skipping generation. Using existing file."
            exit 0
        fi
        rm -f "${OUTPUT_FILE}" "${OUTPUT_FILE%.pmtiles}.mbtiles"
    fi

    # Trap to ensure cleanup on exit
    trap cleanup_temp EXIT

    # Check input
    check_input

    # Detect and use appropriate tool
    local tool=$(detect_tool)

    case "${tool}" in
        tilemaker)
            if generate_with_tilemaker; then
                if verify_output; then
                    cleanup_temp
                    echo "========================================"
                    log_success "PMTiles generation complete!"
                    exit 0
                fi
            fi
            ;;
        planetiler)
            if generate_with_planetiler; then
                if verify_output; then
                    cleanup_temp
                    echo "========================================"
                    log_success "PMTiles generation complete!"
                    exit 0
                fi
            fi
            ;;
        *)
            log_error "Unknown tool: ${tool}"
            exit 1
            ;;
    esac

    # If we get here, something failed
    log_error "Tile generation failed. Check the errors above."
    exit 1
}

# Run main function
main "$@"
