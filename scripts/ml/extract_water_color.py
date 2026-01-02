#!/usr/bin/env python3
"""
Extract water from historical maps using color-based detection.

Water in historical maps is typically rendered in blue tones.
This script uses HSV color thresholding to detect water areas,
which is simpler and more reliable than ML for consistent map styles.

Usage:
    python scripts/ml/extract_water_color.py --input image.png --output mask.png
    python scripts/ml/extract_water_color.py --input data/tiles/1937/ --output masks/1937/

    # With vectorization
    python scripts/ml/extract_water_color.py --input image.png --output water.geojson --vectorize
"""

import argparse
import json
import sys
from pathlib import Path
from typing import List, Tuple, Optional, Dict

import numpy as np
from PIL import Image

try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False

try:
    from rasterio.features import shapes
    from rasterio.transform import from_bounds
    from shapely.geometry import shape, mapping
    from shapely.ops import unary_union
    HAS_RASTERIO = True
except ImportError:
    HAS_RASTERIO = False


# HSV ranges for water detection in different map types
# HSV: Hue (0-180), Saturation (0-255), Value (0-255)
WATER_COLOR_PROFILES = {
    # Blue water on historical maps (most common)
    'blue': {
        'h_min': 90, 'h_max': 130,   # Blue hues
        's_min': 30, 's_max': 255,   # Some saturation required
        'v_min': 50, 'v_max': 255,   # Not too dark
    },
    # Cyan/teal water (some maps)
    'cyan': {
        'h_min': 80, 'h_max': 100,
        's_min': 40, 's_max': 255,
        'v_min': 80, 'v_max': 255,
    },
    # Light blue water (orthophotos, modern maps)
    'light_blue': {
        'h_min': 95, 'h_max': 115,
        's_min': 20, 's_max': 150,
        'v_min': 150, 'v_max': 255,
    },
    # Dark blue/navy (some historical maps)
    'dark_blue': {
        'h_min': 100, 'h_max': 125,
        's_min': 50, 's_max': 255,
        'v_min': 30, 'v_max': 150,
    },
    # Combined broad range
    'broad': {
        'h_min': 80, 'h_max': 135,
        's_min': 20, 's_max': 255,
        'v_min': 40, 'v_max': 255,
    },
}


def detect_water_hsv(
    image: np.ndarray,
    profile: str = 'broad',
    min_area: int = 100,
    morph_kernel: int = 5
) -> np.ndarray:
    """
    Detect water using HSV color thresholding.

    Args:
        image: RGB image as numpy array (H, W, 3)
        profile: Color profile name from WATER_COLOR_PROFILES
        min_area: Minimum contour area to keep (removes noise)
        morph_kernel: Kernel size for morphological operations

    Returns:
        Binary mask where 255 = water, 0 = not water
    """
    if not HAS_CV2:
        raise ImportError("OpenCV (cv2) required. Install with: pip install opencv-python")

    # Get color profile
    if profile not in WATER_COLOR_PROFILES:
        raise ValueError(f"Unknown profile: {profile}. Available: {list(WATER_COLOR_PROFILES.keys())}")

    p = WATER_COLOR_PROFILES[profile]

    # Convert to HSV
    hsv = cv2.cvtColor(image, cv2.COLOR_RGB2HSV)

    # Create mask for color range
    lower = np.array([p['h_min'], p['s_min'], p['v_min']])
    upper = np.array([p['h_max'], p['s_max'], p['v_max']])
    mask = cv2.inRange(hsv, lower, upper)

    # Morphological cleanup
    kernel = np.ones((morph_kernel, morph_kernel), np.uint8)

    # Close small gaps
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

    # Open to remove noise
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)

    # Remove small components
    if min_area > 0:
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        mask_clean = np.zeros_like(mask)
        for cnt in contours:
            if cv2.contourArea(cnt) >= min_area:
                cv2.drawContours(mask_clean, [cnt], -1, 255, -1)
        mask = mask_clean

    return mask


