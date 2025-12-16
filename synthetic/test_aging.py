#!/usr/bin/env python3
"""
Visual test script for aging effects.

This script demonstrates the aging effects module by:
1. Creating a simple test map image
2. Applying different aging styles
3. Generating comparison images
4. Testing all individual effects
"""

import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import numpy as np

# Add synthetic directory to path
sys.path.insert(0, str(Path(__file__).parent))

from age_effects import age_map, get_available_styles, MapAger
from textures import TextureGenerator


def create_test_map(width: int = 512, height: int = 512) -> Image.Image:
    """
    Create a simple test map with buildings, roads, and water.

    Args:
        width: Image width
        height: Image height

    Returns:
        PIL Image of test map
    """
    # Create white background
    img = Image.new('RGB', (width, height), 'white')
    draw = ImageDraw.Draw(img)

    # Draw water bodies (blue)
    draw.rectangle([20, 20, 150, 100], fill='#6B9DC8', outline='#4A7BA7', width=2)
    draw.ellipse([350, 300, 480, 400], fill='#6B9DC8', outline='#4A7BA7', width=2)

    # Draw roads (gray)
    # Vertical road
    draw.rectangle([240, 0, 260, height], fill='#D3D3D3', outline='#A0A0A0', width=1)
    # Horizontal roads
    draw.rectangle([0, 150, width, 170], fill='#D3D3D3', outline='#A0A0A0', width=1)
    draw.rectangle([0, 350, width, 370], fill='#D3D3D3', outline='#A0A0A0', width=1)

    # Draw buildings (dark gray)
    buildings = [
        [50, 200, 100, 250],
        [120, 200, 180, 260],
        [200, 200, 240, 240],
        [280, 200, 340, 280],
        [360, 200, 420, 250],
        [440, 200, 490, 240],
        [50, 390, 110, 450],
        [130, 380, 200, 460],
        [280, 390, 350, 470],
        [380, 410, 460, 480],
    ]

    for bbox in buildings:
        draw.rectangle(bbox, fill='#505050', outline='#303030', width=1)

    # Draw forest/green areas
    draw.ellipse([60, 280, 180, 340], fill='#7CB97C', outline='#5A9359', width=1)
    draw.rectangle([400, 50, 490, 150], fill='#7CB97C', outline='#5A9359', width=1)

    # Add some labels
    try:
        # Try to use a font, fallback to default if not available
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 20)
    except:
        font = ImageFont.load_default()

    draw.text((250, 10), "TRONDHEIM", fill='black', font=font, anchor='mm')
    draw.text((75, 60), "Fjord", fill='#2A5073', font=font, anchor='mm')

    return img


def test_all_styles(output_dir: Path):
    """Test all available aging styles."""
    print("Testing all aging styles...")
    print("=" * 60)

    # Create test map
    test_map = create_test_map()

    # Save original
    output_dir.mkdir(parents=True, exist_ok=True)
    test_map.save(output_dir / "00_original.png")
    print("✓ Saved original test map")

    # Apply each style at different intensities
    styles = get_available_styles()

    for style_id, style_name in styles.items():
        print(f"\nTesting style: {style_name} ({style_id})")

        for intensity in [0.3, 0.5, 0.7, 1.0]:
            aged = age_map(test_map, intensity=intensity, style=style_id, seed=42)

            filename = f"{style_id}_intensity_{int(intensity*100):03d}.png"
            aged.save(output_dir / filename)
            print(f"  ✓ Intensity {intensity:.1f}: {filename}")


def test_individual_effects(output_dir: Path):
    """Test individual aging effects separately."""
    print("\nTesting individual effects...")
    print("=" * 60)

    test_map = create_test_map()
    ager = MapAger(seed=42)

    effects_dir = output_dir / "individual_effects"
    effects_dir.mkdir(parents=True, exist_ok=True)

    # Test each effect individually
    individual_effects = [
        ("blur", {"blur": 0.8, "yellowing": 0, "paper_texture": 0, "noise": 0}),
        ("yellowing", {"yellowing": 0.8, "blur": 0, "paper_texture": 0, "noise": 0}),
        ("paper_texture", {"paper_texture": 0.8, "blur": 0, "yellowing": 0, "noise": 0}),
        ("noise", {"noise": 0.8, "blur": 0, "yellowing": 0, "paper_texture": 0}),
        ("ink_bleed", {"ink_bleed": 0.8, "blur": 0, "yellowing": 0}),
        ("stains", {"stains": 1.0, "yellowing": 0, "blur": 0}),
        ("fold_lines", {"fold_lines": 1.0, "yellowing": 0, "blur": 0}),
        ("edge_wear", {"edge_wear": 1.0, "yellowing": 0, "blur": 0}),
        ("ink_spots", {"ink_spots": 1.0, "yellowing": 0, "blur": 0}),
    ]

    for effect_name, params in individual_effects:
        aged = ager.age_map(test_map, intensity=1.0, style="1900", custom_params=params)
        filename = f"effect_{effect_name}.png"
        aged.save(effects_dir / filename)
        print(f"  ✓ {effect_name}: {filename}")


