#!/usr/bin/env python3
"""
Iterative georeferencing alignment using matched OSM buildings as control points.

Uses polygon-to-polygon IoU matching with train/test split validation and
TPS/TIN transforms with regularization to prevent overfitting.

Usage:
    python scripts/align_to_osm.py --source ortofoto1937
    python scripts/align_to_osm.py --source ortofoto1937 --method tps --smoothing 0.1
    python scripts/align_to_osm.py --source ortofoto1937 --method tin
"""

import argparse
import json
import math
import random
import ssl
import time
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import List, Tuple, Dict, Any, Callable, Optional

import numpy as np
from scipy.interpolate import Rbf
from scipy.spatial import Delaunay
from shapely.geometry import shape, mapping, Point, Polygon, LineString, MultiPolygon
from shapely.ops import transform as shapely_transform

# SSL context for Overpass API
SSL_CONTEXT = ssl.create_default_context()
SSL_CONTEXT.check_hostname = False
SSL_CONTEXT.verify_mode = ssl.CERT_NONE

OVERPASS_URL = "https://overpass-api.de/api/interpreter"


# ============================================================
# 1. Loading Functions
# ============================================================

def load_ml_buildings(source: str) -> List[Dict[str, Any]]:
    """
    Load ML building polygons from data/sources/ml_detected/{source}/buildings.geojson

    Returns list of dicts with:
        - geometry: Shapely geometry
        - properties: dict of properties
    """
    buildings_path = Path(f"data/sources/ml_detected/{source}/buildings.geojson")

    if not buildings_path.exists():
        raise FileNotFoundError(f"ML buildings file not found: {buildings_path}")

    with open(buildings_path) as f:
        data = json.load(f)

    buildings = []
    for feature in data.get('features', []):
        geom = shape(feature['geometry'])
        if geom.is_valid and not geom.is_empty:
            buildings.append({
                'geometry': geom,
                'properties': feature.get('properties', {})
            })

    print(f"Loaded {len(buildings)} ML buildings from {source}")
    return buildings


