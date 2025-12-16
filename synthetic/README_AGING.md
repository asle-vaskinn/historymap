# Historical Map Aging Effects

This module provides realistic aging effects to make rendered maps look like historical documents. It's part of Phase 2 of the Trondheim Historical Map project.

## Overview

The aging effects system transforms modern, crisp map renderings into aged historical documents by applying various effects:

- **Paper texture** - Realistic paper grain and fiber patterns
- **Yellowing/sepia** - Age-appropriate color degradation (non-uniform, darker at edges)
- **Print artifacts** - Blur and ink bleed from old printing methods
- **Noise and grain** - Film grain and paper surface texture
- **Wear effects** - Stains, fold lines, edge darkening, ink spots

All effects are:
- **Configurable** - Intensity from 0.0 to 1.0
- **Reproducible** - Same seed produces identical results
- **Fast** - Process 1000 images in reasonable time
- **Lightweight** - Only requires Pillow and NumPy (scipy optional)

## Installation

```bash
cd /Users/vaskinn/Development/private/historymap/synthetic
pip install -r requirements.txt
```

### Dependencies

**Required:**
- Pillow >= 10.0.0
- NumPy >= 1.24.0

**Optional (recommended for better quality):**
- scipy >= 1.10.0 - Enables better noise generation and image filters

## Quick Start

```python
from PIL import Image
from age_effects import age_map

# Load a modern map
img = Image.open("modern_map.png")

# Apply 1900s aging
aged = age_map(img, intensity=0.6, style="1900", seed=42)

# Save result
aged.save("historical_map.png")
```

## Era Presets

The module includes four historical era presets:

| Style | Era | Description | Key Characteristics |
|-------|-----|-------------|-------------------|
| `1880` | 1880s | Military Survey | Heavy yellowing, strong blur, prominent stains |
| `1900` | 1900s | Cadastral Map | Moderate aging, visible paper texture |
| `1920` | 1920s | Topographic Map | Light aging, subtle effects |
| `1950` | 1950s | Modern Print | Minimal aging, mostly paper texture |

```python
# Get available styles
from age_effects import get_available_styles

styles = get_available_styles()
# {'1880': '1880s Military Survey', '1900': '1900s Cadastral Map', ...}
```

## Usage Examples

### Different Intensities

```python
from age_effects import age_map
from PIL import Image

img = Image.open("map.png")

# Light aging
light = age_map(img, intensity=0.3, style="1900", seed=42)

# Medium aging
medium = age_map(img, intensity=0.6, style="1900", seed=42)

# Heavy aging
heavy = age_map(img, intensity=0.9, style="1900", seed=42)
```

### Custom Parameters

Fine-tune specific effects:

```python
from age_effects import age_map

# Only paper texture and slight yellowing
custom = {
    "paper_texture": 0.8,
    "yellowing": 0.3,
    "blur": 0.1,
    "stains": 0.0,        # Disable stains
    "fold_lines": 0.0,    # Disable fold lines
}

aged = age_map(
    img,
    intensity=1.0,
    style="1900",
    custom_params=custom,
    seed=42
)
```

### Available Parameters

All parameters can be overridden in `custom_params`:

- `yellowing` (0.0-1.0) - Sepia/yellow color shift
- `sepia_tint` (tuple) - RGB multipliers for sepia effect
- `blur` (0.0-1.0) - Gaussian blur intensity
- `ink_bleed` (0.0-1.0) - Ink spread effect
- `paper_texture` (0.0-1.0) - Paper grain overlay
- `noise` (0.0-1.0) - Film grain intensity
- `stains` (0.0-1.0) - Random stain intensity
- `fold_lines` (0.0-1.0) - Fold crease intensity
- `edge_wear` (0.0-1.0) - Edge darkening
- `ink_spots` (0.0-1.0) - Small ink spot intensity

### Batch Processing

Process multiple maps efficiently:

```python
from age_effects import batch_age_maps
from pathlib import Path

# Get all PNG files
input_paths = list(Path("input_maps").glob("*.png"))

# Process all at once
batch_age_maps(
    input_paths,
    output_dir="aged_maps",
    intensity=0.6,
    style="1900",
    seed=42,
    parallel=True  # Use multiprocessing
)
```

### Reproducible Results

Same seed guarantees identical output:

```python
# These will be identical
aged1 = age_map(img, intensity=0.7, style="1900", seed=42)
aged2 = age_map(img, intensity=0.7, style="1900", seed=42)

# This will be different
aged3 = age_map(img, intensity=0.7, style="1900", seed=123)
```

### Generate Training Dataset

Create varied synthetic training data:

```python
from PIL import Image
from age_effects import age_map

img = Image.open("base_map.png")

styles = ["1880", "1900", "1920"]
intensities = [0.3, 0.5, 0.7]

for style in styles:
    for intensity in intensities:
        for variant in range(5):  # 5 variants per combination
            seed = hash((style, intensity, variant)) % 10000

            aged = age_map(img, intensity=intensity, style=style, seed=seed)
            aged.save(f"dataset/map_{style}_{intensity}_{variant}.png")
```

## Module Structure

### `age_effects.py`

Main module with aging pipeline:

- `age_map()` - Main entry point function
- `MapAger` - Class for applying effects
- `ERA_PRESETS` - Predefined style configurations
- `get_available_styles()` - List available presets
- `batch_age_maps()` - Batch processing

### `textures.py`

Procedural texture generation:

- `TextureGenerator` - Texture generation class
  - `generate_paper_texture()` - Paper grain/fiber
  - `generate_noise_pattern()` - Film grain
  - `generate_stains()` - Random stains
  - `generate_fold_lines()` - Fold creases
  - `generate_ink_spots()` - Small ink blots
  - `generate_edge_wear()` - Edge darkening

### `test_aging.py`

Visual test suite that generates:
- All styles at various intensities
- Individual effect demonstrations
- Texture samples
- Comparison grids
- Batch processing tests
- Reproducibility verification

### `example_usage.py`

Comprehensive usage examples:
- Basic usage
- Different eras
- Intensity variations
- Custom parameters
- Batch processing
- Dataset generation
- Before/after comparisons

## Testing

Run the visual test suite:

```bash
python test_aging.py
```

This generates a `test_output/` directory containing:
- Original and aged versions
- Individual effect demonstrations
- Texture samples
- Comparison grids
- Reproducibility tests

Check the generated `test_output/README.md` for inspection checklist.

## Performance

The module is optimized for batch processing:

- **Single image (512x512)**: ~100-200ms
- **1000 images**: ~2-3 minutes (with parallel processing)
- **Memory usage**: Minimal (processes one image at a time in batch mode)

Performance tips:
- Use `parallel=True` for batch processing
- Process images in batches of 100-500
- Use lower resolution for initial testing
- scipy improves quality and performance

## Technical Details

### Aging Pipeline

Effects are applied in this order:

1. **Print artifacts** - Blur and ink bleed
2. **Color aging** - Yellowing and sepia tone
3. **Paper texture** - Overlay grain
4. **Noise** - Film grain
5. **Stains** - Random stains
6. **Ink spots** - Small blots
7. **Fold lines** - Crease marks
8. **Edge wear** - Border darkening

This order ensures realistic layering (e.g., stains appear on top of yellowed paper).

### Color Transformation

The yellowing effect:
- Non-uniform (edges more yellowed than center)
- Uses distance gradient from center
- Applies RGB channel multipliers for sepia
- Adds subtle color variance noise

### Paper Texture

Generated procedurally using:
- Multi-octave Perlin-like noise
- Directional fiber patterns
- Fine grain overlay
- Normalized to light gray range (225-255)

### Reproducibility

All random operations use:
- NumPy's random seed for arrays
- Python's random seed for values
- Consistent texture generation
- Same seed → identical output

## Integration with ML Pipeline

This module is designed to work with the synthetic training pipeline:

```python
from age_effects import age_map
from PIL import Image

# 1. Render modern map (from your rendering pipeline)
modern_map = render_map_tile(lat, lon, zoom, style="modern")

# 2. Apply aging
historical_map = age_map(
    modern_map,
    intensity=0.6,
    style="1900",
    seed=tile_hash
)

# 3. Save as training image
historical_map.save(f"training_data/image_{tile_id}.png")

# 4. Save corresponding mask (from your mask generation)
mask = generate_segmentation_mask(lat, lon, zoom)
mask.save(f"training_data/mask_{tile_id}.png")
```

## Troubleshooting

### Import Error: No module named 'scipy'

Scipy is optional. The module will work without it, using fallback methods:
- Install scipy for better quality: `pip install scipy>=1.10.0`
- Or continue without it (slightly lower quality noise/blur)

### Images look too aged

Reduce intensity:
```python
aged = age_map(img, intensity=0.3, style="1900")  # Lighter aging
```

Or use a newer era preset:
```python
aged = age_map(img, intensity=0.5, style="1920")  # Less aging
```

### Stains/folds look unrealistic

Disable or reduce specific effects:
```python
custom = {"stains": 0.1, "fold_lines": 0.0}
aged = age_map(img, style="1900", custom_params=custom)
```

### Processing is slow

Enable parallel processing for batches:
```python
batch_age_maps(files, "output/", parallel=True)
```

### Colors look wrong

Check input image mode:
```python
img = Image.open("map.png")
if img.mode != 'RGB':
    img = img.convert('RGB')
aged = age_map(img, ...)
```

## Future Enhancements

Possible additions:
- [ ] Water damage effects
- [ ] Torn edges
- [ ] Mold/foxing spots
- [ ] Color-specific fading (reds fade first)
- [ ] Regional variation (Norwegian climate-specific aging)
- [ ] Archival tape marks
- [ ] Marginalia/annotations
- [ ] Custom texture uploads

## References

Historical cartography characteristics:
- Paper: Rag paper aging (18th-20th century)
- Ink: Iron gall ink oxidation
- Printing: Lithography and copperplate artifacts
- Wear: Folding, handling, storage conditions

Norwegian map archives:
- Kartverket Historical Maps
- National Library of Norway
- Norwegian Mapping Authority archives

## License

Part of the Trondheim Historical Map project.
See main project LICENSE file.

## Credits

Created for Phase 2 of the Trondheim Historical Map System.
See `/Users/vaskinn/Development/private/historymap/HISTORICAL_MAP_PROJECT_PLAN.md` for project overview.
