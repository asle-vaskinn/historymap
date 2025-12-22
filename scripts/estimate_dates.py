#!/usr/bin/env python3
"""
Estimate building dates using heuristics and spatial interpolation.

Philosophy: Better to show estimated buildings than empty gaps.
This is for visualization, not precise historical records.

Estimation methods (in priority order):
1. SEFRAK - exact dates from cultural heritage registry
2. Matrikkelen - official construction year (when available)
3. OSM tags - explicit start_date tags
4. Spatial interpolation - nearby buildings built around same time
5. City center distance - older buildings tend to be in center
6. Building size heuristic - large industrial buildings tend to be newer
"""

import json
import sqlite3
import sys
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
import math

sys.path.insert(0, str(Path(__file__).parent))

# Constants for Trondheim
CITY_CENTER = (10.395, 63.430)  # Approximate center (Torvet)
OLDEST_AREA_YEAR = 1650  # Buildings near center could be very old
EXPANSION_RATE_PER_KM = 50  # Years newer per km from center (rough estimate)

@dataclass
class DateEstimate:
    """A date estimate with confidence and method."""
    building_id: str
    start_year: Optional[int]
    end_year: Optional[int]
    confidence: float  # 0-1
    method: str
    reasoning: str


def haversine_km(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Calculate distance in km between two points."""
    R = 6371  # Earth radius in km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return 2 * R * math.asin(math.sqrt(a))


def estimate_by_city_center_distance(lon: float, lat: float) -> Tuple[int, float, str]:
    """
    Estimate building age based on distance from city center.

    Heuristic: Trondheim grew outward from Torvet.
    - Buildings near center: possibly very old (1700s-1800s)
    - Buildings 1-2km out: likely 1900s
    - Buildings 3-5km out: likely 1950s-2000s
    - Buildings 5km+: likely modern
    """
    dist = haversine_km(lon, lat, CITY_CENTER[0], CITY_CENTER[1])

    if dist < 0.5:
        # Inner city - could be old but many rebuilt
        year = 1850
        confidence = 0.3
        reason = f"Inner city ({dist:.1f}km from center), estimated 1850"
    elif dist < 1.0:
        year = 1900
        confidence = 0.35
        reason = f"Near center ({dist:.1f}km), estimated 1900"
    elif dist < 2.0:
        year = 1930
        confidence = 0.3
        reason = f"Mid-city ({dist:.1f}km from center), estimated 1930"
    elif dist < 3.5:
        year = 1960
        confidence = 0.25
        reason = f"Outer ring ({dist:.1f}km from center), estimated 1960"
    else:
        year = 1990
        confidence = 0.2
        reason = f"Suburb ({dist:.1f}km from center), estimated 1990"

    return year, confidence, reason


def estimate_by_building_type(building_type: Optional[str], area_sqm: float) -> Tuple[Optional[int], float, str]:
    """
    Estimate based on building type and size.

    Large industrial/commercial buildings tend to be 20th century.
    Small residential buildings have wider date range.
    """
    if not building_type:
        return None, 0.0, ""

    bt_lower = building_type.lower()

    # Industrial buildings - mostly 20th century
    if any(x in bt_lower for x in ['industrial', 'warehouse', 'factory', 'commercial']):
        if area_sqm > 500:
            return 1950, 0.4, f"Large {building_type} ({area_sqm:.0f}m²), likely post-1950"
        return 1920, 0.3, f"Industrial building, estimated 1920"

    # Churches and schools often have known dates elsewhere
    if any(x in bt_lower for x in ['church', 'cathedral', 'chapel']):
        return 1800, 0.25, "Church - could be historic, estimated 1800"

    # Modern building types
    if any(x in bt_lower for x in ['garage', 'parking', 'supermarket', 'mall']):
        return 1970, 0.5, f"Modern {building_type}, estimated 1970"

    # Apartments - era-dependent
    if 'apartment' in bt_lower or 'residential' in bt_lower:
        if area_sqm > 1000:
            return 1960, 0.35, "Large apartment block, estimated 1960"
        return None, 0.0, ""  # Let other methods decide

    return None, 0.0, ""


def estimate_by_neighbors(
    building_id: str,
    centroid: Tuple[float, float],
    neighbor_dates: List[Tuple[float, float, int, float]],  # (lon, lat, year, confidence)
    max_distance_km: float = 0.3
) -> Tuple[Optional[int], float, str]:
    """
    Estimate date based on nearby buildings with known dates.

    Buildings in the same area were often built around the same time.
    """
    if not neighbor_dates:
        return None, 0.0, ""

    lon, lat = centroid

    # Find nearby buildings with dates
    nearby = []
    for n_lon, n_lat, n_year, n_conf in neighbor_dates:
        dist = haversine_km(lon, lat, n_lon, n_lat)
        if dist <= max_distance_km and dist > 0.001:  # Not self
            nearby.append((dist, n_year, n_conf))

    if not nearby:
        return None, 0.0, ""

    # Weight by distance (closer = more influence)
    total_weight = 0
    weighted_year = 0

    for dist, year, conf in nearby:
        weight = conf * (1 - dist/max_distance_km)  # Decay with distance
        weighted_year += year * weight
        total_weight += weight

    if total_weight == 0:
        return None, 0.0, ""

    estimated_year = int(weighted_year / total_weight)
    confidence = min(0.6, total_weight / len(nearby) * 0.5)  # Cap at 0.6

    return estimated_year, confidence, f"Interpolated from {len(nearby)} nearby buildings"


def load_buildings_for_estimation(db_path: Path) -> List[Dict]:
    """Load buildings from database."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    query = """
        SELECT
            b.building_id,
            b.centroid_lon,
            b.centroid_lat,
            b.building_type,
            b.est_start_year,
            b.est_end_year,
            b.est_confidence,
            b.geometry_json
        FROM buildings b
    """

    rows = conn.execute(query).fetchall()
    conn.close()

    buildings = []
    for row in rows:
        geom_area = 0
        if row['geometry_json']:
            try:
                geom = json.loads(row['geometry_json'])
                # Rough area calculation for polygons
                if geom.get('type') == 'Polygon':
                    coords = geom['coordinates'][0]
                    # Simple shoelace formula approximation in sq degrees
                    area_deg = abs(sum(
                        coords[i][0] * coords[(i+1)%len(coords)][1] -
                        coords[(i+1)%len(coords)][0] * coords[i][1]
                        for i in range(len(coords))
                    )) / 2
                    # Convert to rough sqm (at 63°N: 1 deg lat ≈ 111km, 1 deg lon ≈ 55km)
                    geom_area = area_deg * 111000 * 55000
            except:
                pass

        buildings.append({
            'building_id': row['building_id'],
            'lon': row['centroid_lon'],
            'lat': row['centroid_lat'],
            'building_type': row['building_type'],
            'current_year': row['est_start_year'],
            'current_end': row['est_end_year'],
            'current_confidence': row['est_confidence'] or 0,
            'area_sqm': geom_area
        })

    return buildings


def estimate_all_buildings(buildings: List[Dict]) -> List[DateEstimate]:
    """
    Run estimation on all buildings.

    Strategy:
    1. First pass: Collect all buildings with known dates
    2. Second pass: Estimate unknown buildings using multiple methods
    3. Combine estimates with weighted averaging
    """
    estimates = []

    # Collect buildings with known dates for neighbor interpolation
    dated_buildings = [
        (b['lon'], b['lat'], b['current_year'], b['current_confidence'])
        for b in buildings
        if b['current_year'] and b['current_confidence'] > 0.5
    ]

    print(f"Found {len(dated_buildings)} buildings with reliable dates for interpolation")

    for b in buildings:
        # Skip if already has high-confidence date
        if b['current_year'] and b['current_confidence'] >= 0.7:
            estimates.append(DateEstimate(
                building_id=b['building_id'],
                start_year=b['current_year'],
                end_year=b['current_end'],
                confidence=b['current_confidence'],
                method='existing',
                reasoning='High-confidence existing estimate'
            ))
            continue

        # Collect estimates from different methods
        method_estimates = []

        # Method 1: City center distance
        if b['lon'] and b['lat']:
            year, conf, reason = estimate_by_city_center_distance(b['lon'], b['lat'])
            if conf > 0:
                method_estimates.append((year, conf, 'center_distance', reason))

        # Method 2: Building type
        year, conf, reason = estimate_by_building_type(b['building_type'], b['area_sqm'])
        if conf > 0:
            method_estimates.append((year, conf, 'building_type', reason))

        # Method 3: Neighbor interpolation
        if b['lon'] and b['lat'] and dated_buildings:
            year, conf, reason = estimate_by_neighbors(
                b['building_id'],
                (b['lon'], b['lat']),
                dated_buildings
            )
            if conf > 0:
                method_estimates.append((year, conf, 'neighbor_interpolation', reason))

        # Combine estimates
        if method_estimates:
            # Weight by confidence
            total_weight = sum(conf for _, conf, _, _ in method_estimates)
            weighted_year = sum(year * conf for year, conf, _, _ in method_estimates) / total_weight
            combined_conf = min(0.7, max(conf for _, conf, _, _ in method_estimates))

            # Build reasoning string
            methods_used = [m for _, _, m, _ in method_estimates]
            best_method = max(method_estimates, key=lambda x: x[1])

            estimates.append(DateEstimate(
                building_id=b['building_id'],
                start_year=int(weighted_year),
                end_year=b['current_end'],
                confidence=combined_conf,
                method='+'.join(methods_used),
                reasoning=best_method[3]
            ))
        else:
            # Default fallback - estimate based on existence
            estimates.append(DateEstimate(
                building_id=b['building_id'],
                start_year=1950,  # Safe middle estimate
                end_year=b['current_end'],
                confidence=0.15,
                method='default',
                reasoning='No estimation method available, using 1950 default'
            ))

    return estimates


def save_estimates_to_db(estimates: List[DateEstimate], db_path: Path):
    """Save estimates back to database."""
    conn = sqlite3.connect(db_path)

    updated = 0
    for est in estimates:
        conn.execute("""
            UPDATE buildings
            SET est_start_year = ?,
                est_end_year = ?,
                est_confidence = ?,
                est_method = ?
            WHERE building_id = ?
        """, (est.start_year, est.end_year, est.confidence, est.method, est.building_id))
        updated += 1

    conn.commit()
    conn.close()

    return updated


def main():
    """Run date estimation pipeline."""
    print("=" * 60)
    print("Building Date Estimation Pipeline")
    print("Philosophy: Better to estimate than leave gaps")
    print("=" * 60)

    db_path = Path(__file__).parent.parent / "data" / "db" / "buildings.db"

    if not db_path.exists():
        print(f"Database not found: {db_path}")
        print("Run the import pipeline first.")
        return

    print(f"\nLoading buildings from {db_path}...")
    buildings = load_buildings_for_estimation(db_path)
    print(f"Loaded {len(buildings)} buildings")

    # Count current state
    has_date = sum(1 for b in buildings if b['current_year'])
    high_conf = sum(1 for b in buildings if b['current_confidence'] and b['current_confidence'] > 0.5)
    print(f"  - With dates: {has_date}")
    print(f"  - High confidence (>0.5): {high_conf}")

    print("\nRunning estimation...")
    estimates = estimate_all_buildings(buildings)

    # Statistics
    by_method = {}
    for est in estimates:
        m = est.method
        by_method[m] = by_method.get(m, 0) + 1

    print("\nEstimation results by method:")
    for method, count in sorted(by_method.items(), key=lambda x: -x[1]):
        print(f"  {method}: {count}")

    # Confidence distribution
    conf_buckets = {
        '0.0-0.2': 0,
        '0.2-0.4': 0,
        '0.4-0.6': 0,
        '0.6-0.8': 0,
        '0.8-1.0': 0
    }
    for est in estimates:
        if est.confidence < 0.2:
            conf_buckets['0.0-0.2'] += 1
        elif est.confidence < 0.4:
            conf_buckets['0.2-0.4'] += 1
        elif est.confidence < 0.6:
            conf_buckets['0.4-0.6'] += 1
        elif est.confidence < 0.8:
            conf_buckets['0.6-0.8'] += 1
        else:
            conf_buckets['0.8-1.0'] += 1

    print("\nConfidence distribution:")
    for bucket, count in conf_buckets.items():
        pct = count / len(estimates) * 100
        bar = '#' * int(pct / 2)
        print(f"  {bucket}: {count:5d} ({pct:5.1f}%) {bar}")

    print("\nSaving estimates to database...")
    updated = save_estimates_to_db(estimates, db_path)
    print(f"Updated {updated} buildings")

    print("\nDone!")


if __name__ == "__main__":
    main()
