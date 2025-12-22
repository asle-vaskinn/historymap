#!/usr/bin/env python3
"""
Compare ML-extracted 1880 buildings with current OSM buildings to date them.

This script:
1. Loads ML-extracted buildings from 1880 historical map
2. Loads current buildings from the temporal dataset
3. Compares footprints to identify:
   - Buildings that existed in 1880 (overlap with ML detection)
   - Buildings that are post-1880 (no overlap)
   - Buildings from 1880 that may have been demolished (in ML but not in current)
4. Updates the temporal dataset with improved dating
"""

import json
import sys
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import math

def load_geojson(path: str) -> Dict:
    """Load a GeoJSON file."""
    with open(path, 'r') as f:
        return json.load(f)

def save_geojson(data: Dict, path: str):
    """Save a GeoJSON file."""
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)

def get_polygon_centroid(coords: List) -> Tuple[float, float]:
    """Calculate centroid of a polygon."""
    if not coords or not coords[0]:
        return (0, 0)

    ring = coords[0]  # Outer ring
    n = len(ring)
    if n == 0:
        return (0, 0)

    cx = sum(p[0] for p in ring) / n
    cy = sum(p[1] for p in ring) / n
    return (cx, cy)

def get_bbox(coords: List) -> Tuple[float, float, float, float]:
    """Get bounding box of a polygon."""
    if not coords or not coords[0]:
        return (0, 0, 0, 0)

    ring = coords[0]
    xs = [p[0] for p in ring]
    ys = [p[1] for p in ring]
    return (min(xs), min(ys), max(xs), max(ys))

def bboxes_overlap(bbox1: Tuple, bbox2: Tuple, buffer: float = 0.0001) -> bool:
    """Check if two bounding boxes overlap with a buffer."""
    return not (bbox1[2] + buffer < bbox2[0] - buffer or  # bbox1 is left of bbox2
                bbox1[0] - buffer > bbox2[2] + buffer or  # bbox1 is right of bbox2
                bbox1[3] + buffer < bbox2[1] - buffer or  # bbox1 is below bbox2
                bbox1[1] - buffer > bbox2[3] + buffer)    # bbox1 is above bbox2

def polygon_area(coords: List) -> float:
    """Calculate approximate area of a polygon using shoelace formula."""
    if not coords or not coords[0]:
        return 0

    ring = coords[0]
    n = len(ring)
    area = 0
    for i in range(n):
        j = (i + 1) % n
        area += ring[i][0] * ring[j][1]
        area -= ring[j][0] * ring[i][1]
    return abs(area) / 2

def point_in_polygon(point: Tuple[float, float], coords: List) -> bool:
    """Check if a point is inside a polygon using ray casting."""
    if not coords or not coords[0]:
        return False

    ring = coords[0]
    x, y = point
    n = len(ring)
    inside = False

    j = n - 1
    for i in range(n):
        xi, yi = ring[i]
        xj, yj = ring[j]

        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
            inside = not inside
        j = i

    return inside

def calculate_overlap_score(ml_coords: List, osm_coords: List) -> float:
    """
    Calculate how much the ML building overlaps with OSM building.
    Returns a score from 0 to 1.
    """
    ml_centroid = get_polygon_centroid(ml_coords)
    osm_centroid = get_polygon_centroid(osm_coords)

    # Check if centroids are inside each other's polygons
    ml_in_osm = point_in_polygon(ml_centroid, osm_coords)
    osm_in_ml = point_in_polygon(osm_centroid, ml_coords)

    if ml_in_osm or osm_in_ml:
        return 0.8  # Strong overlap

    # Check distance between centroids
    dist = math.sqrt((ml_centroid[0] - osm_centroid[0])**2 +
                     (ml_centroid[1] - osm_centroid[1])**2)

    # If very close (within ~20m at Trondheim latitude), consider it a match
    if dist < 0.0002:  # ~20m
        return 0.6

    return 0


