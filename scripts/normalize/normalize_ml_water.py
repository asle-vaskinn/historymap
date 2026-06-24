#!/usr/bin/env python3
"""
Normalize ML-detected water features to standard water schema.

This script converts raw ML water detections to the normalized water schema:
- Assigns temporal metadata based on map year
- Sets evidence level (low for ML, as it needs verification)
- Infers water type from geometry characteristics
- Generates unique feature IDs

Input: data/sources/ml_water/raw/ml_water.geojson
Output: data/sources/ml_water/normalized/water.geojson

Usage:
    python scripts/normalize/normalize_ml_water.py
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    from shapely.geometry import shape
    from shapely.ops import unary_union
    HAS_SHAPELY = True
except ImportError:
    HAS_SHAPELY = False

# Import base class
try:
    from normalize.base import BaseNormalizer
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from normalize.base import BaseNormalizer


# Water type inference based on geometry
WATER_TYPE_RULES = {
    # Area thresholds in square meters (approximate at 63°N)
    'large_threshold': 100000,  # > 100,000 m² = lake or fjord
    'medium_threshold': 10000,  # > 10,000 m² = lake or harbor
    'small_threshold': 1000,    # > 1,000 m² = pond or canal
    # Elongation threshold (length/width ratio)
    'river_elongation': 5.0,    # Length > 5x width = likely river
}


def estimate_area_m2(geometry: Dict, lat: float = 63.43) -> float:
    """
    Estimate polygon area in square meters.

    Args:
        geometry: GeoJSON geometry
        lat: Latitude for degree-to-meter conversion

    Returns:
        Approximate area in square meters
    """
    if not HAS_SHAPELY:
        return 0

    try:
        geom = shape(geometry)
        # At 63°N: 1° lat ≈ 111km, 1° lon ≈ 50km
        deg_to_m_lat = 111000
        deg_to_m_lon = 50000

        # Get bounds and estimate area
        bounds = geom.bounds
        width_deg = bounds[2] - bounds[0]
        height_deg = bounds[3] - bounds[1]

        width_m = width_deg * deg_to_m_lon
        height_m = height_deg * deg_to_m_lat

        # Use shapely area (in degrees²) and scale
        area_deg2 = geom.area
        area_m2 = area_deg2 * deg_to_m_lat * deg_to_m_lon

        return area_m2
    except Exception:
        return 0


def estimate_elongation(geometry: Dict) -> float:
    """
    Estimate elongation ratio of a polygon.

    Returns:
        Length/width ratio (higher = more elongated)
    """
    if not HAS_SHAPELY:
        return 1.0

    try:
        geom = shape(geometry)
        bounds = geom.bounds
        width = bounds[2] - bounds[0]
        height = bounds[3] - bounds[1]

        if width == 0 or height == 0:
            return 1.0

        return max(width, height) / min(width, height)
    except Exception:
        return 1.0


def infer_water_type(geometry: Dict, area_m2: float) -> str:
    """
    Infer water type from geometry characteristics.

    Args:
        geometry: GeoJSON geometry
        area_m2: Estimated area in square meters

    Returns:
        Water type: fjord, lake, river, harbor, canal, pond, stream
    """
    elongation = estimate_elongation(geometry)

    # Highly elongated = river or stream
    if elongation > WATER_TYPE_RULES['river_elongation']:
        if area_m2 > WATER_TYPE_RULES['medium_threshold']:
            return 'river'
        else:
            return 'stream'

    # Large area = lake or fjord
    if area_m2 > WATER_TYPE_RULES['large_threshold']:
        return 'lake'  # Conservative - manual review may upgrade to fjord

    # Medium area = lake or harbor
    if area_m2 > WATER_TYPE_RULES['medium_threshold']:
        return 'lake'

    # Small area = pond or canal
    if area_m2 > WATER_TYPE_RULES['small_threshold']:
        if elongation > 3.0:
            return 'canal'
        else:
            return 'pond'

    # Very small = pond
    return 'pond'


class MLWaterNormalizer(BaseNormalizer):
    """Normalize ML-detected water features."""

    def __init__(self, data_dir: Optional[Path] = None):
        super().__init__(source_id='ml_water', data_dir=data_dir)
        self.raw_path = self.raw_dir / 'ml_water.geojson'

    def load_raw_data(self) -> Tuple[List[Dict], Dict]:
        """Load raw ML water features."""
        if not self.raw_path.exists():
            print(f"  Warning: Raw file not found: {self.raw_path}")
            return [], {}

        with open(self.raw_path) as f:
            data = json.load(f)

        features = data.get('features', [])
        metadata = data.get('metadata', {})

        print(f"  Loaded {len(features)} raw features")
        return features, metadata

    def normalize_feature(self, feature: Dict, index: int) -> Optional[Dict]:
        """
        Normalize a single ML water feature.

        Args:
            feature: Raw GeoJSON feature
            index: Feature index for ID generation

        Returns:
            Normalized feature or None if invalid
        """
        props = feature.get('properties', {})
        geometry = feature.get('geometry')

        if not geometry:
            return None

        # Get map year from properties
        year = props.get('year')
        if not year:
            # Try to infer from source_file
            source_file = props.get('source_file', '')
            for y in ['1880', '1904', '1937', '1947', '1964', '2006']:
                if y in source_file:
                    year = int(y)
                    break

        if not year:
            year = 1900  # Default fallback

        # Generate unique ID
        src_id = f"ml_{year}_{index:06d}"

        # Estimate area and infer water type
        area_m2 = estimate_area_m2(geometry)
        water_type = infer_water_type(geometry, area_m2)

        # ML confidence if available
        confidence = props.get('confidence', props.get('mlc', 0.5))

        # Evidence level based on confidence
        if confidence >= 0.9:
            evidence = 'm'  # Medium - still needs verification
        else:
            evidence = 'l'  # Low - needs verification

        # Create normalized feature
        normalized_props = {
            '_src': 'ml_water',
            '_src_id': src_id,
            '_ingested': datetime.utcnow().strftime('%Y-%m-%d'),
            'sd': year,  # Start date = map year (water existed by this date)
            'ev': evidence,
            'wtype': water_type,
            'src': 'ml',
        }

        # Add confidence score
        if confidence:
            normalized_props['mlc'] = round(confidence, 2)

        # Add area estimate
        if area_m2 > 0:
            normalized_props['area_m2'] = round(area_m2, 0)

        # Preserve original properties
        normalized_props['_raw'] = props

        return {
            'type': 'Feature',
            'properties': normalized_props,
            'geometry': geometry
        }

    def normalize(self) -> List[Dict]:
        """
        Normalize all ML water features.

        Returns:
            List of normalized GeoJSON features
        """
        features, metadata = self.load_raw_data()

        if not features:
            print("  No features to normalize")
            return []

        normalized = []
        skipped = 0

        for i, feat in enumerate(features):
            norm_feat = self.normalize_feature(feat, i)
            if norm_feat:
                normalized.append(norm_feat)
            else:
                skipped += 1

        if skipped > 0:
            print(f"  Skipped {skipped} invalid features")

        # Group by water type for stats
        by_type = {}
        for feat in normalized:
            wtype = feat['properties'].get('wtype', 'unknown')
            by_type[wtype] = by_type.get(wtype, 0) + 1

        print(f"  By water type: {by_type}")

        return normalized

    def run(self) -> bool:
        """Run normalization and save output."""
        print(f"Normalizing {self.source_id}...")

        try:
            features = self.normalize()

            # Save output (water.geojson, not buildings.geojson)
            output_path = self.normalized_dir / 'water.geojson'
            output = {
                'type': 'FeatureCollection',
                'features': features,
                'metadata': {
                    'source': 'ml_water',
                    'normalized_at': datetime.utcnow().isoformat() + 'Z',
                    'count': len(features)
                }
            }
            with open(output_path, 'w') as f:
                json.dump(output, f)

            # Update manifest
            manifest = self.load_manifest()
            manifest['normalized_at'] = datetime.utcnow().isoformat() + 'Z'
            manifest['normalized_file'] = 'water.geojson'
            manifest['normalized_count'] = len(features)
            self.save_manifest(manifest)

            print(f"  Success: {len(features)} features normalized")
            print(f"  Output: {output_path}")
            return True

        except Exception as e:
            print(f"  Error: {e}")
            import traceback
            traceback.print_exc()
            return False


# Alias for pipeline discovery
Normalizer = MLWaterNormalizer


def main():
    import argparse

    parser = argparse.ArgumentParser(description='Normalize ML water features')
    parser.add_argument(
        '--data-dir', '-d',
        type=Path,
        default=None,
        help='Data directory (default: data/)'
    )

    args = parser.parse_args()

    normalizer = MLWaterNormalizer(data_dir=args.data_dir)
    success = normalizer.run()

    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
