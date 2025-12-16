#!/bin/bash

###############################################################################
# Phase 4 Validation Script
# Validates the Real Data Integration setup for historical map extraction
###############################################################################

set -e  # Exit on error

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Counters
CHECKS_PASSED=0
CHECKS_FAILED=0
CHECKS_WARNING=0

###############################################################################
# Helper Functions
###############################################################################

print_header() {
    echo -e "${BLUE}============================================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}============================================================${NC}"
}

print_subheader() {
    echo -e "\n${BLUE}--- $1 ---${NC}"
}

check_pass() {
    echo -e "${GREEN}✓ $1${NC}"
    ((CHECKS_PASSED++))
}

check_fail() {
    echo -e "${RED}✗ $1${NC}"
    ((CHECKS_FAILED++))
}

check_warn() {
    echo -e "${YELLOW}⚠ $1${NC}"
    ((CHECKS_WARNING++))
}

###############################################################################
# Validation Checks
###############################################################################

print_header "Phase 4: Real Data Integration - Validation"

echo "Project root: $PROJECT_ROOT"
echo ""

# 1. Check directory structure
print_subheader "1. Directory Structure"

REQUIRED_DIRS=(
    "data/kartverket"
    "data/kartverket/raw"
    "data/kartverket/georeferenced"
    "data/kartverket/tiles"
    "data/annotations"
    "data/annotations/images"
    "data/annotations/masks"
    "data/extracted"
    "scripts"
    "ml"
    "models/checkpoints"
)

for dir in "${REQUIRED_DIRS[@]}"; do
    if [ -d "$PROJECT_ROOT/$dir" ]; then
        check_pass "Directory exists: $dir"
    else
        check_fail "Directory missing: $dir"
    fi
done

# 2. Check scripts exist
print_subheader "2. Phase 4 Scripts"

REQUIRED_SCRIPTS=(
    "scripts/fine_tune.py"
    "scripts/batch_extract.py"
    "scripts/validate_phase4.sh"
)

for script in "${REQUIRED_SCRIPTS[@]}"; do
    if [ -f "$PROJECT_ROOT/$script" ]; then
        check_pass "Script exists: $script"

        # Check if executable
        if [ -x "$PROJECT_ROOT/$script" ]; then
            check_pass "  Script is executable"
        else
            check_warn "  Script is not executable (run: chmod +x $script)"
        fi
    else
        check_fail "Script missing: $script"
    fi
done

# 3. Check ML module dependencies
print_subheader "3. ML Module Dependencies"

ML_MODULES=(
    "ml/model.py"
    "ml/dataset.py"
    "ml/predict.py"
    "ml/vectorize.py"
    "ml/evaluate.py"
    "ml/losses.py"
)

for module in "${ML_MODULES[@]}"; do
    if [ -f "$PROJECT_ROOT/$module" ]; then
        check_pass "ML module exists: $module"
    else
        check_fail "ML module missing: $module"
    fi
done

# 4. Check for Kartverket data
print_subheader "4. Kartverket Data"

KARTVERKET_RAW="$PROJECT_ROOT/data/kartverket/raw"
if [ -d "$KARTVERKET_RAW" ]; then
    RAW_COUNT=$(find "$KARTVERKET_RAW" -type f \( -name "*.tif" -o -name "*.tiff" -o -name "*.jpg" -o -name "*.png" \) 2>/dev/null | wc -l)
    if [ "$RAW_COUNT" -gt 0 ]; then
        check_pass "Found $RAW_COUNT raw historical map files"
    else
        check_warn "No raw historical map files found in $KARTVERKET_RAW"
        echo "  Download historical maps from Kartverket first"
    fi
else
    check_fail "Kartverket raw directory not found"
fi

KARTVERKET_GEOREF="$PROJECT_ROOT/data/kartverket/georeferenced"
if [ -d "$KARTVERKET_GEOREF" ]; then
    GEOREF_COUNT=$(find "$KARTVERKET_GEOREF" -type f \( -name "*.tif" -o -name "*.tiff" \) 2>/dev/null | wc -l)
    if [ "$GEOREF_COUNT" -gt 0 ]; then
        check_pass "Found $GEOREF_COUNT georeferenced map files"
    else
        check_warn "No georeferenced files found"
        echo "  Run georeferencing script after downloading raw maps"
    fi
fi

KARTVERKET_TILES="$PROJECT_ROOT/data/kartverket/tiles"
if [ -d "$KARTVERKET_TILES" ]; then
    TILES_COUNT=$(find "$KARTVERKET_TILES" -type f \( -name "*.png" -o -name "*.jpg" \) 2>/dev/null | wc -l)
    if [ "$TILES_COUNT" -gt 0 ]; then
        check_pass "Found $TILES_COUNT tile files"
    else
        check_warn "No tile files found"
        echo "  Run tiling script after georeferencing"
    fi