def detect_water_multi_profile(
    image: np.ndarray,
    profiles: List[str] = None,
    min_area: int = 100
) -> np.ndarray:
    """
    Detect water using multiple color profiles and combine results.

    Args:
        image: RGB image as numpy array
        profiles: List of profile names to try (default: all)
        min_area: Minimum contour area

    Returns:
        Combined binary mask
    """
    if profiles is None:
        profiles = ['blue', 'cyan', 'light_blue']

    combined_mask = np.zeros((image.shape[0], image.shape[1]), dtype=np.uint8)

    for profile in profiles:
        try:
            mask = detect_water_hsv(image, profile=profile, min_area=min_area)
            combined_mask = cv2.bitwise_or(combined_mask, mask)
        except Exception:
            continue

    return combined_mask


def vectorize_mask(
    mask: np.ndarray,
    bounds: Tuple[float, float, float, float] = None,
    simplify_tolerance: float = 0.0001,
    min_area_deg2: float = 1e-8
) -> List[Dict]:
    """
    Convert binary mask to GeoJSON polygons.

    Args:
        mask: Binary mask (255 = water)
        bounds: Geographic bounds (west, south, east, north) or None for pixel coords
        simplify_tolerance: Simplification tolerance in coordinate units
        min_area_deg2: Minimum polygon area to keep

    Returns:
        List of GeoJSON feature dictionaries
    """
    if not HAS_RASTERIO:
        raise ImportError("rasterio and shapely required. Install with: pip install rasterio shapely")

    # Create transform
    if bounds:
        transform = from_bounds(bounds[0], bounds[1], bounds[2], bounds[3],
                                mask.shape[1], mask.shape[0])
    else:
        transform = from_bounds(0, 0, mask.shape[1], mask.shape[0],
                                mask.shape[1], mask.shape[0])

    # Extract shapes
    features = []
    mask_binary = (mask > 0).astype(np.uint8)

    for geom, value in shapes(mask_binary, transform=transform):
        if value == 1:  # Water
            poly = shape(geom)

            # Filter by area
            if poly.area < min_area_deg2:
                continue

            # Simplify
            if simplify_tolerance > 0:
                poly = poly.simplify(simplify_tolerance, preserve_topology=True)

            if poly.is_valid and not poly.is_empty:
                features.append({
                    'type': 'Feature',
                    'properties': {
                        'class': 'water',
                        'src': 'color_detection',
                        'area_deg2': poly.area
                    },
                    'geometry': mapping(poly)
                })

    return features


def process_image(
    input_path: Path,
    output_path: Path,
    profile: str = 'broad',
    vectorize: bool = False,
    bounds: Tuple[float, float, float, float] = None,
    min_area: int = 100
) -> Dict:
    """
    Process a single image for water detection.

    Args:
        input_path: Path to input image
        output_path: Path for output (mask PNG or GeoJSON)
        profile: Color profile to use
        vectorize: If True, output GeoJSON instead of mask
        bounds: Geographic bounds for vectorization
        min_area: Minimum pixel area for detection

    Returns:
        Result dictionary with statistics
    """
    # Load image
    img = Image.open(input_path).convert('RGB')
    img_array = np.array(img)

    # Detect water
    mask = detect_water_hsv(img_array, profile=profile, min_area=min_area)

    # Calculate statistics
    total_pixels = mask.shape[0] * mask.shape[1]
    water_pixels = np.sum(mask > 0)
    water_percent = 100 * water_pixels / total_pixels

    result = {
        'input': str(input_path),
        'output': str(output_path),
        'water_pixels': int(water_pixels),
        'total_pixels': total_pixels,
        'water_percent': round(water_percent, 2)
    }

    # Output
    if vectorize:
        features = vectorize_mask(mask, bounds=bounds)
        output = {
            'type': 'FeatureCollection',
            'features': features,
            'metadata': {
                'source': str(input_path),
                'profile': profile,
                'water_percent': water_percent
            }
        }
        with open(output_path, 'w') as f:
            json.dump(output, f)
        result['feature_count'] = len(features)
    else:
        # Save as mask (class 3 = water in our schema)
        mask_class = np.where(mask > 0, 3, 0).astype(np.uint8)
        Image.fromarray(mask_class).save(output_path)

    return result


