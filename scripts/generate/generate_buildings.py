#!/usr/bin/env python3
"""
Generate procedural building footprints within parcels.

Fills parcels with plausible 1800s-era building footprints using
rule-based procedural generation with era-appropriate constraints.

Parameters (1800s Trondheim):
- Building width: 6-12m (typical wooden house)
- Building depth: 8-15m (pre-industrial construction)
- Setback: 0-2m (often built to street edge)
- Coverage: 60-80% of parcel
- Gap probability: 20% (fire breaks, alleys)

Usage:
    python scripts/generate/generate_buildings.py \
        --parcels data/sources/generated/kv1880/parcels.geojson \
        --output data/sources/generated/kv1880/buildings.geojson \
        --year 1880

Or generate directly from zones:
    python scripts/generate/generate_buildings.py \
        --zones data/sources/generated/zones/test_zone.geojson \
        --streets data/roads_temporal.geojson \
        --output data/sources/generated/kv1880/buildings.geojson \
        --year 1880
"""

import argparse
import json
import math
import random
from pathlib import Path
from typing import List, Tuple, Optional

from shapely.geometry import Polygon, LineString, Point, box, mapping, shape
from shapely.affinity import rotate, translate
from shapely.ops import unary_union
import numpy as np


# Building generation parameters (1800s era)
BUILDING_WIDTH_MIN = 6.0   # meters
BUILDING_WIDTH_MAX = 12.0  # meters
BUILDING_DEPTH_MIN = 8.0   # meters
BUILDING_DEPTH_MAX = 15.0  # meters
SETBACK_MIN = 0.0          # meters (from parcel edge)
SETBACK_MAX = 2.0          # meters
COVERAGE_TARGET = 0.7      # 70% coverage
GAP_PROBABILITY = 0.2      # 20% chance of gap
SIZE_VARIATION = 0.15      # ±15% size variation
ROTATION_VARIATION = 5.0   # ±5 degrees rotation jitter
POSITION_JITTER = 1.0      # ±1 meter position jitter


def meters_to_degrees(meters: float, latitude: float = 63.43) -> float:
    """Convert meters to approximate degrees at given latitude."""
    lat_factor = 111000
    return meters / lat_factor


def degrees_to_meters(degrees: float, latitude: float = 63.43) -> float:
    """Convert degrees to approximate meters."""
    lat_factor = 111000
    return degrees * lat_factor


def get_parcel_orientation(parcel: Polygon) -> float:
    """
    Determine the primary orientation angle of a parcel.
    Returns angle in degrees.
    """
    import warnings

    # Get the minimum rotated rectangle, suppress warnings for edge cases
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            min_rect = parcel.minimum_rotated_rectangle
        except Exception:
            return 0

    if min_rect is None or min_rect.is_empty or min_rect.geom_type != 'Polygon':
        return 0

    coords = list(min_rect.exterior.coords)

    # Find the longer edge to determine orientation
    edges = []
    for i in range(len(coords) - 1):
        dx = coords[i+1][0] - coords[i][0]
        dy = coords[i+1][1] - coords[i][1]
        length = math.sqrt(dx*dx + dy*dy)
        angle = math.degrees(math.atan2(dy, dx))
        edges.append((length, angle))

    # Return angle of shortest edge (building faces street)
    edges.sort(key=lambda x: x[0])
    return edges[0][1] if edges else 0


def generate_building_in_parcel(parcel: Polygon, year: int,
                                 zone_id: str = "",
                                 seed: Optional[int] = None) -> Optional[dict]:
    """
    Generate a building footprint within a parcel.

    Args:
        parcel: Parcel polygon
        year: Construction year for the building
        zone_id: Zone identifier for grouping
        seed: Random seed for reproducibility

    Returns:
        GeoJSON feature dict or None if skipped
    """
    if seed is not None:
        random.seed(seed)

    # 20% chance to skip (creates gaps for fire breaks, alleys)
    if random.random() < GAP_PROBABILITY:
        return None

    # Get parcel properties
    centroid = parcel.centroid
    lat = centroid.y

    # Calculate parcel dimensions in meters
    bounds = parcel.bounds
    parcel_width_deg = bounds[2] - bounds[0]
    parcel_height_deg = bounds[3] - bounds[1]

    # Rough conversion (longitude degrees smaller at high latitudes)
    lon_factor = 111000 * math.cos(math.radians(lat))
    lat_factor = 111000

    parcel_width_m = parcel_width_deg * lon_factor
    parcel_height_m = parcel_height_deg * lat_factor
    parcel_area_m2 = parcel.area * lon_factor * lat_factor

    # Determine building size with variation
    variation = 1.0 + random.uniform(-SIZE_VARIATION, SIZE_VARIATION)

    building_width = random.uniform(BUILDING_WIDTH_MIN, BUILDING_WIDTH_MAX) * variation
    building_depth = random.uniform(BUILDING_DEPTH_MIN, BUILDING_DEPTH_MAX) * variation

    # Ensure building fits in parcel
    max_width = parcel_width_m - SETBACK_MIN * 2
    max_depth = parcel_height_m - SETBACK_MIN * 2

    building_width = min(building_width, max_width * 0.9)
    building_depth = min(building_depth, max_depth * 0.9)

    if building_width < BUILDING_WIDTH_MIN * 0.5 or building_depth < BUILDING_DEPTH_MIN * 0.5:
        return None  # Parcel too small

    # Convert to degrees
    building_width_deg = building_width / lon_factor
    building_depth_deg = building_depth / lat_factor

    # Get parcel orientation
    base_angle = get_parcel_orientation(parcel)

    # Add rotation jitter
    rotation = base_angle + random.uniform(-ROTATION_VARIATION, ROTATION_VARIATION)

    # Calculate setback
    setback_m = random.uniform(SETBACK_MIN, SETBACK_MAX)
    setback_deg = setback_m / lat_factor

    # Create building rectangle centered on parcel centroid
    half_w = building_width_deg / 2
    half_h = building_depth_deg / 2

    building = box(
        centroid.x - half_w,
        centroid.y - half_h,
        centroid.x + half_w,
        centroid.y + half_h
    )

    # Apply rotation
    building = rotate(building, rotation, origin=centroid)

    # Apply position jitter
    jitter_m = random.uniform(-POSITION_JITTER, POSITION_JITTER)
    jitter_deg = jitter_m / lat_factor
    building = translate(building, jitter_deg, jitter_deg)

    # Clip to parcel (with small buffer for setback)
    parcel_inner = parcel.buffer(-setback_deg) if setback_deg > 0 else parcel
    if parcel_inner.is_empty or not parcel_inner.is_valid:
        parcel_inner = parcel

    building = building.intersection(parcel_inner)

    if building.is_empty or not building.is_valid:
        return None

    # Ensure we have a polygon
    if building.geom_type == 'MultiPolygon':
        building = max(building.geoms, key=lambda g: g.area)
    elif building.geom_type != 'Polygon':
        return None

    # Calculate actual building area
    building_area_m2 = building.area * lon_factor * lat_factor

    if building_area_m2 < 20:  # Less than 20 m²
        return None

    # Create feature
    feature = {
        "type": "Feature",
        "properties": {
            "src": "gen",
            "sd": year,
            "sd_t": "n",  # not-later-than
            "ev": "l",    # low evidence (generated)
            "gen": True,
            "gen_src": f"kv{year}",
            "gen_zone": zone_id,
            "gen_conf": 0.5,  # Zone detection quality (placeholder)
            "area_m2": round(building_area_m2, 1),
        },
        "geometry": mapping(building)
    }

    return feature


