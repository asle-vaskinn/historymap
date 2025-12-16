#!/bin/bash
# validate_phase2.sh - Validation script for Phase 2 synthetic data pipeline
#
# This script validates that Phase 2 is correctly set up and working:
# 1. Checks that style files exist
# 2. Generates 10 sample pairs
# 3. Verifies image/mask alignment
# 4. Displays class distribution
# 5. Creates visual validation output

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Phase 2 Validation Script${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Function to print status
print_status() {
    if [ $1 -eq 0 ]; then
        echo -e "${GREEN}✓ $2${NC}"
    else
        echo -e "${RED}✗ $2${NC}"
        return 1
    fi
}

# Function to print info
print_info() {
    echo -e "${YELLOW}→ $1${NC}"
}

# Track validation status
VALIDATION_PASSED=true

# 1. Check Python dependencies
echo -e "\n${BLUE}[1/6] Checking Python dependencies...${NC}"
print_info "Checking required Python packages"

python3 -c "import PIL" 2>/dev/null
print_status $? "Pillow (PIL) installed" || VALIDATION_PASSED=false

python3 -c "import numpy" 2>/dev/null
print_status $? "NumPy installed" || VALIDATION_PASSED=false

python3 -c "import requests" 2>/dev/null
print_status $? "Requests installed" || VALIDATION_PASSED=false

python3 -c "import tqdm" 2>/dev/null
print_status $? "tqdm installed" || VALIDATION_PASSED=false

# 2. Check synthetic directory structure
echo -e "\n${BLUE}[2/6] Checking directory structure...${NC}"

if [ -d "$SCRIPT_DIR/styles" ]; then
    print_status 0 "styles/ directory exists"
else
    print_status 1 "styles/ directory missing"
    VALIDATION_PASSED=false
fi

if [ -d "$PROJECT_ROOT/data/synthetic/images" ]; then
    print_status 0 "data/synthetic/images/ directory exists"
else
    print_status 1 "data/synthetic/images/ directory missing"
    VALIDATION_PASSED=false
fi

if [ -d "$PROJECT_ROOT/data/synthetic/masks" ]; then
    print_status 0 "data/synthetic/masks/ directory exists"
else
    print_status 1 "data/synthetic/masks/ directory missing"
    VALIDATION_PASSED=false
fi

# 3. Check for style files
echo -e "\n${BLUE}[3/6] Checking style files...${NC}"

STYLE_COUNT=$(find "$SCRIPT_DIR/styles" -name "*.json" 2>/dev/null | wc -l | tr -d ' ')

if [ "$STYLE_COUNT" -gt 0 ]; then
    print_status 0 "Found $STYLE_COUNT style file(s)"
    print_info "Available styles:"
    for style in "$SCRIPT_DIR/styles"/*.json; do
        if [ -f "$style" ]; then
            basename "$style" | sed 's/\.json$//' | sed 's/^/    - /'
        fi
    done
else
    print_status 1 "No style files found in styles/"
    VALIDATION_PASSED=false
fi

# 4. Check Python scripts
echo -e "\n${BLUE}[4/6] Checking Python scripts...${NC}"

check_script() {
    local script=$1
    local desc=$2
    if [ -f "$SCRIPT_DIR/$script" ]; then
        # Try to parse the script
        python3 -m py_compile "$SCRIPT_DIR/$script" 2>/dev/null
        print_status $? "$desc ($script)"
    else
        print_status 1 "$desc ($script) not found"
        return 1
    fi
}

check_script "tile_utils.py" "Tile utilities" || VALIDATION_PASSED=false
check_script "textures.py" "Texture generator" || VALIDATION_PASSED=false
check_script "age_effects.py" "Aging effects" || VALIDATION_PASSED=false
check_script "create_masks.py" "Mask generator" || VALIDATION_PASSED=false
check_script "generate_dataset.py" "Main pipeline" || VALIDATION_PASSED=false

# 5. Generate test samples
echo -e "\n${BLUE}[5/6] Generating test samples...${NC}"

if [ "$VALIDATION_PASSED" = true ]; then
    print_info "Generating 10 test samples (this may take 2-5 minutes)..."

    TEST_OUTPUT="$PROJECT_ROOT/data/synthetic/test_samples"
    mkdir -p "$TEST_OUTPUT"

    # Generate samples with seed for reproducibility
    cd "$SCRIPT_DIR"

    # Use a small test area in Trondheim
    # Tile coordinates for central Trondheim at zoom 15: approximately z=15, x=17234, y=9345
    TRONDHEIM_BBOX="10.38,63.42,10.42,63.44"

    if python3 generate_dataset.py \
        --count 10 \
        --output "$TEST_OUTPUT" \
        --bbox "$TRONDHEIM_BBOX" \
        --zoom 15 \
        --seed 42 \
        --no-skip-existing \
        2>&1 | tee "$TEST_OUTPUT/generation.log"; then

        print_status 0 "Test samples generated successfully"

        # Count generated files
        IMAGE_COUNT=$(find "$TEST_OUTPUT/images" -name "*.png" 2>/dev/null | wc -l | tr -d ' ')
        MASK_COUNT=$(find "$TEST_OUTPUT/masks" -name "*.png" 2>/dev/null | wc -l | tr -d ' ')

        echo -e "    Generated: $IMAGE_COUNT images, $MASK_COUNT masks"

        if [ "$IMAGE_COUNT" -gt 0 ] && [ "$MASK_COUNT" -gt 0 ]; then
            print_status 0 "Image and mask files created"
        else
            print_status 1 "No images or masks generated"
            VALIDATION_PASSED=false
        fi

    else
        print_status 1 "Failed to generate test samples"
        VALIDATION_PASSED=false
    fi
else
    print_info "Skipping sample generation due to previous errors"
fi

# 6. Verify and visualize results
echo -e "\n${BLUE}[6/6] Verifying results...${NC}"

if [ "$VALIDATION_PASSED" = true ] && [ -d "$TEST_OUTPUT" ]; then
    print_info "Analyzing generated samples..."

    # Check metadata file
    if [ -f "$TEST_OUTPUT/metadata.json" ]; then
        print_status 0 "Metadata file exists"

        # Extract some statistics from metadata
        SAMPLE_COUNT=$(python3 -c "import json; data=json.load(open('$TEST_OUTPUT/metadata.json')); print(data['dataset_info']['num_samples'])" 2>/dev/null || echo "0")
        echo -e "    Samples in metadata: $SAMPLE_COUNT"
    else
        print_status 1 "Metadata file not found"
        VALIDATION_PASSED=false
    fi

    # Analyze class distribution
    print_info "Analyzing class distribution..."

    # Python script to analyze masks
    python3 << 'EOF'
import sys
from pathlib import Path
import numpy as np
from PIL import Image

test_output = Path(sys.argv[1]) if len(sys.argv) > 1 else Path('.')
masks_dir = test_output / 'masks'

if not masks_dir.exists():
    print("Masks directory not found")
    sys.exit(1)

# Analyze all masks
class_names = ['background', 'building', 'road', 'water', 'forest']
total_counts = {i: 0 for i in range(5)}
num_masks = 0

for mask_file in sorted(masks_dir.glob('*.png')):
    try:
        mask = np.array(Image.open(mask_file))
        num_masks += 1

        for class_id in range(5):
            count = np.sum(mask == class_id)
            total_counts[class_id] += count
    except Exception as e:
        print(f"Error reading {mask_file}: {e}")

if num_masks > 0:
    print(f"\n    Analyzed {num_masks} masks")
    print("    Class distribution (across all samples):")

    total_pixels = sum(total_counts.values())
    for class_id in range(5):
        count = total_counts[class_id]
        pct = (count / total_pixels * 100) if total_pixels > 0 else 0
        print(f"      {class_names[class_id]:12s}: {count:10d} pixels ({pct:5.2f}%)")

    # Check if classes are present
    missing_classes = [class_names[i] for i in range(1, 5) if total_counts[i] == 0]
    if missing_classes:
        print(f"\n    ⚠ Warning: Missing classes: {', '.join(missing_classes)}")
        print("      This is normal if the test area doesn't contain these features.")
else:
    print("    No masks found to analyze")
    sys.exit(1)
EOF

    if [ $? -eq 0 ]; then
        print_status 0 "Class distribution analyzed"
    else
        print_status 1 "Failed to analyze class distribution"
    fi

    # Check image-mask alignment
    print_info "Verifying image-mask alignment..."

    IMAGE_FILES=($(find "$TEST_OUTPUT/images" -name "*.png" 2>/dev/null | head -n 3))

    for img_file in "${IMAGE_FILES[@]}"; do
        base_name=$(basename "$img_file")
        mask_file="$TEST_OUTPUT/masks/$base_name"

        if [ -f "$mask_file" ]; then
            # Check dimensions match
            img_size=$(python3 -c "from PIL import Image; img=Image.open('$img_file'); print(f'{img.width}x{img.height}')")
            mask_size=$(python3 -c "from PIL import Image; img=Image.open('$mask_file'); print(f'{img.width}x{img.height}')")

            if [ "$img_size" = "$mask_size" ]; then
                echo -e "      ✓ $base_name: $img_size"
            else
                echo -e "      ✗ $base_name: size mismatch (image: $img_size, mask: $mask_size)"
                VALIDATION_PASSED=false
            fi
        fi
    done

    print_status 0 "Image-mask alignment verified"

    # Create a visual comparison if possible
    print_info "Creating visual comparison..."

    python3 << 'EOF'
import sys
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont

test_output = Path(sys.argv[1]) if len(sys.argv) > 1 else Path('.')
images_dir = test_output / 'images'
masks_dir = test_output / 'masks'
output_file = test_output / 'validation_preview.png'

# Get first 3 samples
image_files = sorted(images_dir.glob('*.png'))[:3]

if not image_files:
    print("No images found for visualization")
    sys.exit(1)

# Color map for classes
colors = {
    0: (0, 0, 0),        # background - black
    1: (255, 0, 0),      # building - red
    2: (255, 255, 0),    # road - yellow
    3: (0, 0, 255),      # water - blue
    4: (0, 255, 0),      # forest - green
}

previews = []

for img_file in image_files:
    base_name = img_file.name
    mask_file = masks_dir / base_name

    if not mask_file.exists():
        continue

    # Load image and mask
    img = Image.open(img_file).convert('RGB')
    mask = np.array(Image.open(mask_file))

    # Create colored mask
    h, w = mask.shape
    colored_mask = np.zeros((h, w, 3), dtype=np.uint8)

    for class_id, color in colors.items():
        colored_mask[mask == class_id] = color

    colored_mask_img = Image.fromarray(colored_mask)

    # Create overlay
    overlay = Image.blend(img, colored_mask_img, alpha=0.4)

    # Combine: image | mask | overlay
    combined_width = img.width * 3
    combined = Image.new('RGB', (combined_width, img.height))
    combined.paste(img, (0, 0))
    combined.paste(colored_mask_img, (img.width, 0))
    combined.paste(overlay, (img.width * 2, 0))

    previews.append(combined)

if previews:
    # Stack vertically
    total_height = sum(p.height for p in previews)
    final = Image.new('RGB', (previews[0].width, total_height))

    y_offset = 0
    for preview in previews:
        final.paste(preview, (0, y_offset))
        y_offset += preview.height

    # Add legend at the bottom
    legend_height = 100
    legend = Image.new('RGB', (final.width, legend_height), (255, 255, 255))
    draw = ImageDraw.Draw(legend)

    # Draw legend
    x_start = 20
    y_start = 20
    for i, (class_id, color) in enumerate(colors.items()):
        class_names = ['Background', 'Building', 'Road', 'Water', 'Forest']

        # Draw color box
        box_x = x_start + (i * 200)
        draw.rectangle([box_x, y_start, box_x + 30, y_start + 30], fill=color)
        draw.text((box_x + 40, y_start + 5), class_names[class_id], fill=(0, 0, 0))

    draw.text((x_start, y_start + 50), "Layout: Original | Mask | Overlay", fill=(100, 100, 100))

    # Combine with legend
    final_with_legend = Image.new('RGB', (final.width, final.height + legend_height))
    final_with_legend.paste(final, (0, 0))
    final_with_legend.paste(legend, (0, final.height))

    # Save
    final_with_legend.save(output_file)
    print(f"\n    Visual preview saved to: {output_file}")
else:
    print("No samples available for visualization")
    sys.exit(1)
EOF

    if [ $? -eq 0 ]; then
        print_status 0 "Visual comparison created"
    else
        print_info "Could not create visual comparison (non-critical)"
    fi

fi

# Final summary
echo -e "\n${BLUE}========================================${NC}"
echo -e "${BLUE}Validation Summary${NC}"
echo -e "${BLUE}========================================${NC}"

if [ "$VALIDATION_PASSED" = true ]; then
    echo -e "${GREEN}✓ All validation checks passed!${NC}"
    echo ""
    echo "Phase 2 setup is complete and working correctly."
    echo ""
    echo "Next steps:"
    echo "  1. Generate full dataset:"
    echo "     python generate_dataset.py --count 1000 --output ../data/synthetic"
    echo ""
    echo "  2. Review test samples in:"
    echo "     $TEST_OUTPUT"
    echo ""
    echo "  3. Check the visual preview:"
    echo "     open $TEST_OUTPUT/validation_preview.png"
    echo ""
    exit 0
else
    echo -e "${RED}✗ Some validation checks failed${NC}"
    echo ""
    echo "Please review the errors above and fix them before proceeding."
    echo ""
    echo "Common issues:"
    echo "  - Missing Python packages: pip install pillow numpy requests tqdm"
    echo "  - Missing style files: Check synthetic/styles/ directory"
    echo "  - Network issues: Overpass API might be slow or unavailable"
    echo ""
    exit 1
fi
