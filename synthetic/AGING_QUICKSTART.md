# Aging Effects - Quick Start

## Installation (1 minute)

```bash
cd /Users/vaskinn/Development/private/historymap/synthetic
pip install Pillow numpy scipy
```

## Verify (10 seconds)

```bash
./verify_installation.sh
```

## Quick Demo (5 seconds)

```bash
python3 demo.py
```

Output: `demo_output/all_styles_comparison.png`

## Basic Usage

```python
from PIL import Image
from age_effects import age_map

img = Image.open("map.png")
aged = age_map(img, intensity=0.6, style="1900", seed=42)
aged.save("aged_map.png")
```

## Available Styles

- `1880` - Heavy aging (military surveys)
- `1900` - Moderate aging (cadastral maps)
- `1920` - Light aging (topographic maps)
- `1950` - Minimal aging (modern prints)

## Intensity Levels

- `0.0-0.3` - Subtle aging
- `0.4-0.6` - Moderate aging
- `0.7-0.9` - Heavy aging
- `1.0` - Maximum aging

## Custom Parameters

```python
custom = {
    "yellowing": 0.7,      # 0.0-1.0
    "paper_texture": 0.5,  # 0.0-1.0
    "blur": 0.3,           # 0.0-1.0
    "stains": 0.2,         # 0.0-1.0
    "fold_lines": 0.0,     # Disable
}

aged = age_map(img, intensity=1.0, custom_params=custom)
```

## Batch Processing

```python
from age_effects import batch_age_maps
from pathlib import Path

files = list(Path("input/").glob("*.png"))
batch_age_maps(files, "output/", intensity=0.6, style="1900", parallel=True)
```

## Documentation

- `README_AGING.md` - Complete API documentation
- `SETUP.md` - Detailed setup and testing
- `example_usage.py` - More code examples
- `PHASE2_AGING_COMPLETE.md` - Implementation summary

## Testing

```bash
python3 test_aging.py  # Comprehensive tests (~60s)
```

## Key Files

| File | Purpose | Size |
|------|---------|------|
| `age_effects.py` | Main aging pipeline | 15KB |
| `textures.py` | Texture generation | 12KB |
| `demo.py` | Quick demo | 6.5KB |

Total: ~2000 lines of documented code

## Performance

- Single 512x512 image: ~100-200ms
- 1000 images (parallel): ~2-3 minutes

## Help

```bash
./verify_installation.sh  # Check installation
python3 demo.py           # Visual demo
python3 test_aging.py     # Run tests
```

For issues, see `README_AGING.md` or `SETUP.md`.
