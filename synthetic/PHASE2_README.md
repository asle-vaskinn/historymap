# Phase 2: Synthetic Data Pipeline

This directory contains the complete synthetic data generation pipeline for creating training datasets for historical map feature extraction.

## Overview

Phase 2 generates synthetic historical map images paired with ground truth segmentation masks. The pipeline:

1. Renders map tiles using historical cartographic styles
2. Applies realistic aging effects (yellowing, paper texture, wear, etc.)
3. Generates pixel-perfect segmentation masks with 5 classes:
   - 0: background
   - 1: building
   - 2: road
   - 3: water
   - 4: forest/vegetation

## Files Created

### Core Pipeline Scripts

- **`create_masks.py`** - Generates ground truth segmentation masks
  - Fetches OSM data for tile coordinates
  - Rasterizes features into class-labeled masks
  - Handles overlapping features with priority rules
  - Saves as single-channel PNG (values 0-4)

- **`generate_dataset.py`** - Main orchestration pipeline
  - Coordinates all steps: render → age → mask → save
  - Supports batch generation with progress bars
  - Generates metadata.json with sample information
  - Configurable styles, aging intensity, and tile selection

- **`validate_phase2.sh`** - Validation and testing script
  - Checks dependencies and directory structure
  - Generates 10 test samples
  - Verifies image/mask alignment
  - Analyzes class distribution
  - Creates visual previews

### Supporting Scripts (Already Present)

- **`render_tiles.py`** - Renders styled map tiles from vector data
- **`age_effects.py`** - Applies historical aging effects
- **`tile_utils.py`** - Tile coordinate utilities
- **`textures.py`** - Procedural texture generation

### Styles

Located in `styles/` directory:
- `military_1880.json` - 1880s military survey style
- `cadastral_1900.json` - 1900s cadastral map style
- `topographic_1920.json` - 1920s topographic map style

## Quick Start

### 1. Install Dependencies

```bash
cd /Users/vaskinn/Development/private/historymap/synthetic
pip install -r requirements.txt
```

Required packages:
- Pillow (image processing)
- numpy (numerical operations)
- requests (OSM data fetching)
- tqdm (progress bars)
- scipy (optional, for advanced effects)

### 2. Validate Setup

```bash
./validate_phase2.sh
```

This will:
- Check all dependencies
- Verify directory structure
- Generate 10 test samples
- Create visual validation output
- Report any issues

### 3. Generate Dataset

Generate 1000 training samples:

```bash
python generate_dataset.py --count 1000 --output ../data/synthetic
```

With custom parameters:

```bash
# Specific area (Trondheim center)
python generate_dataset.py \
  --count 1000 \
  --bbox 10.38,63.42,10.42,63.44 \
  --zoom 15 \
  --output ../data/synthetic

# Specific styles only
python generate_dataset.py \
  --count 500 \
  --styles military_1880 cadastral_1900 \
  --output ../data/synthetic

# Custom aging intensity range
python generate_dataset.py \
  --count 1000 \
  --aging-min 0.3 \
  --aging-max 0.9 \
  --output ../data/synthetic

# Reproducible with seed
python generate_dataset.py \
  --count 1000 \
  --seed 42 \
  --output ../data/synthetic
```

## Output Structure

After running `generate_dataset.py`, the output directory contains:

```
data/synthetic/
├── images/                      # Styled, aged map images
│   ├── tile_15_17234_9345_a1b2c3d4.png
│   ├── tile_15_17235_9345_e5f6g7h8.png
│   └── ...
├── masks/                       # Ground truth segmentation masks
│   ├── tile_15_17234_9345_a1b2c3d4.png
│   ├── tile_15_17235_9345_e5f6g7h8.png
│   └── ...
└── metadata.json                # Sample metadata and parameters
```

### Metadata Format

The `metadata.json` file contains:

```json
{
  "dataset_info": {
    "num_samples": 1000,
    "tile_size": 512,
    "styles": ["military_1880", "cadastral_1900", "topographic_1920"],
    "generation_date": "2024-12-16 15:45:00",
    "seed": 42
  },
  "samples": [
    {
      "image_file": "images/tile_15_17234_9345_a1b2c3d4.png",
      "mask_file": "masks/tile_15_17234_9345_a1b2c3d4.png",
      "tile_z": 15,
      "tile_x": 17234,
      "tile_y": 9345,
      "style": "military_1880",
      "aging_intensity": 0.65,
      "aging_seed": 42,
      "bbox": [10.3827, 63.4201, 10.3937, 63.4265],
      "class_counts": {
        "0": 245678,  // background
        "1": 12345,   // building
        "2": 3456,    // road
        "3": 789,     // water
        "4": 1234     // forest
      },
      "timestamp": "2024-12-16 15:45:23"
    }
  ]
}
```

## Command-Line Tools

### create_masks.py

Generate individual masks:

