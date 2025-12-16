#!/usr/bin/env python3
"""
Phase 5: Data Merging Script
Combines OSM current data with extracted historical features into a unified GeoJSON file.

This script:
1. Loads current OSM data (from Phase 1)
2. Loads extracted historical GeoJSON files (from Phase 4)
3. Handles overlapping features (deduplication by geometry similarity)
4. Ensures consistent temporal schema
5. Validates temporal consistency
6. Outputs merged data for tile generation

Usage:
    python merge_data.py --osm ../data/trondheim.geojson \
                        --historical ../data/extracted/ \
                        --output ../data/final/trondheim_all_eras.geojson
"""

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime

import geojson
from shapely.geometry import shape, mapping
from shapely.ops import unary_union
from shapely.strtree import STRtree
import numpy as np

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class FeatureNormalizer:
    """Normalizes features to consistent schema."""

    REQUIRED_PROPERTIES = ['start_date', 'end_date', 'source', 'feature_class']
    FEATURE_CLASSES = ['building', 'road', 'water', 'forest', 'railway', 'other']

    @staticmethod
    def normalize_feature(feature: Dict, source: str) -> Optional[Dict]:
        """
        Normalize a feature to consistent schema.

        Args:
            feature: GeoJSON feature
            source: Data source identifier

        Returns:
            Normalized feature or None if invalid
        """
        try:
            props = feature.get('properties', {})

            # Extract or infer feature class
            feature_class = FeatureNormalizer._infer_feature_class(props, feature.get('geometry', {}).get('type'))

            # Extract temporal data
            start_date = FeatureNormalizer._extract_date(props, 'start_date', 'start_year', 'year')
            end_date = FeatureNormalizer._extract_date(props, 'end_date', 'end_year', 'demolished')

            # Build normalized properties
            normalized_props = {
                'start_date': start_date,
                'end_date': end_date,
                'source': source,
                'feature_class': feature_class,
                'confidence': float(props.get('confidence', 1.0)),
                'original_props': {k: v for k, v in props.items()
                                 if k not in ['start_date', 'end_date', 'source', 'feature_class', 'confidence']}
            }

            # Validate
            if not FeatureNormalizer._validate_temporal(start_date, end_date):
                logger.warning(f"Invalid temporal data: start={start_date}, end={end_date}")
                return None

            return {
                'type': 'Feature',
                'geometry': feature['geometry'],
                'properties': normalized_props
            }

        except Exception as e:
            logger.error(f"Error normalizing feature: {e}")
            return None

    @staticmethod
    def _infer_feature_class(props: Dict, geom_type: str) -> str:
        """Infer feature class from properties and geometry."""
        # Check explicit class field
        for key in ['feature_class', 'class', 'type', 'category']:
            if key in props:
                value = str(props[key]).lower()
                for fc in FeatureNormalizer.FEATURE_CLASSES:
                    if fc in value:
                        return fc

        # Check OSM tags
        if 'building' in props:
            return 'building'
        if any(k in props for k in ['highway', 'road', 'street']):
            return 'road'
        if any(k in props for k in ['railway', 'rail']):
            return 'railway'
        if any(k in props for k in ['water', 'waterway', 'natural']):
            if str(props.get('natural', '')).lower() in ['water', 'lake', 'river']:
                return 'water'
        if 'landuse' in props:
            if str(props['landuse']).lower() in ['forest', 'wood']:
                return 'forest'

        # Infer from geometry type
        if geom_type in ['Polygon', 'MultiPolygon']:
            return 'building'
        elif geom_type in ['LineString', 'MultiLineString']:
            return 'road'

        return 'other'

    @staticmethod
    def _extract_date(props: Dict, *keys) -> Optional[int]:
        """Extract year from properties, trying multiple keys."""
        for key in keys:
            if key in props:
                value = props[key]
                if value is None:
                    continue

                # Try direct integer
                try:
                    year = int(value)
                    if 1700 <= year <= 2100:
                        return year
                except (ValueError, TypeError):
                    pass

                # Try extracting year from string
                try:
                    value_str = str(value)
                    # Look for 4-digit year
                    import re
                    match = re.search(r'\b(1[7-9]\d{2}|20\d{2})\b', value_str)
                    if match:
                        return int(match.group(1))
                except Exception:
                    pass

        return None

    @staticmethod
    def _validate_temporal(start_date: Optional[int], end_date: Optional[int]) -> bool:
        """Validate temporal consistency."""
        if start_date is not None and end_date is not None:
            if start_date > end_date:
                return False

        current_year = datetime.now().year
        if start_date is not None and start_date > current_year:
            return False
        if end_date is not None and end_date > current_year + 10:  # Allow some future planning
            return False

        return True


