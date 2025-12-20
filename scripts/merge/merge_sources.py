#!/usr/bin/env python3
"""
Merge normalized building data from multiple sources.

Reads merge_config.json and combines enabled sources according to:
- Priority order
- Spatial matching rules
- Conflict resolution rules
- Building replacement detection
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Optional: Use shapely for spatial operations if available
try:
    from shapely.geometry import shape, mapping
    from shapely.ops import unary_union
    from shapely.strtree import STRtree
    HAS_SHAPELY = True
except ImportError:
    HAS_SHAPELY = False
    print("Warning: shapely not installed. Spatial matching will be limited.")


def load_config(config_path: Path) -> Dict:
    """Load and validate merge configuration."""
    with open(config_path) as f:
        config = json.load(f)

    # Validate required fields
    required = ['sources', 'matching', 'conflict_resolution', 'output']
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


def build_osm_ref_index(features: List[Dict]) -> Dict[str, Dict]:
    """
    Build an index of features by their osm_ref field for O(1) lookup.

    Args:
        features: List of GeoJSON features

    Returns:
        Dictionary mapping osm_ref values to features
    """
    index = {}
    for feat in features:
        props = feat.get('properties', {})
        osm_ref = props.get('osm_ref')
        if osm_ref:
            index[osm_ref] = feat
        # Also index by _src_id for OSM features
        if props.get('_src') == 'osm':
            src_id = props.get('_src_id', '')
            if src_id:
                index[src_id] = feat
    return index


def find_osm_ref_match(feature: Dict, osm_ref_index: Dict[str, Dict]) -> Optional[Dict]:
    """
    Find a matching feature via osm_ref field.

    Args:
        feature: Feature to find match for (should have osm_ref property)
        osm_ref_index: Index built by build_osm_ref_index

    Returns:
        Matching feature or None
    """
    osm_ref = feature.get('properties', {}).get('osm_ref')
    if not osm_ref:
        return None
    return osm_ref_index.get(osm_ref)


def calculate_overlap(geom1: Dict, geom2: Dict) -> float:
    """
    Calculate overlap ratio between two geometries.

    Returns ratio of intersection area to smaller geometry area.
    """
    if not HAS_SHAPELY:
        # Fallback: simple bounding box check
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

    except Exception:
        return 0.0


def build_spatial_index(features: List[Dict]) -> Optional[Tuple[Any, List, List[Dict]]]:
    """
    Build a spatial index for fast lookup.

    Args:
        features: List of GeoJSON features

    Returns:
        Tuple of (STRtree index, list of shapely geometries, list of features)
        or None if shapely is not available or features is empty
    """
    if not HAS_SHAPELY:
        return None

    if not features:
        return None

    geometries = []
    indexed_features = []

    for feat in features:
        geom = feat.get('geometry')
        if not geom:
            continue

        try:
            shp = shape(geom)
            if shp.is_valid:
                geometries.append(shp)
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


def find_matches(
    feature: Dict,
    candidates: List[Dict],
    threshold: float = 0.5,
    spatial_index: Optional[Tuple[Any, List, List[Dict]]] = None
) -> List[Tuple[Dict, float]]:
    """
    Find matching features based on spatial overlap.

    Args:
        feature: Feature to find matches for
        candidates: List of candidate features (used only if spatial_index is None)
        threshold: Minimum overlap ratio to consider a match
        spatial_index: Optional tuple of (STRtree, geometries, features) for O(log n) lookup

    Returns:
        List of (feature, overlap_score) tuples sorted by score descending.
    """
    matches = []
    geom = feature.get('geometry')
    if not geom:
        return matches

    # Use spatial index if available for O(log n) performance
    if spatial_index is not None and HAS_SHAPELY:
        index, geometries, indexed_features = spatial_index

        try:
            query_shape = shape(geom)
            if not query_shape.is_valid:
                return matches

            # Query index for candidates that intersect the bounding box
            candidate_indices = index.query(query_shape)

            # Calculate precise overlap only for candidates
            for idx in candidate_indices:
                candidate = indexed_features[idx]
                cand_geom = geometries[idx]

                # Skip self-match
                feat_id = f"{feature['properties'].get('_src')}:{feature['properties'].get('_src_id')}"
                cand_id = f"{candidate['properties'].get('_src')}:{candidate['properties'].get('_src_id')}"
                if feat_id == cand_id:
                    continue

                try:
                    # Calculate precise overlap
                    intersection = query_shape.intersection(cand_geom)
                    if intersection.is_empty:
                        continue

                    min_area = min(query_shape.area, cand_geom.area)
                    if min_area == 0:
                        continue

                    overlap = intersection.area / min_area
                    if overlap >= threshold:
                        matches.append((candidate, overlap))

                except Exception:
                    continue

        except Exception:
            # Fall back to O(n²) if spatial index fails
            pass

    # Fall back to O(n²) iteration if no spatial index or if it failed
    if not matches and spatial_index is None:
        for candidate in candidates:
            cand_geom = candidate.get('geometry')
            if not cand_geom:
                continue

            overlap = calculate_overlap(geom, cand_geom)
            if overlap >= threshold:
                matches.append((candidate, overlap))

    return sorted(matches, key=lambda x: x[1], reverse=True)


def merge_properties(
    base_props: Dict,
    new_props: Dict,
    base_config: Optional[Dict] = None,
    new_config: Optional[Dict] = None
) -> Dict:
    """
    Merge properties from two features with date priority resolution.

    Args:
        base_props: Properties from first source
        new_props: Properties from second source
        base_config: Source config for base (contains date_priority)
        new_config: Source config for new (contains date_priority)

    Returns:
        Merged properties with date priority resolution
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

    # Add merge metadata
    if '_merge_info' not in merged:
        merged['_merge_info'] = {
            'matched_at': datetime.utcnow().isoformat(),
            'sources': {},
            'dates': {}
        }

    # Track source info
    merged['_merge_info']['sources'][new_props.get('_src', 'unknown')] = {
        'src_id': new_props.get('_src_id'),
        'sd': new_props.get('sd'),
        'ev': new_props.get('ev')
    }

    # Track all dates from all sources
    if 'dates' not in merged['_merge_info']:
        merged['_merge_info']['dates'] = {}

    base_src = base_props.get('_src', 'unknown')
    new_src = new_props.get('_src', 'unknown')

    if base_props.get('sd') is not None:
        merged['_merge_info']['dates'][base_src] = base_props.get('sd')
    if new_props.get('sd') is not None:
        merged['_merge_info']['dates'][new_src] = new_props.get('sd')

    # Date priority resolution for 'sd' (construction year)
    # Lower date_priority number = higher priority
    base_date_priority = 999
    new_date_priority = 999

    if base_config:
        base_date_priority = base_config.get('date_priority', base_config.get('priority', 999))
    if new_config:
        new_date_priority = new_config.get('date_priority', new_config.get('priority', 999))

    base_sd = base_props.get('sd')
    new_sd = new_props.get('sd')

    # Determine which source's date to use
    if base_sd is not None and new_sd is not None:
        # Both have dates - use date_priority
        if new_date_priority < base_date_priority:
            merged['sd'] = new_sd
            merged['sd_src'] = new_src
        else:
            merged['sd'] = base_sd
            merged['sd_src'] = base_src
    elif new_sd is not None and base_sd is None:
        # Only new has date
        merged['sd'] = new_sd
        merged['sd_src'] = new_src
    elif base_sd is not None:
        # Only base has date (keep it)
        merged['sd_src'] = base_src

    return merged