def test_textures(output_dir: Path):
    """Test texture generation."""
    print("\nTesting texture generation...")
    print("=" * 60)

    textures_dir = output_dir / "textures"
    textures_dir.mkdir(parents=True, exist_ok=True)

    gen = TextureGenerator(seed=42)

    # Test different textures
    textures = {
        'paper': lambda: gen.generate_paper_texture(512, 512),
        'paper_fine': lambda: gen.generate_paper_texture(512, 512, scale=0.5),
        'paper_coarse': lambda: gen.generate_paper_texture(512, 512, scale=2.0),
        'noise_low': lambda: gen.generate_noise_pattern(512, 512, intensity=0.05),
        'noise_high': lambda: gen.generate_noise_pattern(512, 512, intensity=0.3),
        'stains': lambda: gen.generate_stains(512, 512, num_stains=5),
        'fold_lines': lambda: gen.generate_fold_lines(512, 512, num_folds=3),
        'ink_spots': lambda: gen.generate_ink_spots(512, 512, num_spots=15),
        'edge_wear': lambda: gen.generate_edge_wear(512, 512, border_size=60),
    }

    for name, texture_func in textures.items():
        texture = texture_func()
        filename = f"texture_{name}.png"
        texture.save(textures_dir / filename)
        print(f"  ✓ {name}: {filename}")


def create_comparison_grid(output_dir: Path):
    """Create a comparison grid of all styles."""
    print("\nCreating comparison grid...")
    print("=" * 60)

    test_map = create_test_map(width=400, height=400)
    styles = list(get_available_styles().keys())

    # Create grid: original + 4 styles
    grid_width = 5
    grid_height = 1
    cell_width = 400
    cell_height = 400

    grid = Image.new(
        'RGB',
        (cell_width * grid_width, cell_height * grid_height),
        'white'
    )

    # Add original
    grid.paste(test_map, (0, 0))

    # Add aged versions
    for idx, style in enumerate(styles, 1):
        aged = age_map(test_map, intensity=0.6, style=style, seed=42)
        grid.paste(aged, (cell_width * idx, 0))

    # Add labels
    draw = ImageDraw.Draw(grid)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 24)
    except:
        font = ImageFont.load_default()

    labels = ["Original"] + styles
    for idx, label in enumerate(labels):
        x = cell_width * idx + cell_width // 2
        y = 10
        # Draw text with background
        bbox = draw.textbbox((x, y), label, font=font, anchor='mt')
        draw.rectangle([bbox[0]-5, bbox[1]-5, bbox[2]+5, bbox[3]+5], fill='white', outline='black')
        draw.text((x, y), label, fill='black', font=font, anchor='mt')

    grid.save(output_dir / "comparison_grid.png")
    print("✓ Saved comparison grid")


def test_batch_processing(output_dir: Path):
    """Test batch processing capability."""
    print("\nTesting batch processing...")
    print("=" * 60)

    # Create multiple test maps
    batch_input_dir = output_dir / "batch_input"
    batch_output_dir = output_dir / "batch_output"

    batch_input_dir.mkdir(parents=True, exist_ok=True)

    # Generate 5 different test maps
    for i in range(5):
        test_map = create_test_map()
        # Add variation
        draw = ImageDraw.Draw(test_map)
        np.random.seed(i)
        for _ in range(5):
            x = np.random.randint(50, 450)
            y = np.random.randint(50, 450)
            size = np.random.randint(30, 80)
            color = tuple(np.random.randint(100, 200, 3))
            draw.rectangle([x, y, x+size, y+size], fill=color, outline='black')

        test_map.save(batch_input_dir / f"test_map_{i:02d}.png")

    print(f"✓ Created 5 test maps in {batch_input_dir}")

    # Process in batch
    from age_effects import batch_age_maps

    input_paths = list(batch_input_dir.glob("*.png"))
    batch_age_maps(
        input_paths,
        str(batch_output_dir),
        intensity=0.6,
        style="1900",
        seed=42,
        parallel=False  # Disable parallel for testing
    )

    print(f"✓ Processed batch to {batch_output_dir}")