class GeometryMatcher:
    """Handles geometry-based deduplication."""

    def __init__(self, similarity_threshold: float = 0.8):
        """
        Initialize geometry matcher.

        Args:
            similarity_threshold: Minimum IoU to consider features as duplicates
        """
        self.similarity_threshold = similarity_threshold

    def find_duplicates(self, features: List[Dict]) -> List[List[int]]:
        """
        Find groups of duplicate features based on geometry similarity.

        Args:
            features: List of GeoJSON features

        Returns:
            List of groups, where each group is a list of feature indices
        """
        if not features:
            return []

        # Build spatial index
        geometries = []
        valid_indices = []

        for i, feature in enumerate(features):
            try:
                geom = shape(feature['geometry'])
                if geom.is_valid and not geom.is_empty:
                    geometries.append(geom)
                    valid_indices.append(i)
            except Exception as e:
                logger.warning(f"Invalid geometry at index {i}: {e}")

        if not geometries:
            return []

        # Build STRtree for spatial queries
        tree = STRtree(geometries)

        # Find candidate pairs
        duplicate_groups = []
        processed = set()

        for i, geom in enumerate(geometries):
            if i in processed:
                continue

            # Query nearby geometries
            candidates = tree.query(geom)

            # Check similarity
            group = [valid_indices[i]]
            processed.add(i)

            for candidate_geom in candidates:
                candidate_idx = geometries.index(candidate_geom)
                if candidate_idx in processed or candidate_idx == i:
                    continue

                similarity = self._compute_similarity(geom, candidate_geom)
                if similarity >= self.similarity_threshold:
                    group.append(valid_indices[candidate_idx])
                    processed.add(candidate_idx)

            if len(group) > 1:
                duplicate_groups.append(group)

        return duplicate_groups

    def _compute_similarity(self, geom1, geom2) -> float:
        """Compute IoU (Intersection over Union) similarity."""
        try:
            if not geom1.intersects(geom2):
                return 0.0

            intersection = geom1.intersection(geom2).area
            union = geom1.union(geom2).area

            if union == 0:
                return 0.0

            return intersection / union
        except Exception as e:
            logger.warning(f"Error computing similarity: {e}")
            return 0.0