def process_directory(
    input_dir: Path,
    output_dir: Path,
    profile: str = 'broad',
    vectorize: bool = False,
    min_area: int = 100
) -> List[Dict]:
    """Process all images in a directory."""
    output_dir.mkdir(parents=True, exist_ok=True)

    results = []
    image_files = list(input_dir.glob('*.png')) + list(input_dir.glob('*.jpg'))

    for i, img_path in enumerate(image_files):
        if vectorize:
            out_path = output_dir / f"{img_path.stem}.geojson"
        else:
            out_path = output_dir / img_path.name

        try:
            result = process_image(img_path, out_path, profile=profile,
                                   vectorize=vectorize, min_area=min_area)
            results.append(result)

            if (i + 1) % 10 == 0:
                print(f"  [{i+1}/{len(image_files)}] Processed {img_path.name}")
        except Exception as e:
            print(f"  Error processing {img_path.name}: {e}")
            results.append({'input': str(img_path), 'error': str(e)})

    return results


def main():
    parser = argparse.ArgumentParser(
        description='Extract water from maps using color detection'
    )
    parser.add_argument(
        '--input', '-i',
        type=Path,
        required=True,
        help='Input image or directory'
    )
    parser.add_argument(
        '--output', '-o',
        type=Path,
        required=True,
        help='Output mask/GeoJSON or directory'
    )
    parser.add_argument(
        '--profile', '-p',
        type=str,
        default='broad',
        choices=list(WATER_COLOR_PROFILES.keys()),
        help=f'Color profile (default: broad)'
    )
    parser.add_argument(
        '--vectorize', '-v',
        action='store_true',
        help='Output GeoJSON instead of mask'
    )
    parser.add_argument(
        '--min-area',
        type=int,
        default=100,
        help='Minimum pixel area for detection (default: 100)'
    )
    parser.add_argument(
        '--bounds',
        type=float,
        nargs=4,
        metavar=('WEST', 'SOUTH', 'EAST', 'NORTH'),
        help='Geographic bounds for vectorization'
    )

    args = parser.parse_args()

    if not HAS_CV2:
        print("Error: OpenCV required. Install with: pip install opencv-python")
        sys.exit(1)

    print(f"Water extraction using color profile: {args.profile}")
    print(f"  Input: {args.input}")
    print(f"  Output: {args.output}")

    bounds = tuple(args.bounds) if args.bounds else None

    if args.input.is_dir():
        results = process_directory(
            args.input, args.output,
            profile=args.profile,
            vectorize=args.vectorize,
            min_area=args.min_area
        )

        # Summary
        successful = [r for r in results if 'error' not in r]
        water_images = [r for r in successful if r.get('water_percent', 0) > 0]

        print(f"\nProcessed {len(results)} images")
        print(f"  Successful: {len(successful)}")
        print(f"  With water: {len(water_images)}")
        if successful:
            avg_water = np.mean([r['water_percent'] for r in successful])
            print(f"  Average water: {avg_water:.2f}%")
    else:
        result = process_image(
            args.input, args.output,
            profile=args.profile,
            vectorize=args.vectorize,
            bounds=bounds,
            min_area=args.min_area
        )
        print(f"\nResult:")
        print(f"  Water: {result['water_percent']:.2f}%")
        if 'feature_count' in result:
            print(f"  Features: {result['feature_count']}")

    print("\nDone!")


if __name__ == '__main__':
    main()
