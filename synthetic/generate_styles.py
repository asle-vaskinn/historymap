#!/usr/bin/env python3
"""
Generate MapLibre GL style variations for historical Norwegian maps.

This script can create new style variations by randomizing colors within
period-appropriate palettes, allowing for domain randomization in ML training.
"""

import json
import random
import colorsys
from pathlib import Path
from typing import Dict, List, Tuple, Any
import argparse


# Period-appropriate color palettes (RGB values)
COLOR_PALETTES = {
    "military_1880": {
        "background": [(232, 224, 208), (225, 218, 200), (238, 228, 210)],
        "water": [(95, 122, 138), (85, 110, 125), (105, 132, 148)],
        "forest": [(168, 195, 160), (158, 185, 150), (178, 205, 170)],
        "grass": [(200, 212, 184), (190, 202, 174), (210, 222, 194)],
        "building": [(61, 53, 48), (51, 43, 38), (71, 63, 58)],
        "road_primary": [(122, 101, 66), (112, 91, 56), (132, 111, 76)],
        "road_secondary": [(148, 128, 90), (138, 118, 80), (158, 138, 100)],
    },
    "cadastral_1900": {
        "background": [(250, 248, 245), (245, 243, 238), (252, 250, 247)],
        "water": [(197, 227, 240), (187, 217, 230), (207, 237, 250)],
        "forest": [(232, 240, 232), (222, 230, 222), (242, 250, 242)],
        "grass": [(240, 245, 232), (230, 235, 222), (250, 255, 242)],
        "building": [(230, 184, 184), (220, 174, 174), (240, 194, 194)],
        "building_outline": [(176, 128, 128), (166, 118, 118), (186, 138, 138)],
        "road": [(58, 58, 58), (48, 48, 48), (68, 68, 68)],
    },
    "topographic_1920": {
        "background": [(245, 243, 237), (240, 238, 230), (248, 246, 240)],
        "water": [(184, 217, 232), (174, 207, 222), (194, 227, 242)],
        "forest": [(213, 229, 200), (203, 219, 190), (223, 239, 210)],
        "grass": [(224, 234, 213), (214, 224, 203), (234, 244, 223)],
        "building": [(216, 208, 192), (206, 198, 182), (226, 218, 202)],
        "building_outline": [(42, 37, 32), (32, 27, 22), (52, 47, 42)],
        "road_primary": [(200, 64, 48), (190, 54, 38), (210, 74, 58)],
        "road_secondary": [(26, 21, 16), (16, 11, 6), (36, 31, 26)],
    },
}


def rgb_to_hex(rgb: Tuple[int, int, int]) -> str:
    """Convert RGB tuple to hex color string."""
    return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"


def vary_color(rgb: Tuple[int, int, int], variation: float = 0.1) -> str:
    """
    Vary a color slightly by adjusting HSV values.

    Args:
        rgb: RGB color tuple (0-255)
        variation: Maximum variation factor (0.0-1.0)

    Returns:
        Hex color string
    """
    # Convert to HSV
    r, g, b = [x / 255.0 for x in rgb]
    h, s, v = colorsys.rgb_to_hsv(r, g, b)

    # Vary hue, saturation, and value
    h = (h + random.uniform(-variation * 0.1, variation * 0.1)) % 1.0
    s = max(0, min(1, s + random.uniform(-variation * 0.3, variation * 0.3)))
    v = max(0, min(1, v + random.uniform(-variation * 0.15, variation * 0.15)))

    # Convert back to RGB
    r, g, b = colorsys.hsv_to_rgb(h, s, v)
    rgb_out = (int(r * 255), int(g * 255), int(b * 255))

    return rgb_to_hex(rgb_out)


def pick_color(colors: List[Tuple[int, int, int]], variation: float = 0.1) -> str:
    """
    Pick a random color from a list and optionally vary it.

    Args:
        colors: List of RGB color tuples
        variation: Variation factor to apply

    Returns:
        Hex color string
    """
    base_color = random.choice(colors)
    if variation > 0:
        return vary_color(base_color, variation)
    else:
        return rgb_to_hex(base_color)


def update_layer_colors(layer: Dict[str, Any], color_map: Dict[str, str]) -> None:
    """
    Update colors in a layer definition based on color_map.

    Args:
        layer: MapLibre layer definition
        color_map: Mapping of color keys to hex values
    """
    if "paint" not in layer:
        return

    paint = layer["paint"]

    # Update fill colors
    if "fill-color" in paint and isinstance(paint["fill-color"], str):
        for key, color in color_map.items():
            if key in layer.get("id", ""):
                paint["fill-color"] = color
                break

    # Update line colors
    if "line-color" in paint and isinstance(paint["line-color"], str):
        for key, color in color_map.items():
            if key in layer.get("id", ""):
                paint["line-color"] = color
                break

    # Update background colors
    if "background-color" in paint:
        if "background" in color_map:
            paint["background-color"] = color_map["background"]


