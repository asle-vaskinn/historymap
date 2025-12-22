#!/usr/bin/env python3
"""
Spatial matching between buildings from different sources.

Matches buildings across sources (e.g., ML-extracted ↔ OSM ↔ SEFRAK)
to combine evidence and improve date estimates.
"""

import json
import sqlite3
import sys
from pathlib import Path
from typing import List, Tuple, Optional, Dict
from dataclasses import dataclass

sys.path.insert(0, str(Path(__file__).parent.parent))

from db.schema import init_db, get_connection
from db.evidence import Evidence, add_evidence, get_evidence_for_building, calculate_best_estimate, save_estimate

# Try to import shapely for spatial operations
try:
    from shapely.geometry import shape, Point
    from shapely.strtree import STRtree
    HAS_SHAPELY = True
except ImportError:
    HAS_SHAPELY = False
    print("Warning: shapely not installed. Spatial matching will be limited.")


@dataclass
class BuildingMatch:
    """A match between two buildings from different sources."""
    building_id_1: str
    building_id_2: str
    source_1: str
    source_2: str
    overlap_ratio: float
    distance_m: float


def load_buildings_with_geometry(conn: sqlite3.Connection, source_filter: Optional[str] = None) -> List[Dict]:
    """Load buildings with geometry from database."""
    query = """
        SELECT building_id, geometry_json, geometry_source,
               centroid_lon, centroid_lat, est_start_year
        FROM buildings
        WHERE geometry_json IS NOT NULL
    """
    params = []

    if source_filter:
        query += " AND geometry_source = ?"
        params.append(source_filter)

    rows = conn.execute(query, params).fetchall()

    buildings = []
    for row in rows:
        geom = None
        if row['geometry_json']:
            try:
                geom = json.loads(row['geometry_json'])
            except:
                continue

        buildings.append({
            'building_id': row['building_id'],
            'geometry': geom,
            'geometry_source': row['geometry_source'],
            'centroid': (row['centroid_lon'], row['centroid_lat']),
            'est_start_year': row['est_start_year']
        })

    return buildings


def calculate_overlap(geom1: Dict, geom2: Dict) -> float:
    """Calculate overlap ratio between two geometries."""
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
    except:
        return 0.0


def calculate_centroid_distance(c1: Tuple[float, float], c2: Tuple[float, float]) -> float:
    """Calculate approximate distance in meters between two centroids."""
    if None in c1 or None in c2:
        return float('inf')

    # Simple approximation for Norway (1 degree lat ≈ 111km, 1 degree lon ≈ 55km at 63°N)
    dlat = (c1[1] - c2[1]) * 111000
    dlon = (c1[0] - c2[0]) * 55000

    return (dlat**2 + dlon**2) ** 0.5


def find_matches(
    source_buildings: List[Dict],
    target_buildings: List[Dict],
    max_distance_m: float = 30.0,
    min_overlap: float = 0.1  # Lower threshold for historical map matching
) -> List[BuildingMatch]:
    """Find matching buildings between two sources."""

    matches = []

    if not HAS_SHAPELY:
        # Fallback: centroid distance only
        for src in source_buildings:
            best_match = None
            best_distance = float('inf')

            for tgt in target_buildings:
                dist = calculate_centroid_distance(src['centroid'], tgt['centroid'])

                if dist < max_distance_m and dist < best_distance:
                    best_distance = dist
                    best_match = tgt

            if best_match:
                matches.append(BuildingMatch(
                    building_id_1=src['building_id'],
                    building_id_2=best_match['building_id'],
                    source_1=src['geometry_source'],
                    source_2=best_match['geometry_source'],
                    overlap_ratio=0.0,
                    distance_m=best_distance
                ))

        return matches

    # Build spatial index for target buildings
    target_shapes = []
    target_data = []  # Parallel list of building data

    for tgt in target_buildings:
        try:
            shp = shape(tgt['geometry'])
            if shp.is_valid:
                # Buffer point geometries for matching
                if shp.geom_type == 'Point':
                    shp = shp.buffer(0.0001)  # ~10m buffer
                target_shapes.append(shp)
                target_data.append(tgt)
        except:
            continue

    if not target_shapes:
        return matches

    index = STRtree(target_shapes)

    # Find matches for each source building
    for src in source_buildings:
        try:
            src_shape = shape(src['geometry'])
            if not src_shape.is_valid:
                continue

            # Buffer for point geometries
            query_shape = src_shape
            if src_shape.geom_type == 'Point':
                query_shape = src_shape.buffer(0.0002)  # ~20m buffer

            # Query spatial index - returns indices in shapely 2.0
            candidate_indices = index.query(query_shape)

            # Handle numpy array from shapely 2.0
            if hasattr(candidate_indices, '__len__') and len(candidate_indices) == 0:
                continue

            best_match = None
            best_overlap = 0.0
            best_distance = float('inf')

            for idx in candidate_indices:
                idx = int(idx)  # Convert numpy int to Python int
                candidate_shape = target_shapes[idx]
                tgt = target_data[idx]

                # Calculate overlap
                try:
                    intersection = src_shape.intersection(candidate_shape)
                    if not intersection.is_empty:
                        min_area = min(src_shape.area, candidate_shape.area)
                        if min_area > 0:
                            overlap = intersection.area / min_area
                        else:
                            overlap = 0.0
                    else:
                        overlap = 0.0
                except:
                    overlap = 0.0

                # Calculate centroid distance
                dist = calculate_centroid_distance(src['centroid'], tgt['centroid'])

                # Pick best match by overlap, then distance
                if overlap >= min_overlap and overlap > best_overlap:
                    best_overlap = overlap
                    best_distance = dist
                    best_match = tgt
                elif overlap < min_overlap and dist < max_distance_m and dist < best_distance:
                    if best_overlap < min_overlap:  # Only if no good overlap match
                        best_distance = dist
                        best_match = tgt

            if best_match:
                matches.append(BuildingMatch(
                    building_id_1=src['building_id'],
                    building_id_2=best_match['building_id'],
                    source_1=src['geometry_source'],
                    source_2=best_match['geometry_source'],
                    overlap_ratio=best_overlap,
                    distance_m=best_distance
                ))

        except Exception as e:
            continue

    return matches


