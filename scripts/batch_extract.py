#!/usr/bin/env python3
"""
Batch extraction script for processing all historical map tiles.

Runs inference on all tiles, vectorizes masks, and merges results per era/map series
with temporal attributes for the frontend time slider.

Features:
- Load fine-tuned model
- Process all tiles in data/kartverket/tiles/
- Run inference with progress bar
- Vectorize each mask to GeoJSON
- Merge all GeoJSON files per era/map series
- Add temporal attributes (start_date, end_date)
- Output: data/extracted/trondheim_{era}.geojson

Usage:
    python batch_extract.py --model ../models/checkpoints/finetuned_model.pth \
                           --tiles ../data/kartverket/tiles/ \
                           --output ../data/extracted/

    python batch_extract.py --model ../models/checkpoints/finetuned_model.pth \
                           --tiles ../data/kartverket/tiles/ \
                           --output ../data/extracted/ \
                           --confidence-threshold 0.7 \
                           --simplify 2.0
"""

import argparse
import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from collections import defaultdict

import numpy as np
import torch
from PIL import Image
from tqdm import tqdm
import geojson
from shapely.geometry import shape, mapping
from shapely.ops import unary_union

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent / 'ml'))

from predict import load_model, load_and_preprocess_image, predict
from vectorize import (
    load_mask,
    extract_contours,
    contour_to_polygon,
    pixel_to_geo_coords,
    transform_polygon_to_geo,
    merge_adjacent_polygons,
    CLASS_NAMES,
    CLASS_COLORS
)


def setup_logging(log_dir: str):
    """Configure logging."""
    os.makedirs(log_dir, exist_ok=True)

    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    logger.handlers = []

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_format = logging.Formatter('%(levelname)s: %(message)s')
    console_handler.setFormatter(console_format)
    logger.addHandler(console_handler)

    # File handler
    log_path = os.path.join(log_dir, 'batch_extraction.log')
    file_handler = logging.FileHandler(log_path)
    file_handler.setLevel(logging.DEBUG)
    file_format = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(file_format)
    logger.addHandler(file_handler)

    return logger


def get_device() -> torch.device:
    """Detect and return the best available device."""
    if torch.cuda.is_available():
        device = torch.device("cuda")
        logging.info(f"Using CUDA device: {torch.cuda.get_device_name(0)}")
    elif hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
        device = torch.device("mps")
        logging.info("Using Apple MPS device")
    else:
        device = torch.device("cpu")
        logging.info("Using CPU device")
    return device


def parse_tile_metadata(tile_path: Path) -> Dict:
    """
    Parse metadata from tile filename.

    Expected format: {era}_{series}_{year}_{tile_id}.png
    Example: 1900_cadastral_1905_tile_123.png

    Returns:
        Dict with era, series, year, tile_id, bounds (if available)
    """
    filename = tile_path.stem

    # Try to extract metadata from filename
    # Format: {era}_{series}_{year}_{tile_id}
    parts = filename.split('_')

    metadata = {
        'filename': tile_path.name,
        'era': None,
        'series': None,
        'year': None,
        'tile_id': None,
        'bounds': None
    }

    # Try to parse structured filename
    if len(parts) >= 4:
        metadata['era'] = parts[0]
        metadata['series'] = parts[1]
        # Look for year (4 digits)
        for part in parts:
            if re.match(r'^\d{4}$', part):
                metadata['year'] = int(part)
                break
        # Tile ID is usually the last part or contains 'tile'
        for part in parts:
            if 'tile' in part.lower():
                metadata['tile_id'] = part
                break
        if metadata['tile_id'] is None:
            metadata['tile_id'] = parts[-1]

    # Try to extract year from filename if not found
    if metadata['year'] is None:
        year_match = re.search(r'(\d{4})', filename)
        if year_match:
            metadata['year'] = int(year_match.group(1))

    # Check for accompanying metadata file
    metadata_file = tile_path.parent / f"{tile_path.stem}_metadata.json"
    if metadata_file.exists():
        with open(metadata_file, 'r') as f:
            file_metadata = json.load(f)
            metadata.update(file_metadata)

    return metadata