def generate_style_variation(
    base_style_path: Path,
    output_path: Path,
    palette_name: str,
    variation: float = 0.1,
    seed: int = None
) -> None:
    """
    Generate a color variation of a base style.

    Args:
        base_style_path: Path to base style JSON
        output_path: Path to save generated style
        palette_name: Name of color palette to use
        variation: Color variation factor (0.0-1.0)
        seed: Random seed for reproducibility
    """
    if seed is not None:
        random.seed(seed)

    # Load base style
    with open(base_style_path, 'r') as f:
        style = json.load(f)

    # Get color palette
    if palette_name not in COLOR_PALETTES:
        raise ValueError(f"Unknown palette: {palette_name}")

    palette = COLOR_PALETTES[palette_name]

    # Generate color variations
    color_map = {
        key: pick_color(colors, variation)
        for key, colors in palette.items()
    }

    # Update style metadata
    style["name"] = f"{style['name']} - Variation"
    if "metadata" not in style:
        style["metadata"] = {}
    style["metadata"]["variation_seed"] = seed if seed is not None else "random"
    style["metadata"]["variation_factor"] = variation

    # Update all layer colors
    for layer in style.get("layers", []):
        update_layer_colors(layer, color_map)

        # Update specific layer colors based on layer ID
        layer_id = layer.get("id", "")
        paint = layer.get("paint", {})

        if "background" in layer_id and "background" in color_map:
            if "background-color" in paint:
                paint["background-color"] = color_map["background"]

        elif "water" in layer_id and "water" in color_map:
            if "fill-color" in paint:
                paint["fill-color"] = color_map["water"]
            if "line-color" in paint:
                paint["line-color"] = vary_color(
                    random.choice(palette["water"]), variation * 1.5
                )

        elif "forest" in layer_id and "forest" in color_map:
            if "fill-color" in paint:
                paint["fill-color"] = color_map["forest"]

        elif "grass" in layer_id and "grass" in color_map:
            if "fill-color" in paint:
                paint["fill-color"] = color_map["grass"]

        elif "building" in layer_id:
            if "fill-color" in paint and "building" in color_map:
                paint["fill-color"] = color_map["building"]
            if "line-color" in paint and "building_outline" in color_map:
                paint["line-color"] = color_map["building_outline"]

        elif "road" in layer_id:
            if "primary" in layer_id and "road_primary" in color_map:
                if "line-color" in paint:
                    paint["line-color"] = color_map["road_primary"]
            elif "secondary" in layer_id and "road_secondary" in color_map:
                if "line-color" in paint:
                    paint["line-color"] = color_map["road_secondary"]
            elif "road" in color_map:
                if "line-color" in paint:
                    paint["line-color"] = color_map["road"]

    # Save generated style
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(style, f, indent=2)

    print(f"Generated style variation: {output_path}")


def generate_batch_variations(
    base_style_path: Path,
    output_dir: Path,
    palette_name: str,
    count: int = 10,
    variation: float = 0.1
) -> List[Path]:
    """
    Generate multiple style variations.

    Args:
        base_style_path: Path to base style JSON
        output_dir: Directory to save generated styles
        palette_name: Name of color palette to use
        count: Number of variations to generate
        variation: Color variation factor

    Returns:
        List of generated style file paths
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    base_name = base_style_path.stem
    generated_paths = []

    for i in range(count):
        output_path = output_dir / f"{base_name}_var{i:03d}.json"
        generate_style_variation(
            base_style_path,
            output_path,
            palette_name,
            variation=variation,
            seed=42 + i  # Reproducible variations
        )
        generated_paths.append(output_path)

    return generated_paths


def create_palette_reference(output_path: Path) -> None:
    """
    Create a JSON reference file showing all available color palettes.

    Args:
        output_path: Path to save palette reference
    """
    palette_ref = {
        name: {
            color_name: [rgb_to_hex(rgb) for rgb in colors]
            for color_name, colors in palette.items()
        }
        for name, palette in COLOR_PALETTES.items()
    }

    with open(output_path, 'w') as f:
        json.dump(palette_ref, f, indent=2)

    print(f"Created palette reference: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Generate MapLibre style variations for historical maps"
    )
    parser.add_argument(
        "base_style",
        type=Path,
        nargs='?',
        help="Path to base style JSON file"
    )
    parser.add_argument(
        "-o", "--output",
        type=Path,
        help="Output path for single variation (default: auto-generated)"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Output directory for batch generation"
    )
    parser.add_argument(
        "-p", "--palette",
        choices=list(COLOR_PALETTES.keys()),
        help="Color palette to use"
    )
    parser.add_argument(
        "-v", "--variation",
        type=float,
        default=0.1,
        help="Color variation factor (0.0-1.0, default: 0.1)"
    )
    parser.add_argument(
        "-c", "--count",
        type=int,
        default=10,
        help="Number of variations to generate in batch mode (default: 10)"
    )
    parser.add_argument(
        "-s", "--seed",
        type=int,
        help="Random seed for reproducibility"
    )
    parser.add_argument(
        "--palette-reference",
        action="store_true",
        help="Generate palette reference file and exit"
    )

    args = parser.parse_args()

    # Generate palette reference
    if args.palette_reference:
        output_path = Path("palette_reference.json")
        create_palette_reference(output_path)
        return 0

    # Validate required arguments
    if not args.base_style:
        print("Error: base_style is required (unless using --palette-reference)")
        return 1

    if not args.palette:
        print("Error: --palette is required")
        return 1

    # Validate base style exists
    if not args.base_style.exists():
        print(f"Error: Base style not found: {args.base_style}")
        return 1

    # Batch generation
    if args.output_dir:
        generated = generate_batch_variations(
            args.base_style,
            args.output_dir,
            args.palette,
            count=args.count,
            variation=args.variation
        )
        print(f"\nGenerated {len(generated)} style variations in {args.output_dir}")
        return 0

    # Single variation
    if args.output:
        output_path = args.output
    else:
        base_name = args.base_style.stem
        output_path = args.base_style.parent / f"{base_name}_variation.json"

    generate_style_variation(
        args.base_style,
        output_path,
        args.palette,
        variation=args.variation,
        seed=args.seed
    )

    return 0


if __name__ == "__main__":
    exit(main())