class DataMerger:
    """Main data merging logic."""

    def __init__(self, similarity_threshold: float = 0.8):
        """
        Initialize data merger.

        Args:
            similarity_threshold: Threshold for geometry similarity
        """
        self.normalizer = FeatureNormalizer()
        self.matcher = GeometryMatcher(similarity_threshold)

    def load_osm_data(self, osm_path: Path) -> List[Dict]:
        """Load and normalize OSM data."""
        logger.info(f"Loading OSM data from {osm_path}")

        features = []

        try:
            # Check if file exists and has content
            if not osm_path.exists():
                logger.warning(f"OSM file not found: {osm_path}")
                return []

            if osm_path.stat().st_size == 0:
                logger.warning(f"OSM file is empty: {osm_path}")
                return []

            with open(osm_path, 'r') as f:
                data = json.load(f)

            raw_features = data.get('features', []) if isinstance(data, dict) else data

            for feature in raw_features:
                normalized = self.normalizer.normalize_feature(feature, 'osm')
                if normalized:
                    # OSM features without explicit dates are assumed current
                    if normalized['properties']['start_date'] is None:
                        normalized['properties']['start_date'] = 1900  # Reasonable default
                    features.append(normalized)

            logger.info(f"Loaded {len(features)} features from OSM")

        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in OSM file: {e}")
        except Exception as e:
            logger.error(f"Error loading OSM data: {e}")

        return features

    def load_historical_data(self, historical_dir: Path) -> List[Dict]:
        """Load and normalize historical extracted data."""
        logger.info(f"Loading historical data from {historical_dir}")

        features = []

        if not historical_dir.exists():
            logger.warning(f"Historical directory not found: {historical_dir}")
            return []

        # Find all GeoJSON files
        geojson_files = list(historical_dir.glob('*.geojson')) + list(historical_dir.glob('*.json'))

        if not geojson_files:
            logger.warning(f"No GeoJSON files found in {historical_dir}")
            return []

        for filepath in geojson_files:
            try:
                # Extract source from filename
                source = filepath.stem

                with open(filepath, 'r') as f:
                    data = json.load(f)

                raw_features = data.get('features', []) if isinstance(data, dict) else data

                for feature in raw_features:
                    normalized = self.normalizer.normalize_feature(feature, source)
                    if normalized:
                        features.append(normalized)

                logger.info(f"Loaded {len(raw_features)} features from {filepath.name}")

            except Exception as e:
                logger.error(f"Error loading {filepath}: {e}")

        logger.info(f"Loaded {len(features)} total historical features")
        return features

    def merge_duplicate_features(self, features: List[Dict]) -> List[Dict]:
        """
        Merge duplicate features, keeping earliest start_date and latest end_date.

        Args:
            features: List of normalized features

        Returns:
            List of merged features
        """
        logger.info(f"Finding duplicates among {len(features)} features...")

        duplicate_groups = self.matcher.find_duplicates(features)

        logger.info(f"Found {len(duplicate_groups)} duplicate groups")

        # Track which features have been merged
        merged_indices = set()
        for group in duplicate_groups:
            merged_indices.update(group)

        # Merge duplicate groups
        merged_features = []

        for group in duplicate_groups:
            merged = self._merge_feature_group([features[i] for i in group])
            merged_features.append(merged)

        # Add non-duplicate features
        for i, feature in enumerate(features):
            if i not in merged_indices:
                merged_features.append(feature)

        logger.info(f"Result: {len(merged_features)} unique features after merging")

        return merged_features

    def _merge_feature_group(self, group: List[Dict]) -> Dict:
        """Merge a group of duplicate features."""
        # Take earliest start_date
        start_dates = [f['properties']['start_date'] for f in group
                      if f['properties']['start_date'] is not None]
        start_date = min(start_dates) if start_dates else None

        # Take latest end_date (None means still exists)
        end_dates = [f['properties']['end_date'] for f in group
                    if f['properties']['end_date'] is not None]
        end_date = max(end_dates) if end_dates else None

        # Take highest confidence
        confidence = max(f['properties']['confidence'] for f in group)

        # Combine sources
        sources = list(set(f['properties']['source'] for f in group))
        source = ', '.join(sources)

        # Use first feature class (they should be similar)
        feature_class = group[0]['properties']['feature_class']

        # Use geometry with highest confidence
        best_feature = max(group, key=lambda f: f['properties']['confidence'])

        return {
            'type': 'Feature',
            'geometry': best_feature['geometry'],
            'properties': {
                'start_date': start_date,
                'end_date': end_date,
                'source': source,
                'feature_class': feature_class,
                'confidence': confidence,
                'merged_count': len(group),
                'original_props': {}
            }
        }

    def merge_all_sources(self, osm_path: Path, historical_dir: Path, output_path: Path) -> bool:
        """
        Main merge pipeline.

        Args:
            osm_path: Path to OSM GeoJSON
            historical_dir: Directory with historical GeoJSON files
            output_path: Path for merged output

        Returns:
            True if successful
        """
        try:
            # Load data
            osm_features = self.load_osm_data(osm_path)
            historical_features = self.load_historical_data(historical_dir)

            all_features = osm_features + historical_features

            if not all_features:
                logger.error("No features loaded from any source")
                return False

            logger.info(f"Total features before merging: {len(all_features)}")
            logger.info(f"  OSM: {len(osm_features)}")
            logger.info(f"  Historical: {len(historical_features)}")

            # Merge duplicates
            merged_features = self.merge_duplicate_features(all_features)

            # Create output GeoJSON
            output = {
                'type': 'FeatureCollection',
                'features': merged_features,
                'metadata': {
                    'generated': datetime.now().isoformat(),
                    'total_features': len(merged_features),
                    'sources': {
                        'osm': len(osm_features),
                        'historical': len(historical_features)
                    }
                }
            }

            # Ensure output directory exists
            output_path.parent.mkdir(parents=True, exist_ok=True)

            # Write output
            logger.info(f"Writing merged data to {output_path}")
            with open(output_path, 'w') as f:
                json.dump(output, f, indent=2)

            # Validate output
            self._validate_output(output_path)

            logger.info("✓ Merge completed successfully")
            return True

        except Exception as e:
            logger.error(f"Error during merge: {e}", exc_info=True)
            return False

    def _validate_output(self, output_path: Path):
        """Validate the output file."""
        logger.info("Validating output...")

        with open(output_path, 'r') as f:
            data = json.load(f)

        features = data.get('features', [])

        # Count features by class
        class_counts = {}
        temporal_stats = {
            'with_start_date': 0,
            'with_end_date': 0,
            'year_range': [float('inf'), float('-inf')]
        }

        for feature in features:
            props = feature['properties']

            # Count by class
            fc = props.get('feature_class', 'unknown')
            class_counts[fc] = class_counts.get(fc, 0) + 1

            # Temporal stats
            if props.get('start_date') is not None:
                temporal_stats['with_start_date'] += 1
                temporal_stats['year_range'][0] = min(temporal_stats['year_range'][0], props['start_date'])
                temporal_stats['year_range'][1] = max(temporal_stats['year_range'][1], props['start_date'])

            if props.get('end_date') is not None:
                temporal_stats['with_end_date'] += 1
                temporal_stats['year_range'][1] = max(temporal_stats['year_range'][1], props['end_date'])

        logger.info("Validation results:")
        logger.info(f"  Total features: {len(features)}")
        logger.info(f"  By class: {class_counts}")
        logger.info(f"  With start_date: {temporal_stats['with_start_date']}")
        logger.info(f"  With end_date: {temporal_stats['with_end_date']}")

        if temporal_stats['year_range'][0] != float('inf'):
            logger.info(f"  Year range: {temporal_stats['year_range'][0]} - {temporal_stats['year_range'][1]}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Merge OSM and historical data into unified GeoJSON',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument(
        '--osm',
        type=Path,
        required=True,
        help='Path to OSM GeoJSON file'
    )

    parser.add_argument(
        '--historical',
        type=Path,
        required=True,
        help='Directory containing historical GeoJSON files'
    )

    parser.add_argument(
        '--output',
        type=Path,
        required=True,
        help='Output path for merged GeoJSON'
    )

    parser.add_argument(
        '--similarity-threshold',
        type=float,
        default=0.8,
        help='Geometry similarity threshold for deduplication (0-1, default: 0.8)'
    )

    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose logging'
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Run merge
    merger = DataMerger(similarity_threshold=args.similarity_threshold)
    success = merger.merge_all_sources(args.osm, args.historical, args.output)

    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
