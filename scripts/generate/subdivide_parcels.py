#!/usr/bin/env python3
"""
Subdivide built-up zones into parcels based on street network.

Algorithm:
1. For each zone polygon, find adjacent street segments
2. Create perpendicular lot lines from street edges at regular intervals
3. Extend lines to zone boundary or opposing street
4. Form parcel polygons between lot lines

Usage:
    python scripts/generate/subdivide_parcels.py \
        --zones data/sources/generated/zones/test_zone.geojson \
        --streets data/roads_temporal.geojson \
        --output data/sources/generated/kv1880/parcels.geojson
"""

import argparse
import json
import math
from pathlib import Path
from typing import List, Tuple, Optional

from shapely.geometry import (
    Polygon, LineString, MultiPolygon, Point,
    box, mapping, shape
)
from shapely.ops import split, unary_union, linemerge
import numpy as np


# Parcel parameters
LOT_WIDTH_MIN = 8.0   # meters
LOT_WIDTH_MAX = 15.0  # meters
LOT_WIDTH_DEFAULT = 10.0  # meters
LOT_DEPTH_MIN = 15.0  # meters
LOT_DEPTH_MAX = 25.0  # meters


def meters_to_degrees(meters: float, latitude: float = 63.43) -> float:
    """Convert meters to approximate degrees at given latitude."""
    # At 63.43°N (Trondheim), 1 degree latitude ≈ 111km, longitude ≈ 49km
    lat_factor = 111000
    return meters / lat_factor


def degrees_to_meters(degrees: float, latitude: float = 63.43) -> float:
    """Convert degrees to approximate meters at given latitude."""
    lat_factor = 111000
    return degrees * lat_factor


def get_street_segments_in_zone(zone: Polygon, streets: List[LineString],
                                 buffer_dist: float = 0.0001) -> List[LineString]:
    """Find street segments that are within or adjacent to zone."""
    zone_buffered = zone.buffer(buffer_dist)
    segments = []

    for street in streets:
        if zone_buffered.intersects(street):
            intersection = zone_buffered.intersection(street)
            if intersection.geom_type == 'LineString' and intersection.length > 0:
                segments.append(intersection)
            elif intersection.geom_type == 'MultiLineString':
                for line in intersection.geoms:
                    if line.length > 0:
                        segments.append(line)

    return segments


def perpendicular_line(point: Point, angle: float, length: float) -> LineString:
    """Create a line perpendicular to given angle, centered on point."""
    # Perpendicular angle
    perp_angle = angle + math.pi / 2

    dx = math.cos(perp_angle) * length / 2
    dy = math.sin(perp_angle) * length / 2

    return LineString([
        (point.x - dx, point.y - dy),
        (point.x + dx, point.y + dy)
    ])


def get_line_angle(line: LineString) -> float:
    """Get angle of line segment in radians."""
    coords = list(line.coords)
    if len(coords) < 2:
        return 0

    dx = coords[-1][0] - coords[0][0]
    dy = coords[-1][1] - coords[0][1]

    return math.atan2(dy, dx)


def subdivide_along_street(zone: Polygon, street: LineString,
                           lot_width: float = LOT_WIDTH_DEFAULT) -> List[Polygon]:
    """
    Create lot lines perpendicular to street and subdivide zone.

    Args:
        zone: Zone polygon to subdivide
        street: Street segment along zone
        lot_width: Target lot width in degrees

    Returns:
        List of parcel polygons
    """
    parcels = []

    # Get the portion of street that's near the zone
    zone_boundary = zone.exterior

    # Calculate number of lots based on street length
    street_length = street.length
    num_lots = max(1, int(street_length / lot_width))
    actual_width = street_length / num_lots

    # Get street angle for perpendicular lines
    angle = get_line_angle(street)

    # Create lot divider lines
    lot_lines = []
    for i in range(num_lots + 1):
        # Point along street
        fraction = i / num_lots
        point = street.interpolate(fraction, normalized=True)

        # Create perpendicular line extending into zone
        # Use zone bounds to determine line length
        max_dim = max(zone.bounds[2] - zone.bounds[0],
                      zone.bounds[3] - zone.bounds[1])
        perp_line = perpendicular_line(Point(point.x, point.y),
                                       angle, max_dim * 2)

        # Clip to zone
        clipped = zone.intersection(perp_line)
        if clipped.geom_type == 'LineString' and clipped.length > 0:
            lot_lines.append(clipped)

    if len(lot_lines) < 2:
        return [zone]

    # Use lot lines to split zone
    # Merge all lot lines into splitting geometry
    all_lines = unary_union(lot_lines + [zone.exterior])

    # Try to create parcels between consecutive lot lines
    for i in range(len(lot_lines) - 1):
        line1 = lot_lines[i]
        line2 = lot_lines[i + 1]

        # Create polygon between two lot lines
        try:
            # Get endpoints on zone boundary
            coords1 = list(line1.coords)
            coords2 = list(line2.coords)

            # Form quadrilateral
            parcel_coords = [
                coords1[0], coords1[-1],
                coords2[-1], coords2[0],
                coords1[0]
            ]

            parcel = Polygon(parcel_coords)
            parcel = parcel.intersection(zone)

            if parcel.is_valid and parcel.area > 0:
                if parcel.geom_type == 'Polygon':
                    parcels.append(parcel)
                elif parcel.geom_type == 'MultiPolygon':
                    parcels.extend(list(parcel.geoms))
        except Exception:
            continue

    return parcels if parcels else [zone]