def generate_buildings_for_parcels(parcels: List[dict], year: int,
                                    base_seed: int = 42) -> List[dict]:
    """
    Generate buildings for all parcels.

    Args:
        parcels: List of parcel GeoJSON features
        year: Construction year
        base_seed: Base random seed for reproducibility

    Returns:
        List of building GeoJSON features
    """
    buildings = []

    for i, parcel_feature in enumerate(parcels):
        parcel = shape(parcel_feature['geometry'])
        zone_id = parcel_feature.get('properties', {}).get('zone_id', '')
        parcel_id = parcel_feature.get('properties', {}).get('id', f'parcel_{i}')

        # Use deterministic seed per parcel
        seed = base_seed + hash(parcel_id) % 1000000

        building = generate_building_in_parcel(
            parcel, year, zone_id, seed
        )

        if building:
            building['properties']['parcel_id'] = parcel_id
            buildings.append(building)

    return buildings


def load_geojson(path: Path) -> dict:
    """Load GeoJSON file."""
    with open(path) as f:
        return json.load(f)


def main():
    parser = argparse.ArgumentParser(description='Generate procedural buildings')
    parser.add_argument('--parcels', type=str,
                        help='GeoJSON file with parcel polygons')
    parser.add_argument('--zones', type=str,
                        help='GeoJSON file with zone polygons (alternative to parcels)')
    parser.add_argument('--streets', type=str,
                        help='GeoJSON file with street network (required with --zones)')
    parser.add_argument('--output', type=str, required=True,
                        help='Output GeoJSON file for buildings')
    parser.add_argument('--year', type=int, default=1880,
                        help='Map/construction year (default: 1880)')
    parser.add_argument('--seed', type=int, default=42,
                        help='Random seed for reproducibility (default: 42)')
    args = parser.parse_args()

    # Determine input mode
    if args.parcels:
        print(f"Loading parcels from {args.parcels}...")
        parcels_geojson = load_geojson(Path(args.parcels))
        parcels = parcels_geojson.get('features', [])
        print(f"  Found {len(parcels)} parcels")

    elif args.zones:
        if not args.streets:
            parser.error("--streets is required when using --zones")

        # Import subdivision module
        from subdivide_parcels import (
            extract_polygons, extract_linestrings, subdivide_zones
        )

        print(f"Loading zones from {args.zones}...")
        zones_geojson = load_geojson(Path(args.zones))
        zones = extract_polygons(zones_geojson)
        print(f"  Found {len(zones)} zones")

        print(f"Loading streets from {args.streets}...")
        streets_geojson = load_geojson(Path(args.streets))
        streets = extract_linestrings(streets_geojson)
        print(f"  Found {len(streets)} street segments")

        print("\nSubdividing zones into parcels...")
        parcels = subdivide_zones(zones, streets)
        print(f"  Created {len(parcels)} parcels")

    else:
        parser.error("Either --parcels or --zones is required")

    print(f"\nGenerating buildings (year: {args.year}, seed: {args.seed})...")
    buildings = generate_buildings_for_parcels(parcels, args.year, args.seed)
    print(f"  Generated {len(buildings)} buildings")
    print(f"  ({len(parcels) - len(buildings)} parcels skipped for gaps)")

    # Create output GeoJSON
    output = {
        "type": "FeatureCollection",
        "features": buildings
    }

    # Write output
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2)

    print(f"\nOutput written to {args.output}")

    # Summary stats
    if buildings:
        areas = [b['properties']['area_m2'] for b in buildings]
        print(f"\nBuilding statistics:")
        print(f"  Count: {len(buildings)}")
        print(f"  Area range: {min(areas):.1f} - {max(areas):.1f} m²")
        print(f"  Mean area: {sum(areas)/len(areas):.1f} m²")


if __name__ == '__main__':
    main()
