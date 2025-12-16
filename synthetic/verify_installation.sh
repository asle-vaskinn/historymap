#!/bin/bash
# Verification script for aging effects module

echo "======================================================================"
echo "Historical Map Aging Effects - Installation Verification"
echo "======================================================================"
echo ""

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check files
echo "Checking files..."
files=(
    "age_effects.py"
    "textures.py"
    "demo.py"
    "test_aging.py"
    "example_usage.py"
    "__init__.py"
    "README_AGING.md"
    "SETUP.md"
    "requirements.txt"
)

all_files_present=true
for file in "${files[@]}"; do
    if [ -f "$file" ]; then
        echo -e "${GREEN}✓${NC} $file"
    else
        echo -e "${RED}✗${NC} $file (missing)"
        all_files_present=false
    fi
done

echo ""

# Check Python version
echo "Checking Python..."
python_version=$(python3 --version 2>&1 | awk '{print $2}')
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓${NC} Python $python_version"
else
    echo -e "${RED}✗${NC} Python 3 not found"
fi

echo ""

# Check dependencies
echo "Checking dependencies..."
deps_installed=true

if python3 -c "import PIL" 2>/dev/null; then
    pil_version=$(python3 -c "import PIL; print(PIL.__version__)" 2>/dev/null)
    echo -e "${GREEN}✓${NC} Pillow $pil_version"
else
    echo -e "${RED}✗${NC} Pillow (required)"
    deps_installed=false
fi

if python3 -c "import numpy" 2>/dev/null; then
    numpy_version=$(python3 -c "import numpy; print(numpy.__version__)" 2>/dev/null)
    echo -e "${GREEN}✓${NC} NumPy $numpy_version"
else
    echo -e "${RED}✗${NC} NumPy (required)"
    deps_installed=false
fi

if python3 -c "import scipy" 2>/dev/null; then
    scipy_version=$(python3 -c "import scipy; print(scipy.__version__)" 2>/dev/null)
    echo -e "${GREEN}✓${NC} SciPy $scipy_version"
else
    echo -e "${YELLOW}⚠${NC} SciPy (optional but recommended)"
fi

echo ""

# Try importing the module
echo "Testing module import..."
if python3 -c "import sys; sys.path.insert(0, '.'); from age_effects import age_map, get_available_styles" 2>/dev/null; then
    echo -e "${GREEN}✓${NC} Module imports successfully"
    
    # List available styles
    styles=$(python3 -c "import sys; sys.path.insert(0, '.'); from age_effects import get_available_styles; print(', '.join(get_available_styles().keys()))" 2>/dev/null)
    echo -e "${GREEN}✓${NC} Available styles: $styles"
else
    echo -e "${RED}✗${NC} Module import failed"
fi

echo ""
echo "======================================================================"

# Summary
if [ "$all_files_present" = true ] && [ "$deps_installed" = true ]; then
    echo -e "${GREEN}Status: READY ✓${NC}"
    echo ""
    echo "All files present and dependencies installed."
    echo ""
    echo "Quick start:"
    echo "  python3 demo.py          # Run quick demo (~5 seconds)"
    echo "  python3 test_aging.py    # Run full tests (~60 seconds)"
    echo ""
    echo "Documentation:"
    echo "  README_AGING.md          # Complete API documentation"
    echo "  SETUP.md                 # Setup and testing guide"
    echo ""
elif [ "$all_files_present" = true ] && [ "$deps_installed" = false ]; then
    echo -e "${YELLOW}Status: INSTALL DEPENDENCIES${NC}"
    echo ""
    echo "Files are present but dependencies need to be installed."
    echo ""
    echo "Install dependencies:"
    echo "  pip install -r requirements.txt"
    echo ""
    echo "Or manually:"
    echo "  pip install Pillow>=10.0.0 numpy>=1.24.0 scipy>=1.10.0"
    echo ""
else
    echo -e "${RED}Status: INCOMPLETE${NC}"
    echo ""
    echo "Some files are missing or dependencies not installed."
    echo "Please check the installation."
    echo ""
fi

echo "======================================================================"
