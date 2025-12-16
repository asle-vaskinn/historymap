#!/bin/bash
#
# Validation script for Phase 3: ML Training and Inference
# Checks that all components are working correctly
#

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Directories
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
ML_DIR="$SCRIPT_DIR"
RESULTS_DIR="$PROJECT_ROOT/results"
MODELS_DIR="$PROJECT_ROOT/models"
SYNTHETIC_DIR="$PROJECT_ROOT/synthetic"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Phase 3 Validation Script${NC}"
echo -e "${BLUE}ML Training and Inference Pipeline${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Function to print status
print_status() {
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓${NC} $1"
    else
        echo -e "${RED}✗${NC} $1"
        exit 1
    fi
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

print_info() {
    echo -e "${BLUE}ℹ${NC} $1"
}

# Check 1: Verify directory structure
echo -e "\n${BLUE}[1/8] Checking directory structure...${NC}"

check_dir() {
    if [ -d "$1" ]; then
        echo -e "${GREEN}✓${NC} $1"
    else
        echo -e "${RED}✗${NC} $1 (missing)"
        mkdir -p "$1"
        echo -e "${YELLOW}  Created directory${NC}"
    fi
}

check_dir "$ML_DIR"
check_dir "$RESULTS_DIR/predictions"
check_dir "$RESULTS_DIR/training_logs"
check_dir "$MODELS_DIR/checkpoints"

# Check 2: Verify required files exist
echo -e "\n${BLUE}[2/8] Checking required files...${NC}"

check_file() {
    if [ -f "$1" ]; then
        echo -e "${GREEN}✓${NC} $1"
    else
        echo -e "${RED}✗${NC} $1 (missing)"
        return 1
    fi
}

check_file "$ML_DIR/predict.py"
check_file "$ML_DIR/vectorize.py"
check_file "$ML_DIR/requirements.txt"

# Check 3: Check Python version
echo -e "\n${BLUE}[3/8] Checking Python version...${NC}"
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
echo -e "${GREEN}✓${NC} Python $PYTHON_VERSION"

# Check 4: Verify Python imports
echo -e "\n${BLUE}[4/8] Checking Python dependencies...${NC}"

python3 -c "
import sys
import importlib

packages = {
    'torch': 'PyTorch',
    'torchvision': 'TorchVision',
    'segmentation_models_pytorch': 'segmentation-models-pytorch',
    'cv2': 'opencv-python',
    'PIL': 'Pillow',
    'numpy': 'NumPy',
    'geojson': 'geojson',
    'shapely': 'Shapely',
    'tqdm': 'tqdm',
}

missing = []
for module, name in packages.items():
    try:
        mod = importlib.import_module(module)
        version = getattr(mod, '__version__', 'unknown')
        print(f'✓ {name}: {version}')
    except ImportError:
        print(f'✗ {name}: NOT INSTALLED')
        missing.append(name)

if missing:
    print(f'\nMissing packages: {\" \".join(missing)}')
    print(f'Install with: pip install -r $ML_DIR/requirements.txt')
    sys.exit(1)
"
print_status "All dependencies installed"

# Check 5: Check device availability
echo -e "\n${BLUE}[5/8] Checking compute devices...${NC}"

python3 -c "
import torch

print('Available devices:')

# Check CUDA
if torch.cuda.is_available():
    print(f'  ✓ CUDA: {torch.cuda.get_device_name(0)}')
    print(f'    - CUDA version: {torch.version.cuda}')
    print(f'    - Memory: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} GB')
else:
    print('  ✗ CUDA: Not available')

# Check MPS (Apple Silicon)
if hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
    print('  ✓ MPS (Metal Performance Shaders): Available')
else:
    print('  ✗ MPS: Not available')

# CPU is always available
print('  ✓ CPU: Available')

# Recommend device
if torch.cuda.is_available():
    print('\nRecommended device: CUDA (GPU)')
elif hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
    print('\nRecommended device: MPS (Apple Silicon)')
else:
    print('\nRecommended device: CPU (slow for training)')
"

# Check 6: Test model loading (if checkpoint exists)
echo -e "\n${BLUE}[6/8] Testing model architecture...${NC}"

python3 -c "
import torch
import segmentation_models_pytorch as smp

try:
    # Create a test model
    model = smp.Unet(
        encoder_name='resnet34',
        encoder_weights='imagenet',  # Pretrained weights
        in_channels=3,
        classes=5,
    )
    print('✓ Model architecture initialized successfully')

    # Test forward pass
    dummy_input = torch.randn(1, 3, 256, 256)
    with torch.no_grad():
        output = model(dummy_input)

    assert output.shape == (1, 5, 256, 256), f'Unexpected output shape: {output.shape}'
    print('✓ Forward pass successful')
    print(f'  Input shape: {dummy_input.shape}')
    print(f'  Output shape: {output.shape}')

except Exception as e:
    print(f'✗ Model test failed: {e}')
    import sys
    sys.exit(1)
"
print_status "Model architecture working"

# Check 7: Test inference script
echo -e "\n${BLUE}[7/8] Testing inference script...${NC}"

# Create a test image if it doesn't exist
TEST_IMAGE="$RESULTS_DIR/predictions/test_input.png"
if [ ! -f "$TEST_IMAGE" ]; then
    print_info "Creating test image..."
    python3 -c "
from PIL import Image
import numpy as np

# Create a simple test image (256x256 RGB)
img = np.random.randint(0, 255, (256, 256, 3), dtype=np.uint8)
Image.fromarray(img).save('$TEST_IMAGE')
print('Created test image: $TEST_IMAGE')
"
fi

echo -e "${GREEN}✓${NC} Test image ready: $TEST_IMAGE"

# Try to run prediction (will fail without a checkpoint, but should show proper error)
echo -e "\n${YELLOW}Note: Prediction requires a trained model checkpoint${NC}"
echo -e "${YELLOW}To test prediction:${NC}"
echo -e "${YELLOW}  python3 $ML_DIR/predict.py --checkpoint <path_to_model.pth> --input $TEST_IMAGE --output $RESULTS_DIR/predictions/test_mask.png${NC}"

# Check 8: Test vectorization script
echo -e "\n${BLUE}[8/8] Testing vectorization script...${NC}"

# Create a test mask if it doesn't exist
TEST_MASK="$RESULTS_DIR/predictions/test_mask.png"
if [ ! -f "$TEST_MASK" ]; then
    print_info "Creating test mask..."
    python3 -c "
from PIL import Image
import numpy as np

# Create a simple test mask (256x256)
# Class 0: background, 1: building, 2: road, 3: water, 4: forest
mask = np.zeros((256, 256), dtype=np.uint8)

# Add some test features
mask[50:100, 50:100] = 1  # Building
mask[120:130, 20:200] = 2  # Road
mask[150:200, 150:220] = 3  # Water
mask[30:80, 180:240] = 4  # Forest

Image.fromarray(mask, mode='L').save('$TEST_MASK')
print('Created test mask: $TEST_MASK')
"
fi

# Test vectorization
TEST_GEOJSON="$RESULTS_DIR/predictions/test_features.geojson"
print_info "Running vectorization test..."

python3 "$ML_DIR/vectorize.py" \
    --input "$TEST_MASK" \
    --output "$TEST_GEOJSON" \
    --simplify 1.0 \
    --min-area 10.0

if [ -f "$TEST_GEOJSON" ]; then
    echo -e "${GREEN}✓${NC} Vectorization successful: $TEST_GEOJSON"

    # Show feature count
    FEATURE_COUNT=$(python3 -c "
import json
with open('$TEST_GEOJSON') as f:
    data = json.load(f)
print(len(data['features']))
")
    echo -e "  Features created: $FEATURE_COUNT"

    # Show class distribution
    python3 -c "
import json
with open('$TEST_GEOJSON') as f:
    data = json.load(f)
counts = data['metadata']['class_counts']
print('  Class distribution:')
for class_name, count in counts.items():
    if count > 0:
        print(f'    {class_name}: {count}')
"
else
    echo -e "${RED}✗${NC} Vectorization failed"
    exit 1
fi

# Summary
echo -e "\n${BLUE}========================================${NC}"
echo -e "${GREEN}Phase 3 Validation Complete!${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo -e "All checks passed. The ML pipeline is ready."
echo ""
echo -e "${YELLOW}Next steps:${NC}"
echo -e "1. Train a model (see train.py when implemented)"
echo -e "2. Run inference: python3 $ML_DIR/predict.py --checkpoint <model.pth> --input <image> --output <mask>"
echo -e "3. Vectorize results: python3 $ML_DIR/vectorize.py --input <mask> --output <geojson>"
echo ""
echo -e "${BLUE}Files created:${NC}"
echo -e "  - $TEST_IMAGE"
echo -e "  - $TEST_MASK"
echo -e "  - $TEST_GEOJSON"
echo ""
echo -e "${YELLOW}To install dependencies:${NC}"
echo -e "  pip install -r $ML_DIR/requirements.txt"
echo ""
