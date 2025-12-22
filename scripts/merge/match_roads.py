#!/usr/bin/env python3
"""
Match historical road segments to modern OSM roads using LSS-Hausdorff matching.

Uses Longest Similar Subsequence (LSS) ratio and Hausdorff distance to classify
road changes over time (same, widened, rerouted, replaced, removed, new).

LSS Algorithm:
- Sample points along both lines at regular intervals (e.g., 5m)
- Find longest subsequence where point-to-point distance < threshold
- Return ratio of LSS length to shorter line length

Hausdorff Distance:
- Use shapely's hausdorff_distance() method
- Convert to meters for Trondheim latitude (~63°N)

Change Classification:
- 'same': LSS >= 0.9 and Hausdorff <= 5m
- 'widened': LSS >= 0.8 and width difference detected
- 'rerouted': LSS >= 0.5 (partial match)
- 'replaced': No geometry match but connects same endpoints
- 'removed': Historical exists, no OSM match
- 'new': OSM road with no historical match
"""

import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import math

try:
    from shapely.geometry import shape, mapping, LineString, Point
    HAS_SHAPELY = True
except ImportError:
    HAS_SHAPELY = False
    print("ERROR: shapely is required for road matching")
    sys.exit(1)


def sample_line_points(line_geom: LineString, interval_m: float = 5.0) -> List[Point]:
    """
    Sample points along a LineString at regular intervals.

    Args:
        line_geom: Shapely LineString geometry
        interval_m: Interval in meters between samples

    Returns:
        List of sampled Point geometries
    """
    # Convert interval from meters to approximate degrees at 63°N
    # At 63°N: 1° lat ≈ 111km, 1° lon ≈ 50km
    interval_deg = interval_m / 80000  # Average approximation

    points = []
    total_length = line_geom.length

    if total_length == 0:
        return [Point(line_geom.coords[0])]

    # Sample at regular intervals
    distance = 0
    while distance <= total_length:
        point = line_geom.interpolate(distance)
        points.append(point)
        distance += interval_deg

    # Always include the end point
    if distance - interval_deg < total_length:
        points.append(Point(line_geom.coords[-1]))

    return points


def point_distance_m(p1: Point, p2: Point) -> float:
    """
    Calculate distance between two points in meters.

    Uses approximate conversion for Trondheim latitude (~63°N).
    """
    dx = (p1.x - p2.x) * 50000  # longitude to meters at 63°N
    dy = (p1.y - p2.y) * 111000  # latitude to meters
    return math.sqrt(dx**2 + dy**2)


def calculate_lss_ratio(
    line1: LineString,
    line2: LineString,
    sample_interval_m: float = 5.0,
    match_threshold_m: float = 10.0
) -> Tuple[float, int, int]:
    """
    Calculate Longest Similar Subsequence (LSS) ratio between two lines.

    Algorithm:
    1. Sample points along both lines at regular intervals
    2. Find longest subsequence where point-to-point distance < threshold
    3. Return ratio of LSS length to shorter line length

    Args:
        line1: First LineString
        line2: Second LineString
        sample_interval_m: Interval for sampling points (meters)
        match_threshold_m: Maximum distance for points to be considered matching (meters)

    Returns:
        Tuple of (lss_ratio, lss_length, shorter_length)
    """
    # Sample points along both lines
    points1 = sample_line_points(line1, sample_interval_m)
    points2 = sample_line_points(line2, sample_interval_m)

    n1 = len(points1)
    n2 = len(points2)

    if n1 == 0 or n2 == 0:
        return 0.0, 0, 0

    # Dynamic programming to find longest similar subsequence
    # dp[i][j] = length of LSS ending at points1[i] and points2[j]
    dp = [[0] * n2 for _ in range(n1)]
    max_lss = 0

    for i in range(n1):
        for j in range(n2):
            dist = point_distance_m(points1[i], points2[j])

            if dist <= match_threshold_m:
                # Points match - extend previous subsequence
                if i > 0 and j > 0:
                    dp[i][j] = dp[i-1][j-1] + 1
                else:
                    dp[i][j] = 1

                max_lss = max(max_lss, dp[i][j])

    # Calculate ratio relative to shorter sequence
    shorter_length = min(n1, n2)
    lss_ratio = max_lss / shorter_length if shorter_length > 0 else 0.0

    return lss_ratio, max_lss, shorter_length


