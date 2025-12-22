#!/usr/bin/env python3
"""
Extract features from historical maps using color-based segmentation.

This approach works well for maps with distinct colored features like:
- Red buildings (public/important)
- Yellow buildings (residential)
- Blue water
- Green parks/forests

Usage:
    python extract_by_color.py --input map.jpg --output results/
"""

import argparse
import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image


# Color ranges in HSV space for the 1904 Trondheim map
# HSV: Hue (0-180), Saturation (0-255), Value (0-255)
# Key insight: Buildings have HIGHER saturation than the paper background
COLOR_RANGES = {
    'building_red': {
        # Bright red/orange buildings - very high saturation
        'lower': np.array([0, 120, 150]),
        'upper': np.array([15, 255, 255]),
        'lower2': np.array([165, 120, 150]),  # Red wraps around
        'upper2': np.array([180, 255, 255]),
        'class_id': 1,
        'name': 'building'
    },
    'building_yellow': {
        # Yellow/tan buildings - higher saturation than paper (S > 75)
        # Paper is S=43-65, V=217-255
        # Buildings are S=70-110, V=150-220
        'lower': np.array([12, 75, 100]),
        'upper': np.array([30, 180, 220]),
        'class_id': 1,
        'name': 'building'
    },
    'water': {
        # The fjord appears as light blue-green in this map
        'lower': np.array([70, 20, 150]),
        'upper': np.array([110, 100, 255]),
        'class_id': 3,
        'name': 'water'
    },
    'park_green': {
        # Parks and gardens - distinct green
        'lower': np.array([35, 50, 80]),
        'upper': np.array([75, 200, 200]),
        'class_id': 4,
        'name': 'forest'
    }
}

CLASS_COLORS = {
    0: (240, 235, 224),  # background
    1: (212, 163, 115),  # building
    2: (139, 119, 101),  # road
    3: (74, 144, 226),   # water
    4: (76, 153, 0),     # forest
}

CLASS_NAMES = ['background', 'building', 'road', 'water', 'forest']


def extract_color_mask(image_bgr: np.ndarray, color_name: str) -> np.ndarray:
    """Extract mask for a specific color range."""
    hsv = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV)

    color_def = COLOR_RANGES[color_name]
    mask = cv2.inRange(hsv, color_def['lower'], color_def['upper'])

    # Handle red which wraps around in HSV
    if 'lower2' in color_def:
        mask2 = cv2.inRange(hsv, color_def['lower2'], color_def['upper2'])
        mask = cv2.bitwise_or(mask, mask2)

    return mask


def clean_mask(mask: np.ndarray, min_area: int = 100, kernel_size: int = 3) -> np.ndarray:
    """Clean up mask with morphological operations."""
    kernel = np.ones((kernel_size, kernel_size), np.uint8)

    # Close small gaps
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

    # Remove small noise
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)

    # Remove small connected components
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)

    cleaned = np.zeros_like(mask)
    for i in range(1, num_labels):
        if stats[i, cv2.CC_STAT_AREA] >= min_area:
            cleaned[labels == i] = 255

    return cleaned


def extract_all_features(image_path: str, output_dir: str, min_area: int = 100):
    """Extract all color-based features from a map image."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load image
    print(f"Loading {image_path}...")
    image_bgr = cv2.imread(image_path)
    if image_bgr is None:
        raise ValueError(f"Could not load image: {image_path}")

    height, width = image_bgr.shape[:2]
    print(f"Image size: {width}x{height}")

    # Create combined mask
    combined_mask = np.zeros((height, width), dtype=np.uint8)

    # Extract each color
    for color_name, color_def in COLOR_RANGES.items():
        print(f"Extracting {color_name}...")
        mask = extract_color_mask(image_bgr, color_name)
        mask = clean_mask(mask, min_area=min_area)

        # Count pixels
        pixel_count = np.sum(mask > 0)
        pct = pixel_count / (height * width) * 100
        print(f"  Found {pixel_count:,} pixels ({pct:.2f}%)")

        # Add to combined mask (using class_id)
        class_id = color_def['class_id']
        combined_mask[mask > 0] = class_id

    # Save outputs
    input_name = Path(image_path).stem

    # Raw mask
    mask_path = output_dir / f"{input_name}_color_mask.png"
    Image.fromarray(combined_mask, mode='L').save(mask_path)
    print(f"Saved mask to {mask_path}")

    # Colorized visualization
    colorized = np.zeros((height, width, 3), dtype=np.uint8)
    for class_id, color in CLASS_COLORS.items():
        colorized[combined_mask == class_id] = color

    color_path = output_dir / f"{input_name}_color_colorized.png"
    Image.fromarray(colorized).save(color_path)
    print(f"Saved colorized to {color_path}")

    # Overlay
    image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
    overlay = (image_rgb * 0.5 + colorized * 0.5).astype(np.uint8)
    overlay_path = output_dir / f"{input_name}_color_overlay.png"
    Image.fromarray(overlay).save(overlay_path)
    print(f"Saved overlay to {overlay_path}")

    # Print stats
    print("\nClass distribution:")
    unique, counts = np.unique(combined_mask, return_counts=True)
    total = combined_mask.size
    for class_id, count in zip(unique, counts):
        pct = count / total * 100
        print(f"  {CLASS_NAMES[class_id]:12s}: {pct:5.1f}% ({count:,} pixels)")

    return combined_mask, mask_path


def main():
    parser = argparse.ArgumentParser(description='Extract features by color')
    parser.add_argument('--input', '-i', required=True, help='Input map image')
    parser.add_argument('--output', '-o', required=True, help='Output directory')
    parser.add_argument('--min-area', type=int, default=100,
                       help='Minimum feature area in pixels (default: 100)')
    args = parser.parse_args()

    extract_all_features(args.input, args.output, args.min_area)
    print("\nDone!")


if __name__ == '__main__':
    main()
