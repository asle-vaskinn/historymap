#!/usr/bin/env python3
"""
Infer road construction dates from nearby buildings.

Key insight: Local roads are typically built 1-2 years before the houses they serve.

Algorithm:
1. Load roads GeoJSON and buildings GeoJSON
2. For each road segment without a date (sd):
   a. Find all buildings within buffer distance (default 50m)
   b. Get construction dates (sd) from those buildings
   c. Take the EARLIEST (minimum) building date
   d. Subtract offset (default 2 years) for road construction estimate
3. If no nearby buildings, fallback to map era if src='ml':
   - 'kv1880' -> 1880
   - 'kv1904' -> 1904
   - 'air1947' -> 1947
4. Ultimate fallback: 1960

Output properties to add:
- sd: inferred start date
- ev: 'l' (low evidence for inferred)
- sd_method: 'building' | 'bounded' | 'fallback'
- sd_buildings: count of buildings used
- sd_offset: years subtracted (typically -2)
"""

import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    from shapely.geometry import shape, mapping, Point
    from shapely.strtree import STRtree
    HAS_SHAPELY = True
except ImportError:
    HAS_SHAPELY = False
    print("ERROR: shapely is required for spatial operations")
    print("Install with: pip install shapely")
    sys.exit(1)


def extract_map_year(src: str) -> Optional[int]:
    """
    Extract year from source string.

    Examples:
    - 'ml_kv1880' -> 1880
    - 'kv1904' -> 1904
    - 'air1947' -> 1947
    """
    import re

    # Match 4-digit years
    match = re.search(r'(\d{4})', src)
    if match:
        year = int(match.group(1))
        # Only return if it's a historical year
        if 1700 <= year <= 2000:
            return year

    return None


def load_geojson(path: Path) -> Dict:
    """Load GeoJSON file."""
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    with open(path) as f:
        return json.load(f)


def build_building_spatial_index(buildings: List[Dict]) -> Tuple[STRtree, List[Dict], List]:
    """
    Build spatial index for building features.

    Returns:
        (index, indexed_buildings, geometries)
    """
    geometries = []
    indexed_buildings = []

    for building in buildings:
        geom = building.get('geometry')
        if not geom:
            continue

        try:
            shp = shape(geom)
            if shp.is_valid:
                # Use centroid for buildings for faster point-in-polygon checks
                centroid = shp.centroid
                geometries.append(centroid)
                indexed_buildings.append(building)
        except Exception:
            continue

    if not geometries:
        raise ValueError("No valid building geometries found")

    index = STRtree(geometries)
    return index, indexed_buildings, geometries


def find_nearby_buildings(
    road_geometry: Dict,
    building_index: Tuple[STRtree, List[Dict], List],
    buffer_m: float = 50
) -> List[Dict]:
    """
    Find all buildings within buffer distance of road.

    Args:
        road_geometry: Road LineString geometry
        building_index: Spatial index tuple (index, buildings, geometries)
        buffer_m: Search radius in meters

    Returns:
        List of building features within buffer
    """
    index, indexed_buildings, geometries = building_index

    try:
        road_shape = shape(road_geometry)
        if not road_shape.is_valid:
            return []

        # Convert buffer from meters to degrees (approximate at 63°N)
        # 1 degree latitude ≈ 111km, 1 degree longitude ≈ 50km at 63°N
        buffer_deg = buffer_m / 80000

        # Buffer the road
        buffered = road_shape.buffer(buffer_deg)

        # Query spatial index
        candidate_indices = index.query(buffered)

        # Filter to buildings actually within buffer
        nearby = []
        for idx in candidate_indices:
            # Double-check with actual intersection
            if geometries[idx].intersects(buffered):
                nearby.append(indexed_buildings[idx])

        return nearby

    except Exception as e:
        print(f"Warning: Error finding nearby buildings: {e}")
        return []


def get_earliest_building_date(buildings: List[Dict]) -> Optional[int]:
    """
    Get the earliest construction date from a list of buildings.

    Returns:
        Earliest start_date (sd or start_date) or None if no dated buildings
    """
    dates = []

    for building in buildings:
        props = building.get('properties', {})
        # Try both 'sd' (normalized schema) and 'start_date' (legacy)
        sd = props.get('sd') or props.get('start_date')

        if sd and isinstance(sd, (int, float)):
            dates.append(int(sd))

    if not dates:
        return None

    return min(dates)