fi

# 5. Check for annotations
print_subheader "5. Manual Annotations"

ANNOTATIONS_IMAGES="$PROJECT_ROOT/data/annotations/images"
ANNOTATIONS_MASKS="$PROJECT_ROOT/data/annotations/masks"

if [ -d "$ANNOTATIONS_IMAGES" ]; then
    ANNO_IMG_COUNT=$(find "$ANNOTATIONS_IMAGES" -name "*.png" 2>/dev/null | wc -l)
    if [ "$ANNO_IMG_COUNT" -gt 0 ]; then
        check_pass "Found $ANNO_IMG_COUNT annotated images"

        # Check if we have enough annotations (recommended 30-50)
        if [ "$ANNO_IMG_COUNT" -ge 30 ]; then
            check_pass "  Sufficient annotations for fine-tuning (≥30)"
        elif [ "$ANNO_IMG_COUNT" -ge 10 ]; then
            check_warn "  Limited annotations ($ANNO_IMG_COUNT). Recommended: 30-50"
        else
            check_warn "  Very few annotations ($ANNO_IMG_COUNT). Fine-tuning may not be effective"
        fi
    else
        check_warn "No annotated images found"
        echo "  Manual annotation required before fine-tuning"
        echo "  Use QGIS, Label Studio, or custom annotation tool"
    fi
fi

if [ -d "$ANNOTATIONS_MASKS" ]; then
    ANNO_MASK_COUNT=$(find "$ANNOTATIONS_MASKS" -name "*.png" 2>/dev/null | wc -l)
    if [ "$ANNO_MASK_COUNT" -gt 0 ]; then
        check_pass "Found $ANNO_MASK_COUNT annotation masks"

        # Check if images and masks match
        if [ "$ANNO_IMG_COUNT" = "$ANNO_MASK_COUNT" ]; then
            check_pass "  Images and masks count match"
        else
            check_warn "  Image/mask count mismatch: $ANNO_IMG_COUNT images vs $ANNO_MASK_COUNT masks"
        fi
    else
        check_warn "No annotation masks found"
    fi
fi

# 6. Check for pretrained model
print_subheader "6. Pretrained Model (Phase 3)"

BEST_MODEL="$PROJECT_ROOT/models/checkpoints/best_model.pth"
if [ -f "$BEST_MODEL" ]; then
    check_pass "Found pretrained model: best_model.pth"

    # Check model file size (should be substantial)
    MODEL_SIZE=$(du -h "$BEST_MODEL" | cut -f1)
    echo "  Model size: $MODEL_SIZE"

    MODEL_BYTES=$(stat -f%z "$BEST_MODEL" 2>/dev/null || stat -c%s "$BEST_MODEL" 2>/dev/null)
    if [ "$MODEL_BYTES" -gt 10000000 ]; then  # > 10MB
        check_pass "  Model file size is reasonable"
    else
        check_warn "  Model file seems small. May be incomplete."
    fi
else
    check_fail "Pretrained model not found: $BEST_MODEL"
    echo "  Run Phase 3 training first to create pretrained model"
fi

# 7. Check Python dependencies
print_subheader "7. Python Dependencies"

if command -v python3 &> /dev/null; then
    check_pass "Python3 is available"
    PYTHON_VERSION=$(python3 --version)
    echo "  $PYTHON_VERSION"
else
    check_fail "Python3 not found"
fi

# Check for required Python packages
REQUIRED_PACKAGES=(
    "torch"
    "torchvision"
    "segmentation_models_pytorch"
    "albumentations"
    "opencv-python"
    "shapely"
    "geojson"
    "pillow"
    "numpy"
    "tqdm"
    "pyyaml"
)

echo ""
echo "Checking Python packages..."

MISSING_PACKAGES=()
for package in "${REQUIRED_PACKAGES[@]}"; do
    # Convert package name for pip check
    pip_package=$(echo "$package" | sed 's/-/_/g')

    if python3 -c "import ${pip_package//-/_}" 2>/dev/null; then
        check_pass "  $package"
    else
        check_fail "  $package (missing)"
        MISSING_PACKAGES+=("$package")
    fi
done

