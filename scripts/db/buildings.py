#!/usr/bin/env python3
"""
Building record management.
"""

import json
import sqlite3
from typing import Dict, List, Optional, Any
from dataclasses import dataclass


@dataclass
class Building:
    """Building record."""
    building_id: str
    geometry: Optional[Dict] = None
    geometry_source: Optional[str] = None
    centroid_lon: Optional[float] = None
    centroid_lat: Optional[float] = None
    building_type: Optional[str] = None
    name: Optional[str] = None
    est_start_year: Optional[int] = None
    est_end_year: Optional[int] = None
    est_confidence: Optional[float] = None
    est_method: Optional[str] = None


def calculate_centroid(geometry: Dict) -> tuple:
    """Calculate centroid from GeoJSON geometry."""
    geom_type = geometry.get('type', '')
    coords = geometry.get('coordinates', [])

    if geom_type == 'Point':
        return coords[0], coords[1]

    elif geom_type == 'Polygon':
        # Average of exterior ring
        ring = coords[0] if coords else []
        if not ring:
            return None, None
        lon = sum(p[0] for p in ring) / len(ring)
        lat = sum(p[1] for p in ring) / len(ring)
        return lon, lat

    elif geom_type == 'MultiPolygon':
        # Average of all points
        all_points = []
        for polygon in coords:
            if polygon:
                all_points.extend(polygon[0])
        if not all_points:
            return None, None
        lon = sum(p[0] for p in all_points) / len(all_points)
        lat = sum(p[1] for p in all_points) / len(all_points)
        return lon, lat

    return None, None


def upsert_building(
    conn: sqlite3.Connection,
    building_id: str,
    geometry: Optional[Dict] = None,
    geometry_source: Optional[str] = None,
    building_type: Optional[str] = None,
    name: Optional[str] = None,
    update_geometry: bool = True
) -> None:
    """Insert or update a building record."""

    # Check if building exists
    existing = conn.execute(
        "SELECT building_id, geometry_source FROM buildings WHERE building_id = ?",
        (building_id,)
    ).fetchone()

    if existing:
        # Update existing
        updates = []
        params = []

        if building_type:
            updates.append("building_type = ?")
            params.append(building_type)

        if name:
            updates.append("name = ?")
            params.append(name)

        if geometry and update_geometry:
            # Only update geometry if new source is higher priority
            lon, lat = calculate_centroid(geometry)
            updates.append("geometry_json = ?")
            params.append(json.dumps(geometry))
            updates.append("geometry_source = ?")
            params.append(geometry_source)
            updates.append("centroid_lon = ?")
            params.append(lon)
            updates.append("centroid_lat = ?")
            params.append(lat)

        if updates:
            updates.append("updated_at = CURRENT_TIMESTAMP")
            params.append(building_id)
            conn.execute(
                f"UPDATE buildings SET {', '.join(updates)} WHERE building_id = ?",
                params
            )
    else:
        # Insert new
        lon, lat = None, None
        geom_json = None
        if geometry:
            lon, lat = calculate_centroid(geometry)
            geom_json = json.dumps(geometry)

        conn.execute("""
            INSERT INTO buildings
            (building_id, geometry_json, geometry_source, centroid_lon, centroid_lat, building_type, name)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (building_id, geom_json, geometry_source, lon, lat, building_type, name))


def get_building(conn: sqlite3.Connection, building_id: str) -> Optional[Building]:
    """Get a building by ID."""
    row = conn.execute(
        "SELECT * FROM buildings WHERE building_id = ?",
        (building_id,)
    ).fetchone()

    if not row:
        return None

    geometry = None
    if row['geometry_json']:
        geometry = json.loads(row['geometry_json'])

    return Building(
        building_id=row['building_id'],
        geometry=geometry,
        geometry_source=row['geometry_source'],
        centroid_lon=row['centroid_lon'],
        centroid_lat=row['centroid_lat'],
        building_type=row['building_type'],
        name=row['name'],
        est_start_year=row['est_start_year'],
        est_end_year=row['est_end_year'],
        est_confidence=row['est_confidence'],
        est_method=row['est_method'],
    )


def get_buildings_in_bbox(
    conn: sqlite3.Connection,
    min_lon: float,
    min_lat: float,
    max_lon: float,
    max_lat: float,
    limit: int = 10000
) -> List[Building]:
    """Get buildings within bounding box."""
    rows = conn.execute("""
        SELECT * FROM buildings
        WHERE centroid_lon >= ? AND centroid_lon <= ?
          AND centroid_lat >= ? AND centroid_lat <= ?
        LIMIT ?
    """, (min_lon, max_lon, min_lat, max_lat, limit)).fetchall()

    buildings = []
    for row in rows:
        geometry = None
        if row['geometry_json']:
            geometry = json.loads(row['geometry_json'])

        buildings.append(Building(
            building_id=row['building_id'],
            geometry=geometry,
            geometry_source=row['geometry_source'],
            centroid_lon=row['centroid_lon'],
            centroid_lat=row['centroid_lat'],
            building_type=row['building_type'],
            name=row['name'],
            est_start_year=row['est_start_year'],
            est_end_year=row['est_end_year'],
            est_confidence=row['est_confidence'],
            est_method=row['est_method'],
        ))

    return buildings


def get_buildings_with_estimates(
    conn: sqlite3.Connection,
    min_year: Optional[int] = None,
    max_year: Optional[int] = None,
    min_confidence: Optional[float] = None,
    limit: int = 10000
) -> List[Building]:
    """Get buildings with date estimates, optionally filtered."""
    conditions = ["est_start_year IS NOT NULL"]
    params = []

    if min_year:
        conditions.append("est_start_year >= ?")
        params.append(min_year)

    if max_year:
        conditions.append("est_start_year <= ?")
        params.append(max_year)

    if min_confidence:
        conditions.append("est_confidence >= ?")
        params.append(min_confidence)

    params.append(limit)

    query = f"""
        SELECT * FROM buildings
        WHERE {' AND '.join(conditions)}
        ORDER BY est_start_year
        LIMIT ?
    """

    rows = conn.execute(query, params).fetchall()

    buildings = []
    for row in rows:
        geometry = None
        if row['geometry_json']:
            geometry = json.loads(row['geometry_json'])

        buildings.append(Building(
            building_id=row['building_id'],
            geometry=geometry,
            geometry_source=row['geometry_source'],
            centroid_lon=row['centroid_lon'],
            centroid_lat=row['centroid_lat'],
            building_type=row['building_type'],
            name=row['name'],
            est_start_year=row['est_start_year'],
            est_end_year=row['est_end_year'],
            est_confidence=row['est_confidence'],
            est_method=row['est_method'],
        ))

    return buildings


def update_building_estimate(
    conn: sqlite3.Connection,
    building_id: str,
    start_year: Optional[int],
    end_year: Optional[int],
    confidence: float,
    method: str
) -> None:
    """Update the denormalized estimate on a building."""
    conn.execute("""
        UPDATE buildings
        SET est_start_year = ?,
            est_end_year = ?,
            est_confidence = ?,
            est_method = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE building_id = ?
    """, (start_year, end_year, confidence, method, building_id))