def calculate_hausdorff_m(line1: LineString, line2: LineString) -> float:
    """
    Calculate Hausdorff distance between two lines in meters.

    Uses shapely's hausdorff_distance and converts to meters.
    """
    # Hausdorff distance in degrees
    dist_deg = line1.hausdorff_distance(line2)

    # Convert to approximate meters at Trondheim latitude (~63°N)
    dist_m = dist_deg * 80000  # Average approximation

    return dist_m


def detect_width_change(
    line1: LineString,
    line2: LineString,
    sample_points: int = 10
) -> bool:
    """
    Detect if two similar roads have different widths.

    Samples perpendicular distances at multiple points to estimate width change.
    """
    # Sample points along the shorter line
    shorter_line = line1 if line1.length <= line2.length else line2
    longer_line = line2 if shorter_line == line1 else line1

    total_length = shorter_line.length
    if total_length == 0:
        return False

    # Sample distances at regular intervals
    distances = []
    for i in range(sample_points):
        ratio = i / (sample_points - 1) if sample_points > 1 else 0.5
        point = shorter_line.interpolate(ratio, normalized=True)
        dist = point.distance(longer_line)
        distances.append(dist)

    # Check if there's consistent offset (potential widening)
    avg_dist = sum(distances) / len(distances)
    avg_dist_m = avg_dist * 80000  # Convert to meters

    # If average distance is between 2-10m, it might be a widening
    return 2 <= avg_dist_m <= 10


def check_endpoint_match(
    line1: LineString,
    line2: LineString,
    threshold_m: float = 50.0
) -> bool:
    """
    Check if two lines connect the same endpoints (within threshold).

    Used to detect "replaced" roads - same route, different path.
    """
    # Get endpoints
    start1 = Point(line1.coords[0])
    end1 = Point(line1.coords[-1])
    start2 = Point(line2.coords[0])
    end2 = Point(line2.coords[-1])

    # Check if endpoints match (allowing for direction reversal)
    match_forward = (
        point_distance_m(start1, start2) <= threshold_m and
        point_distance_m(end1, end2) <= threshold_m
    )

    match_reverse = (
        point_distance_m(start1, end2) <= threshold_m and
        point_distance_m(end1, start2) <= threshold_m
    )

    return match_forward or match_reverse


def classify_change(
    lss_ratio: float,
    hausdorff_m: float,
    line1: LineString,
    line2: LineString
) -> str:
    """
    Classify the type of change between two road segments.

    Returns:
        'same': LSS >= 0.9 and Hausdorff <= 5m
        'widened': LSS >= 0.8 and width difference detected
        'rerouted': LSS >= 0.5 (partial match)
        'replaced': No geometry match but connects same endpoints
        'removed': (handled externally - no match at all)
    """
    # Same road (minimal change)
    if lss_ratio >= 0.9 and hausdorff_m <= 5:
        return 'same'

    # Widened road
    if lss_ratio >= 0.8 and hausdorff_m <= 10:
        if detect_width_change(line1, line2):
            return 'widened'
        else:
            return 'same'  # Very similar, not widened

    # Rerouted (partial match)
    if lss_ratio >= 0.5:
        return 'rerouted'

    # Check if endpoints match (replaced)
    if check_endpoint_match(line1, line2):
        return 'replaced'

    # No significant match
    return None


def find_best_match(
    historical_road: Dict,
    osm_roads: List[Dict],
    lss_threshold: float,
    hausdorff_max: float,
    sample_interval: float = 5.0,
    match_threshold: float = 10.0
) -> Optional[Tuple[Dict, float, float, str]]:
    """
    Find the best matching OSM road for a historical road segment.

    Returns:
        Tuple of (osm_road, lss_ratio, hausdorff_m, change_type) or None
    """
    hist_geom = shape(historical_road['geometry'])

    if not isinstance(hist_geom, LineString):
        return None

    best_match = None
    best_score = 0.0

    for osm_road in osm_roads:
        osm_geom = shape(osm_road['geometry'])

        if not isinstance(osm_geom, LineString):
            continue

        # Calculate LSS ratio
        lss_ratio, lss_len, shorter_len = calculate_lss_ratio(
            hist_geom,
            osm_geom,
            sample_interval_m=sample_interval,
            match_threshold_m=match_threshold
        )

        # Skip if below LSS threshold
        if lss_ratio < lss_threshold:
            continue

        # Calculate Hausdorff distance
        hausdorff_m = calculate_hausdorff_m(hist_geom, osm_geom)

        # Skip if Hausdorff distance too large
        if hausdorff_m > hausdorff_max:
            continue

        # Classify change type
        change_type = classify_change(lss_ratio, hausdorff_m, hist_geom, osm_geom)

        if change_type is None:
            continue

        # Score: weighted combination of LSS and inverse Hausdorff
        score = lss_ratio * 0.7 + (1 - min(hausdorff_m / hausdorff_max, 1.0)) * 0.3

        if score > best_score:
            best_score = score
            best_match = (osm_road, lss_ratio, hausdorff_m, change_type)

    return best_match


