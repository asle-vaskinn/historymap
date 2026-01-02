#!/usr/bin/env python3
"""
Match detected historical buildings to OSM buildings.

This implements the geometric similarity matching approach:
1. Load detected buildings from historical map
2. Load OSM buildings
3. Match by position and shape similarity
4. Identify:
   - Matched: Buildings that exist in both (still standing)
   - Historical-only: Buildings only in historical map (potentially demolished)
   - OSM-only: Buildings only in OSM (built after historical map date)

Usage:
    python scripts/ml/match_historical_to_osm.py \
        --detected data/detected_1904/detected_buildings.geojson \
        --output data/matched_1904
"""

import argparse
import json
from pathlib import Path
from typing import List, Tuple, Dict, Optional
from datetime import datetime

import numpy as np

try:
    from shapely.geometry import shape, box, mapping
    from shapely.ops import unary_union
    from shapely.strtree import STRtree
    HAS_SHAPELY = True
except ImportError:
    HAS_SHAPELY = False
    print("Error: shapely required. pip install shapely")


def load_geojson(path: Path) -> List[Dict]:
    """Load GeoJSON features."""
    with open(path) as f:
        data = json.load(f)
    return data.get('features', [])


def load_osm_buildings(data_dir: Path, bbox: Optional[Tuple[float, float, float, float]] = None) -> List[Dict]:
    """Load OSM buildings, optionally filtered by bbox."""
    # Try normalized first, then raw
    osm_paths = [
        data_dir / 'sources' / 'osm' / 'normalized' / 'buildings.geojson',
        data_dir / 'sources' / 'osm' / 'raw' / 'buildings.geojson',
        data_dir / 'export' / 'buildings.geojson',
    ]

    osm_data = None
    for path in osm_paths:
        if path.exists():
            print(f"Loading OSM from {path}...")
            with open(path) as f:
                osm_data = json.load(f)
            break

    if osm_data is None:
        print("Error: OSM buildings not found")
        return []

    features = osm_data.get('features', [])
    print(f"Loaded {len(features)} OSM features")

    # Filter by bbox if provided
    if bbox:
        west, south, east, north = bbox
        bbox_box = box(west, south, east, north)
        filtered = []
        for f in features:
            try:
                geom = shape(f['geometry'])
                if geom.intersects(bbox_box):
                    filtered.append(f)
            except:
                pass
        print(f"Filtered to {len(filtered)} features in bbox")
        features = filtered

    return features


def compute_iou(geom1, geom2) -> float:
    """Compute Intersection over Union between two geometries."""
    try:
        intersection = geom1.intersection(geom2)
        union = geom1.union(geom2)
        if union.area > 0:
            return intersection.area / union.area
        return 0.0
    except:
        return 0.0


def compute_overlap(geom1, geom2) -> float:
    """Compute overlap ratio (intersection / smaller geometry area)."""
    try:
        intersection = geom1.intersection(geom2)
        min_area = min(geom1.area, geom2.area)
        if min_area > 0:
            return intersection.area / min_area
        return 0.0
    except:
        return 0.0


def compute_centroid_distance(geom1, geom2) -> float:
    """Compute distance between centroids (in degrees)."""
    try:
        c1 = geom1.centroid
        c2 = geom2.centroid
        return np.sqrt((c1.x - c2.x)**2 + (c1.y - c2.y)**2)
    except:
        return float('inf')


def match_buildings(
    historical_features: List[Dict],
    osm_features: List[Dict],
    iou_threshold: float = 0.3,
    overlap_threshold: float = 0.5,
    distance_threshold: float = 0.0003  # ~30m at 63°N
) -> Tuple[List[Dict], List[Dict], List[Dict]]:
    """
    Match historical buildings to OSM buildings.

    A match requires EITHER:
    - IoU >= iou_threshold, OR
    - Overlap >= overlap_threshold AND centroid distance < distance_threshold

    Returns:
        Tuple of (matched, historical_only, osm_only)
        Each is a list of feature dicts with match info
    """
    if not HAS_SHAPELY:
        return [], [], []

    # Build spatial index for OSM buildings
    osm_geoms = []
    osm_indexed = []
    for f in osm_features:
        try:
            geom = shape(f['geometry'])
            if geom.is_valid and geom.area > 0:
                osm_geoms.append(geom)
                osm_indexed.append(f)
        except:
            pass

    if not osm_geoms:
        return [], historical_features, []

    osm_tree = STRtree(osm_geoms)
    print(f"Built spatial index with {len(osm_geoms)} OSM buildings")

    matched = []
    historical_only = []
    osm_matched_indices = set()

    for hist_feat in historical_features:
        try:
            hist_geom = shape(hist_feat['geometry'])
            if not hist_geom.is_valid or hist_geom.area <= 0:
                continue
        except:
            continue

        # Query spatial index for nearby OSM buildings
        buffer = hist_geom.buffer(distance_threshold * 2)
        candidate_indices = osm_tree.query(buffer)

        best_match = None
        best_score = 0

        for idx in candidate_indices:
            osm_geom = osm_geoms[idx]

            iou = compute_iou(hist_geom, osm_geom)
            overlap = compute_overlap(hist_geom, osm_geom)
            dist = compute_centroid_distance(hist_geom, osm_geom)

            # Check if this is a match
            if iou >= iou_threshold:
                score = iou
                if score > best_score:
                    best_score = score
                    best_match = (idx, 'iou', iou, overlap, dist)
            elif overlap >= overlap_threshold and dist < distance_threshold:
                score = overlap * 0.5  # Slightly lower score for overlap-based matches
                if score > best_score:
                    best_score = score
                    best_match = (idx, 'overlap', iou, overlap, dist)

        if best_match:
            idx, match_type, iou, overlap, dist = best_match
            osm_feat = osm_indexed[idx]
            osm_matched_indices.add(idx)

            # Create matched feature
            matched_feat = {
                'type': 'Feature',
                'geometry': hist_feat['geometry'],  # Use historical geometry
                'properties': {
                    **hist_feat.get('properties', {}),
                    'match_type': match_type,
                    'match_iou': round(iou, 3),
                    'match_overlap': round(overlap, 3),
                    'match_distance': round(dist, 6),
                    'osm_id': osm_feat.get('properties', {}).get('id'),
                    'status': 'matched',
                }
            }
            matched.append(matched_feat)
        else:
            # No match - potentially demolished
            hist_feat = dict(hist_feat)
            hist_feat['properties'] = {
                **hist_feat.get('properties', {}),
                'status': 'historical_only',
                'note': 'Detected on historical map but no OSM match - potentially demolished'
            }
            historical_only.append(hist_feat)

    # Find OSM-only buildings (built after historical map)
    osm_only = []
    for idx, osm_feat in enumerate(osm_indexed):
        if idx not in osm_matched_indices:
            osm_feat = dict(osm_feat)
            osm_feat['properties'] = {
                **osm_feat.get('properties', {}),
                'status': 'osm_only',
                'note': 'In OSM but not detected on historical map - built later'
            }
            osm_only.append(osm_feat)

    return matched, historical_only, osm_only