def calculate_overlap_with_confidence(
    ml_coords: List,
    osm_coords: List,
    ml_confidence: float = 0.7
) -> Dict:
    """
    Calculate overlap score with combined confidence.

    Args:
        ml_coords: ML-extracted building coordinates
        osm_coords: OSM building coordinates
        ml_confidence: ML model confidence for the extracted building (0-1)

    Returns:
        Dict with overlap details:
        - overlap_score: Geometric overlap (0-1)
        - centroid_distance: Distance in degrees
        - area_ratio: Smaller area / larger area (0-1)
        - combined_score: Weighted combination (0-1)
        - quality: 'high', 'medium', or 'low'
    """
    ml_centroid = get_polygon_centroid(ml_coords)
    osm_centroid = get_polygon_centroid(osm_coords)

    # Calculate centroid distance
    centroid_dist = math.sqrt(
        (ml_centroid[0] - osm_centroid[0])**2 +
        (ml_centroid[1] - osm_centroid[1])**2
    )

    # Calculate overlap score
    ml_in_osm = point_in_polygon(ml_centroid, osm_coords)
    osm_in_ml = point_in_polygon(osm_centroid, ml_coords)

    if ml_in_osm or osm_in_ml:
        overlap_score = 0.8
    elif centroid_dist < 0.0002:  # ~20m
        overlap_score = 0.6
    else:
        overlap_score = 0

    # Calculate area ratio
    ml_area = polygon_area(ml_coords)
    osm_area = polygon_area(osm_coords)
    if ml_area > 0 and osm_area > 0:
        area_ratio = min(ml_area, osm_area) / max(ml_area, osm_area)
    else:
        area_ratio = 0

    # Normalize centroid distance (20m ~ 0.0002 degrees)
    centroid_score = max(0, 1 - (centroid_dist / 0.0002))

    # Combined confidence calculation
    combined_score = (
        0.4 * ml_confidence +
        0.3 * overlap_score +
        0.2 * min(area_ratio, 1.0) +
        0.1 * centroid_score
    )
    combined_score = min(1.0, max(0.0, combined_score))

    # Determine quality level
    if combined_score >= 0.7:
        quality = 'high'
    elif combined_score >= 0.5:
        quality = 'medium'
    else:
        quality = 'low'

    return {
        'overlap_score': overlap_score,
        'centroid_distance': centroid_dist,
        'area_ratio': area_ratio,
        'combined_score': combined_score,
        'quality': quality,
        'ml_confidence': ml_confidence
    }


def update_building_evidence(
    building: Dict,
    detection: Dict,
    map_date: int,
    map_id: str
) -> Dict:
    """
    Update building feature with verification evidence.

    Args:
        building: Building feature dict (modified in place)
        detection: Detection result from calculate_overlap_with_confidence
        map_date: Year of the historical map
        map_id: Identifier for the map source

    Returns:
        Updated building feature
    """
    props = building.setdefault('properties', {})

    # Initialize verification structure if not present
    if '_verification' not in props:
        props['_verification'] = {
            'maps_checked': [],
            'detections': [],
            'verified': False,
            'verified_date': None
        }

    verification = props['_verification']

    # Add map to checked list
    if map_date not in verification['maps_checked']:
        verification['maps_checked'].append(map_date)
        verification['maps_checked'].sort()

    # Add detection record
    detection_record = {
        'map_date': map_date,
        'map_id': map_id,
        'combined_score': round(detection['combined_score'], 3),
        'quality': detection['quality'],
        'overlap_score': round(detection['overlap_score'], 2),
        'ml_confidence': round(detection['ml_confidence'], 2)
    }
    verification['detections'].append(detection_record)

    # Update verification status if this is a high-quality detection
    if detection['combined_score'] >= 0.5:
        verification['verified'] = True
        if verification['verified_date'] is None or map_date < verification['verified_date']:
            verification['verified_date'] = map_date

    # Update temporal fields
    if verification['verified'] and verification['verified_date']:
        current_sd = props.get('sd')
        if current_sd is None or verification['verified_date'] < current_sd:
            props['sd'] = verification['verified_date']
            props['sd_t'] = 'n'  # not-later-than
            props['sd_s'] = f"ml{map_date % 100:02d}"
            props['sd_c'] = detection['combined_score']

        # Update evidence level
        if detection['quality'] == 'high':
            props['ev'] = 'h'
        elif detection['quality'] == 'medium' and props.get('ev') != 'h':
            props['ev'] = 'm'

    return building


