#!/bin/bash
#
# Example usage of historical map styles and variation generator
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PARENT_DIR="$(dirname "$SCRIPT_DIR")"

echo "======================================"
echo "Historical Map Styles - Example Usage"
echo "======================================"
echo

# 1. Generate palette reference
echo "1. Generating palette reference..."
cd "$PARENT_DIR"
python3 generate_styles.py --palette-reference
echo "   ✓ Created palette_reference.json"
echo

# 2. Generate single variations
echo "2. Generating single style variations..."
mkdir -p variations/examples

python3 generate_styles.py styles/military_1880.json \
    --palette military_1880 \
    --variation 0.1 \
    --seed 100 \
    --output variations/examples/military_var_subtle.json

python3 generate_styles.py styles/cadastral_1900.json \
    --palette cadastral_1900 \
    --variation 0.2 \
    --seed 200 \
    --output variations/examples/cadastral_var_strong.json

echo "   ✓ Created 2 example variations"
echo

# 3. Generate batch variations for training
echo "3. Generating batch variations for ML training..."

python3 generate_styles.py styles/military_1880.json \
    --palette military_1880 \
    --output-dir variations/military \
    --count 5 \
    --variation 0.15

python3 generate_styles.py styles/cadastral_1900.json \
    --palette cadastral_1900 \
    --output-dir variations/cadastral \
    --count 5 \
    --variation 0.15

python3 generate_styles.py styles/topographic_1920.json \
    --palette topographic_1920 \
    --output-dir variations/topographic \
    --count 5 \
    --variation 0.15

echo "   ✓ Generated 15 training variations total"
echo

# 4. Validate all generated styles
echo "4. Validating all generated JSON files..."
for style in variations/**/*.json; do
    if [ -f "$style" ]; then
        if python3 -m json.tool "$style" > /dev/null 2>&1; then
            echo "   ✓ $style"
        else
            echo "   ✗ $style - INVALID JSON"
            exit 1
        fi
    fi
done

echo
echo "======================================"
echo "Summary"
echo "======================================"
echo "Base styles:         3 (military, cadastral, topographic)"
echo "Example variations:  2"
echo "Training variations: 15 (5 per base style)"
echo "Total styles:        20"
echo
echo "Variations saved in: $PARENT_DIR/variations/"
echo "Palette reference:   $PARENT_DIR/palette_reference.json"
echo
echo "Done! All styles generated successfully."