def merge_road_properties(
    historical_props: Dict,
    osm_props: Dict,
    lss_ratio: float,
    hausdorff_m: float,
    change_type: str
) -> Dict:
    """
    Merge properties from historical and OSM roads.

    Keeps temporal info from historical, metadata from OSM.
    """
    merged = dict(historical_props)

    # Add OSM name if available
    if osm_props.get('nm'):
        merged['name'] = osm_props['nm']

    # Add match metadata
    merged['match_score'] = round(lss_ratio, 3)
    merged['hausdorff'] = round(hausdorff_m, 2)
    merged['change'] = change_type

    # Track sources
    sources = set()
    if historical_props.get('src'):
        sources.add(historical_props['src'])
    if osm_props.get('src'):
        sources.add(osm_props['src'])
    merged['src_all'] = sorted(list(sources))

    return merged


def match_roads(
    historical_path: Path,
    osm_path: Path,
    output_path: Path,
    lss_threshold: float = 0.7,
    hausdorff_max: float = 20.0,
    sample_interval: float = 5.0,
    match_threshold: float = 10.0
) -> bool:
    """
    Match historical roads to modern OSM roads using LSS-Hausdorff matching.

    Args:
        historical_path: Path to historical roads GeoJSON
        osm_path: Path to OSM roads GeoJSON
        output_path: Path to output merged GeoJSON
        lss_threshold: Minimum LSS ratio for match (default 0.7)
        hausdorff_max: Maximum Hausdorff distance in meters (default 20)
        sample_interval: Point sampling interval in meters (default 5)
        match_threshold: Point matching threshold in meters (default 10)

    Returns:
        True if successful
    """
    print(f"Loading historical roads from {historical_path}...")
    with open(historical_path) as f:
        historical_data = json.load(f)
    historical_roads = historical_data.get('features', [])
    print(f"  Loaded {len(historical_roads)} historical road segments")

    print(f"\nLoading OSM roads from {osm_path}...")
    with open(osm_path) as f:
        osm_data = json.load(f)
    osm_roads = osm_data.get('features', [])
    print(f"  Loaded {len(osm_roads)} OSM road segments")

    # Statistics
    stats = {
        'same': 0,
        'widened': 0,
        'rerouted': 0,
        'replaced': 0,
        'removed': 0,
        'new': 0
    }

    # Process historical roads
    print(f"\nMatching historical roads to OSM (LSS >= {lss_threshold}, Hausdorff <= {hausdorff_max}m)...")
    merged_features = []
    matched_osm_ids = set()

    for hist_road in historical_roads:
        match_result = find_best_match(
            hist_road,
            osm_roads,
            lss_threshold,
            hausdorff_max,
            sample_interval,
            match_threshold
        )

        if match_result:
            osm_road, lss_ratio, hausdorff_m, change_type = match_result

            # Merge properties
            merged_props = merge_road_properties(
                hist_road['properties'],
                osm_road['properties'],
                lss_ratio,
                hausdorff_m,
                change_type
            )

            # Use OSM geometry (more accurate)
            merged_feature = {
                'type': 'Feature',
                'properties': merged_props,
                'geometry': osm_road['geometry']
            }

            merged_features.append(merged_feature)
            stats[change_type] += 1

            # Track matched OSM road
            osm_id = osm_road['properties'].get('_src_id', '')
            if osm_id:
                matched_osm_ids.add(osm_id)
        else:
            # No match - historical road removed
            props = dict(hist_road['properties'])
            props['change'] = 'removed'
            props['match_score'] = 0.0
            props['hausdorff'] = None

            # Set end date if not already set
            if not props.get('ed'):
                props['ed'] = 1950  # Default demolition year
                props['ed_inferred'] = True

            merged_features.append({
                'type': 'Feature',
                'properties': props,
                'geometry': hist_road['geometry']
            })

            stats['removed'] += 1

    # Add unmatched OSM roads (new roads)
    print(f"\nAdding unmatched OSM roads (new roads)...")
    for osm_road in osm_roads:
        osm_id = osm_road['properties'].get('_src_id', '')

        if osm_id not in matched_osm_ids:
            props = dict(osm_road['properties'])
            props['change'] = 'new'
            props['match_score'] = 0.0
            props['hausdorff'] = None

            # New road - no historical presence
            # Keep sd from OSM if available, otherwise unknown

            merged_features.append({
                'type': 'Feature',
                'properties': props,
                'geometry': osm_road['geometry']
            })

            stats['new'] += 1

    # Generate output
    output = {
        'type': 'FeatureCollection',
        'features': merged_features
    }

    print(f"\nWriting merged roads to {output_path}...")
    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2)

    # Print statistics
    print(f"\n{'='*60}")
    print("ROAD MATCHING STATISTICS")
    print(f"{'='*60}")
    print(f"Historical roads:        {len(historical_roads)}")
    print(f"OSM roads:               {len(osm_roads)}")
    print(f"Total merged:            {len(merged_features)}")
    print(f"\nChange classification:")
    print(f"  Same (minimal change): {stats['same']}")
    print(f"  Widened:               {stats['widened']}")
    print(f"  Rerouted:              {stats['rerouted']}")
    print(f"  Replaced:              {stats['replaced']}")
    print(f"  Removed (historical):  {stats['removed']}")
    print(f"  New (modern only):     {stats['new']}")
    print(f"{'='*60}")

    # Generate report
    report = {
        'input': {
            'historical': str(historical_path),
            'osm': str(osm_path),
            'historical_count': len(historical_roads),
            'osm_count': len(osm_roads)
        },
        'parameters': {
            'lss_threshold': lss_threshold,
            'hausdorff_max': hausdorff_max,
            'sample_interval_m': sample_interval,
            'match_threshold_m': match_threshold
        },
        'output': {
            'total_roads': len(merged_features),
            'statistics': stats
        }
    }

    report_path = output_path.with_suffix('.report.json')
    print(f"\nWriting report to {report_path}...")
    with open(report_path, 'w') as f:
        json.dump(report, f, indent=2)

    print(f"\nRoad matching complete!")
    print(f"  Output: {output_path}")
    print(f"  Report: {report_path}")

    return True


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description='Match historical road segments to modern OSM roads using LSS-Hausdorff matching'
    )
    parser.add_argument(
        '--historical',
        type=Path,
        required=True,
        help='Path to historical roads GeoJSON'
    )
    parser.add_argument(
        '--osm',
        type=Path,
        required=True,
        help='Path to OSM roads GeoJSON'
    )
    parser.add_argument(
        '--output',
        type=Path,
        required=True,
        help='Path to output merged GeoJSON'
    )
    parser.add_argument(
        '--lss-threshold',
        type=float,
        default=0.7,
        help='Minimum LSS ratio for match (default: 0.7)'
    )
    parser.add_argument(
        '--hausdorff-max',
        type=float,
        default=20.0,
        help='Maximum Hausdorff distance in meters (default: 20)'
    )
    parser.add_argument(
        '--sample-interval',
        type=float,
        default=5.0,
        help='Point sampling interval in meters (default: 5)'
    )
    parser.add_argument(
        '--match-threshold',
        type=float,
        default=10.0,
        help='Point matching threshold in meters (default: 10)'
    )

    args = parser.parse_args()

    if not args.historical.exists():
        print(f"ERROR: Historical roads file not found: {args.historical}")
        sys.exit(1)

    if not args.osm.exists():
        print(f"ERROR: OSM roads file not found: {args.osm}")
        sys.exit(1)

    # Create output directory if needed
    args.output.parent.mkdir(parents=True, exist_ok=True)

    success = match_roads(
        args.historical,
        args.osm,
        args.output,
        args.lss_threshold,
        args.hausdorff_max,
        args.sample_interval,
        args.match_threshold
    )

    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
