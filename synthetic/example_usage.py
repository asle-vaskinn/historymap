#!/usr/bin/env python3
"""
Example usage of the aging effects module.

This script demonstrates common use cases for aging historical maps.
"""

from pathlib import Path
from PIL import Image
from age_effects import age_map, get_available_styles, batch_age_maps


def example_basic_usage():
    """Basic usage: age a single map."""
    print("Example 1: Basic Usage")
    print("-" * 40)

    # Load a map image
    input_path = "modern_map.png"
    if not Path(input_path).exists():
        print(f"Note: {input_path} not found, skipping example")
        return

    img = Image.open(input_path)

    # Apply aging with default settings
    aged = age_map(img, intensity=0.5, style="1900", seed=42)

    # Save result
    aged.save("aged_map_1900.png")
    print("✓ Saved aged_map_1900.png")
    print()


def example_different_eras():
    """Apply aging for different historical eras."""
    print("Example 2: Different Historical Eras")
    print("-" * 40)

    input_path = "modern_map.png"
    if not Path(input_path).exists():
        print(f"Note: {input_path} not found, skipping example")
        return

    img = Image.open(input_path)

    # Get all available styles
    styles = get_available_styles()
    print("Available styles:")
    for style_id, name in styles.items():
        print(f"  - {style_id}: {name}")

    # Process for each era
    for style_id in styles.keys():
        aged = age_map(img, intensity=0.6, style=style_id, seed=42)
        output_name = f"map_{style_id}.png"
        aged.save(output_name)
        print(f"✓ Saved {output_name}")
    print()


def example_intensity_variations():
    """Show effect of different intensity levels."""
    print("Example 3: Intensity Variations")
    print("-" * 40)

    input_path = "modern_map.png"
    if not Path(input_path).exists():
        print(f"Note: {input_path} not found, skipping example")
        return

    img = Image.open(input_path)

    # Test different intensity levels
    intensities = [0.2, 0.5, 0.8, 1.0]

    for intensity in intensities:
        aged = age_map(img, intensity=intensity, style="1900", seed=42)
        output_name = f"map_intensity_{int(intensity*100)}.png"
        aged.save(output_name)
        print(f"✓ Intensity {intensity}: {output_name}")
    print()


def example_custom_parameters():
    """Use custom parameters to fine-tune aging effects."""
    print("Example 4: Custom Parameters")
    print("-" * 40)

    input_path = "modern_map.png"
    if not Path(input_path).exists():
        print(f"Note: {input_path} not found, skipping example")
        return

    img = Image.open(input_path)

    # Example 1: Heavy yellowing, light stains
    custom1 = {
        "yellowing": 0.9,
        "stains": 0.1,
        "fold_lines": 0.0,  # No fold lines
    }
    aged1 = age_map(img, intensity=0.7, style="1900", custom_params=custom1)
    aged1.save("map_heavy_yellowing.png")
    print("✓ Heavy yellowing, light stains: map_heavy_yellowing.png")

    # Example 2: Just paper texture and slight blur
    custom2 = {
        "paper_texture": 0.8,
        "blur": 0.3,
        "yellowing": 0.1,
        "stains": 0.0,
        "fold_lines": 0.0,
    }
    aged2 = age_map(img, intensity=1.0, style="1900", custom_params=custom2)
    aged2.save("map_paper_only.png")
    print("✓ Paper texture only: map_paper_only.png")

    # Example 3: Strong degradation effects
    custom3 = {
        "stains": 1.0,
        "fold_lines": 0.8,
        "edge_wear": 1.0,
        "ink_spots": 0.5,
    }
    aged3 = age_map(img, intensity=0.8, style="1880", custom_params=custom3)
    aged3.save("map_heavily_worn.png")
    print("✓ Heavily worn: map_heavily_worn.png")
    print()


def example_reproducible_results():
    """Demonstrate reproducibility with seeds."""
    print("Example 5: Reproducible Results")
    print("-" * 40)

    input_path = "modern_map.png"
    if not Path(input_path).exists():
        print(f"Note: {input_path} not found, skipping example")
        return

    img = Image.open(input_path)

    # Same seed produces identical results
    aged1 = age_map(img, intensity=0.7, style="1900", seed=42)
    aged2 = age_map(img, intensity=0.7, style="1900", seed=42)

    aged1.save("map_seed42_a.png")
    aged2.save("map_seed42_b.png")
    print("✓ Same seed: map_seed42_a.png and map_seed42_b.png (should be identical)")

    # Different seed produces different results
    aged3 = age_map(img, intensity=0.7, style="1900", seed=123)
    aged3.save("map_seed123.png")
    print("✓ Different seed: map_seed123.png (should be different)")
    print()