def vectorize_tile_mask(
    mask: np.ndarray,
    metadata: Dict,
    simplify_tolerance: float = 1.0,
    min_area: float = 10.0
) -> List[geojson.Feature]:
    """
    Vectorize a single tile mask to GeoJSON features.

    Args:
        mask: Predicted segmentation mask (H, W)
        metadata: Tile metadata including bounds
        simplify_tolerance: Polygon simplification tolerance
        min_area: Minimum polygon area

    Returns:
        List of GeoJSON features
    """
    features = []
    mask_shape = mask.shape
    bounds = metadata.get('bounds')

    # Process each class (skip background class 0)
    for class_id in range(1, 5):
        class_name = CLASS_NAMES.get(class_id, f'class_{class_id}')

        # Extract contours for this class
        contours = extract_contours(mask, class_id)

        if not contours:
            continue

        # Convert contours to polygons
        polygons = []
        for contour in contours:
            polygon = contour_to_polygon(contour, min_area=min_area)
            if polygon is not None:
                polygons.append(polygon)

        if not polygons:
            continue

        # Merge adjacent polygons
        polygons = merge_adjacent_polygons(polygons)

        # Simplify polygons
        if simplify_tolerance > 0:
            from shapely import simplify as shapely_simplify
            polygons = [shapely_simplify(p, tolerance=simplify_tolerance, preserve_topology=True)
                       for p in polygons]
            polygons = [p for p in polygons if p.is_valid and p.area >= min_area]

        # Transform to geographic coordinates if bounds available
        if bounds is not None:
            polygons = [transform_polygon_to_geo(p, mask_shape, bounds) for p in polygons]

        # Create GeoJSON features
        for i, polygon in enumerate(polygons):
            properties = {
                'class': class_name,
                'class_id': int(class_id),
                'feature_id': f'{metadata["tile_id"]}_{class_name}_{i}',
                'area': float(polygon.area),
                'source_tile': metadata['filename'],
                'era': metadata.get('era'),
                'series': metadata.get('series'),
                'year': metadata.get('year'),
            }

            # Add temporal attributes for time slider
            if metadata.get('year'):
                properties['start_date'] = metadata['year']
                # For historical features, end_date could be:
                # - null (if feature still exists today)
                # - start_date (if we don't know when it disappeared)
                # - specific year (if we have information about when it was demolished)
                properties['end_date'] = metadata['year']  # Default: same as start

            # Add color for styling
            if class_id in CLASS_COLORS and CLASS_COLORS[class_id]:
                properties['color'] = CLASS_COLORS[class_id]

            feature = geojson.Feature(
                geometry=mapping(polygon),
                properties=properties
            )
            features.append(feature)

    return features


def process_tile(
    tile_path: Path,
    model: torch.nn.Module,
    device: torch.device,
    confidence_threshold: Optional[float],
    simplify_tolerance: float,
    min_area: float
) -> Tuple[List[geojson.Feature], Dict]:
    """
    Process a single tile: inference + vectorization.

    Returns:
        Tuple of (features, metadata)
    """
    # Parse metadata
    metadata = parse_tile_metadata(tile_path)

    # Load and preprocess image
    image_tensor, original_size = load_and_preprocess_image(str(tile_path), target_size=None)

    # Run inference
    predicted_mask, probability_map = predict(
        model, image_tensor, device, confidence_threshold
    )

    # Vectorize mask
    features = vectorize_tile_mask(
        predicted_mask,
        metadata,
        simplify_tolerance=simplify_tolerance,
        min_area=min_area
    )

    return features, metadata