def subdivide_zone(zone: Polygon, streets: List[LineString],
                   lot_width_m: float = LOT_WIDTH_DEFAULT) -> List[Polygon]:
    """
    Subdivide a zone into parcels based on adjacent streets.

    Args:
        zone: Zone polygon to subdivide
        streets: List of street LineStrings
        lot_width_m: Target lot width in meters

    Returns:
        List of parcel polygons
    """
    # Convert lot width to degrees
    centroid = zone.centroid
    lot_width = meters_to_degrees(lot_width_m, centroid.y)

    # Find streets near/in zone
    street_segments = get_street_segments_in_zone(zone, streets)

    if not street_segments:
        # No streets - return zone as single parcel
        return [zone]

    # Pick the longest street segment as primary
    primary_street = max(street_segments, key=lambda s: s.length)

    # Subdivide along primary street
    parcels = subdivide_along_street(zone, primary_street, lot_width)

    # Filter out tiny parcels
    min_area = meters_to_degrees(LOT_WIDTH_MIN, centroid.y) * \
               meters_to_degrees(LOT_DEPTH_MIN, centroid.y)
    parcels = [p for p in parcels if p.area >= min_area * 0.5]

    return parcels


def subdivide_zones(zones: List[Polygon], streets: List[LineString],
                    lot_width_m: float = LOT_WIDTH_DEFAULT) -> List[dict]:
    """
    Subdivide multiple zones into parcels.

    Returns list of parcel features with properties.
    """
    features = []
    parcel_id = 0

    for zone_idx, zone in enumerate(zones):
        parcels = subdivide_zone(zone, streets, lot_width_m)

        for parcel in parcels:
            if parcel.is_valid and parcel.area > 0:
                # Calculate parcel properties
                centroid = parcel.centroid
                area_m2 = parcel.area * (111000 ** 2) * \
                          math.cos(math.radians(centroid.y))

                feature = {
                    "type": "Feature",
                    "properties": {
                        "id": f"parcel_{parcel_id:04d}",
                        "zone_id": f"zone_{zone_idx:03d}",
                        "area_m2": round(area_m2, 1),
                    },
                    "geometry": mapping(parcel)
                }
                features.append(feature)
                parcel_id += 1

    return features


def load_geojson(path: Path) -> dict:
    """Load GeoJSON file."""
    with open(path) as f:
        return json.load(f)


def extract_polygons(geojson: dict) -> List[Polygon]:
    """Extract Polygon geometries from GeoJSON."""
    polygons = []

    features = geojson.get('features', [])
    for feature in features:
        geom = shape(feature['geometry'])
        if geom.geom_type == 'Polygon':
            polygons.append(geom)
        elif geom.geom_type == 'MultiPolygon':
            polygons.extend(list(geom.geoms))

    return polygons


def extract_linestrings(geojson: dict) -> List[LineString]:
    """Extract LineString geometries from GeoJSON."""
    lines = []

    features = geojson.get('features', [])
    for feature in features:
        geom = shape(feature['geometry'])
        if geom.geom_type == 'LineString':
            lines.append(geom)
        elif geom.geom_type == 'MultiLineString':
            lines.extend(list(geom.geoms))

    return lines


def main():
    parser = argparse.ArgumentParser(description='Subdivide zones into parcels')
    parser.add_argument('--zones', type=str, required=True,
                        help='GeoJSON file with zone polygons')
    parser.add_argument('--streets', type=str, required=True,
                        help='GeoJSON file with street network')
    parser.add_argument('--output', type=str, required=True,
                        help='Output GeoJSON file for parcels')
    parser.add_argument('--lot-width', type=float, default=LOT_WIDTH_DEFAULT,
                        help=f'Target lot width in meters (default: {LOT_WIDTH_DEFAULT})')
    args = parser.parse_args()

    print(f"Loading zones from {args.zones}...")
    zones_geojson = load_geojson(Path(args.zones))
    zones = extract_polygons(zones_geojson)
    print(f"  Found {len(zones)} zones")

    print(f"Loading streets from {args.streets}...")
    streets_geojson = load_geojson(Path(args.streets))
    streets = extract_linestrings(streets_geojson)
    print(f"  Found {len(streets)} street segments")

    print(f"\nSubdividing zones into parcels (target lot width: {args.lot_width}m)...")
    parcel_features = subdivide_zones(zones, streets, args.lot_width)
    print(f"  Created {len(parcel_features)} parcels")

    # Create output GeoJSON
    output = {
        "type": "FeatureCollection",
        "features": parcel_features
    }

    # Write output
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2)

    print(f"\nOutput written to {args.output}")


if __name__ == '__main__':
    main()