def parse_min_evidence_from_rule(rule: Dict) -> str:
    """
    Parse minimum evidence level from a rule's old_building_hidden_when string.

    Examples:
    - "new_building_evidence >= high" -> "h"
    - "new_building_evidence >= medium" -> "m"
    - "new_building_exists" -> "l" (any evidence)

    Args:
        rule: Rule dict with 'old_building_hidden_when' field

    Returns:
        Evidence level: 'h', 'm', or 'l'
    """
    condition = rule.get('old_building_hidden_when', '').lower()

    if 'high' in condition:
        return 'h'
    elif 'medium' in condition:
        return 'm'
    else:
        # "new_building_exists" or any other condition means any evidence is sufficient
        return 'l'


def detect_replacements(
    features: List[Dict],
    config: Dict
) -> List[Dict]:
    """
    Detect building replacements and infer end dates.

    For each historical building, check if a newer building overlaps.
    Uses era-based rules to determine if replacement should be marked:
    - pre_1900 (sd < 1900): requires high evidence (h)
    - 1900_1950 (1900 <= sd < 1950): requires medium evidence (m)
    - post_1950 (sd >= 1950): requires any evidence

    When a replacement is detected:
    - If old building has no explicit end date (ed), infer it from new building's start date
    - The inferred demolition year can be new_sd or new_sd - 1 (configurable via infer_demolition_offset)
    - Explicit end dates are never overridden

    Falls back to simple overlap threshold if era rules not configured.
    """
    if not config.get('replacement_detection', {}).get('enabled', False):
        return features

    replacement_config = config.get('replacement_detection', {})
    threshold = replacement_config.get('overlap_threshold', 0.5)

    # Offset for inferring demolition date: 0 = same year as new building, -1 = year before
    # Default to 0 (demolished same year new building was constructed)
    demolition_offset = replacement_config.get('infer_demolition_offset', 0)

    # Load era-based rules if available
    era_rules = config.get('replacement_detection', {}).get('rules', [])
    use_era_rules = bool(era_rules)

    # Evidence ordering for comparison
    ev_order = {'h': 3, 'm': 2, 'l': 1}

    # Separate buildings with dates from those without
    dated = [f for f in features if f['properties'].get('sd')]
    undated = [f for f in features if not f['properties'].get('sd')]

    # Sort by start date
    dated.sort(key=lambda f: f['properties'].get('sd', 9999))

    # Build spatial index for all newer buildings (dated[i+1:] + undated)
    # We'll build it once for all features for simplicity
    all_newer = dated + undated
    spatial_index = None
    if HAS_SHAPELY and len(all_newer) > 100:
        print("  Building spatial index for replacement detection...")
        spatial_index = build_spatial_index(all_newer)
        if spatial_index:
            print(f"  Indexed {len(spatial_index[1])} geometries")

    # Check each building for replacements
    for i, old_feat in enumerate(dated):
        old_sd = old_feat['properties'].get('sd')
        if not old_sd:
            continue

        # Prepare list of newer buildings
        newer_buildings = dated[i+1:] + undated

        # Use spatial index if available
        if spatial_index:
            # Find all overlapping buildings using spatial index
            matches = find_matches(old_feat, [], threshold, spatial_index)

            for new_feat, overlap in matches:
                new_sd = new_feat['properties'].get('sd')

                # Skip if new building is older or same age
                if new_sd and new_sd <= old_sd:
                    continue

                # Determine if replacement should be marked
                should_mark_replacement = False

                if use_era_rules:
                    # Determine era of old building
                    if old_sd < 1900:
                        era = 'pre_1900'
                    elif old_sd < 1950:
                        era = '1900_1950'
                    else:
                        era = 'post_1950'

                    # Find matching rule from the rules array
                    era_rule = next((r for r in era_rules if r.get('era') == era), None)
                    if era_rule:
                        min_evidence = parse_min_evidence_from_rule(era_rule)
                    else:
                        # Fallback if no rule found for this era
                        min_evidence = 'l'

                    # Get new building evidence
                    new_ev = new_feat['properties'].get('ev', 'l')

                    # Check if new building meets evidence requirement
                    new_ev_level = ev_order.get(new_ev, 0)
                    min_ev_level = ev_order.get(min_evidence, 0)

                    should_mark_replacement = new_ev_level >= min_ev_level
                else:
                    # Backward compatibility: mark all overlapping as replacements
                    should_mark_replacement = True

                if should_mark_replacement:
                    # Mark old building as replaced
                    old_feat['properties']['rep_by'] = new_feat['properties'].get('_src_id')
                    old_feat['properties']['rep_ev'] = new_feat['properties'].get('ev', 'l')

                    # Infer demolition date only if not explicitly set
                    if old_feat['properties'].get('ed') is None:
                        if new_sd:
                            # Use new building's start date with optional offset
                            old_feat['properties']['ed'] = new_sd + demolition_offset
                            old_feat['properties']['ed_inferred'] = True
                        else:
                            # New building has no date, assume modern (1950)
                            old_feat['properties']['ed'] = 1950
                            old_feat['properties']['ed_inferred'] = True

                    break  # Only one replacement per building
        else:
            # Fall back to O(n²) if no spatial index
            for new_feat in newer_buildings:
                new_sd = new_feat['properties'].get('sd')

                # Skip if new building is older or same age
                if new_sd and new_sd <= old_sd:
                    continue

                # Check overlap
                overlap = calculate_overlap(
                    old_feat.get('geometry'),
                    new_feat.get('geometry')
                )

                if overlap >= threshold:
                    # Determine if replacement should be marked
                    should_mark_replacement = False

                    if use_era_rules:
                        # Determine era of old building
                        if old_sd < 1900:
                            era = 'pre_1900'
                        elif old_sd < 1950:
                            era = '1900_1950'
                        else:
                            era = 'post_1950'

                        # Find matching rule from the rules array
                        era_rule = next((r for r in era_rules if r.get('era') == era), None)
                        if era_rule:
                            min_evidence = parse_min_evidence_from_rule(era_rule)
                        else:
                            # Fallback if no rule found for this era
                            min_evidence = 'l'

                        # Get new building evidence
                        new_ev = new_feat['properties'].get('ev', 'l')

                        # Check if new building meets evidence requirement
                        new_ev_level = ev_order.get(new_ev, 0)
                        min_ev_level = ev_order.get(min_evidence, 0)

                        should_mark_replacement = new_ev_level >= min_ev_level
                    else:
                        # Backward compatibility: mark all overlapping as replacements
                        should_mark_replacement = True

                    if should_mark_replacement:
                        # Mark old building as replaced
                        old_feat['properties']['rep_by'] = new_feat['properties'].get('_src_id')
                        old_feat['properties']['rep_ev'] = new_feat['properties'].get('ev', 'l')

                        # Infer demolition date only if not explicitly set
                        if old_feat['properties'].get('ed') is None:
                            if new_sd:
                                # Use new building's start date with optional offset
                                old_feat['properties']['ed'] = new_sd + demolition_offset
                                old_feat['properties']['ed_inferred'] = True
                            else:
                                # New building has no date, assume modern (1950)
                                old_feat['properties']['ed'] = 1950
                                old_feat['properties']['ed_inferred'] = True

                        break  # Only one replacement per building

    return features