def merge_features_by_era(
    all_features: List[Tuple[List[geojson.Feature], Dict]],
    group_by: str = 'era'
) -> Dict[str, geojson.FeatureCollection]:
    """
    Merge features by era/series into separate GeoJSON files.

    Args:
        all_features: List of (features, metadata) tuples
        group_by: How to group features ('era', 'series', 'year')

    Returns:
        Dict mapping group name to FeatureCollection
    """
    grouped = defaultdict(list)

    # Group features
    for features, metadata in all_features:
        group_key = metadata.get(group_by, 'unknown')
        if group_key is None:
            group_key = 'unknown'
        grouped[str(group_key)].extend(features)

    # Create FeatureCollections
    feature_collections = {}

    for group_name, features in grouped.items():
        # Calculate statistics
        class_counts = defaultdict(int)
        years = []

        for feature in features:
            class_counts[feature['properties']['class']] += 1
            year = feature['properties'].get('year')
            if year:
                years.append(year)

        # Create FeatureCollection
        feature_collection = geojson.FeatureCollection(features)

        # Add metadata
        feature_collection['metadata'] = {
            'group': group_name,
            'group_by': group_by,
            'feature_count': len(features),
            'class_counts': dict(class_counts),
            'year_range': [min(years), max(years)] if years else None,
            'generated_at': datetime.now().isoformat(),
        }

        feature_collections[group_name] = feature_collection

    return feature_collections


def save_feature_collections(
    feature_collections: Dict[str, geojson.FeatureCollection],
    output_dir: Path,
    prefix: str = 'trondheim'
):
    """Save feature collections to GeoJSON files."""
    output_dir.mkdir(parents=True, exist_ok=True)

    for group_name, feature_collection in feature_collections.items():
        # Sanitize group name for filename
        safe_name = re.sub(r'[^\w\-]', '_', str(group_name))
        output_file = output_dir / f"{prefix}_{safe_name}.geojson"

        with open(output_file, 'w') as f:
            json.dump(feature_collection, f, indent=2)

        logging.info(f"Saved {len(feature_collection['features'])} features to {output_file}")


def calculate_extraction_stats(
    feature_collections: Dict[str, geojson.FeatureCollection]
) -> Dict:
    """Calculate statistics about extracted features."""
    total_features = 0
    total_by_class = defaultdict(int)
    groups = []

    for group_name, fc in feature_collections.items():
        metadata = fc['metadata']
        total_features += metadata['feature_count']

        for class_name, count in metadata['class_counts'].items():
            total_by_class[class_name] += count

        groups.append({
            'name': group_name,
            'features': metadata['feature_count'],
            'classes': metadata['class_counts']
        })

    return {
        'total_features': total_features,
        'total_by_class': dict(total_by_class),
        'groups': groups
    }


