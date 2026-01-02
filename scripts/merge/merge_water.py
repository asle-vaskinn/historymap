#!/usr/bin/env python3
"""
Merge normalized water data from multiple sources.

Simple union merge strategy for water features:
1. Load water sources (OSM, manual)
2. Resolve conflicts where features overlap (manual takes priority)
3. Output merged water.geojson

Usage:
    As module:
        from scripts.merge.merge_water import merge_water
        merge_water(config_path, output_path)

    As CLI:
        python scripts/merge/merge_water.py --config data/merged/water_merge_config.json
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Import constants
from constants import (
    WATER_MERGED,
    SOURCES_DIR
)

# Optional: Use shapely for spatial operations if available
try:
    from shapely.geometry import shape, mapping
    from shapely.strtree import STRtree
    HAS_SHAPELY = True
except ImportError:
    HAS_SHAPELY = False
    print("Warning: shapely not installed. Spatial matching will be limited.")


def load_config(config_path: Path) -> Dict:
    """Load and validate merge configuration."""
    with open(config_path) as f:
        config = json.load(f)

    # Validate required fields
    required = ['sources', 'output']
    for field in required:
        if field not in config:
            raise ValueError(f"Missing required config field: {field}")

    return config


def load_source(source_config: Dict, base_dir: Path) -> Optional[List[Dict]]:
    """Load normalized features from a source."""
    if not source_config.get('enabled', False):
        return None

    path = base_dir / source_config['path']
    if not path.exists():
        print(f"  Warning: Source file not found: {path}")
        return None

    with open(path) as f:
        data = json.load(f)

    return data.get('features', [])


def calculate_overlap(geom1: Dict, geom2: Dict) -> float:
    """
    Calculate overlap ratio between two geometries.

    Returns ratio of intersection area to smaller geometry area.
    """
    if not HAS_SHAPELY:
        return 0.0

    try:
        shape1 = shape(geom1)
        shape2 = shape(geom2)

        if not shape1.is_valid or not shape2.is_valid:
            return 0.0

        intersection = shape1.intersection(shape2)
        if intersection.is_empty:
            return 0.0

        min_area = min(shape1.area, shape2.area)
        if min_area == 0:
            return 0.0

        return intersection.area / min_area

    except Exception:
        return 0.0


def build_spatial_index(features: List[Dict]) -> Optional[Tuple[Any, List, List[Dict]]]:
    """
    Build a spatial index for fast overlap detection.

    Args:
        features: List of GeoJSON features

    Returns:
        Tuple of (STRtree index, list of shapely geometries, list of features)
        or None if shapely is not available or features is empty
    """
    if not HAS_SHAPELY:
        return None

    if not features:
        return None

    geometries = []
    indexed_features = []

    for feat in features:
        geom = feat.get('geometry')
        if not geom:
            continue

        try:
            shp = shape(geom)
            if shp.is_valid:
                geometries.append(shp)
                indexed_features.append(feat)
        except Exception:
            continue

    if not geometries:
        return None

    try:
        index = STRtree(geometries)
        return (index, geometries, indexed_features)
    except Exception:
        return None


def find_overlapping_features(
    feature: Dict,
    candidates: List[Dict],
    threshold: float = 0.8,
    spatial_index: Optional[Tuple[Any, List, List[Dict]]] = None
) -> List[Tuple[Dict, float]]:
    """
    Find overlapping water features.

    Args:
        feature: Feature to find overlaps for
        candidates: List of candidate features (used only if spatial_index is None)
        threshold: Minimum overlap ratio to consider a match (default: 0.8 for water)
        spatial_index: Optional tuple of (STRtree, geometries, features) for O(log n) lookup

    Returns:
        List of (feature, overlap_score) tuples sorted by score descending.
    """
    matches = []
    geom = feature.get('geometry')
    if not geom:
        return matches

    # Use spatial index if available
    if spatial_index is not None and HAS_SHAPELY:
        index, geometries, indexed_features = spatial_index

        try:
            query_shape = shape(geom)
            if not query_shape.is_valid:
                return matches

            # Query index for candidates that intersect
            candidate_indices = index.query(query_shape)

            for idx in candidate_indices:
                candidate = indexed_features[idx]

                # Skip self-match
                feat_id = f"{feature['properties'].get('_src')}:{feature['properties'].get('_src_id')}"
                cand_id = f"{candidate['properties'].get('_src')}:{candidate['properties'].get('_src_id')}"
                if feat_id == cand_id:
                    continue

                # Calculate overlap
                overlap = calculate_overlap(geom, candidate['geometry'])
                if overlap >= threshold:
                    matches.append((candidate, overlap))

        except Exception:
            pass

    # Fall back to O(n²) if no spatial index
    if not matches and spatial_index is None:
        for candidate in candidates:
            cand_geom = candidate.get('geometry')
            if not cand_geom:
                continue

            overlap = calculate_overlap(geom, cand_geom)
            if overlap >= threshold:
                matches.append((candidate, overlap))

    return sorted(matches, key=lambda x: x[1], reverse=True)


def merge_water_properties(
    base_props: Dict,
    new_props: Dict,
    priority: str = 'base'
) -> Dict:
    """
    Merge properties from two water features.

    Manual features take priority over OSM for conflicts.

    Args:
        base_props: Properties from base feature
        new_props: Properties from overlapping feature
        priority: 'base' or 'new' (which to prefer for conflicts)

    Returns:
        Merged properties
    """
    merged = dict(base_props)

    # Track all sources
    sources = set()
    if '_src' in base_props:
        sources.add(base_props['_src'])
    if '_src' in new_props:
        sources.add(new_props['_src'])
    merged['src_all'] = sorted(list(sources))

    # Merge evidence: take highest
    ev_order = {'h': 3, 'm': 2, 'l': 1}
    base_ev = base_props.get('ev', 'l')
    new_ev = new_props.get('ev', 'l')
    if ev_order.get(new_ev, 0) > ev_order.get(base_ev, 0):
        merged['ev'] = new_ev

    # Prefer explicit dates from higher-priority source
    # Manual takes priority over OSM
    if priority == 'new' or (priority == 'base' and not merged.get('sd') and new_props.get('sd')):
        if new_props.get('sd'):
            merged['sd'] = new_props['sd']

    # Prefer name from higher-priority source
    if priority == 'new' or (priority == 'base' and not merged.get('nm') and new_props.get('nm')):
        if new_props.get('nm'):
            merged['nm'] = new_props['nm']

    # Prefer wtype from higher-priority source
    if priority == 'new' or (priority == 'base' and not merged.get('wtype') and new_props.get('wtype')):
        if new_props.get('wtype'):
            merged['wtype'] = new_props['wtype']

    # Add merge metadata
    if '_merge_info' not in merged:
        merged['_merge_info'] = {
            'matched_at': datetime.utcnow().isoformat(),
            'sources': {}
        }

    merged['_merge_info']['sources'][new_props.get('_src', 'unknown')] = {
        'src_id': new_props.get('_src_id'),
        'wtype': new_props.get('wtype'),
        'ev': new_props.get('ev')
    }

    return merged


def merge_water(config_path: Path, output_path: Optional[Path] = None) -> bool:
    """
    Main water merge function.

    Simple union strategy: Load all sources, resolve conflicts where
    features overlap significantly (>80%). Manual features take priority.

    Args:
        config_path: Path to water_merge_config.json (optional, can be None for defaults)
        output_path: Override output path (optional)

    Returns:
        True if successful
    """
    # Support being called without config (use defaults)
    if config_path and config_path.exists():
        print("Loading water merge configuration...")
        config = load_config(config_path)
        base_dir = config_path.parent
    else:
        print("No config provided, using default paths...")
        config = {
            'sources': {
                'osm': {
                    'enabled': True,
                    'path': '../sources/osm/normalized/water.geojson',
                    'priority': 3  # Lowest - current state
                },
                'manual': {
                    'enabled': True,
                    'path': '../sources/manual/normalized/water.geojson',
                    'priority': 1  # Highest - human verified
                },
                'ml_water': {
                    'enabled': True,
                    'path': '../sources/ml_water/normalized/water.geojson',
                    'priority': 2  # Medium - ML detected, needs verification
                }
            },
            'matching': {
                'overlap_threshold': 0.8
            },
            'output': {
                'output_file': 'water_merged.geojson'
            }
        }
        # Use default base_dir
        base_dir = Path(__file__).parent.parent.parent / 'data' / 'merged'

    # Load enabled sources in priority order
    sources_config = config['sources']
    sorted_sources = sorted(
        sources_config.items(),
        key=lambda x: x[1].get('priority', 999)
    )

    print(f"\nLoading water sources (priority order):")
    all_features = []
    source_stats = {}

    for source_id, source_config in sorted_sources:
        if not source_config.get('enabled', False):
            print(f"  - {source_id}: DISABLED")
            continue

        features = load_source(source_config, base_dir)
        if features is None:
            print(f"  - {source_id}: NOT FOUND")
            continue

        print(f"  - {source_id}: {len(features)} water features (priority {source_config.get('priority', 999)})")
        source_stats[source_id] = len(features)

        # Tag features with source priority
        for f in features:
            f['_priority'] = source_config.get('priority', 999)
            f['_source_id'] = source_id

        all_features.extend(features)

    if not all_features:
        print("\nNo water features to merge!")
        return False

    print(f"\nTotal water features before merging: {len(all_features)}")

    # Merge matching features
    print("\nResolving conflicts (>80% overlap)...")
    threshold = config.get('matching', {}).get('overlap_threshold', 0.8)

    merged_features = []
    matched_ids = set()

    # Process features in priority order (higher priority first)
    all_features.sort(key=lambda f: f.get('_priority', 999))

    # Build spatial index
    spatial_index = None
    if HAS_SHAPELY and len(all_features) > 50:
        print("Building spatial index for conflict detection...")
        spatial_index = build_spatial_index(all_features)
        if spatial_index:
            print(f"  Indexed {len(spatial_index[1])} water geometries")

    conflicts_resolved = 0

    for feat in all_features:
        feat_id = f"{feat['properties'].get('_src')}:{feat['properties'].get('_src_id')}"

        if feat_id in matched_ids:
            continue

        # Find overlapping features
        if spatial_index:
            overlaps = find_overlapping_features(feat, [], threshold, spatial_index)
            # Filter out already matched
            overlaps = [(m, s) for m, s in overlaps
                       if f"{m['properties'].get('_src')}:{m['properties'].get('_src_id')}" not in matched_ids]
        else:
            remaining = [f for f in all_features
                        if f"{f['properties'].get('_src')}:{f['properties'].get('_src_id')}" not in matched_ids
                        and f is not feat]
            overlaps = find_overlapping_features(feat, remaining, threshold)

        # Merge overlapping features (manual takes priority)
        merged_props = dict(feat['properties'])
        for overlap_feat, score in overlaps:
            overlap_id = f"{overlap_feat['properties'].get('_src')}:{overlap_feat['properties'].get('_src_id')}"
            matched_ids.add(overlap_id)

            # Determine priority: manual > ml_water > osm
            base_src = feat.get('_source_id', feat['properties'].get('_src'))
            overlap_src = overlap_feat.get('_source_id', overlap_feat['properties'].get('_src'))

            # Priority order: manual (1) > ml_water (2) > osm (3)
            priority_order = {'manual': 1, 'ml_water': 2, 'osm': 3}
            base_priority = priority_order.get(base_src, 999)
            overlap_priority = priority_order.get(overlap_src, 999)

            # Lower number = higher priority
            if overlap_priority < base_priority:
                merged_props = merge_water_properties(
                    merged_props,
                    overlap_feat['properties'],
                    priority='new'
                )
            else:
                merged_props = merge_water_properties(
                    merged_props,
                    overlap_feat['properties'],
                    priority='base'
                )

            conflicts_resolved += 1

        # Clean up internal fields
        if '_priority' in merged_props:
            del merged_props['_priority']
        if '_source_id' in merged_props:
            del merged_props['_source_id']

        merged_feat = {
            'type': 'Feature',
            'properties': merged_props,
            'geometry': feat['geometry']
        }
        merged_features.append(merged_feat)
        matched_ids.add(feat_id)

    print(f"  Conflicts resolved: {conflicts_resolved}")
    print(f"Water features after merging: {len(merged_features)}")

    # Generate output
    output = {
        'type': 'FeatureCollection',
        'features': merged_features
    }

    # Determine output path
    if output_path is None:
        output_file = config['output'].get('output_file', 'water_merged.geojson')
        output_path = base_dir / output_file

    print(f"\nWriting output to {output_path}...")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(output, f)

    # Generate simple statistics report
    report = {
        'merged_at': datetime.utcnow().isoformat(),
        'config_file': str(config_path) if config_path else 'default',
        'source_stats': source_stats,
        'total_input': sum(source_stats.values()),
        'total_output': len(merged_features),
        'conflicts_resolved': conflicts_resolved,
        'water_types': {}
    }

    # Count water types
    for feat in merged_features:
        wtype = feat['properties'].get('wtype', 'unknown')
        report['water_types'][wtype] = report['water_types'].get(wtype, 0) + 1

    report_path = output_path.with_suffix('.report.json')
    with open(report_path, 'w') as f:
        json.dump(report, f, indent=2)

    # Print summary
    print("\n" + "="*60)
    print("WATER MERGE SUMMARY")
    print("="*60)
    print(f"\nSources merged:")
    for source, count in sorted(source_stats.items()):
        print(f"  {source}: {count} features")
    print(f"\nTotal input: {sum(source_stats.values())}")
    print(f"Total output: {len(merged_features)}")
    print(f"Conflicts resolved: {conflicts_resolved}")
    print(f"\nWater types:")
    for wtype, count in sorted(report['water_types'].items(), key=lambda x: x[1], reverse=True):
        print(f"  {wtype}: {count}")
    print("\n" + "="*60)

    print(f"\nWater merge complete!")
    print(f"  Output: {output_path}")
    print(f"  Report: {report_path}")

    return True


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description='Merge water data from multiple sources')
    parser.add_argument('--config', '-c', type=Path, default=None,
                        help='Path to water_merge_config.json (optional)')
    parser.add_argument('--output', '-o', type=Path, default=None,
                        help='Output file path (overrides config)')

    args = parser.parse_args()

    # Use default paths if no config
    if args.config is None:
        config_path = Path(__file__).parent.parent.parent / 'data' / 'merged' / 'water_merge_config.json'
        if not config_path.exists():
            print(f"No config found at {config_path}, using defaults...")
            config_path = None
    else:
        config_path = args.config
        if not config_path.exists():
            print(f"Config file not found: {config_path}")
            sys.exit(1)

    success = merge_water(config_path, args.output)
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