def main():
    parser = argparse.ArgumentParser(description='Match historical buildings to OSM')
    parser.add_argument('--detected', '-d', type=Path, required=True,
                        help='Path to detected buildings GeoJSON')
    parser.add_argument('--output', '-o', type=Path, required=True,
                        help='Output directory')
    parser.add_argument('--iou-threshold', type=float, default=0.3,
                        help='IoU threshold for matching')
    parser.add_argument('--overlap-threshold', type=float, default=0.5,
                        help='Overlap threshold for matching')
    parser.add_argument('--distance-threshold', type=float, default=0.0003,
                        help='Maximum centroid distance (degrees)')
    parser.add_argument('--bbox', type=str, default=None,
                        help='Bounding box for OSM filter: west,south,east,north')

    args = parser.parse_args()

    if not HAS_SHAPELY:
        return 1

    args.output.mkdir(parents=True, exist_ok=True)

    # Load detected historical buildings
    print(f"Loading detected buildings from {args.detected}...")
    historical_features = load_geojson(args.detected)
    print(f"Loaded {len(historical_features)} detected buildings")

    # Compute bbox from historical features
    if args.bbox:
        bbox = tuple(map(float, args.bbox.split(',')))
    else:
        # Auto-compute from detected features
        all_coords = []
        for f in historical_features:
            try:
                geom = shape(f['geometry'])
                bounds = geom.bounds
                all_coords.extend([(bounds[0], bounds[1]), (bounds[2], bounds[3])])
            except:
                pass
        if all_coords:
            xs, ys = zip(*all_coords)
            bbox = (min(xs) - 0.01, min(ys) - 0.01, max(xs) + 0.01, max(ys) + 0.01)
        else:
            bbox = (10.35, 63.40, 10.45, 63.46)  # Default Trondheim
        print(f"Auto-computed bbox: {bbox}")

    # Load OSM buildings
    data_dir = Path('data')
    osm_features = load_osm_buildings(data_dir, bbox)

    if not osm_features:
        print("Error: No OSM buildings found")
        return 1

    # Match buildings
    print("\nMatching buildings...")
    matched, historical_only, osm_only = match_buildings(
        historical_features,
        osm_features,
        iou_threshold=args.iou_threshold,
        overlap_threshold=args.overlap_threshold,
        distance_threshold=args.distance_threshold
    )

    # Save results
    def save_geojson(features: List[Dict], path: Path, name: str):
        geojson = {
            'type': 'FeatureCollection',
            'features': features,
            'properties': {
                'name': name,
                'generated_at': datetime.now().isoformat(),
                'count': len(features)
            }
        }
        with open(path, 'w') as f:
            json.dump(geojson, f, indent=2)
        print(f"Saved {len(features)} features to {path}")

    save_geojson(matched, args.output / 'matched.geojson', 'Matched buildings')
    save_geojson(historical_only, args.output / 'historical_only.geojson', 'Historical only (potentially demolished)')
    save_geojson(osm_only, args.output / 'osm_only.geojson', 'OSM only (built later)')

    # Summary
    print("\n" + "=" * 60)
    print("MATCHING COMPLETE")
    print("=" * 60)
    print(f"Total detected on historical map: {len(historical_features)}")
    print(f"Total OSM buildings in area: {len(osm_features)}")
    print()
    print(f"Matched (both): {len(matched)}")
    print(f"Historical only (demolished?): {len(historical_only)}")
    print(f"OSM only (built later): {len(osm_only)}")
    print()
    print(f"Output: {args.output}")
    print("=" * 60)

    # Create combined output for visualization
    all_features = []
    for f in matched:
        f['properties']['category'] = 'matched'
        all_features.append(f)
    for f in historical_only:
        f['properties']['category'] = 'demolished'
        all_features.append(f)

    save_geojson(all_features, args.output / 'historical_buildings.geojson', 'All historical buildings')

    return 0


if __name__ == '__main__':
    exit(main())