def propagate_evidence(conn: sqlite3.Connection, matches: List[BuildingMatch]) -> int:
    """
    Propagate evidence between matched buildings.

    For each match, copy evidence from one building to the other,
    adjusting confidence based on match quality.
    """
    propagated = 0

    for match in matches:
        # Get evidence from both buildings
        ev1 = get_evidence_for_building(conn, match.building_id_1)
        ev2 = get_evidence_for_building(conn, match.building_id_2)

        # Calculate match confidence
        if match.overlap_ratio >= 0.7:
            match_confidence = 0.9
        elif match.overlap_ratio >= 0.5:
            match_confidence = 0.8
        elif match.overlap_ratio >= 0.3:
            match_confidence = 0.7
        elif match.distance_m < 5:
            match_confidence = 0.7
        elif match.distance_m < 10:
            match_confidence = 0.6
        else:
            match_confidence = 0.5

        # Propagate evidence from 1 to 2
        for ev in ev1:
            # Create new evidence for building 2
            new_ev = Evidence(
                building_id=match.building_id_2,
                source_id=ev.source_id,
                evidence_type=ev.evidence_type,
                min_year=ev.min_year,
                max_year=ev.max_year,
                exact_year=ev.exact_year,
                end_year=ev.end_year,
                confidence=ev.confidence * match_confidence,
                confidence_reason=f"propagated_from_{match.building_id_1}",
                source_local_id=ev.source_local_id,
                method='propagated'
            )

            # Only add if building 2 doesn't already have evidence from this source
            existing_sources = {e.source_id for e in ev2}
            if ev.source_id not in existing_sources:
                add_evidence(conn, new_ev)
                propagated += 1

        # Propagate evidence from 2 to 1
        for ev in ev2:
            new_ev = Evidence(
                building_id=match.building_id_1,
                source_id=ev.source_id,
                evidence_type=ev.evidence_type,
                min_year=ev.min_year,
                max_year=ev.max_year,
                exact_year=ev.exact_year,
                end_year=ev.end_year,
                confidence=ev.confidence * match_confidence,
                confidence_reason=f"propagated_from_{match.building_id_2}",
                source_local_id=ev.source_local_id,
                method='propagated'
            )

            existing_sources = {e.source_id for e in ev1}
            if ev.source_id not in existing_sources:
                add_evidence(conn, new_ev)
                propagated += 1

    conn.commit()
    return propagated


def main():
    """Run spatial matching between sources."""
    print("Spatial Matching Between Sources")
    print("=" * 50)

    conn = init_db()

    # Load buildings by source
    print("\nLoading buildings...")
    osm_buildings = load_buildings_with_geometry(conn, 'osm')
    print(f"  OSM: {len(osm_buildings)} buildings")

    sefrak_buildings = load_buildings_with_geometry(conn, 'sefrak')
    print(f"  SEFRAK: {len(sefrak_buildings)} buildings")

    map_1880_buildings = load_buildings_with_geometry(conn, 'map_1880')
    print(f"  Map 1880: {len(map_1880_buildings)} buildings")

    # Match SEFRAK to OSM
    print("\nMatching SEFRAK → OSM...")
    sefrak_osm_matches = find_matches(sefrak_buildings, osm_buildings, max_distance_m=30)
    print(f"  Found {len(sefrak_osm_matches)} matches")

    # Match 1880 map to OSM
    print("\nMatching Map 1880 → OSM...")
    map_osm_matches = find_matches(map_1880_buildings, osm_buildings, max_distance_m=30)
    print(f"  Found {len(map_osm_matches)} matches")

    # Propagate evidence
    all_matches = sefrak_osm_matches + map_osm_matches
    print(f"\nPropagating evidence for {len(all_matches)} matches...")
    propagated = propagate_evidence(conn, all_matches)
    print(f"  Propagated {propagated} evidence records")

    # Recalculate estimates for matched buildings
    print("\nRecalculating estimates for matched buildings...")
    matched_ids = set()
    for m in all_matches:
        matched_ids.add(m.building_id_1)
        matched_ids.add(m.building_id_2)

    updated = 0
    for building_id in matched_ids:
        evidences = get_evidence_for_building(conn, building_id)
        if evidences:
            estimate = calculate_best_estimate(evidences)
            save_estimate(conn, estimate)
            updated += 1

    print(f"  Updated {updated} building estimates")

    # Show statistics
    print("\nMatch Statistics:")

    # SEFRAK-OSM matches
    good_sefrak = sum(1 for m in sefrak_osm_matches if m.overlap_ratio >= 0.5)
    print(f"  SEFRAK-OSM: {len(sefrak_osm_matches)} total, {good_sefrak} high quality (≥50% overlap)")

    # Map-OSM matches
    good_map = sum(1 for m in map_osm_matches if m.overlap_ratio >= 0.5)
    print(f"  Map1880-OSM: {len(map_osm_matches)} total, {good_map} high quality (≥50% overlap)")

    # Check improvement in estimates
    improved = conn.execute("""
        SELECT COUNT(*) FROM estimates
        WHERE method != 'unknown' AND method != 'none'
    """).fetchone()[0]
    print(f"\nBuildings with date estimates: {improved}")

    conn.close()
    print("\nMatching complete!")


if __name__ == "__main__":
    main()