def generate_quality_report(features: List[Dict], config: Dict) -> Dict:
    """
    Analyze merged data quality and return a comprehensive report.

    Args:
        features: List of merged building features
        config: Merge configuration

    Returns:
        Dictionary containing quality metrics and anomalies
    """
    report = {
        'generated_at': datetime.utcnow().isoformat(),
        'total_buildings': len(features),
        'date_anomalies': {
            'future_dates': [],
            'suspiciously_old': [],
            'invalid_date_ranges': []
        },
        'source_coverage': {
            'by_source': {},
            'by_evidence': {'h': 0, 'm': 0, 'l': 0, 'none': 0},
            'multi_source': 0,
            'single_source': 0
        },
        'spatial_issues': {
            'invalid_geometries': [],
            'very_small_buildings': [],
            'very_large_buildings': []
        },
        'replacement_stats': {
            'total_replacements': 0,
            'demolition_dates_inferred': 0,
            'demolition_dates_explicit': 0,
            'by_era': {
                'pre_1900': 0,
                '1900_1950': 0,
                'post_1950': 0
            },
            'lifespans': []
        }
    }

    # Analyze each feature
    for feat in features:
        props = feat.get('properties', {})
        geom = feat.get('geometry')

        # 1. Date anomalies
        start_date = props.get('sd')
        end_date = props.get('ed')

        if start_date:
            if start_date > 2025:
                report['date_anomalies']['future_dates'].append({
                    'id': props.get('_src_id'),
                    'source': props.get('_src'),
                    'start_date': start_date
                })
            elif start_date < 1600:
                report['date_anomalies']['suspiciously_old'].append({
                    'id': props.get('_src_id'),
                    'source': props.get('_src'),
                    'start_date': start_date
                })

        if start_date and end_date and end_date <= start_date:
            report['date_anomalies']['invalid_date_ranges'].append({
                'id': props.get('_src_id'),
                'source': props.get('_src'),
                'start_date': start_date,
                'end_date': end_date
            })

        # 2. Source coverage
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

        # Evidence level
        evidence = props.get('ev', 'none')
        if evidence in ['h', 'm', 'l']:
            report['source_coverage']['by_evidence'][evidence] += 1
        else:
            report['source_coverage']['by_evidence']['none'] += 1

        # 3. Spatial issues
        if HAS_SHAPELY and geom:
            try:
                geom_shape = shape(geom)

                # Check validity
                if not geom_shape.is_valid:
                    report['spatial_issues']['invalid_geometries'].append({
                        'id': props.get('_src_id'),
                        'source': props.get('_src'),
                        'reason': 'invalid_geometry'
                    })

                # Check area
                area = geom_shape.area
                if area < 5:  # Very small (< 5 sq meters)
                    report['spatial_issues']['very_small_buildings'].append({
                        'id': props.get('_src_id'),
                        'source': props.get('_src'),
                        'area': round(area, 2)
                    })
                elif area > 50000:  # Very large (> 50000 sq meters)
                    report['spatial_issues']['very_large_buildings'].append({
                        'id': props.get('_src_id'),
                        'source': props.get('_src'),
                        'area': round(area, 2)
                    })
            except Exception as e:
                report['spatial_issues']['invalid_geometries'].append({
                    'id': props.get('_src_id'),
                    'source': props.get('_src'),
                    'reason': str(e)
                })

        # 4. Replacement stats
        if end_date and props.get('rep_by'):
            report['replacement_stats']['total_replacements'] += 1

            # Track if demolition date was inferred or explicit
            if props.get('ed_inferred'):
                report['replacement_stats']['demolition_dates_inferred'] += 1
            else:
                report['replacement_stats']['demolition_dates_explicit'] += 1

            # Categorize by era
            if start_date:
                if start_date < 1900:
                    report['replacement_stats']['by_era']['pre_1900'] += 1
                elif start_date <= 1950:
                    report['replacement_stats']['by_era']['1900_1950'] += 1
                else:
                    report['replacement_stats']['by_era']['post_1950'] += 1

                # Calculate lifespan
                if end_date:
                    lifespan = end_date - start_date
                    if lifespan > 0:
                        report['replacement_stats']['lifespans'].append(lifespan)

    # Calculate summary statistics
    if report['replacement_stats']['lifespans']:
        avg_lifespan = sum(report['replacement_stats']['lifespans']) / \
                      len(report['replacement_stats']['lifespans'])
        report['replacement_stats']['average_lifespan'] = round(avg_lifespan, 1)
    else:
        report['replacement_stats']['average_lifespan'] = None

    # Calculate evidence percentages
    total = len(features)
    if total > 0:
        report['source_coverage']['evidence_percentages'] = {
            'high': round(100 * report['source_coverage']['by_evidence']['h'] / total, 1),
            'medium': round(100 * report['source_coverage']['by_evidence']['m'] / total, 1),
            'low': round(100 * report['source_coverage']['by_evidence']['l'] / total, 1),
            'none': round(100 * report['source_coverage']['by_evidence']['none'] / total, 1)
        }

    return report