```bash
# By tile coordinates
python create_masks.py --zxy 15 17234 9345 --output mask.png

# By tile string
python create_masks.py --tile 15/17234/9345 --output mask.png

# By bounding box
python create_masks.py --bbox 10.38,63.42,10.39,63.43 --zoom 15 --output mask.png

# Custom size
python create_masks.py --tile 15/17234/9345 --size 1024 --output mask.png
```

## Architecture

### Data Flow

```
1. Tile Selection
   └─> Random tiles from bounding box at zoom level

2. Style Selection
   └─> Random style from available styles

3. Rendering
   └─> Fetch OSM data via Overpass API
   └─> Apply historical map style
   └─> Generate base image (512x512)

4. Aging
   └─> Apply era-specific aging effects
   └─> Paper texture, yellowing, wear, stains, etc.
   └─> Configurable intensity

5. Mask Generation
   └─> Fetch same OSM data
   └─> Rasterize into segmentation classes
   └─> Handle overlapping features by priority
   └─> Generate mask (512x512, grayscale)

6. Save
   └─> Save image and mask with matching filenames
   └─> Update metadata
```

### Feature Priority

When features overlap, priority is (highest to lowest):
1. Water (rivers, lakes)
2. Buildings
3. Roads
4. Forest/vegetation
5. Background

This ensures water bodies aren't hidden behind buildings, etc.

## Configuration

### Aging Parameters

Each era preset has specific aging characteristics:

**1880s Military Survey** (`military_1880`)
- Heavy yellowing (0.7)
- Strong sepia tint
- Significant blur (old printing)
- Paper texture visible
- Common stains and fold lines

**1900s Cadastral** (`cadastral_1900`)
- Moderate yellowing (0.5)
- Light sepia tint
- Medium blur
- Some paper texture
- Occasional stains

**1920s Topographic** (`topographic_1920`)
- Light yellowing (0.35)
- Minimal sepia tint
- Slight blur
- Subtle paper texture
- Rare stains

### Customization

Override aging parameters:

```python
from age_effects import age_map

custom_params = {
    "yellowing": 0.8,
    "stains": 0.0,      # Disable stains
    "fold_lines": 0.0,  # Disable fold lines
    "noise": 0.2
}

aged = age_map(
    image,
    intensity=0.7,
    style="1900",
    custom_params=custom_params
)
```

## Performance

### Generation Speed

- Single sample: ~3-5 seconds
  - Overpass API fetch: ~1-2s
  - Rendering: ~0.5s
  - Aging: ~0.5s
  - Mask generation: ~1-2s

- 1000 samples: ~60-90 minutes
  - Sequential processing
  - Network dependent (Overpass API)

### Optimization Tips

1. **Use caching**: Pre-download OSM data for area
2. **Parallel processing**: Modify for multiprocessing
3. **Local data**: Use PMTiles instead of Overpass API
4. **Batch size**: Generate in smaller batches to avoid API rate limits

## Troubleshooting

### Common Issues

**"Module not found" errors**
```bash
pip install -r requirements.txt
```

**Overpass API timeouts**
- Reduce tile area or zoom level
- Add delay between requests
- Use local OSM data instead

**Empty masks (all background)**
- Selected area has no features
- Try different bounding box
- Check zoom level (15 is recommended)

**Out of memory errors**
- Reduce batch size
- Reduce tile size (--tile-size 256)
- Process in multiple runs

**Rate limiting from Overpass API**
- Add delays: `time.sleep(1)` between samples
- Use local OSM data with PMTiles
- Reduce count per run

## Next Steps

After generating your dataset:

1. **Review samples**: Check `data/synthetic/test_samples/validation_preview.png`

2. **Verify quality**:
   - Are all feature classes present?
   - Do images look realistically aged?
   - Are masks properly aligned?

3. **Generate full dataset**:
   ```bash
   python generate_dataset.py --count 5000 --output ../data/synthetic
   ```

4. **Proceed to Phase 3**: ML Training
   - Use generated images and masks to train U-Net model
   - See `ml/README.md` for training instructions

## API Reference

### create_masks.py

```python
def create_mask(z: int, x: int, y: int, size: int = 512) -> Optional[np.ndarray]:
    """
    Create segmentation mask for a tile.

    Returns:
        Numpy array of shape (size, size) with class IDs 0-4
    """
```

### generate_dataset.py

```python
class DatasetGenerator:
    def generate_dataset(
        count: int,
        bbox: Tuple[float, float, float, float] = None,
        zoom: int = 15,
        aging_intensity_range: Tuple[float, float] = (0.4, 0.8)
    ) -> List[SampleMetadata]:
        """Generate N image/mask pairs."""
```

## Credits

- OSM data: © OpenStreetMap contributors
- Overpass API: https://overpass-api.de/
- Historical map styles: Based on Norwegian historical cartography

## License

See project root LICENSE file.