def load_osm_buildings(bounds: Dict[str, float], cache_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """
    Fetch OSM buildings via Overpass API or load from cached file.

    Args:
        bounds: dict with 'west', 'south', 'east', 'north'
        cache_path: optional path to cache file

    Returns list of dicts with:
        - geometry: Shapely geometry
        - osm_id: OSM way ID
        - tags: dict of OSM tags
    """
    # Try loading from cache first
    if cache_path and cache_path.exists():
        print(f"Loading OSM buildings from cache: {cache_path}")
        with open(cache_path) as f:
            data = json.load(f)

        buildings = []
        for feature in data.get('features', []):
            geom = shape(feature['geometry'])
            if geom.is_valid and not geom.is_empty:
                buildings.append({
                    'geometry': geom,
                    'osm_id': feature['properties'].get('osm_id'),
                    'tags': feature['properties'].get('tags', {})
                })

        print(f"  Loaded {len(buildings)} OSM buildings from cache")
        return buildings

    # Fetch from Overpass API
    query = f"""
    [out:json][timeout:180];
    (
      way["building"]({bounds['south']},{bounds['west']},{bounds['north']},{bounds['east']});
      relation["building"]({bounds['south']},{bounds['west']},{bounds['north']},{bounds['east']});
    );
    out body;
    >;
    out skel qt;
    """

    print("Fetching OSM buildings from Overpass API...")

    for attempt in range(3):
        try:
            req = urllib.request.Request(
                OVERPASS_URL,
                data=query.encode('utf-8'),
                headers={'Content-Type': 'text/plain'}
            )
            with urllib.request.urlopen(req, timeout=180, context=SSL_CONTEXT) as response:
                data = json.loads(response.read().decode('utf-8'))
                break
        except Exception as e:
            print(f"  Attempt {attempt + 1}/3 failed: {e}")
            if attempt < 2:
                time.sleep(10)
            else:
                raise

    # Build node lookup
    nodes = {}
    for el in data.get('elements', []):
        if el.get('type') == 'node':
            nodes[el['id']] = (el['lon'], el['lat'])

    # Extract building polygons
    buildings = []
    for el in data.get('elements', []):
        if el.get('type') == 'way' and 'building' in el.get('tags', {}):
            coords = []
            for node_id in el.get('nodes', []):
                if node_id in nodes:
                    coords.append(nodes[node_id])

            if len(coords) >= 3:
                try:
                    poly = Polygon(coords)
                    if not poly.is_valid:
                        poly = poly.buffer(0)
                    if poly.is_valid and not poly.is_empty:
                        buildings.append({
                            'geometry': poly,
                            'osm_id': el['id'],
                            'tags': el.get('tags', {})
                        })
                except:
                    continue

    print(f"  Fetched {len(buildings)} OSM buildings")

    # Save to cache if path provided
    if cache_path:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        features = []
        for b in buildings:
            features.append({
                'type': 'Feature',
                'geometry': mapping(b['geometry']),
                'properties': {
                    'osm_id': b['osm_id'],
                    'tags': b['tags']
                }
            })

        geojson = {
            'type': 'FeatureCollection',
            'features': features
        }

        with open(cache_path, 'w') as f:
            json.dump(geojson, f)

        print(f"  Cached OSM buildings to {cache_path}")

    return buildings


# ============================================================
# 2. Matching Functions
# ============================================================

def calc_iou(geom1, geom2) -> float:
    """Calculate Intersection over Union for two geometries."""
    try:
        intersection = geom1.intersection(geom2).area
        union = geom1.union(geom2).area

        if union == 0:
            return 0.0

        return intersection / union
    except:
        return 0.0


def match_buildings(ml_buildings: List[Dict], osm_buildings: List[Dict],
                   min_iou: float = 0.3) -> List[Tuple[Any, Any, float, Tuple, Tuple]]:
    """
    Match ML buildings to OSM buildings by IoU.

    Returns list of tuples:
        (ml_geom, osm_geom, iou, ml_centroid, osm_centroid)
    """
    matches = []

    print(f"Matching {len(ml_buildings)} ML buildings to {len(osm_buildings)} OSM buildings (min_iou={min_iou})...")

    for ml_bldg in ml_buildings:
        ml_geom = ml_bldg['geometry']
        ml_centroid = ml_geom.centroid

        best_match = None
        best_iou = min_iou

        # Find all OSM buildings that intersect
        for osm_bldg in osm_buildings:
            osm_geom = osm_bldg['geometry']

            # Quick check: do they intersect?
            if not ml_geom.intersects(osm_geom):
                continue

            iou = calc_iou(ml_geom, osm_geom)

            if iou > best_iou:
                best_iou = iou
                best_match = osm_geom

        if best_match is not None:
            osm_centroid = best_match.centroid
            matches.append((
                ml_geom,
                best_match,
                best_iou,
                (ml_centroid.x, ml_centroid.y),
                (osm_centroid.x, osm_centroid.y)
            ))

    print(f"  Found {len(matches)} matches")
    return matches


# ============================================================
# 3. Transform Functions
# ============================================================

def fit_tps_transform(control_points: List[Tuple[Tuple, Tuple]],
                     smoothing: float = 0.0) -> Callable:
    """
    Fit Thin-Plate Spline transform using scipy.interpolate.Rbf.

    Models the DELTA (offset) instead of absolute coordinates for numerical stability.

    Args:
        control_points: list of ((src_x, src_y), (dst_x, dst_y))
        smoothing: smoothing parameter (0.0 = exact interpolation)

    Returns function that transforms (x, y) -> (x', y')
    """
    if len(control_points) < 3:
        raise ValueError("Need at least 3 control points for TPS")

    src_points = np.array([cp[0] for cp in control_points])
    dst_points = np.array([cp[1] for cp in control_points])

    src_x = src_points[:, 0]
    src_y = src_points[:, 1]

    # Model delta (offset) instead of absolute coordinates
    # This is much more numerically stable for geographic coordinates
    delta_x = dst_points[:, 0] - src_x
    delta_y = dst_points[:, 1] - src_y

    # Use minimum smoothing to avoid singular matrices
    effective_smoothing = max(smoothing, 1e-10)

    # Fit RBF interpolators for delta_x and delta_y
    try:
        rbf_dx = Rbf(src_x, src_y, delta_x, function='thin_plate', smooth=effective_smoothing)
        rbf_dy = Rbf(src_x, src_y, delta_y, function='thin_plate', smooth=effective_smoothing)
    except np.linalg.LinAlgError:
        # If still singular, increase smoothing
        print(f"  Warning: Matrix singular with smoothing={effective_smoothing}, increasing to 0.01")
        effective_smoothing = 0.01
        rbf_dx = Rbf(src_x, src_y, delta_x, function='thin_plate', smooth=effective_smoothing)
        rbf_dy = Rbf(src_x, src_y, delta_y, function='thin_plate', smooth=effective_smoothing)

    def transform(x, y):
        """Transform point (x, y) to (x', y') by adding interpolated delta"""
        dx = float(rbf_dx(x, y))
        dy = float(rbf_dy(x, y))
        return (x + dx, y + dy)

    return transform


def fit_tin_transform(control_points: List[Tuple[Tuple, Tuple]]) -> Callable:
    """
    Fit Triangulated Irregular Network transform.

    Uses Delaunay triangulation with local affine transform per triangle.

    Args:
        control_points: list of ((src_x, src_y), (dst_x, dst_y))

    Returns function that transforms (x, y) -> (x', y')
    """
    if len(control_points) < 3:
        raise ValueError("Need at least 3 control points for TIN")

    src_points = np.array([cp[0] for cp in control_points])
    dst_points = np.array([cp[1] for cp in control_points])

    # Build Delaunay triangulation on source points
    tri = Delaunay(src_points)

    # Precompute affine transforms for each triangle
    transforms = {}
    for simplex_idx, simplex in enumerate(tri.simplices):
        # Source triangle vertices
        p0_src, p1_src, p2_src = src_points[simplex]

        # Destination triangle vertices
        p0_dst, p1_dst, p2_dst = dst_points[simplex]

        # Compute affine transform from source to destination
        # Using barycentric coordinates
        src_mat = np.array([
            [p0_src[0], p1_src[0], p2_src[0]],
            [p0_src[1], p1_src[1], p2_src[1]],
            [1, 1, 1]
        ])

        dst_mat = np.array([
            [p0_dst[0], p1_dst[0], p2_dst[0]],
            [p0_dst[1], p1_dst[1], p2_dst[1]],
            [1, 1, 1]
        ])

        try:
            # Affine transform: dst = M * src
            M = dst_mat @ np.linalg.inv(src_mat)
            transforms[simplex_idx] = M
        except:
            # Singular matrix - use identity
            transforms[simplex_idx] = np.eye(3)

    def transform(x, y):
        """Transform point (x, y) to (x', y')"""
        point = np.array([x, y])

        # Find which triangle contains this point
        simplex_idx = tri.find_simplex(point)

        if simplex_idx == -1:
            # Point outside triangulation - no transform
            return (x, y)

        # Apply affine transform
        M = transforms[int(simplex_idx)]
        src_vec = np.array([x, y, 1])
        dst_vec = M @ src_vec

        return (float(dst_vec[0]), float(dst_vec[1]))

    return transform


def fit_affine_transform(control_points: List[Tuple[Tuple, Tuple]]) -> Callable:
    """
    Fit simple 6-parameter affine transform using least squares.

    Args:
        control_points: list of ((src_x, src_y), (dst_x, dst_y))

    Returns function that transforms (x, y) -> (x', y')
    """
    if len(control_points) < 3:
        raise ValueError("Need at least 3 control points for affine")

    src_points = np.array([cp[0] for cp in control_points])
    dst_points = np.array([cp[1] for cp in control_points])

    # Build design matrix for least squares
    # x' = a*x + b*y + c
    # y' = d*x + e*y + f
    A = np.zeros((2 * len(control_points), 6))
    b = np.zeros(2 * len(control_points))

    for i, (src, dst) in enumerate(control_points):
        # x' equation
        A[2*i, 0] = src[0]
        A[2*i, 1] = src[1]
        A[2*i, 2] = 1
        b[2*i] = dst[0]

        # y' equation
        A[2*i+1, 3] = src[0]
        A[2*i+1, 4] = src[1]
        A[2*i+1, 5] = 1
        b[2*i+1] = dst[1]

    # Solve least squares
    params, _, _, _ = np.linalg.lstsq(A, b, rcond=None)

    a, b_param, c, d, e, f = params

    def transform(x, y):
        """Transform point (x, y) to (x', y')"""
        x_new = float(a * x + b_param * y + c)
        y_new = float(d * x + e * y + f)
        return (x_new, y_new)

    return transform


def apply_transform(geometry, transform_fn: Callable):
    """
    Apply transform to any Shapely geometry.

    Args:
        geometry: Shapely Point, Polygon, LineString, etc.
        transform_fn: function (x, y) -> (x', y')

    Returns transformed geometry
    """
    if transform_fn is None:
        return geometry

    def transform_coords(x, y, z=None):
        x_new, y_new = transform_fn(x, y)
        if z is not None:
            return (x_new, y_new, z)
        return (x_new, y_new)

    return shapely_transform(transform_coords, geometry)


# ============================================================
# 4. Evaluation Functions
# ============================================================

def train_test_split(matches: List, test_ratio: float = 0.2) -> Tuple[List, List]:
    """Split matches into train and test sets."""
    random.shuffle(matches)
    split_idx = int(len(matches) * (1 - test_ratio))
    return matches[:split_idx], matches[split_idx:]


def calc_rmse(matches: List[Tuple], transform_fn: Callable) -> float:
    """
    Calculate RMSE between transformed ML centroids and OSM centroids.

    Args:
        matches: list of (ml_geom, osm_geom, iou, ml_centroid, osm_centroid)
        transform_fn: transform function

    Returns RMSE in degrees (can be converted to meters later)
    """
    if not matches:
        return 0.0

    errors = []
    for _, _, _, ml_centroid, osm_centroid in matches:
        # Transform ML centroid
        ml_x, ml_y = ml_centroid
        osm_x, osm_y = osm_centroid

        if transform_fn is not None:
            ml_x_transformed, ml_y_transformed = transform_fn(ml_x, ml_y)
        else:
            ml_x_transformed, ml_y_transformed = ml_x, ml_y

        # Calculate distance in degrees
        dx = ml_x_transformed - osm_x
        dy = ml_y_transformed - osm_y
        error = math.sqrt(dx**2 + dy**2)
        errors.append(error)

    rmse = math.sqrt(sum(e**2 for e in errors) / len(errors))

    # Convert degrees to meters (approximate at 63.43°N)
    # 1 degree longitude ≈ 111320 * cos(lat) meters
    # 1 degree latitude ≈ 111320 meters
    lat = 63.43
    meters_per_degree = 111320 * math.cos(math.radians(lat))
    rmse_meters = rmse * meters_per_degree

    return rmse_meters


def check_convergence(iterations: List[Dict], window: int = 3) -> bool:
    """
    Check if alignment has converged.

    Converged if:
    - Number of matches has stabilized (< 5% change in last window)
    - Test RMSE has stabilized or increased (early stopping)
    """
    if len(iterations) < window + 1:
        return False

    recent = iterations[-window:]

    # Check if matches have stabilized
    match_counts = [it['matches'] for it in recent]
    match_variance = np.std(match_counts) / np.mean(match_counts) if np.mean(match_counts) > 0 else 1.0

    if match_variance > 0.05:
        return False

    # Check if test RMSE is increasing (overfitting)
    test_rmses = [it['test_rmse'] for it in iterations[-window:]]
    if len(test_rmses) >= 2 and test_rmses[-1] > test_rmses[-2]:
        print("  Early stopping: test RMSE increasing")
        return True

    # Check if test RMSE has stabilized
    if len(test_rmses) >= window:
        rmse_variance = np.std(test_rmses) / np.mean(test_rmses) if np.mean(test_rmses) > 0 else 1.0
        if rmse_variance < 0.05:
            print("  Converged: RMSE stabilized")
            return True

    return False


# ============================================================
# 5. Iterative Alignment
# ============================================================

def iterative_align(ml_buildings: List[Dict],
                   osm_buildings: List[Dict],
                   method: str = 'tps',
                   smoothing: float = 0.1,
                   min_iou: float = 0.3,
                   max_rounds: int = 10,
                   test_ratio: float = 0.2) -> Tuple[Callable, List[Dict]]:
    """
    Iteratively align ML buildings to OSM buildings.

    Args:
        ml_buildings: list of ML building dicts
        osm_buildings: list of OSM building dicts
        method: 'tps', 'tin', or 'affine'
        smoothing: TPS smoothing parameter
        min_iou: minimum IoU for matching
        max_rounds: maximum number of iterations
        test_ratio: fraction of matches to hold out for testing

    Returns:
        (transform_fn, iterations)
    """
    transform = None
    iterations = []

    print(f"\nStarting iterative alignment with method={method}")

    for round_num in range(max_rounds):
        print(f"\n--- Round {round_num + 1}/{max_rounds} ---")

        # Apply current transform to ML buildings
        if transform is not None:
            transformed_buildings = []
            for ml_bldg in ml_buildings:
                transformed_geom = apply_transform(ml_bldg['geometry'], transform)
                transformed_buildings.append({
                    'geometry': transformed_geom,
                    'properties': ml_bldg['properties']
                })
        else:
            transformed_buildings = ml_buildings

        # Match buildings
        matches = match_buildings(transformed_buildings, osm_buildings, min_iou)

        if len(matches) < 3:
            print(f"  Error: Only {len(matches)} matches found, need at least 3")
            break

        # Split train/test
        train_matches, test_matches = train_test_split(matches, test_ratio)

        print(f"  Train set: {len(train_matches)} matches")
        print(f"  Test set:  {len(test_matches)} matches")

        # Build control points from train set
        control_points = [(ml_centroid, osm_centroid)
                         for _, _, _, ml_centroid, osm_centroid in train_matches]

        # Fit transform on train set
        try:
            if method == 'tps':
                new_transform = fit_tps_transform(control_points, smoothing)
            elif method == 'tin':
                new_transform = fit_tin_transform(control_points)
            elif method == 'affine':
                new_transform = fit_affine_transform(control_points)
            else:
                raise ValueError(f"Unknown method: {method}")
        except Exception as e:
            print(f"  Error fitting transform: {e}")
            break

        # Evaluate on train and test sets
        train_rmse = calc_rmse(train_matches, new_transform)
        test_rmse = calc_rmse(test_matches, new_transform)

        print(f"  Train RMSE: {train_rmse:.2f} m")
        print(f"  Test RMSE:  {test_rmse:.2f} m")

        # Record iteration
        iterations.append({
            'round': round_num + 1,
            'matches': len(matches),
            'train_rmse': round(train_rmse, 2),
            'test_rmse': round(test_rmse, 2)
        })

        # Update transform for next round
        transform = new_transform

        # Check convergence
        if check_convergence(iterations):
            print(f"\nConverged after {round_num + 1} rounds")
            break

    return transform, iterations


# ============================================================
# 6. Main Pipeline
# ============================================================

def save_aligned_geojson(buildings: List[Dict], transform_fn: Callable,
                        output_path: Path, original_path: Path):
    """Save aligned buildings to GeoJSON."""
    features = []

    for bldg in buildings:
        geom = bldg['geometry']
        aligned_geom = apply_transform(geom, transform_fn)

        features.append({
            'type': 'Feature',
            'geometry': mapping(aligned_geom),
            'properties': bldg['properties']
        })

    geojson = {
        'type': 'FeatureCollection',
        'features': features,
        'metadata': {
            'source': 'ML detected buildings, aligned to OSM',
            'original_file': str(original_path),
            'aligned_at': datetime.utcnow().isoformat() + 'Z'
        }
    }

    with open(output_path, 'w') as f:
        json.dump(geojson, f)

    print(f"Saved {len(features)} aligned buildings to {output_path}")


def load_roads(source: str) -> List[Dict]:
    """Load roads from source."""
    roads_path = Path(f"data/sources/ml_detected/{source}/roads_extracted.geojson")

    if not roads_path.exists():
        print(f"Roads file not found: {roads_path}")
        return []

    with open(roads_path) as f:
        data = json.load(f)

    roads = []
    for feature in data.get('features', []):
        geom = shape(feature['geometry'])
        if geom.is_valid and not geom.is_empty:
            roads.append({
                'geometry': geom,
                'properties': feature.get('properties', {})
            })

    print(f"Loaded {len(roads)} roads from {source}")
    return roads


def save_aligned_roads(roads: List[Dict], transform_fn: Callable,
                      output_path: Path, original_path: Path):
    """Save aligned roads to GeoJSON."""
    features = []

    for road in roads:
        geom = road['geometry']
        aligned_geom = apply_transform(geom, transform_fn)

        features.append({
            'type': 'Feature',
            'geometry': mapping(aligned_geom),
            'properties': road['properties']
        })

    geojson = {
        'type': 'FeatureCollection',
        'features': features,
        'metadata': {
            'source': 'ML detected roads, aligned to OSM',
            'original_file': str(original_path),
            'aligned_at': datetime.utcnow().isoformat() + 'Z'
        }
    }

    with open(output_path, 'w') as f:
        json.dump(geojson, f)

    print(f"Saved {len(features)} aligned roads to {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description='Iterative georeferencing alignment using OSM buildings as control points'
    )
    parser.add_argument('--source', default='ortofoto1937',
                       help='Source name (e.g., ortofoto1937)')
    parser.add_argument('--method', choices=['tps', 'tin', 'affine'], default='tps',
                       help='Transform method: tps (default), tin, or affine')
    parser.add_argument('--smoothing', type=float, default=0.1,
                       help='TPS smoothing parameter (default: 0.1)')
    parser.add_argument('--min-iou', type=float, default=0.3,
                       help='Minimum IoU for matching (default: 0.3)')
    parser.add_argument('--max-rounds', type=int, default=10,
                       help='Maximum number of iterations (default: 10)')
    parser.add_argument('--test-ratio', type=float, default=0.2,
                       help='Test set ratio (default: 0.2)')
    parser.add_argument('--bounds', type=str, default=None,
                       help='Bounds as "west,south,east,north" (default: auto from ML buildings)')

    args = parser.parse_args()

    print(f"Aligning ML buildings from {args.source} to OSM")
    print(f"Method: {args.method}")
    print(f"Parameters: smoothing={args.smoothing}, min_iou={args.min_iou}, max_rounds={args.max_rounds}, test_ratio={args.test_ratio}")

    # Load ML buildings
    ml_buildings = load_ml_buildings(args.source)

    if not ml_buildings:
        print("Error: No ML buildings loaded")
        return

    # Determine bounds
    if args.bounds:
        parts = args.bounds.split(',')
        bounds = {
            'west': float(parts[0]),
            'south': float(parts[1]),
            'east': float(parts[2]),
            'north': float(parts[3])
        }
    else:
        # Auto-detect from ML buildings
        all_coords = []
        for bldg in ml_buildings:
            geom = bldg['geometry']
            if hasattr(geom, 'exterior'):
                all_coords.extend(geom.exterior.coords)
            elif hasattr(geom, 'coords'):
                all_coords.extend(geom.coords)

        lons = [c[0] for c in all_coords]
        lats = [c[1] for c in all_coords]

        # Add 0.01 degree buffer (~1km)
        bounds = {
            'west': min(lons) - 0.01,
            'south': min(lats) - 0.01,
            'east': max(lons) + 0.01,
            'north': max(lats) + 0.01
        }

    print(f"Bounds: {bounds}")

    # Load OSM buildings
    cache_path = Path(f"data/sources/ml_detected/{args.source}/osm_cache.geojson")
    osm_buildings = load_osm_buildings(bounds, cache_path)

    if not osm_buildings:
        print("Error: No OSM buildings loaded")
        return

    # Run iterative alignment
    transform_fn, iterations = iterative_align(
        ml_buildings,
        osm_buildings,
        method=args.method,
        smoothing=args.smoothing,
        min_iou=args.min_iou,
        max_rounds=args.max_rounds,
        test_ratio=args.test_ratio
    )

    if transform_fn is None:
        print("Error: Alignment failed")
        return

    # Save aligned buildings
    source_dir = Path(f"data/sources/ml_detected/{args.source}")
    buildings_path = source_dir / "buildings.geojson"
    aligned_buildings_path = source_dir / "buildings_aligned.geojson"

    save_aligned_geojson(ml_buildings, transform_fn, aligned_buildings_path, buildings_path)

    # Load and save aligned roads if they exist
    roads = load_roads(args.source)
    if roads:
        roads_path = source_dir / "roads_extracted.geojson"
        aligned_roads_path = source_dir / "roads_extracted_aligned.geojson"
        save_aligned_roads(roads, transform_fn, aligned_roads_path, roads_path)

    # Generate alignment report
    final_stats = iterations[-1] if iterations else {}

    report = {
        'source': args.source,
        'method': args.method,
        'smoothing': args.smoothing,
        'min_iou': args.min_iou,
        'bounds': bounds,
        'iterations': iterations,
        'final': {
            'total_matches': final_stats.get('matches', 0),
            'train_rmse_m': final_stats.get('train_rmse', 0),
            'test_rmse_m': final_stats.get('test_rmse', 0),
            'buildings_transformed': len(ml_buildings),
            'roads_transformed': len(roads) if roads else 0
        },
        'aligned_at': datetime.utcnow().isoformat() + 'Z'
    }

    report_path = source_dir / "alignment_report.json"
    with open(report_path, 'w') as f:
        json.dump(report, f, indent=2)

    print(f"\n=== Alignment Complete ===")
    print(f"Final matches: {report['final']['total_matches']}")
    print(f"Train RMSE: {report['final']['train_rmse_m']:.2f} m")
    print(f"Test RMSE: {report['final']['test_rmse_m']:.2f} m")
    print(f"Buildings transformed: {report['final']['buildings_transformed']}")
    print(f"Roads transformed: {report['final']['roads_transformed']}")
    print(f"\nReport saved to {report_path}")


if __name__ == '__main__':
    main()