def print_quality_summary(report: Dict):
    """Print a human-readable summary of the quality report to console."""
    print("\n" + "="*60)
    print("DATA QUALITY REPORT")
    print("="*60)

    # Date anomalies
    print("\n[DATE ANOMALIES]")
    print(f"  Future dates (>2025): {len(report['date_anomalies']['future_dates'])}")
    print(f"  Suspiciously old (<1600): {len(report['date_anomalies']['suspiciously_old'])}")
    print(f"  Invalid ranges (end<=start): {len(report['date_anomalies']['invalid_date_ranges'])}")

    # Source coverage
    print("\n[SOURCE COVERAGE]")
    for source, count in sorted(report['source_coverage']['by_source'].items()):
        print(f"  {source}: {count} buildings")
    print(f"  Multi-source buildings: {report['source_coverage']['multi_source']}")
    print(f"  Single-source buildings: {report['source_coverage']['single_source']}")

    print("\n[EVIDENCE QUALITY]")
    ev_pct = report['source_coverage'].get('evidence_percentages', {})
    print(f"  High evidence: {ev_pct.get('high', 0)}%")
    print(f"  Medium evidence: {ev_pct.get('medium', 0)}%")
    print(f"  Low evidence: {ev_pct.get('low', 0)}%")
    print(f"  No evidence: {ev_pct.get('none', 0)}%")

    # Spatial issues
    if HAS_SHAPELY:
        print("\n[SPATIAL ISSUES]")
        print(f"  Invalid geometries: {len(report['spatial_issues']['invalid_geometries'])}")
        print(f"  Very small buildings (<5 sq m): {len(report['spatial_issues']['very_small_buildings'])}")
        print(f"  Very large buildings (>50000 sq m): {len(report['spatial_issues']['very_large_buildings'])}")

    # Replacement stats
    print("\n[REPLACEMENT STATISTICS]")
    print(f"  Total replacements: {report['replacement_stats']['total_replacements']}")
    print(f"    - Demolition dates inferred: {report['replacement_stats']['demolition_dates_inferred']}")
    print(f"    - Demolition dates explicit: {report['replacement_stats']['demolition_dates_explicit']}")
    print(f"  By era:")
    print(f"    - Pre-1900: {report['replacement_stats']['by_era']['pre_1900']}")
    print(f"    - 1900-1950: {report['replacement_stats']['by_era']['1900_1950']}")
    print(f"    - Post-1950: {report['replacement_stats']['by_era']['post_1950']}")
    avg = report['replacement_stats']['average_lifespan']
    if avg:
        print(f"  Average lifespan: {avg} years")
    else:
        print(f"  Average lifespan: N/A")

    print("\n" + "="*60)