def example_batch_processing():
    """Process multiple maps at once."""
    print("Example 6: Batch Processing")
    print("-" * 40)

    # Create example input directory
    input_dir = Path("maps_to_age")
    if not input_dir.exists() or not list(input_dir.glob("*.png")):
        print(f"Note: {input_dir} not found or empty, skipping example")
        print(f"Create {input_dir}/ and add some PNG files to test batch processing")
        return

    output_dir = Path("aged_maps_output")

    # Get all PNG files
    input_paths = list(input_dir.glob("*.png"))
    print(f"Found {len(input_paths)} maps to process")

    # Process all at once
    batch_age_maps(
        input_paths,
        str(output_dir),
        intensity=0.6,
        style="1900",
        seed=42,
        parallel=True  # Use multiprocessing for speed
    )

    print(f"\n✓ Batch processing complete, check {output_dir}/")
    print()


def example_synthetic_dataset_generation():
    """Generate training dataset with varied aging."""
    print("Example 7: Synthetic Dataset Generation")
    print("-" * 40)

    input_path = "modern_map.png"
    if not Path(input_path).exists():
        print(f"Note: {input_path} not found, skipping example")
        return

    img = Image.open(input_path)

    output_dir = Path("synthetic_dataset")
    output_dir.mkdir(exist_ok=True)

    # Generate multiple variations
    styles = ["1880", "1900", "1920"]
    intensities = [0.3, 0.5, 0.7]

    count = 0
    for style in styles:
        for intensity in intensities:
            # Generate 3 variants with different seeds
            for variant in range(3):
                seed = count * 100 + variant

                aged = age_map(img, intensity=intensity, style=style, seed=seed)

                filename = f"map_{style}_int{int(intensity*10)}_{variant:02d}.png"
                aged.save(output_dir / filename)

                count += 1

    print(f"✓ Generated {count} synthetic training images in {output_dir}/")
    print()


def example_progressive_aging():
    """Show progressive aging over time."""
    print("Example 8: Progressive Aging Animation")
    print("-" * 40)

    input_path = "modern_map.png"
    if not Path(input_path).exists():
        print(f"Note: {input_path} not found, skipping example")
        return

    img = Image.open(input_path)

    output_dir = Path("progressive_aging")
    output_dir.mkdir(exist_ok=True)

    # Create sequence from modern to very old
    frames = []
    for i in range(11):  # 0 to 1.0 in steps of 0.1
        intensity = i / 10.0

        aged = age_map(img, intensity=intensity, style="1900", seed=42)

        filename = f"frame_{i:02d}_intensity_{int(intensity*100):03d}.png"
        aged.save(output_dir / filename)
        frames.append(aged)

        print(f"✓ Frame {i}: intensity {intensity:.1f}")

    # Optionally create GIF
    try:
        gif_path = output_dir / "aging_animation.gif"
        frames[0].save(
            gif_path,
            save_all=True,
            append_images=frames[1:],
            duration=500,  # 500ms per frame
            loop=0
        )
        print(f"\n✓ Created animation: {gif_path}")
    except Exception as e:
        print(f"\nNote: Could not create GIF: {e}")

    print()


def example_compare_before_after():
    """Create side-by-side comparison."""
    print("Example 9: Before/After Comparison")
    print("-" * 40)

    input_path = "modern_map.png"
    if not Path(input_path).exists():
        print(f"Note: {input_path} not found, skipping example")
        return

    img = Image.open(input_path)

    # Age the map
    aged = age_map(img, intensity=0.7, style="1900", seed=42)

    # Create side-by-side comparison
    width, height = img.size
    comparison = Image.new('RGB', (width * 2, height), 'white')

    comparison.paste(img, (0, 0))
    comparison.paste(aged, (width, 0))

    # Add labels
    from PIL import ImageDraw, ImageFont
    draw = ImageDraw.Draw(comparison)

    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 32)
    except:
        font = ImageFont.load_default()

    draw.text((width // 2, 20), "Modern", fill='black', font=font, anchor='mt')
    draw.text((width + width // 2, 20), "1900s", fill='black', font=font, anchor='mt')

    comparison.save("comparison_before_after.png")
    print("✓ Saved comparison_before_after.png")
    print()


def print_help():
    """Print help information."""
    print("=" * 60)
    print("Historical Map Aging Effects - Example Usage")
    print("=" * 60)
    print()
    print("This script demonstrates various use cases for the aging")
    print("effects module. Run individual examples or all of them.")
    print()
    print("Available styles:")
    for style_id, name in get_available_styles().items():
        print(f"  - {style_id}: {name}")
    print()
    print("Basic usage in your own code:")
    print("  from age_effects import age_map")
    print("  aged = age_map(img, intensity=0.6, style='1900', seed=42)")
    print()


def main():
    """Run all examples."""
    print_help()

    examples = [
        example_basic_usage,
        example_different_eras,
        example_intensity_variations,
        example_custom_parameters,
        example_reproducible_results,
        example_batch_processing,
        example_synthetic_dataset_generation,
        example_progressive_aging,
        example_compare_before_after,
    ]

    for example_func in examples:
        try:
            example_func()
        except Exception as e:
            print(f"✗ Error in {example_func.__name__}: {e}")
            print()

    print("=" * 60)
    print("Examples complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
