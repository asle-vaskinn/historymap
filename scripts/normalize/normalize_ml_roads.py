#!/usr/bin/env python3
"""
ML-detected road data normalization.

Converts ML-extracted road centerlines from historical maps to normalized GeoJSON schema.
Roads are extracted as class_id=2 by the ML pipeline (ml/vectorize.py).
"""

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base_road import BaseRoadNormalizer


def parse_map_date_from_source_id(source_id: str) -> Optional[int]:
    """
    Parse map date from source ID.

    Examples:
        'ml_kartverket_1880' -> 1880
        'ml_aerial_1947' -> 1947
        'ml_kv1904' -> 1904
    """
    match = re.search(r'(\d{4})', source_id)
    if match:
        return int(match.group(1))
    return None


def parse_map_source_code(source_id: str) -> str:
    """
    Extract map source code from source ID.

    Examples:
        'ml_kartverket_1880' -> 'kv1880'
        'ml_aerial_1947' -> 'air1947'
    """
    if 'kartverket' in source_id.lower():
        year = parse_map_date_from_source_id(source_id)
        return f'kv{year}' if year else 'kv_unknown'
    elif 'aerial' in source_id.lower() or 'air' in source_id.lower():
        year = parse_map_date_from_source_id(source_id)
        return f'air{year}' if year else 'air_unknown'
    else:
        year = parse_map_date_from_source_id(source_id)
        return f'map{year}' if year else 'map_unknown'


def confidence_to_evidence_level(confidence: float) -> str:
    """Map ML confidence score to evidence level."""
    if confidence >= 0.9:
        return 'h'
    elif confidence >= 0.7:
        return 'm'
    else:
        return 'l'


