# Quick Start Guide - Rendering Pipeline

Get started with the Phase 2 rendering pipeline in 5 minutes.

## Prerequisites

```bash
# Navigate to synthetic directory
cd /Users/vaskinn/Development/private/historymap/synthetic

# Install dependencies
pip install -r requirements.txt
```

## Step 1: Verify Installation

Run the test suite to ensure everything is working:

```bash
python test_render.py
```

Expected output:
```
============================================================
Rendering Pipeline Test Suite
============================================================

Testing tile coordinate utilities...
✓ Converted (10.4, 63.43) -> tile (14/8378/4543)
✓ Tile bbox: (...)
✓ Tile center: (...)
✓ Coordinates are within tile bounds

Testing basic rendering...
✓ Renderer initialized with style: basic_map.json
✓ Created 4 test features
✓ Rendered tile z=14, x=8378, y=4543
✓ Saved test output to: test_output.png
✓ Output file is valid (...)

Testing multiple historical styles...
  ✓ basic_map.json -> test_basic_map.png
  ✓ military_1880.json -> test_military_1880.png
  ✓ cadastral_1900.json -> test_cadastral_1900.png
  ✓ topographic_1920.json -> test_topographic_1920.png
✓ All 4 styles rendered successfully

============================================================
Test Summary
============================================================
✓ PASS: Tile Coordinates
✓ PASS: Basic Rendering
✓ PASS: Multiple Styles

Total: 3/3 tests passed

✓ All tests passed! Rendering pipeline is working correctly.
```

This creates several test images you can examine:
- `test_output.png` - Basic test render
- `test_basic_map.json` - Modern style
- `test_military_1880.png` - 1880s military style
- `test_cadastral_1900.png` - 1900s cadastral style
- `test_topographic_1920.png` - 1920s topographic style

## Step 2: Render a Real Tile (Optional)

If you have a PMTiles file with OSM data:

```bash
# Single tile - Trondheim city center
python render_tiles.py \
  --style styles/military_1880.json \
  --pmtiles ../data/trondheim.pmtiles \
  --tile 14 8378 4543 \
  --output trondheim_military.png

# View the result
open trondheim_military.png  # macOS
# or: xdg-open trondheim_military.png  # Linux
```

## Step 3: Batch Rendering

Create a file with tiles to render:

```bash
# Generate tile list for Trondheim
cat > my_tiles.txt << 'EOF'
# Trondheim city center tiles (zoom 14)
14 8378 4543
14 8378 4544
14 8379 4543
14 8379 4544
EOF

# Render all tiles
python render_tiles.py \
  --style styles/topographic_1920.json \
  --pmtiles ../data/trondheim.pmtiles \
  --batch my_tiles.txt \
  --output-dir output/batch_test/ \
  --workers 4
```

## Step 4: Generate Training Dataset

Use the complete pipeline to generate synthetic training data:

```bash
# Generate 100 training pairs (images + masks)
python generate_dataset.py \
  --count 100 \
  --output ../data/synthetic/ \
  --pmtiles ../data/trondheim.pmtiles \
  --zoom 14 \
  --styles military_1880 cadastral_1900 topographic_1920

# This creates:
# ../data/synthetic/images/  - Rendered map images
# ../data/synthetic/masks/   - Ground truth segmentation masks
# ../data/synthetic/metadata.json - Pairing information
```

## Understanding Tile Coordinates

The rendering system uses slippy map tile coordinates (z/x/y):
- **z** = Zoom level (0-22)
- **x** = Tile column (0 to 2^z - 1)
- **y** = Tile row (0 to 2^z - 1)

### Trondheim Reference Points

| Location | Zoom | Tile (x, y) | Description |
|----------|------|-------------|-------------|
| Trondheim region | 10 | 524, 340 | Wide area view |
| City overview | 12 | 2095, 1135 | Full city |
| City center | 14 | 8378, 4543 | District detail |
| Street level | 16 | 33512, 18172 | Individual streets |

### Find Coordinates Programmatically

```python
from tile_utils import TileCoordinates

# Your location (lon, lat)
lon, lat = 10.4, 63.43
zoom = 14

# Get tile coordinates
x, y = TileCoordinates.lonlat_to_tile(lon, lat, zoom)
print(f"Tile: {zoom}/{x}/{y}")

# Get tile bounds
bbox = TileCoordinates.tile_to_bbox(zoom, x, y)
print(f"BBox: {bbox}")  # (min_lon, min_lat, max_lon, max_lat)
```

## Project Structure

```
synthetic/
├── README.md              # Comprehensive documentation
├── QUICKSTART.md          # This file
├── requirements.txt       # Python dependencies
│
├── render_tiles.py        # Main rendering script ⭐
├── tile_utils.py          # Coordinate conversion utilities
├── test_render.py         # Test suite
│
├── age_effects.py         # Historical aging effects
├── create_masks.py        # Ground truth mask generation
├── generate_dataset.py    # Complete dataset pipeline
├── generate_styles.py     # Style variation generator
│
└── styles/                # Historical map styles
    ├── basic_map.json
    ├── military_1880.json
    ├── cadastral_1900.json
    └── topographic_1920.json
```

## Next Steps

1. **Read the full documentation**: [README.md](README.md)
2. **Explore styles**: [styles/README.md](styles/README.md)
3. **Generate your first dataset**: See examples in README.md
4. **Move to Phase 3**: ML training with synthetic data

## Troubleshooting

### "pmtiles library not installed"
```bash
pip install pmtiles mapbox-vector-tile
```

### "No tile data for z=X, x=Y, y=Z"
The PMTiles file doesn't contain that tile. Check:
- File path is correct
- Zoom level matches data (most OSM extracts: z=0-14)
- Coordinates are within bounds

### Blank/white output images
Check that:
- Style JSON source-layer names match your data
- PMTiles file contains vector data (not raster)
- Use `--verbose` flag for debugging

### Need help?
- Check the [README.md](README.md) for detailed examples
- Review the [project plan](../HISTORICAL_MAP_PROJECT_PLAN.md)
- Run `python render_tiles.py --help`

## Examples Cheat Sheet

```bash
# Test the pipeline
python test_render.py

# Render single tile
python render_tiles.py --style styles/basic_map.json --tile 14 8378 4543 --output test.png

# Batch render with PMTiles
python render_tiles.py --style styles/military_1880.json --pmtiles data.pmtiles --batch tiles.txt --output-dir out/

# Generate full dataset
python generate_dataset.py --count 1000 --output ../data/synthetic/

# Check tile coordinates
python -c "from tile_utils import TileCoordinates; print(TileCoordinates.lonlat_to_tile(10.4, 63.43, 14))"
```

## Performance Tips

- Use `--workers 8` for faster batch rendering (adjust to your CPU cores)
- Smaller tiles (`--size 256`) render ~2x faster than 512px
- Keep PMTiles files on SSD for best I/O performance
- Lower PNG compression (`compression_level=3` in code) for speed

---

**Ready to start?** Run `python test_render.py` to verify your setup!
