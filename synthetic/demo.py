#!/usr/bin/env python3
"""
Quick demonstration of aging effects.

This script creates a simple test map and applies aging effects,
showing before/after comparisons. Run this to quickly verify the
module is working correctly.
"""

import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import numpy as np

# Ensure we can import from current directory
sys.path.insert(0, str(Path(__file__).parent))

from age_effects import age_map, get_available_styles


def create_demo_map(width=800, height=600):
    """Create a simple map for demonstration."""
    img = Image.new('RGB', (width, height), '#F5F5DC')  # Beige background
    draw = ImageDraw.Draw(img)

    # Draw water
    draw.ellipse([50, 50, 300, 250], fill='#4A90C8', outline='#2E5C8C', width=3)

    # Draw roads
    draw.rectangle([0, 280, width, 300], fill='#808080', outline='#606060', width=2)
    draw.rectangle([400, 0, 420, height], fill='#808080', outline='#606060', width=2)

    # Draw buildings
    buildings = [
        [100, 320, 180, 400],
        [220, 310, 300, 420],
        [340, 330, 400, 390],
        [450, 320, 530, 410],
        [580, 310, 670, 400],
        [100, 450, 170, 540],
        [220, 460, 310, 550],
        [450, 450, 540, 530],
        [600, 470, 720, 560],
    ]

    for bbox in buildings:
        draw.rectangle(bbox, fill='#505050', outline='#202020', width=2)

    # Draw green space
    draw.ellipse([500, 80, 720, 240], fill='#6B8E6B', outline='#4A6B4A', width=2)

    # Add title
    try:
        font_large = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 48)
        font_small = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 24)
    except:
        font_large = ImageFont.load_default()
        font_small = ImageFont.load_default()

    draw.text((width//2, 20), "TRONDHEIM", fill='#000000', font=font_large, anchor='mt')
    draw.text((175, 150), "Fjord", fill='#1A3A5C', font=font_small, anchor='mm')
    draw.text((610, 160), "Park", fill='#2A4A2A', font=font_small, anchor='mm')

    return img


def create_comparison(original, aged, style_name):
    """Create side-by-side comparison."""
    width, height = original.size
    comparison = Image.new('RGB', (width * 2 + 20, height + 60), 'white')

    # Paste images
    comparison.paste(original, (10, 50))
    comparison.paste(aged, (width + 10, 50))

    # Add labels
    draw = ImageDraw.Draw(comparison)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 28)
    except:
        font = ImageFont.load_default()

    draw.text((width//2 + 10, 15), "Modern", fill='black', font=font, anchor='mm')
    draw.text((width + width//2 + 10, 15), style_name, fill='black', font=font, anchor='mm')

    return comparison


def main():
    """Run demonstration."""
    print("=" * 70)
    print("Historical Map Aging Effects - Quick Demo")
    print("=" * 70)
    print()

    # Create output directory
    output_dir = Path(__file__).parent / "demo_output"
    output_dir.mkdir(exist_ok=True)

    # Create test map
    print("Creating demo map...")
    demo_map = create_demo_map()
    demo_map.save(output_dir / "demo_original.png")
    print(f"✓ Saved original: {output_dir / 'demo_original.png'}")
    print()

    # Apply each style
    print("Applying aging effects...")
    print("-" * 70)

    styles = get_available_styles()
    intensity = 0.6

    for style_id, style_name in styles.items():
        print(f"\nStyle: {style_name} ({style_id})")

        # Age the map
        aged = age_map(demo_map, intensity=intensity, style=style_id, seed=42)

        # Save individual aged version
        aged_path = output_dir / f"demo_{style_id}.png"
        aged.save(aged_path)
        print(f"  ✓ Aged version: {aged_path}")

        # Create comparison
        comparison = create_comparison(demo_map, aged, style_name)
        comparison_path = output_dir / f"comparison_{style_id}.png"
        comparison.save(comparison_path)
        print(f"  ✓ Comparison: {comparison_path}")

    # Create mega comparison (all styles)
    print("\nCreating combined comparison...")
    all_styles = list(styles.keys())
    cols = len(all_styles) + 1  # +1 for original
    cell_width = 400
    cell_height = 300

    mega = Image.new('RGB', (cell_width * cols, cell_height + 40), 'white')

    # Add original
    resized_original = demo_map.resize((cell_width, cell_height), Image.Resampling.LANCZOS)
    mega.paste(resized_original, (0, 40))

    # Add aged versions
    for idx, style_id in enumerate(all_styles, 1):
        aged = age_map(demo_map, intensity=intensity, style=style_id, seed=42)
        resized_aged = aged.resize((cell_width, cell_height), Image.Resampling.LANCZOS)
        mega.paste(resized_aged, (cell_width * idx, 40))

    # Add labels
    draw = ImageDraw.Draw(mega)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 20)
    except:
        font = ImageFont.load_default()

    labels = ["Original"] + all_styles
    for idx, label in enumerate(labels):
        x = cell_width * idx + cell_width // 2
        y = 10
        draw.text((x, y), label, fill='black', font=font, anchor='mt')

    mega_path = output_dir / "all_styles_comparison.png"
    mega.save(mega_path)
    print(f"✓ Combined comparison: {mega_path}")

    # Summary
    print()
    print("=" * 70)
    print("Demo complete!")
    print("=" * 70)
    print(f"\nOutput directory: {output_dir}")
    print("\nGenerated files:")
    print("  • demo_original.png - Original test map")
    for style_id in styles.keys():
        print(f"  • demo_{style_id}.png - Aged with {style_id} style")
        print(f"  • comparison_{style_id}.png - Side-by-side comparison")
    print("  • all_styles_comparison.png - All styles in one image")
    print()
    print("Visual inspection checklist:")
    print("  [ ] 1880 shows heavy aging (strong yellowing, blur, stains)")
    print("  [ ] 1900 shows moderate aging (paper texture, some yellowing)")
    print("  [ ] 1920 shows light aging (subtle effects)")
    print("  [ ] 1950 shows minimal aging (mostly paper texture)")
    print("  [ ] Effects look realistic and period-appropriate")
    print()
    print("Next steps:")
    print("  1. Review the generated images")
    print("  2. Run test_aging.py for comprehensive tests")
    print("  3. See example_usage.py for code examples")
    print("  4. Read README_AGING.md for full documentation")
    print()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