def infer_road_dates(
    roads_path: Path,
    buildings_path: Path,
    output_path: Path,
    buffer_m: float = 50,
    offset_years: int = 2
):
    """
    Infer road construction dates from nearby buildings.

    Args:
        roads_path: Input roads GeoJSON
        buildings_path: Buildings GeoJSON with dates
        output_path: Output roads GeoJSON with dates
        buffer_m: Search radius in meters (default 50)
        offset_years: Years to subtract from building date (default 2)
    """
    print(f"Loading roads from {roads_path}...")
    roads_data = load_geojson(roads_path)
    roads = roads_data.get('features', [])
    print(f"  Loaded {len(roads)} roads")

    print(f"\nLoading buildings from {buildings_path}...")
    buildings_data = load_geojson(buildings_path)
    buildings = buildings_data.get('features', [])
    print(f"  Loaded {len(buildings)} buildings")

    # Filter to buildings with dates (check both 'sd' and 'start_date')
    dated_buildings = [
        b for b in buildings
        if b.get('properties', {}).get('sd') or b.get('properties', {}).get('start_date')
    ]
    print(f"  Buildings with dates: {len(dated_buildings)}")

    if not dated_buildings:
        print("\nWARNING: No dated buildings found. Cannot infer road dates.")
        return

    # Build spatial index
    print("\nBuilding spatial index for buildings...")
    building_index = build_building_spatial_index(dated_buildings)
    print(f"  Indexed {len(building_index[1])} buildings")

    # Statistics
    stats = {
        'total_roads': len(roads),
        'already_dated': 0,
        'dated_by_building': 0,
        'dated_by_map_era': 0,
        'dated_by_fallback': 0,
        'no_date': 0
    }

    print(f"\nInferring road dates (buffer={buffer_m}m, offset={offset_years}y)...")

    for road in roads:
        props = road.get('properties', {})

        # Skip if already has a date
        if props.get('sd'):
            stats['already_dated'] += 1
            continue

        geom = road.get('geometry')
        if not geom:
            stats['no_date'] += 1
            continue

        # Find nearby buildings
        nearby_buildings = find_nearby_buildings(geom, building_index, buffer_m)

        if nearby_buildings:
            # Get earliest building date
            earliest_date = get_earliest_building_date(nearby_buildings)

            if earliest_date:
                # Infer road date by subtracting offset
                inferred_date = earliest_date - offset_years

                props['sd'] = inferred_date
                props['ev'] = 'l'  # Low evidence
                props['sd_method'] = 'building'
                props['sd_buildings'] = len(nearby_buildings)
                props['sd_offset'] = -offset_years

                stats['dated_by_building'] += 1
                continue

        # Fallback 1: Use map era if ML source
        src = props.get('src', '')
        if 'ml' in src.lower() or 'kv' in src.lower():
            map_year = extract_map_year(src)
            if map_year:
                props['sd'] = map_year
                props['ev'] = 'l'
                props['sd_method'] = 'bounded'
                props['sd_offset'] = 0

                stats['dated_by_map_era'] += 1
                continue

        # Fallback 2: Default to 1960
        props['sd'] = 1960
        props['ev'] = 'l'
        props['sd_method'] = 'fallback'
        props['sd_offset'] = 0

        stats['dated_by_fallback'] += 1

    # Write output
    print(f"\nWriting output to {output_path}...")
    output_data = {
        'type': 'FeatureCollection',
        'features': roads
    }

    with open(output_path, 'w') as f:
        json.dump(output_data, f)

    # Print statistics
    print("\n" + "=" * 60)
    print("ROAD DATE INFERENCE STATISTICS")
    print("=" * 60)
    print(f"Total roads:               {stats['total_roads']:>6}")
    print(f"Already dated:             {stats['already_dated']:>6} ({100*stats['already_dated']/stats['total_roads']:.1f}%)")
    print(f"Dated by building:         {stats['dated_by_building']:>6} ({100*stats['dated_by_building']/stats['total_roads']:.1f}%)")
    print(f"Dated by map era:          {stats['dated_by_map_era']:>6} ({100*stats['dated_by_map_era']/stats['total_roads']:.1f}%)")
    print(f"Dated by fallback (1960):  {stats['dated_by_fallback']:>6} ({100*stats['dated_by_fallback']/stats['total_roads']:.1f}%)")
    print(f"No date:                   {stats['no_date']:>6} ({100*stats['no_date']/stats['total_roads']:.1f}%)")
    print("=" * 60)

    # Calculate total with dates
    total_dated = (stats['already_dated'] + stats['dated_by_building'] +
                   stats['dated_by_map_era'] + stats['dated_by_fallback'])
    print(f"\nTotal roads with dates:    {total_dated:>6} ({100*total_dated/stats['total_roads']:.1f}%)")
    print(f"\nOutput written to: {output_path}")


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description='Infer road construction dates from nearby buildings',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic usage
  python infer_road_dates.py \\
    --roads data/roads_temporal.geojson \\
    --buildings data/buildings_temporal.geojson \\
    --output data/roads_dated.geojson

  # Custom parameters
  python infer_road_dates.py \\
    --roads data/roads_temporal.geojson \\
    --buildings data/buildings_temporal.geojson \\
    --output data/roads_dated.geojson \\
    --buffer 75 \\
    --offset 3

Algorithm:
  1. For each road without a date (sd):
     a. Find buildings within buffer distance (default 50m)
     b. Take EARLIEST building construction date
     c. Subtract offset years (default 2) for road date
  2. If no nearby buildings, use map era if ML source
  3. Ultimate fallback: 1960
        """
    )

    parser.add_argument('--roads', type=Path, required=True,
                        help='Input roads GeoJSON')
    parser.add_argument('--buildings', type=Path, required=True,
                        help='Buildings GeoJSON with dates')
    parser.add_argument('--output', type=Path, required=True,
                        help='Output roads GeoJSON with dates')
    parser.add_argument('--buffer', type=float, default=50,
                        help='Search radius in meters (default: 50)')
    parser.add_argument('--offset', type=int, default=2,
                        help='Years to subtract from building date (default: 2)')

    args = parser.parse_args()

    # Validate inputs
    if not args.roads.exists():
        print(f"ERROR: Roads file not found: {args.roads}")
        sys.exit(1)

    if not args.buildings.exists():
        print(f"ERROR: Buildings file not found: {args.buildings}")
        sys.exit(1)

    # Create output directory if needed
    args.output.parent.mkdir(parents=True, exist_ok=True)

    try:
        infer_road_dates(
            args.roads,
            args.buildings,
            args.output,
            args.buffer,
            args.offset
        )
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