if [ ${#MISSING_PACKAGES[@]} -gt 0 ]; then
    echo ""
    echo -e "${YELLOW}To install missing packages:${NC}"
    echo "  pip install ${MISSING_PACKAGES[*]}"
fi

# 8. Test fine_tune.py script
print_subheader "8. Test Fine-tune Script"

FINE_TUNE_SCRIPT="$PROJECT_ROOT/scripts/fine_tune.py"
if [ -f "$FINE_TUNE_SCRIPT" ]; then
    # Test with --help flag
    if python3 "$FINE_TUNE_SCRIPT" --help &> /dev/null; then
        check_pass "fine_tune.py --help works"
    else
        check_fail "fine_tune.py has errors"
    fi
else
    check_fail "fine_tune.py not found"
fi

# 9. Test batch_extract.py script
print_subheader "9. Test Batch Extract Script"

BATCH_EXTRACT_SCRIPT="$PROJECT_ROOT/scripts/batch_extract.py"
if [ -f "$BATCH_EXTRACT_SCRIPT" ]; then
    # Test with --help flag
    if python3 "$BATCH_EXTRACT_SCRIPT" --help &> /dev/null; then
        check_pass "batch_extract.py --help works"
    else
        check_fail "batch_extract.py has errors"
    fi
else
    check_fail "batch_extract.py not found"
fi

# 10. Check extraction output directory
print_subheader "10. Extraction Output"

EXTRACTED_DIR="$PROJECT_ROOT/data/extracted"
if [ -d "$EXTRACTED_DIR" ]; then
    EXTRACTED_COUNT=$(find "$EXTRACTED_DIR" -name "*.geojson" 2>/dev/null | wc -l)
    if [ "$EXTRACTED_COUNT" -gt 0 ]; then
        check_pass "Found $EXTRACTED_COUNT extracted GeoJSON files"

        echo ""
        echo "Extracted files:"
        find "$EXTRACTED_DIR" -name "*.geojson" -exec basename {} \; | while read file; do
            echo "  - $file"
        done
    else
        check_warn "No extracted GeoJSON files yet"
        echo "  Run batch_extract.py after fine-tuning"
    fi
fi

###############################################################################
# Summary
###############################################################################

print_header "Validation Summary"

echo -e "Checks passed:  ${GREEN}$CHECKS_PASSED${NC}"
echo -e "Checks failed:  ${RED}$CHECKS_FAILED${NC}"
echo -e "Warnings:       ${YELLOW}$CHECKS_WARNING${NC}"
echo ""

if [ $CHECKS_FAILED -eq 0 ]; then
    if [ $CHECKS_WARNING -eq 0 ]; then
        echo -e "${GREEN}✓ All checks passed! Phase 4 setup is complete.${NC}"
        EXIT_CODE=0
    else
        echo -e "${YELLOW}⚠ Setup mostly complete with some warnings.${NC}"
        EXIT_CODE=0
    fi
else
    echo -e "${RED}✗ Some checks failed. Please fix the issues above.${NC}"
    EXIT_CODE=1
fi

###############################################################################
# Next Steps
###############################################################################

echo ""
print_header "Next Steps for Phase 4"

echo "1. Download Historical Maps"
echo "   - Visit Kartverket's historical map archive"
echo "   - Download maps for Trondheim area"
echo "   - Place in data/kartverket/raw/"
echo ""

echo "2. Georeference Maps"
echo "   - Use GDAL/QGIS to align historical maps to modern coordinates"
echo "   - Save georeferenced maps to data/kartverket/georeferenced/"
echo ""

echo "3. Generate Tiles"
echo "   - Cut large maps into training-size tiles (256x256 or 512x512)"
echo "   - Save tiles to data/kartverket/tiles/"
echo ""

echo "4. Manual Annotation (30-50 tiles recommended)"
echo "   - Select diverse tiles (urban, rural, different eras)"
echo "   - Use QGIS or annotation tool to trace:"
echo "     - Buildings"
echo "     - Roads"
echo "     - Water bodies"
echo "     - Forests"
echo "   - Save images to data/annotations/images/"
echo "   - Save masks to data/annotations/masks/"
echo ""

echo "5. Fine-tune Model"
echo "   python scripts/fine_tune.py \\"
echo "     --pretrained models/checkpoints/best_model.pth \\"
echo "     --annotations data/annotations/ \\"
echo "     --output models/checkpoints/finetuned_model.pth \\"
echo "     --epochs 20 --lr 1e-4"
echo ""

echo "6. Batch Extract Features"
echo "   python scripts/batch_extract.py \\"
echo "     --model models/checkpoints/finetuned_model.pth \\"
echo "     --tiles data/kartverket/tiles/ \\"
echo "     --output data/extracted/"
echo ""

echo "7. Validate Extraction Quality"
echo "   - Load extracted GeoJSON in QGIS"
echo "   - Overlay on modern maps"
echo "   - Check alignment and accuracy"
echo "   - Calculate IoU metrics"
echo ""

exit $EXIT_CODE
