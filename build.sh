#!/bin/bash
# Build script for Trondheim Historical Map
# Generates all data files before Docker deployment
#
# Usage:
#   ./build.sh              # Full build
#   ./build.sh --skip-ml    # Skip ML inference (use existing detections)
#   ./build.sh --quick      # Skip PMTiles generation

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Parse arguments
SKIP_ML=false
SKIP_PMTILES=false
for arg in "$@"; do
    case $arg in
        --skip-ml) SKIP_ML=true ;;
        --quick) SKIP_PMTILES=true ;;
        --help|-h)
            echo "Usage: ./build.sh [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --skip-ml     Skip ML inference (use existing detections)"
            echo "  --quick       Skip PMTiles generation (GeoJSON only)"
            echo "  --help, -h    Show this help message"
            exit 0
            ;;
    esac
done

echo "============================================================"
echo "  Trondheim Historical Map - Build Pipeline"
echo "============================================================"
echo ""

# Step 1: Check Python environment
log_info "Checking Python environment..."
if ! command -v python3 &> /dev/null; then
    log_error "Python 3 not found. Please install Python 3.11+"
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
log_info "Python version: $PYTHON_VERSION"

# Step 2: Check/install dependencies
log_info "Checking dependencies..."
if [ ! -d "venv" ]; then
    log_warn "Virtual environment not found. Creating..."
    python3 -m venv venv
fi

source venv/bin/activate
pip install -q --upgrade pip

if ! python3 -c "import shapely" 2>/dev/null; then
    log_info "Installing dependencies from requirements.txt..."
    pip install -r requirements.txt
else
    log_info "Dependencies already installed"
fi

# Step 3: Run data pipeline
echo ""
echo "============================================================"
echo "  Stage 1: Data Ingestion"
echo "============================================================"
log_info "Running ingestion for all sources..."
python3 scripts/pipeline.py --stage ingest || log_warn "Some ingestion steps failed (may be expected)"

echo ""
echo "============================================================"
echo "  Stage 2: Normalization"
echo "============================================================"
log_info "Normalizing data to common schema..."
python3 scripts/pipeline.py --stage normalize || log_warn "Some normalization steps failed"

# Step 4: ML inference (optional)
if [ "$SKIP_ML" = false ]; then
    echo ""
    echo "============================================================"
    echo "  Stage 3: ML Inference (optional)"
    echo "============================================================"
    if [ -f "models/checkpoints/best_model.pth" ]; then
        log_info "Running ML inference on historical maps..."
        # Add ML inference commands here when ready
        log_warn "ML inference not yet configured - skipping"
    else
        log_warn "No trained model found at models/checkpoints/best_model.pth"
        log_warn "Skipping ML inference"
    fi
else
    log_info "Skipping ML inference (--skip-ml flag)"
fi

echo ""
echo "============================================================"
echo "  Stage 4: Merge Sources"
echo "============================================================"
log_info "Merging all sources according to config..."
python3 scripts/pipeline.py --stage merge

echo ""
echo "============================================================"
echo "  Stage 5: Export"
echo "============================================================"
if [ "$SKIP_PMTILES" = true ]; then
    log_info "Exporting GeoJSON only (--quick flag)..."
    python3 scripts/pipeline.py --stage export --no-pmtiles
else
    log_info "Exporting GeoJSON and PMTiles..."
    python3 scripts/pipeline.py --stage export
fi

# Step 5: Copy to frontend
echo ""
echo "============================================================"
echo "  Stage 6: Prepare Frontend Data"
echo "============================================================"
log_info "Copying exported data to frontend..."

mkdir -p frontend/data

if [ -f "data/export/buildings.geojson" ]; then
    cp data/export/buildings.geojson frontend/data/
    log_info "Copied buildings.geojson"
fi

if [ -f "data/export/buildings.pmtiles" ]; then
    cp data/export/buildings.pmtiles frontend/data/
    log_info "Copied buildings.pmtiles"
fi

# Step 6: Summary
echo ""
echo "============================================================"
echo "  Build Complete!"
echo "============================================================"
echo ""
log_info "Output files:"
ls -lh frontend/data/ 2>/dev/null || log_warn "No data files generated"

echo ""
log_info "Next steps:"
echo "  1. Review the data: python3 -m http.server 8080 -d frontend"
echo "  2. Deploy with Docker: docker compose up -d"
echo ""