def merge_sources(config_path: Path, output_path: Optional[Path] = None) -> bool:
    """
    Main merge function.

    Args:
        config_path: Path to merge_config.json
        output_path: Override output path (optional)

    Returns:
        True if successful
    """
    print("Loading merge configuration...")
    config = load_config(config_path)
    base_dir = config_path.parent

    # Load enabled sources in priority order
    sources_config = config['sources']
    sorted_sources = sorted(
        sources_config.items(),
        key=lambda x: x[1].get('priority', 999)
    )

    print(f"\nLoading sources (priority order):")
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

        print(f"  - {source_id}: {len(features)} features (priority {source_config.get('priority', 999)})")
        source_stats[source_id] = len(features)

        # Tag features with source priority for later merging
        for f in features:
            f['_priority'] = source_config.get('priority', 999)
            f['_source_config'] = source_config

        all_features.extend(features)

    if not all_features:
        print("\nNo features to merge!")
        return False

    print(f"\nTotal features before merging: {len(all_features)}")

    # Merge matching features
    print("\nMatching features across sources...")
    threshold = config['matching'].get('overlap_threshold', 0.5)

    merged_features = []
    matched_ids = set()

    # Process features in priority order (already sorted)
    all_features.sort(key=lambda f: f.get('_priority', 999))

    # Build osm_ref index for FINN matching
    print("Building osm_ref index for FINN matching...")
    osm_ref_index = build_osm_ref_index(all_features)
    print(f"  Indexed {len(osm_ref_index)} osm_ref entries")

    # Build spatial index for fast matching (O(n log n) instead of O(n²))
    spatial_index = None
    if HAS_SHAPELY and len(all_features) > 100:
        print("Building spatial index for feature matching...")
        spatial_index = build_spatial_index(all_features)
        if spatial_index:
            print(f"  Indexed {len(spatial_index[1])} geometries")
        else:
            print("  Warning: Failed to build spatial index, falling back to O(n²) matching")

    if not HAS_SHAPELY:
        print("  Warning: shapely not available, using O(n²) matching")

    # Track osm_ref matches for statistics
    osm_ref_matches = 0
    spatial_matches = 0

    for feat in all_features:
        feat_id = f"{feat['properties'].get('_src')}:{feat['properties'].get('_src_id')}"

        if feat_id in matched_ids:
            continue

        feat_src = feat['properties'].get('_src')
        feat_config = feat.get('_source_config', {})

        # Check if this source uses osm_ref matching (e.g., FINN)
        match_by = feat_config.get('match_by', [])
        matches = []

        # Try osm_ref matching first if configured
        if 'osm_ref' in match_by:
            osm_match = find_osm_ref_match(feat, osm_ref_index)
            if osm_match:
                match_id = f"{osm_match['properties'].get('_src')}:{osm_match['properties'].get('_src_id')}"
                if match_id not in matched_ids and match_id != feat_id:
                    matches.append((osm_match, 1.0))  # Score 1.0 for exact osm_ref match
                    osm_ref_matches += 1

        # Fall back to spatial matching if no osm_ref match or if spatial is also configured
        if not matches and ('spatial' in match_by or not match_by):
            if spatial_index:
                spatial_matches_found = find_matches(feat, [], threshold, spatial_index)
                # Filter out already matched features
                spatial_matches_found = [(m, s) for m, s in spatial_matches_found
                          if f"{m['properties'].get('_src')}:{m['properties'].get('_src_id')}" not in matched_ids]
                if spatial_matches_found:
                    matches.extend(spatial_matches_found)
                    spatial_matches += len(spatial_matches_found)
            else:
                # Find matches in remaining features (O(n) fallback)
                remaining = [f for f in all_features
                            if f"{f['properties'].get('_src')}:{f['properties'].get('_src_id')}" not in matched_ids
                            and f is not feat]
                spatial_matches_found = find_matches(feat, remaining, threshold)
                if spatial_matches_found:
                    matches.extend(spatial_matches_found)
                    spatial_matches += len(spatial_matches_found)

        # Merge all matches into this feature
        merged_props = dict(feat['properties'])
        best_geometry = feat['geometry']
        best_geom_src = feat_src

        for match_feat, score in matches:
            match_id = f"{match_feat['properties'].get('_src')}:{match_feat['properties'].get('_src_id')}"
            matched_ids.add(match_id)

            match_config = match_feat.get('_source_config', {})

            merged_props = merge_properties(
                merged_props,
                match_feat['properties'],
                base_config=feat_config,
                new_config=match_config
            )

            # Geometry selection: prefer OSM polygons over point geometries
            match_src = match_feat['properties'].get('_src')
            match_geom = match_feat.get('geometry', {})

            # Prefer OSM geometry (usually polygons) over other sources (usually points)
            if match_src == 'osm' and match_geom:
                best_geometry = match_geom
                best_geom_src = match_src
            # Also prefer any polygon over any point
            elif match_geom.get('type') == 'Polygon' and best_geometry.get('type') == 'Point':
                best_geometry = match_geom
                best_geom_src = match_src

        # Clean up internal fields
        if '_priority' in merged_props:
            del merged_props['_priority']
        if '_source_config' in merged_props:
            del merged_props['_source_config']

        # Record geometry source
        merged_props['geom_src'] = best_geom_src

        merged_feat = {
            'type': 'Feature',
            'properties': merged_props,
            'geometry': best_geometry
        }
        merged_features.append(merged_feat)
        matched_ids.add(feat_id)

    print(f"  osm_ref matches: {osm_ref_matches}")
    print(f"  spatial matches: {spatial_matches}")

    print(f"Features after merging: {len(merged_features)}")

    # Detect replacements
    print("\nDetecting building replacements...")
    merged_features = detect_replacements(merged_features, config)

    replacements = sum(1 for f in merged_features if 'ed' in f['properties'])
    print(f"Buildings with end dates (replaced/demolished): {replacements}")

    # Generate output
    output = {
        'type': 'FeatureCollection',
        'features': merged_features
    }

    # Determine output path
    if output_path is None:
        output_file = config['output'].get('output_file', 'buildings_merged.geojson')
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
        'total_output': len(merged_features),
        'buildings_with_dates': sum(1 for f in merged_features if 'sd' in f['properties']),
        'buildings_replaced': replacements
    }

    report_path = output_path.with_suffix('.report.json')
    with open(report_path, 'w') as f:
        json.dump(report, f, indent=2)

    # Generate quality report
    print("\nGenerating data quality report...")
    quality_report = generate_quality_report(merged_features, config)

    # Save quality report to JSON
    quality_path = output_path.with_name(
        output_path.stem + '.quality.json'
    )
    with open(quality_path, 'w') as f:
        json.dump(quality_report, f, indent=2)

    # Print quality summary to console
    print_quality_summary(quality_report)

    print(f"\nMerge complete!")
    print(f"  Output: {output_path}")
    print(f"  Report: {report_path}")
    print(f"  Quality Report: {quality_path}")

    return True


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description='Merge building data from multiple sources')
    parser.add_argument('--config', '-c', type=Path,
                        default=Path(__file__).parent.parent.parent / 'data' / 'merged' / 'merge_config.json',
                        help='Path to merge_config.json')
    parser.add_argument('--output', '-o', type=Path, default=None,
                        help='Output file path (overrides config)')

    args = parser.parse_args()

    if not args.config.exists():
        print(f"Config file not found: {args.config}")
        sys.exit(1)

    success = merge_sources(args.config, args.output)
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