def test_reproducibility(output_dir: Path):
    """Test that same seed produces same output."""
    print("\nTesting reproducibility...")
    print("=" * 60)

    test_map = create_test_map()
    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(parents=True, exist_ok=True)

    # Generate same image multiple times with same seed
    for i in range(3):
        aged = age_map(test_map, intensity=0.7, style="1900", seed=42)
        aged.save(repro_dir / f"aged_seed42_{i}.png")

    # Generate with different seed
    aged_different = age_map(test_map, intensity=0.7, style="1900", seed=123)
    aged_different.save(repro_dir / "aged_seed123.png")

    print("✓ Generated reproducibility test images")
    print("  Check that aged_seed42_*.png are identical")
    print("  Check that aged_seed123.png is different")


def generate_readme(output_dir: Path):
    """Generate README for test output."""
    readme_content = """# Aging Effects Test Output

This directory contains test outputs for the historical map aging effects system.

## Directory Structure

- `00_original.png` - Original test map (before aging)
- `1880_intensity_*.png` - 1880s military survey style at various intensities
- `1900_intensity_*.png` - 1900s cadastral map style at various intensities
- `1920_intensity_*.png` - 1920s topographic map style at various intensities
- `1950_intensity_*.png` - 1950s modern print style at various intensities
- `comparison_grid.png` - Side-by-side comparison of all styles
- `individual_effects/` - Each aging effect applied separately
- `textures/` - Raw texture samples
- `batch_output/` - Batch processing test results
- `reproducibility/` - Seed reproducibility tests

## Visual Inspection Checklist

### Overall Aging Styles
- [ ] 1880 style has strongest aging (heavy yellowing, blur, stains)
- [ ] 1900 style has moderate aging (visible paper texture, some yellowing)
- [ ] 1920 style has lighter aging (subtle effects)
- [ ] 1950 style has minimal aging (mostly just paper texture)
- [ ] Intensity scaling works correctly (higher = more aged)

### Individual Effects
Check `individual_effects/` directory:
- [ ] `effect_blur.png` - Buildings and roads appear slightly blurred
- [ ] `effect_yellowing.png` - Image has sepia/yellow tint, darker at edges
- [ ] `effect_paper_texture.png` - Visible paper grain/fiber texture
- [ ] `effect_noise.png` - Film grain visible across image
- [ ] `effect_ink_bleed.png` - Dark areas slightly expanded
- [ ] `effect_stains.png` - Brown irregular stains visible
- [ ] `effect_fold_lines.png` - Subtle fold creases visible
- [ ] `effect_edge_wear.png` - Edges darker than center
- [ ] `effect_ink_spots.png` - Small dark spots scattered

### Textures
Check `textures/` directory:
- [ ] Paper textures show realistic grain
- [ ] Different paper scales produce different detail levels
- [ ] Noise patterns look random but natural
- [ ] Stains are irregular and organic-looking
- [ ] Fold lines have natural waviness

### Technical
- [ ] All images saved successfully
- [ ] No artifacts or corruption
- [ ] Images with same seed are identical (reproducibility)
- [ ] Batch processing works correctly

## Usage Examples

Based on these test results, here are recommended settings:

### Light aging (1920s-1950s maps)
```python
aged = age_map(img, intensity=0.3, style="1920", seed=42)
```

### Medium aging (1900s maps)
```python
aged = age_map(img, intensity=0.6, style="1900", seed=42)
```

### Heavy aging (1880s maps)
```python
aged = age_map(img, intensity=0.8, style="1880", seed=42)
```

### Custom parameters
```python
custom = {
    "yellowing": 0.5,
    "stains": 0.1,      # Reduce stains
    "fold_lines": 0.0,  # Remove fold lines
}
aged = age_map(img, intensity=0.6, style="1900", custom_params=custom)
```
"""

    with open(output_dir / "README.md", "w") as f:
        f.write(readme_content)

    print("✓ Generated README.md")


def main():
    """Run all tests."""
    print("Historical Map Aging Effects - Visual Test Suite")
    print("=" * 60)

    # Create output directory
    output_dir = Path(__file__).parent / "test_output"
    output_dir.mkdir(exist_ok=True)

    print(f"\nOutput directory: {output_dir}")
    print()

    # Run all tests
    try:
        test_all_styles(output_dir)
        test_individual_effects(output_dir)
        test_textures(output_dir)
        create_comparison_grid(output_dir)
        test_batch_processing(output_dir)
        test_reproducibility(output_dir)
        generate_readme(output_dir)

        print("\n" + "=" * 60)
        print("All tests completed successfully!")
        print(f"Check {output_dir} for visual results")
        print("=" * 60)

    except Exception as e:
        print(f"\n✗ Error during testing: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