class Normalizer(BaseRoadNormalizer):
    """ML-detected road data normalizer."""

    # Road class ID from ML model
    ROAD_CLASS_ID = 2

    def __init__(self, source_id: str = 'ml_detected', map_source: Optional[str] = None, **kwargs):
        """
        Initialize ML road normalizer.

        Args:
            source_id: Source directory name (e.g., 'ml_kartverket_1880')
            map_source: Optional specific map source subdirectory
        """
        if map_source:
            source_id = f'ml_detected/{map_source}'

        super().__init__(source_id, **kwargs)
        self.map_source = map_source or source_id

    def normalize(self) -> List[Dict]:
        """Normalize ML-detected roads to common schema."""

        # Load manifest to get map date and metadata
        manifest = self.load_manifest()

        # Get reference year from manifest (date of the source map)
        reference_year = None
        if 'coverage' in manifest and 'temporal' in manifest['coverage']:
            reference_year = manifest['coverage']['temporal'].get('reference_year')

        # If no reference year in manifest, try to parse from source_id
        if reference_year is None:
            reference_year = parse_map_date_from_source_id(self.source_id)

        # Get map source code for ml_src field
        ml_src_code = parse_map_source_code(self.source_id)

        # Get confidence threshold from manifest if available
        confidence_threshold = 0.5
        if 'ml_model' in manifest and 'confidence_threshold' in manifest['ml_model']:
            confidence_threshold = manifest['ml_model']['confidence_threshold']

        # Find raw GeoJSON files - look for roads.geojson or roads/*.geojson
        raw_files = []

        # Check for roads subdirectory
        roads_dir = self.raw_dir / 'roads'
        if roads_dir.exists():
            raw_files.extend(roads_dir.glob('*.geojson'))

        # Check for roads.geojson in raw directory
        roads_file = self.raw_dir / 'roads.geojson'
        if roads_file.exists():
            raw_files.append(roads_file)

        # Also check all geojson files for road features
        if not raw_files:
            raw_files = list(self.raw_dir.glob('*.geojson'))

        if not raw_files:
            print(f"  Warning: No GeoJSON files found in {self.raw_dir}")
            return []

        print(f"  Processing {len(raw_files)} GeoJSON file(s) for roads")

        features = []

        for raw_file in raw_files:
            with open(raw_file) as f:
                data = json.load(f)

            # Handle both FeatureCollection and single features
            if data.get('type') == 'FeatureCollection':
                raw_features = data.get('features', [])
            elif data.get('type') == 'Feature':
                raw_features = [data]
            else:
                print(f"  Warning: Unrecognized GeoJSON type in {raw_file.name}")
                continue

            for feat in raw_features:
                props = feat.get('properties', {})
                geometry = feat.get('geometry')

                if not geometry:
                    continue

                # Only process roads (class_id == 2 or class == 'road')
                class_id = props.get('class_id')
                class_name = props.get('class', '').lower()

                if class_id != self.ROAD_CLASS_ID and class_name != 'road':
                    continue

                # Only process LineString or MultiLineString geometries
                if geometry.get('type') not in ('LineString', 'MultiLineString'):
                    continue

                # Extract confidence score
                confidence = props.get('confidence', confidence_threshold)

                # Map confidence to evidence level
                ev = confidence_to_evidence_level(confidence)

                # Generate source-specific ID
                feature_id = props.get('feature_id', props.get('id', f'road_{len(features)}'))
                src_id = f"{ml_src_code}_road_{feature_id}"

                # Create normalized feature
                feature = self.create_normalized_road_feature(
                    src_id=src_id,
                    geometry=geometry,
                    sd=reference_year,  # Road existed by this date
                    ed=None,  # No end date for ML detections
                    ev=ev,
                    nm=None,  # ML detections don't have names
                    rt='historical',  # Mark as historical road
                    length=self.calculate_length(geometry),
                    raw_props={
                        'ml_confidence': confidence,
                        'ml_src': ml_src_code,
                        'class_id': class_id,
                        'class_name': class_name,
                        'feature_id': feature_id,
                        'source_file': raw_file.name,
                    }
                )

                # Add ML-specific fields directly to properties
                feature['properties']['mlc'] = confidence
                feature['properties']['ml_src'] = ml_src_code

                features.append(feature)

        print(f"  Found {len(features)} road features")

        return features


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description='Normalize ML-detected road data',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Normalize specific map source
  python normalize_ml_roads.py --map-source kartverket_1880

  # Normalize all ML-detected sources
  python normalize_ml_roads.py --all
        """
    )

    parser.add_argument(
        '--map-source',
        help='Specific map source subdirectory (e.g., kartverket_1880, aerial_1947)'
    )

    parser.add_argument(
        '--all',
        action='store_true',
        help='Normalize all ML-detected sources in ml_detected directory'
    )

    parser.add_argument(
        '--data-dir',
        type=Path,
        help='Override data directory path (default: ../../data relative to script)'
    )

    args = parser.parse_args()

    if not args.map_source and not args.all:
        parser.error("Must specify either --map-source or --all")

    # Get data directory
    data_dir = args.data_dir
    if data_dir is None:
        data_dir = Path(__file__).parent.parent.parent / 'data'

    # Find all map sources if --all specified
    if args.all:
        ml_detected_dir = data_dir / 'sources' / 'ml_detected'

        if not ml_detected_dir.exists():
            print(f"Error: ML detected directory not found: {ml_detected_dir}")
            return 1

        # Find subdirectories with manifest.json
        map_sources = [
            d.name for d in ml_detected_dir.iterdir()
            if d.is_dir() and (d / 'manifest.json').exists()
        ]

        if not map_sources:
            print(f"No ML-detected map sources found in {ml_detected_dir}")
            return 1

        print(f"Found {len(map_sources)} ML-detected map source(s):")
        for src in map_sources:
            print(f"  - {src}")
        print()

        # Process each source
        success_count = 0
        for map_source in map_sources:
            normalizer = Normalizer(map_source=map_source, data_dir=data_dir)
            if normalizer.run():
                success_count += 1

        print(f"\nSuccessfully normalized {success_count}/{len(map_sources)} source(s)")
        return 0 if success_count == len(map_sources) else 1

    else:
        # Process single map source
        normalizer = Normalizer(map_source=args.map_source, data_dir=data_dir)
        success = normalizer.run()
        return 0 if success else 1


if __name__ == '__main__':
    import sys
    sys.exit(main())
