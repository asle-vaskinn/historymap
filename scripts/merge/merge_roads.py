#!/usr/bin/env python3
"""
Merge normalized road data from multiple sources.

Integrates the road temporal pipeline by:
1. Loading road sources (OSM, ML historical, manual)
2. Matching roads using network topology (buffer overlap + Hausdorff distance + name similarity)
3. Inferring dates from:
   - Historical map presence (ML-detected roads)
   - Nearby buildings (from buildings_unified.geojson)
4. Merging and classifying change types
5. Outputting roads_temporal.geojson

Configuration via roads_merge_config.json:
- sources: OSM roads, ML roads from kartverket maps, manual roads
- matching: Buffer distance, overlap threshold, Hausdorff threshold
- date_inference: Historical map presence
- building_date_inference: Use nearby buildings for date estimation
- output: roads_temporal.geojson

Usage:
    As module:
        from scripts.merge.merge_roads import merge_roads
        merge_roads(config_path, output_path)

    As CLI:
        python scripts/merge/merge_roads.py --config data/merged/roads_merge_config.json
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Optional: Use shapely for spatial operations if available
try:
    from shapely.geometry import shape, mapping, LineString, MultiLineString
    from shapely.ops import linemerge
    from shapely.strtree import STRtree
    HAS_SHAPELY = True
except ImportError:
    HAS_SHAPELY = False
    print("Warning: shapely not installed. Road matching will be limited.")


def load_config(config_path: Path) -> Dict:
    """Load and validate merge configuration."""
    with open(config_path) as f:
        config = json.load(f)

    # Validate required fields
    required = ['sources', 'matching', 'output']
    for field in required:
        if field not in config:
            raise ValueError(f"Missing required config field: {field}")

    return config


def load_source(source_config: Dict, base_dir: Path) -> Optional[List[Dict]]:
    """Load normalized features from a source."""
    if not source_config.get('enabled', False):
        return None

    path = base_dir / source_config['path']
    if not path.exists():
        print(f"  Warning: Source file not found: {path}")
        return None

    with open(path) as f:
        data = json.load(f)

    return data.get('features', [])


def calculate_hausdorff_distance(geom1: Dict, geom2: Dict) -> float:
    """
    Calculate Hausdorff distance between two line geometries.

    Returns distance in approximate meters (assuming WGS84 at ~63°N latitude).
    """
    if not HAS_SHAPELY:
        return float('inf')

    try:
        shape1 = shape(geom1)
        shape2 = shape(geom2)

        if not shape1.is_valid or not shape2.is_valid:
            return float('inf')

        # Hausdorff distance in degrees
        dist_deg = shape1.hausdorff_distance(shape2)

        # Convert to approximate meters at Trondheim latitude (~63°N)
        # 1 degree latitude ≈ 111km, 1 degree longitude ≈ 50km at 63°N
        dist_m = dist_deg * 80000  # Average approximation

        return dist_m

    except Exception:
        return float('inf')


def calculate_buffer_overlap(geom1: Dict, geom2: Dict, buffer_m: float = 10) -> float:
    """
    Calculate overlap ratio between buffered line geometries.

    Args:
        geom1: First line geometry
        geom2: Second line geometry
        buffer_m: Buffer distance in meters

    Returns:
        Overlap ratio (0-1)
    """
    if not HAS_SHAPELY:
        return 0.0

    try:
        shape1 = shape(geom1)
        shape2 = shape(geom2)

        if not shape1.is_valid or not shape2.is_valid:
            return 0.0

        # Convert buffer from meters to degrees (approximate)
        buffer_deg = buffer_m / 80000

        # Buffer both lines
        buffer1 = shape1.buffer(buffer_deg)
        buffer2 = shape2.buffer(buffer_deg)

        # Calculate intersection
        intersection = buffer1.intersection(buffer2)
        if intersection.is_empty:
            return 0.0

        # Ratio to smaller buffer
        min_area = min(buffer1.area, buffer2.area)
        if min_area == 0:
            return 0.0

        return intersection.area / min_area

    except Exception:
        return 0.0


def name_similarity(name1: Optional[str], name2: Optional[str]) -> float:
    """
    Calculate name similarity score (0-1).

    Uses simple case-insensitive comparison.
    """
    if not name1 or not name2:
        return 0.0

    name1 = name1.lower().strip()
    name2 = name2.lower().strip()

    if name1 == name2:
        return 1.0

    # Check if one contains the other
    if name1 in name2 or name2 in name1:
        return 0.7

    # Check common prefix
    common = 0
    for c1, c2 in zip(name1, name2):
        if c1 == c2:
            common += 1
        else:
            break

    if common >= 3:
        return 0.3

    return 0.0


def build_spatial_index(features: List[Dict], buffer_m: float = 20) -> Optional[Tuple[Any, List, List[Dict]]]:
    """
    Build a spatial index for road features.

    Uses buffered geometries for index since roads are lines.
    """
    if not HAS_SHAPELY:
        return None

    if not features:
        return None

    buffer_deg = buffer_m / 80000  # Approximate conversion

    geometries = []
    indexed_features = []

    for feat in features:
        geom = feat.get('geometry')
        if not geom:
            continue

        try:
            shp = shape(geom)
            if shp.is_valid:
                # Use buffered geometry for spatial index
                buffered = shp.buffer(buffer_deg)
                geometries.append(buffered)
                indexed_features.append(feat)
        except Exception:
            continue

    if not geometries:
        return None

    try:
        index = STRtree(geometries)
        return (index, geometries, indexed_features)
    except Exception:
        return None


def calculate_match_score(
    feat1: Dict,
    feat2: Dict,
    config: Dict
) -> float:
    """
    Calculate match score between two road features.

    Combines:
    - Buffer overlap (weight: 0.4)
    - Hausdorff distance (weight: 0.3)
    - Name similarity (weight: 0.3)

    Returns score 0-1, or 0 if definitely not a match.
    """
    geom1 = feat1.get('geometry')
    geom2 = feat2.get('geometry')

    if not geom1 or not geom2:
        return 0.0

    matching_config = config.get('matching', {})
    buffer_m = matching_config.get('buffer_distance_m', 10)
    hausdorff_threshold_m = matching_config.get('hausdorff_threshold_m', 20)
    name_boost = matching_config.get('name_match_boost', 0.3)

    # Calculate buffer overlap
    overlap = calculate_buffer_overlap(geom1, geom2, buffer_m)

    # Calculate Hausdorff distance
    hausdorff = calculate_hausdorff_distance(geom1, geom2)
    if hausdorff > hausdorff_threshold_m:
        return 0.0  # Too far apart

    hausdorff_score = 1 - (hausdorff / hausdorff_threshold_m)

    # Calculate name similarity
    name1 = feat1.get('properties', {}).get('nm')
    name2 = feat2.get('properties', {}).get('nm')
    name_score = name_similarity(name1, name2)

    # Combine scores
    score = overlap * 0.4 + hausdorff_score * 0.3 + name_score * name_boost

    return min(1.0, max(0.0, score))


def find_road_matches(
    feature: Dict,
    candidates: List[Dict],
    config: Dict,
    spatial_index: Optional[Tuple[Any, List, List[Dict]]] = None,
    threshold: float = 0.3
) -> List[Tuple[Dict, float]]:
    """
    Find matching road features.

    Returns list of (feature, score) tuples sorted by score descending.
    """
    matches = []
    geom = feature.get('geometry')
    if not geom:
        return matches

    matching_config = config.get('matching', {})
    min_overlap = matching_config.get('min_overlap_ratio', 0.3)

    # Use spatial index if available
    if spatial_index is not None and HAS_SHAPELY:
        index, geometries, indexed_features = spatial_index

        try:
            query_shape = shape(geom)
            if not query_shape.is_valid:
                return matches

            # Query index for candidates
            buffer_deg = matching_config.get('buffer_distance_m', 20) / 80000
            query_buffered = query_shape.buffer(buffer_deg)
            candidate_indices = index.query(query_buffered)

            for idx in candidate_indices:
                candidate = indexed_features[idx]

                # Skip self-match
                feat_id = f"{feature['properties'].get('_src')}:{feature['properties'].get('_src_id')}"
                cand_id = f"{candidate['properties'].get('_src')}:{candidate['properties'].get('_src_id')}"
                if feat_id == cand_id:
                    continue

                score = calculate_match_score(feature, candidate, config)
                if score >= threshold:
                    matches.append((candidate, score))

        except Exception:
            pass

    # Fall back to O(n²) if no spatial index
    if not matches and spatial_index is None:
        for candidate in candidates:
            score = calculate_match_score(feature, candidate, config)
            if score >= threshold:
                matches.append((candidate, score))

    return sorted(matches, key=lambda x: x[1], reverse=True)


def merge_road_properties(
    base_props: Dict,
    new_props: Dict,
    priority: str = 'base'
) -> Dict:
    """
    Merge properties from two road features.

    Prefers higher-priority source for conflicts.
    """
    merged = dict(base_props)

    # Track all sources
    sources = set()
    if '_src' in base_props:
        sources.add(base_props['_src'])
    if '_src' in new_props:
        sources.add(new_props['_src'])
    merged['src_all'] = sorted(list(sources))

    # Merge evidence: take highest
    ev_order = {'h': 3, 'm': 2, 'l': 1}
    base_ev = base_props.get('ev', 'l')
    new_ev = new_props.get('ev', 'l')
    if ev_order.get(new_ev, 0) > ev_order.get(base_ev, 0):
        merged['ev'] = new_ev

    # Prefer explicit dates from higher-priority source
    # But if base has no date and new does, use new
    if not merged.get('sd') and new_props.get('sd'):
        merged['sd'] = new_props['sd']

    # Prefer name from higher-priority source
    if not merged.get('nm') and new_props.get('nm'):
        merged['nm'] = new_props['nm']

    # Keep NVDB ID if available
    if not merged.get('nvdb_id') and new_props.get('nvdb_id'):
        merged['nvdb_id'] = new_props['nvdb_id']

    # Add merge metadata
    if '_merge_info' not in merged:
        merged['_merge_info'] = {
            'matched_at': datetime.utcnow().isoformat(),
            'sources': {}
        }

    merged['_merge_info']['sources'][new_props.get('_src', 'unknown')] = {
        'src_id': new_props.get('_src_id'),
        'sd': new_props.get('sd'),
        'ev': new_props.get('ev')
    }

    return merged


def infer_dates_from_historical_maps(features: List[Dict], config: Dict) -> List[Dict]:
    """
    Infer road construction dates from historical map presence.

    Logic:
    - If road in 1880 map: start_date = 1880 (or earlier)
    - If road in 1904 but not 1880: start_date = 1890 (midpoint)
    - If road only in modern: leave unknown

    Only applies to roads without explicit dates.
    """
    date_inference = config.get('date_inference', {})
    if not date_inference.get('enabled', True):
        return features

    # Find historical map sources
    historical_years = {}
    for feat in features:
        src = feat.get('properties', {}).get('_src', '')
        if 'ml_' in src or 'kv' in src.lower() or 'kartverket' in src.lower():
            # Extract year
            import re
            match = re.search(r'(\d{4})', src)
            if match:
                year = int(match.group(1))
                if year < 2000:
                    historical_years[feat['properties'].get('_src_id')] = year

    # Apply inference
    for feat in features:
        props = feat.get('properties', {})

        # Skip if already has explicit date
        if props.get('sd'):
            continue

        # Check merge info for historical sources
        merge_info = props.get('_merge_info', {})
        sources = merge_info.get('sources', {})

        historical_dates = []
        for src_name, src_info in sources.items():
            if 'ml_' in src_name or 'kv' in src_name.lower():
                sd = src_info.get('sd')
                if sd and sd < 2000:
                    historical_dates.append(sd)

        # Also check src_all
        for src in props.get('src_all', []):
            if src in historical_years:
                # This road was in a historical map
                pass

        if historical_dates:
            # Use oldest historical date
            props['sd'] = min(historical_dates)
            props['sd_inferred'] = True

    return features


def infer_dates_from_buildings(
    road_features: List[Dict],
    building_features: List[Dict],
    buffer_m: float = 50.0
) -> Tuple[List[Dict], Dict]:
    """
    Infer road construction dates from nearby buildings.

    For roads without dates, find buildings within buffer distance
    and use the median building construction date as road date estimate.

    Args:
        road_features: List of road features
        building_features: List of building features (from buildings_unified.geojson)
        buffer_m: Buffer distance in meters for finding nearby buildings

    Returns:
        Tuple of (updated road features, stats dict)
    """
    import statistics

    if not HAS_SHAPELY:
        print("Warning: shapely not available, skipping building-based date inference")
        return road_features, {'skipped': True, 'reason': 'no_shapely'}

    print(f"\n=== DATE INFERENCE FROM BUILDINGS (buffer: {buffer_m}m) ===")

    # Filter buildings with dates and good evidence
    dated_buildings = []
    building_centroids = []

    for b in building_features:
        props = b.get('properties', {})
        sd = props.get('sd')
        ev = props.get('ev', '')

        # Only use buildings with high/medium evidence
        if sd and ev in ('h', 'm'):
            try:
                geom = shape(b['geometry'])
                if geom.is_valid:
                    dated_buildings.append(b)
                    building_centroids.append(geom.centroid)
            except Exception:
                continue

    print(f"  Building donors (h/m evidence): {len(dated_buildings)}")

    if not dated_buildings:
        print("  No dated buildings available")
        return road_features, {
            'buildings_available': 0,
            'roads_processed': 0,
            'roads_dated': 0
        }

    # Build spatial index
    building_tree = STRtree(building_centroids)

    # Convert buffer from meters to degrees (approximate at 63°N)
    buffer_deg = (buffer_m / 1000.0) * 0.025

    # Process roads without dates
    roads_processed = 0
    roads_dated = 0

    for road in road_features:
        props = road.get('properties', {})

        # Skip if already has date
        if props.get('sd'):
            continue

        roads_processed += 1

        try:
            geom = shape(road['geometry'])
            if not geom.is_valid:
                continue

            # Query nearby buildings
            query_box = geom.buffer(buffer_deg)
            candidate_indices = building_tree.query(query_box)

            # Collect dates from nearby buildings
            nearby_dates = []
            for idx in candidate_indices:
                building_centroid = building_centroids[idx]

                # Calculate actual distance
                dist_m = geom.distance(building_centroid) * 80000  # Approx conversion to meters

                if dist_m <= buffer_m:
                    building_sd = dated_buildings[idx]['properties']['sd']
                    nearby_dates.append(building_sd)

            # Use median if we found nearby buildings
            if nearby_dates:
                median_date = int(statistics.median(nearby_dates))
                props['sd'] = median_date
                props['ev'] = 'l'  # Low evidence for inferred dates
                props['sd_inferred'] = True
                props['sd_method'] = 'nearby_buildings'
                props['sd_building_count'] = len(nearby_dates)
                roads_dated += 1

        except Exception:
            continue

    print(f"  Roads processed: {roads_processed}")
    print(f"  Roads dated from buildings: {roads_dated}")

    stats = {
        'buildings_available': len(dated_buildings),
        'roads_processed': roads_processed,
        'roads_dated': roads_dated
    }

    return road_features, stats


def classify_road_changes(merged_features: List[Dict], all_features: List[Dict]) -> Tuple[List[Dict], List[Dict], Dict]:
    """
    Classify road changes and separate removed roads.

    Analyzes merged features to identify:
    - Current roads (exist in OSM)
    - Removed roads (historical only, not in OSM)
    - Changed roads (route modifications)

    Args:
        merged_features: Merged road features
        all_features: All original features before merging

    Returns:
        Tuple of (current_roads, removed_roads, stats)
    """
    current_roads = []
    removed_roads = []

    stats = {
        'total_roads': len(merged_features),
        'current_roads': 0,
        'removed_roads': 0,
        'roads_with_historical_source': 0
    }

    for feat in merged_features:
        props = feat.get('properties', {})
        sources = props.get('src_all', [props.get('_src')])

        # Check if road exists in OSM (current)
        has_osm = 'osm' in sources or props.get('_src') == 'osm'

        # Check if road has historical sources
        has_historical = any('ml_' in s or 'kv' in s.lower() or s == 'manual' for s in sources)

        if has_osm:
            # Road exists in modern OSM
            current_roads.append(feat)
            stats['current_roads'] += 1

            if has_historical:
                stats['roads_with_historical_source'] += 1
        else:
            # Road only in historical sources - it was removed
            removed_roads.append(feat)
            stats['removed_roads'] += 1

            # Mark as removed
            props['status'] = 'removed'
            props['rt'] = 'historical'

            # Infer end date if not set (assume removed by 1950)
            if not props.get('ed'):
                props['ed'] = 1950
                props['ed_inferred'] = True

    stats['total_roads'] = len(merged_features)

    return current_roads, removed_roads, stats


def print_road_quality_summary(report: Dict):
    """Print a human-readable summary of the road quality report to console."""
    print("\n" + "="*60)
    print("ROAD DATA QUALITY REPORT")
    print("="*60)

    # Date coverage
    print("\n[DATE COVERAGE]")
    dc = report['date_coverage']
    total = report['total_roads']
    print(f"  With dates: {dc['with_dates']} ({dc['with_dates']/total*100:.1f}%)")
    print(f"  Dates inferred: {dc['dates_inferred']}")
    print(f"  Without dates: {dc['without_dates']} ({dc['without_dates']/total*100:.1f}%)")

    # Source coverage
    print("\n[SOURCE COVERAGE]")
    for source, count in sorted(report['source_coverage']['by_source'].items()):
        print(f"  {source}: {count} roads")
    print(f"  Multi-source roads: {report['source_coverage']['multi_source']}")
    print(f"  Single-source roads: {report['source_coverage']['single_source']}")

    # Evidence quality
    print("\n[EVIDENCE QUALITY]")
    ev = report['source_coverage']['by_evidence']
    print(f"  High evidence: {ev['h']}")
    print(f"  Medium evidence: {ev['m']}")
    print(f"  Low evidence: {ev['l']}")
    print(f"  No evidence: {ev['none']}")

    # Road types
    print("\n[ROAD TYPES]")
    for rt, count in sorted(report['road_types'].items(), key=lambda x: x[1], reverse=True)[:10]:
        print(f"  {rt}: {count}")

    # Length stats
    print("\n[LENGTH STATISTICS]")
    print(f"  Total network: {report['length_stats']['total_km']} km")
    print(f"  By type:")
    for rt, km in sorted(report['length_stats']['by_type'].items(), key=lambda x: x[1], reverse=True)[:5]:
        print(f"    {rt}: {km} km")

    print("\n" + "="*60)


def generate_road_quality_report(features: List[Dict], config: Dict) -> Dict:
    """Generate quality report for merged road data."""
    report = {
        'generated_at': datetime.utcnow().isoformat(),
        'total_roads': len(features),
        'date_coverage': {
            'with_dates': 0,
            'dates_inferred': 0,
            'without_dates': 0
        },
        'source_coverage': {
            'by_source': {},
            'by_evidence': {'h': 0, 'm': 0, 'l': 0, 'none': 0},
            'multi_source': 0,
            'single_source': 0
        },
        'road_types': {},
        'length_stats': {
            'total_km': 0,
            'by_type': {}
        }
    }

    for feat in features:
        props = feat.get('properties', {})

        # Date coverage
        if props.get('sd'):
            report['date_coverage']['with_dates'] += 1
            if props.get('sd_inferred'):
                report['date_coverage']['dates_inferred'] += 1
        else:
            report['date_coverage']['without_dates'] += 1

        # Source coverage
        sources = props.get('src_all', [props.get('_src')])
        if isinstance(sources, list):
            for src in sources:
                if src:
                    report['source_coverage']['by_source'][src] = \
                        report['source_coverage']['by_source'].get(src, 0) + 1

            if len(sources) > 1:
                report['source_coverage']['multi_source'] += 1
            else:
                report['source_coverage']['single_source'] += 1

        # Evidence
        evidence = props.get('ev', 'none')
        if evidence in ['h', 'm', 'l']:
            report['source_coverage']['by_evidence'][evidence] += 1
        else:
            report['source_coverage']['by_evidence']['none'] += 1

        # Road types
        rt = props.get('rt', 'unknown')
        report['road_types'][rt] = report['road_types'].get(rt, 0) + 1

        # Length
        length = props.get('len', 0)
        if length:
            length_km = length / 1000
            report['length_stats']['total_km'] += length_km
            report['length_stats']['by_type'][rt] = \
                report['length_stats']['by_type'].get(rt, 0) + length_km

    # Round length stats
    report['length_stats']['total_km'] = round(report['length_stats']['total_km'], 2)
    for rt in report['length_stats']['by_type']:
        report['length_stats']['by_type'][rt] = round(report['length_stats']['by_type'][rt], 2)

    return report


def merge_roads(config_path: Path, output_path: Optional[Path] = None) -> bool:
    """
    Main road merge function.

    Args:
        config_path: Path to roads_merge_config.json
        output_path: Override output path (optional)

    Returns:
        True if successful
    """
    print("Loading road merge configuration...")
    config = load_config(config_path)
    base_dir = config_path.parent

    # Load enabled sources in priority order
    sources_config = config['sources']
    sorted_sources = sorted(
        sources_config.items(),
        key=lambda x: x[1].get('priority', 999)
    )

    print(f"\nLoading road sources (priority order):")
    all_features = []
    source_stats = {}

    for source_id, source_config in sorted_sources:
        if not source_config.get('enabled', False):
            print(f"  - {source_id}: DISABLED")
            continue

        features = load_source(source_config, base_dir)
        if features is None:
            print(f"  - {source_id}: NOT FOUND")
            continue

        print(f"  - {source_id}: {len(features)} roads (priority {source_config.get('priority', 999)})")
        source_stats[source_id] = len(features)

        # Tag features with source priority
        for f in features:
            f['_priority'] = source_config.get('priority', 999)
            f['_source_config'] = source_config

        all_features.extend(features)

    if not all_features:
        print("\nNo road features to merge!")
        return False

    print(f"\nTotal road features before merging: {len(all_features)}")

    # Merge matching features
    print("\nMatching road features across sources...")
    matching_config = config.get('matching', {})
    threshold = matching_config.get('min_overlap_ratio', 0.3)

    merged_features = []
    matched_ids = set()

    # Process features in priority order
    all_features.sort(key=lambda f: f.get('_priority', 999))

    # Build spatial index
    spatial_index = None
    if HAS_SHAPELY and len(all_features) > 50:
        print("Building spatial index for road matching...")
        spatial_index = build_spatial_index(all_features)
        if spatial_index:
            print(f"  Indexed {len(spatial_index[1])} road geometries")

    for feat in all_features:
        feat_id = f"{feat['properties'].get('_src')}:{feat['properties'].get('_src_id')}"

        if feat_id in matched_ids:
            continue

        # Find matches
        if spatial_index:
            matches = find_road_matches(feat, [], config, spatial_index, threshold)
            matches = [(m, s) for m, s in matches
                      if f"{m['properties'].get('_src')}:{m['properties'].get('_src_id')}" not in matched_ids]
        else:
            remaining = [f for f in all_features
                        if f"{f['properties'].get('_src')}:{f['properties'].get('_src_id')}" not in matched_ids
                        and f is not feat]
            matches = find_road_matches(feat, remaining, config, None, threshold)

        # Merge all matches
        merged_props = dict(feat['properties'])
        for match_feat, score in matches:
            match_id = f"{match_feat['properties'].get('_src')}:{match_feat['properties'].get('_src_id')}"
            matched_ids.add(match_id)

            merged_props = merge_road_properties(
                merged_props,
                match_feat['properties'],
                priority='base'
            )

        # Clean up internal fields
        if '_priority' in merged_props:
            del merged_props['_priority']
        if '_source_config' in merged_props:
            del merged_props['_source_config']

        merged_feat = {
            'type': 'Feature',
            'properties': merged_props,
            'geometry': feat['geometry']
        }
        merged_features.append(merged_feat)
        matched_ids.add(feat_id)

    print(f"Road features after merging: {len(merged_features)}")

    # Infer dates from historical maps
    print("\nInferring dates from historical map presence...")
    merged_features = infer_dates_from_historical_maps(merged_features, config)

    dated_after_maps = sum(1 for f in merged_features if f['properties'].get('sd'))
    print(f"Roads with dates after historical map inference: {dated_after_maps}")

    # Infer dates from nearby buildings
    building_inference_config = config.get('building_date_inference', {})
    if building_inference_config.get('enabled', True):
        buildings_path = building_inference_config.get(
            'buildings_file',
            base_dir / 'buildings_unified.geojson'
        )

        # Convert to Path if string
        if isinstance(buildings_path, str):
            buildings_path = Path(buildings_path)

        # Resolve relative path
        if not buildings_path.is_absolute():
            buildings_path = base_dir / buildings_path

        if buildings_path.exists():
            print(f"\nLoading buildings from {buildings_path}...")
            try:
                with open(buildings_path) as f:
                    buildings_data = json.load(f)
                building_features = buildings_data.get('features', [])
                print(f"  Loaded {len(building_features)} buildings")

                buffer_m = building_inference_config.get('buffer_m', 50.0)
                merged_features, building_stats = infer_dates_from_buildings(
                    merged_features,
                    building_features,
                    buffer_m=buffer_m
                )
            except Exception as e:
                print(f"  Warning: Could not load buildings: {e}")
        else:
            print(f"\nBuildings file not found: {buildings_path}")
            print("  Skipping building-based date inference")

    dated = sum(1 for f in merged_features if f['properties'].get('sd'))
    print(f"\nFinal roads with dates: {dated}")

    # Classify road changes
    print("\nClassifying road changes...")
    current_roads, removed_roads, change_stats = classify_road_changes(merged_features, all_features)
    print(f"  Current roads (in OSM): {change_stats['current_roads']}")
    print(f"  Removed roads (historical only): {change_stats['removed_roads']}")
    print(f"  Roads with historical sources: {change_stats['roads_with_historical_source']}")

    # Combine all roads (current + removed) for output
    all_output_roads = current_roads + removed_roads

    # Generate output
    output = {
        'type': 'FeatureCollection',
        'features': all_output_roads
    }

    # Determine output path
    if output_path is None:
        # Support both old format (string) and new format (dict with output_file key)
        output_config = config.get('output', {})
        if isinstance(output_config, str):
            output_file = output_config
        else:
            output_file = output_config.get('output_file', 'roads_temporal.geojson')
        output_path = base_dir / output_file

    print(f"\nWriting output to {output_path}...")
    with open(output_path, 'w') as f:
        json.dump(output, f)

    # Generate report
    report = {
        'merged_at': datetime.utcnow().isoformat(),
        'config_file': str(config_path),
        'source_stats': source_stats,
        'total_input': sum(source_stats.values()),
        'total_output': len(all_output_roads),
        'roads_with_dates': dated,
        'change_classification': change_stats
    }

    report_path = output_path.with_suffix('.report.json')
    with open(report_path, 'w') as f:
        json.dump(report, f, indent=2)

    # Generate quality report
    print("\nGenerating road data quality report...")
    quality_report = generate_road_quality_report(all_output_roads, config)

    quality_path = output_path.with_name(output_path.stem + '.quality.json')
    with open(quality_path, 'w') as f:
        json.dump(quality_report, f, indent=2)

    # Print quality summary
    print_road_quality_summary(quality_report)

    print(f"\nRoad merge complete!")
    print(f"  Output: {output_path}")
    print(f"  Report: {report_path}")
    print(f"  Quality Report: {quality_path}")

    return True


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description='Merge road data from multiple sources')
    parser.add_argument('--config', '-c', type=Path,
                        default=Path(__file__).parent.parent.parent / 'data' / 'merged' / 'roads_merge_config.json',
                        help='Path to roads_merge_config.json')
    parser.add_argument('--output', '-o', type=Path, default=None,
                        help='Output file path (overrides config)')

    args = parser.parse_args()

    if not args.config.exists():
        print(f"Config file not found: {args.config}")
        print(f"Creating default config at {args.config}...")

        # Create default config
        default_config = {
            "version": "1.0",
            "description": "Road merge configuration for Trondheim historical map",
            "sources": {
                "osm_roads": {
                    "enabled": True,
                    "path": "../sources/osm_roads/normalized/roads.geojson",
                    "priority": 1,
                    "comment": "OSM roads as baseline"
                },
                "ml_kartverket_1880": {
                    "enabled": False,
                    "path": "../sources/ml_detected/kartverket_1880/normalized/roads.geojson",
                    "priority": 10,
                    "reference_year": 1880,
                    "comment": "ML-detected roads from 1880 Kartverket map"
                },
                "ml_kartverket_1904": {
                    "enabled": False,
                    "path": "../sources/ml_detected/kartverket_1904/normalized/roads.geojson",
                    "priority": 11,
                    "reference_year": 1904,
                    "comment": "ML-detected roads from 1904 Kartverket map"
                },
                "manual": {
                    "enabled": False,
                    "path": "../sources/manual/normalized/roads.geojson",
                    "priority": 5,
                    "comment": "Manually digitized roads"
                }
            },
            "matching": {
                "method": "network_topology",
                "buffer_distance_m": 10,
                "min_overlap_ratio": 0.3,
                "hausdorff_threshold_m": 20,
                "name_match_boost": 0.3
            },
            "date_inference": {
                "enabled": True,
                "comment": "Infer dates from historical map presence"
            },
            "building_date_inference": {
                "enabled": True,
                "buildings_file": "buildings_unified.geojson",
                "buffer_m": 50.0,
                "comment": "Infer road dates from nearby buildings"
            },
            "output": {
                "output_file": "roads_temporal.geojson"
            }
        }

        args.config.parent.mkdir(parents=True, exist_ok=True)
        with open(args.config, 'w') as f:
            json.dump(default_config, f, indent=2)

        print(f"Created default config. Edit as needed and re-run.")
        sys.exit(0)

    success = merge_roads(args.config, args.output)
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