def batch_extract(
    model_checkpoint: str,
    tiles_dir: str,
    output_dir: str,
    confidence_threshold: Optional[float] = None,
    simplify_tolerance: float = 1.0,
    min_area: float = 10.0,
    group_by: str = 'era',
    prefix: str = 'trondheim'
):
    """
    Main batch extraction function.

    Args:
        model_checkpoint: Path to fine-tuned model checkpoint
        tiles_dir: Directory containing tile images
        output_dir: Directory for output GeoJSON files
        confidence_threshold: Minimum confidence for predictions
        simplify_tolerance: Polygon simplification tolerance
        min_area: Minimum polygon area
        group_by: How to group features ('era', 'series', 'year')
        prefix: Prefix for output filenames
    """
    # Setup
    log_dir = Path(output_dir) / 'logs'
    logger = setup_logging(log_dir)

    logger.info("=" * 80)
    logger.info("Starting batch extraction")
    logger.info("=" * 80)
    logger.info(f"Model checkpoint: {model_checkpoint}")
    logger.info(f"Tiles directory: {tiles_dir}")
    logger.info(f"Output directory: {output_dir}")
    logger.info(f"Confidence threshold: {confidence_threshold}")
    logger.info(f"Simplify tolerance: {simplify_tolerance}")
    logger.info(f"Minimum area: {min_area}")
    logger.info(f"Group by: {group_by}")

    # Load model
    device = get_device()
    logger.info(f"Loading model from {model_checkpoint}")
    model = load_model(model_checkpoint, device, num_classes=5)

    # Find all tile images
    tiles_path = Path(tiles_dir)
    tile_files = []
    for ext in ['.png', '.jpg', '.jpeg', '.tif', '.tiff']:
        tile_files.extend(tiles_path.glob(f'**/*{ext}'))

    if not tile_files:
        logger.error(f"No tile images found in {tiles_dir}")
        return

    logger.info(f"Found {len(tile_files)} tiles to process")

    # Process all tiles
    all_features = []
    failed_tiles = []

    for tile_path in tqdm(tile_files, desc="Processing tiles"):
        try:
            features, metadata = process_tile(
                tile_path,
                model,
                device,
                confidence_threshold,
                simplify_tolerance,
                min_area
            )
            all_features.append((features, metadata))

            if len(features) > 0:
                logger.debug(f"Extracted {len(features)} features from {tile_path.name}")
            else:
                logger.debug(f"No features extracted from {tile_path.name}")

        except Exception as e:
            logger.error(f"Error processing {tile_path.name}: {e}")
            failed_tiles.append(tile_path.name)
            continue

    # Merge features by era/series
    logger.info("\nMerging features by era/series...")
    feature_collections = merge_features_by_era(all_features, group_by=group_by)

    # Save results
    logger.info("\nSaving GeoJSON files...")
    save_feature_collections(feature_collections, Path(output_dir), prefix=prefix)

    # Calculate and report statistics
    logger.info("\n" + "=" * 80)
    logger.info("Extraction completed!")
    logger.info("=" * 80)

    stats = calculate_extraction_stats(feature_collections)

    logger.info(f"\nOverall Statistics:")
    logger.info(f"  Total tiles processed: {len(tile_files)}")
    logger.info(f"  Successful: {len(tile_files) - len(failed_tiles)}")
    logger.info(f"  Failed: {len(failed_tiles)}")
    logger.info(f"  Total features extracted: {stats['total_features']}")

    logger.info(f"\nFeatures by class:")
    for class_name, count in stats['total_by_class'].items():
        logger.info(f"  {class_name}: {count}")

    logger.info(f"\nFeatures by {group_by}:")
    for group in stats['groups']:
        logger.info(f"  {group['name']}: {group['features']} features")

    if failed_tiles:
        logger.warning(f"\nFailed tiles ({len(failed_tiles)}):")
        for tile_name in failed_tiles[:10]:
            logger.warning(f"  - {tile_name}")
        if len(failed_tiles) > 10:
            logger.warning(f"  ... and {len(failed_tiles) - 10} more")

    # Save statistics
    stats_file = Path(output_dir) / 'extraction_stats.json'
    with open(stats_file, 'w') as f:
        json.dump(stats, f, indent=2)
    logger.info(f"\nStatistics saved to {stats_file}")


def main():
    parser = argparse.ArgumentParser(
        description='Batch extract features from all historical map tiles',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )

    # Required arguments
    parser.add_argument('--model', required=True,
                       help='Path to fine-tuned model checkpoint')
    parser.add_argument('--tiles', required=True,
                       help='Directory containing tile images')
    parser.add_argument('--output', required=True,
                       help='Directory for output GeoJSON files')

    # Processing arguments
    parser.add_argument('--confidence-threshold', type=float, default=None,
                       help='Minimum confidence for predictions (0-1)')
    parser.add_argument('--simplify', type=float, default=1.0,
                       help='Polygon simplification tolerance')
    parser.add_argument('--min-area', type=float, default=10.0,
                       help='Minimum polygon area')

    # Grouping arguments
    parser.add_argument('--group-by', type=str, default='era',
                       choices=['era', 'series', 'year'],
                       help='How to group output files')
    parser.add_argument('--prefix', type=str, default='trondheim',
                       help='Prefix for output filenames')

    args = parser.parse_args()

    # Run batch extraction
    batch_extract(
        model_checkpoint=args.model,
        tiles_dir=args.tiles,
        output_dir=args.output,
        confidence_threshold=args.confidence_threshold,
        simplify_tolerance=args.simplify,
        min_area=args.min_area,
        group_by=args.group_by,
        prefix=args.prefix
    )


if __name__ == '__main__':
    main()