def generate_verification_report(
    buildings: List[Dict],
    maps_processed: List[str]
) -> Dict:
    """
    Generate summary report of verification results.

    Args:
        buildings: List of building features with verification data
        maps_processed: List of map IDs that were processed

    Returns:
        Report dict with statistics
    """
    total = len(buildings)
    verified = 0
    not_verified = 0
    quality_counts = {'high': 0, 'medium': 0, 'low': 0}
    by_era = {'pre_1900': 0, '1900_1950': 0, '1950_2000': 0, 'post_2000': 0}

    for feat in buildings:
        props = feat.get('properties', {})
        verification = props.get('_verification', {})

        if verification.get('verified'):
            verified += 1
            # Get best detection quality
            detections = verification.get('detections', [])
            if detections:
                best = max(detections, key=lambda d: d.get('combined_score', 0))
                quality = best.get('quality', 'low')
                quality_counts[quality] += 1

            # Categorize by era
            verified_date = verification.get('verified_date')
            if verified_date:
                if verified_date < 1900:
                    by_era['pre_1900'] += 1
                elif verified_date < 1950:
                    by_era['1900_1950'] += 1
                elif verified_date < 2000:
                    by_era['1950_2000'] += 1
                else:
                    by_era['post_2000'] += 1
        else:
            not_verified += 1

    return {
        'total_buildings': total,
        'buildings_verified': verified,
        'buildings_not_verified': not_verified,
        'verification_rate': round(verified / total * 100, 1) if total > 0 else 0,
        'detections_by_quality': quality_counts,
        'verified_by_era': by_era,
        'maps_processed': maps_processed
    }

def find_overlapping_buildings(ml_buildings: List[Dict], osm_buildings: List[Dict]) -> Dict:
    """
    Find overlapping buildings between ML-extracted and OSM buildings.

    Returns:
        Dict with:
        - matched: List of (ml_idx, osm_idx, overlap_score)
        - unmatched_ml: List of ml_idx (buildings from 1880 not in OSM - possibly demolished)
        - unmatched_osm: List of osm_idx (buildings not detected in 1880 - newer buildings)
    """
    # Pre-compute bounding boxes for all buildings
    ml_bboxes = []
    for feat in ml_buildings:
        if feat['geometry']['type'] == 'Polygon':
            ml_bboxes.append(get_bbox(feat['geometry']['coordinates']))
        else:
            ml_bboxes.append((0, 0, 0, 0))

    osm_bboxes = []
    for feat in osm_buildings:
        if feat['geometry']['type'] == 'Polygon':
            osm_bboxes.append(get_bbox(feat['geometry']['coordinates']))
        else:
            osm_bboxes.append((0, 0, 0, 0))

    matched = []
    matched_ml = set()
    matched_osm = set()

    print(f"Comparing {len(ml_buildings)} ML buildings with {len(osm_buildings)} OSM buildings...")

    # For each ML building, find overlapping OSM buildings
    for ml_idx, ml_feat in enumerate(ml_buildings):
        if ml_feat['geometry']['type'] != 'Polygon':
            continue

        ml_bbox = ml_bboxes[ml_idx]
        ml_coords = ml_feat['geometry']['coordinates']

        best_match = None
        best_score = 0

        for osm_idx, osm_feat in enumerate(osm_buildings):
            if osm_feat['geometry']['type'] != 'Polygon':
                continue

            osm_bbox = osm_bboxes[osm_idx]

            # Quick bbox check
            if not bboxes_overlap(ml_bbox, osm_bbox):
                continue

            # Detailed overlap check
            osm_coords = osm_feat['geometry']['coordinates']
            score = calculate_overlap_score(ml_coords, osm_coords)

            if score > best_score:
                best_score = score
                best_match = osm_idx

        if best_match is not None and best_score >= 0.5:
            matched.append((ml_idx, best_match, best_score))
            matched_ml.add(ml_idx)
            matched_osm.add(best_match)

    unmatched_ml = [i for i in range(len(ml_buildings))
                   if i not in matched_ml and ml_buildings[i]['geometry']['type'] == 'Polygon']
    unmatched_osm = [i for i in range(len(osm_buildings))
                   if i not in matched_osm and osm_buildings[i]['geometry']['type'] == 'Polygon']

    return {
        'matched': matched,
        'unmatched_ml': unmatched_ml,
        'unmatched_osm': unmatched_osm
    }

def main():
    # Paths
    data_dir = Path(__file__).parent.parent / 'data'
    ml_buildings_path = data_dir / 'kartverket' / 'buildings_1880.geojson'
    temporal_path = data_dir / 'buildings_temporal.geojson'
    output_path = data_dir / 'buildings_dated.geojson'
    demolished_path = data_dir / 'buildings_demolished_since_1880.geojson'

    # Check if files exist
    if not ml_buildings_path.exists():
        print(f"Error: ML buildings file not found: {ml_buildings_path}")
        sys.exit(1)

    if not temporal_path.exists():
        print(f"Error: Temporal buildings file not found: {temporal_path}")
        sys.exit(1)

    # Load data
    print("Loading ML-extracted 1880 buildings...")
    ml_data = load_geojson(ml_buildings_path)
    ml_buildings = ml_data['features']
    print(f"  Loaded {len(ml_buildings)} buildings from 1880 map")

    print("Loading current temporal buildings...")
    temporal_data = load_geojson(temporal_path)
    osm_buildings = temporal_data['features']
    print(f"  Loaded {len(osm_buildings)} current buildings")

    # Find overlaps
    print("\nFinding overlapping buildings...")
    results = find_overlapping_buildings(ml_buildings, osm_buildings)

    print(f"\nResults:")
    print(f"  Matched buildings (existed in 1880): {len(results['matched'])}")
    print(f"  Unmatched ML buildings (possibly demolished): {len(results['unmatched_ml'])}")
    print(f"  Unmatched OSM buildings (post-1880): {len(results['unmatched_osm'])}")

    # Update temporal dataset with improved dates
    print("\nUpdating building dates...")
    updated_count = 0

    for ml_idx, osm_idx, score in results['matched']:
        osm_feat = osm_buildings[osm_idx]
        props = osm_feat.get('properties', {})
        current_start = props.get('start_date')
        source = props.get('source', '')

        # Only update if current date is later than 1880 and source is "osm_assumed"
        if source == 'osm_assumed' or (isinstance(current_start, int) and current_start > 1880):
            props['start_date'] = 1880
            props['source'] = 'ml_1880_matched'
            props['ml_confidence'] = round(score, 2)
            updated_count += 1

    # Mark unmatched OSM buildings as post-1880
    for osm_idx in results['unmatched_osm']:
        osm_feat = osm_buildings[osm_idx]
        props = osm_feat.get('properties', {})
        source = props.get('source', '')
        current_start = props.get('start_date')

        # Only update buildings with assumed dates
        if source == 'osm_assumed':
            props['source'] = 'ml_1880_not_detected'
            props['start_date_min'] = 1881  # Definitely after 1880
            # Keep existing start_date as an estimate

    print(f"  Updated {updated_count} buildings with 1880 start date")

    # Save updated temporal dataset
    temporal_data['name'] = 'Trondheim Buildings with ML-Enhanced Dating'
    save_geojson(temporal_data, output_path)
    print(f"\nSaved updated dataset to: {output_path}")

    # Create demolished buildings dataset
    demolished_features = []
    for ml_idx in results['unmatched_ml']:
        ml_feat = ml_buildings[ml_idx]
        feat_copy = {
            'type': 'Feature',
            'properties': {
                'source': 'ml_1880',
                'status': 'demolished',
                'existed_in': 1880,
                'confidence': ml_feat.get('properties', {}).get('confidence', 0.5)
            },
            'geometry': ml_feat['geometry']
        }
        demolished_features.append(feat_copy)

    demolished_data = {
        'type': 'FeatureCollection',
        'name': 'Buildings Demolished Since 1880',
        'features': demolished_features
    }
    save_geojson(demolished_data, demolished_path)
    print(f"Saved demolished buildings to: {demolished_path}")

    # Print summary statistics
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)

    # Count by source
    source_counts = {}
    date_counts = {'pre_1900': 0, '1900_1950': 0, '1950_2000': 0, 'post_2000': 0}

    for feat in osm_buildings:
        props = feat.get('properties', {})
        source = props.get('source', 'unknown')
        source_counts[source] = source_counts.get(source, 0) + 1

        start_date = props.get('start_date')
        if isinstance(start_date, int):
            if start_date < 1900:
                date_counts['pre_1900'] += 1
            elif start_date < 1950:
                date_counts['1900_1950'] += 1
            elif start_date < 2000:
                date_counts['1950_2000'] += 1
            else:
                date_counts['post_2000'] += 1

    print("\nBuildings by source:")
    for source, count in sorted(source_counts.items(), key=lambda x: -x[1]):
        print(f"  {source}: {count}")

    print("\nBuildings by era:")
    print(f"  Pre-1900: {date_counts['pre_1900']}")
    print(f"  1900-1950: {date_counts['1900_1950']}")
    print(f"  1950-2000: {date_counts['1950_2000']}")
    print(f"  Post-2000: {date_counts['post_2000']}")

    print(f"\nPotentially demolished buildings: {len(demolished_features)}")

if __name__ == '__main__':
    main()
