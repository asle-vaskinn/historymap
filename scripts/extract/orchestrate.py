#!/usr/bin/env python3
"""
Extraction Pipeline Orchestrator.

Coordinates running multiple extractors to fetch data from external sources.

The extraction pipeline retrieves data from:
- OSM (OpenStreetMap) - buildings, roads, water via Overpass API
- NVDB (Norwegian Road Database) - road network
- ML (Machine Learning) - historical map inference (optional)

Usage:
    from extract.orchestrate import run_extraction

    # Run all extractors
    results = run_extraction()

    # Run specific sources
    results = run_extraction(sources=['osm', 'nvdb'])

    # Run specific feature types
    results = run_extraction(feature_types=['buildings', 'roads'])

CLI Usage:
    python scripts/extract/orchestrate.py
    python scripts/extract/orchestrate.py --sources osm nvdb
    python scripts/extract/orchestrate.py --feature-types buildings roads
    python scripts/extract/orchestrate.py --skip-ml
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

# Import extractors
try:
    from extract.base import BaseExtractor
    from extract.extract_osm import OSMExtractor
    from extract.extract_nvdb import NVDBExtractor
    from constants import DATA_DIR, EXPORT_DIR
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from extract.base import BaseExtractor
    from extract.extract_osm import OSMExtractor
    from extract.extract_nvdb import NVDBExtractor
    from constants import DATA_DIR, EXPORT_DIR


# Registry of available extractors
EXTRACTORS = {
    'osm_buildings': lambda: OSMExtractor(feature_type='buildings'),
    'osm_roads': lambda: OSMExtractor(feature_type='roads'),
    'osm_water': lambda: OSMExtractor(feature_type='water'),
    'nvdb': lambda: NVDBExtractor(),
}

# Feature type to extractor mapping
FEATURE_TYPE_EXTRACTORS = {
    'buildings': ['osm_buildings'],
    'roads': ['osm_roads', 'nvdb'],
    'water': ['osm_water'],
}

# Source to extractor mapping
SOURCE_EXTRACTORS = {
    'osm': ['osm_buildings', 'osm_roads', 'osm_water'],
    'nvdb': ['nvdb'],
}


def get_extractors(
    sources: Optional[List[str]] = None,
    feature_types: Optional[List[str]] = None
) -> List[str]:
    """Get list of extractor IDs based on filters.

    Args:
        sources: Filter by source (osm, nvdb)
        feature_types: Filter by feature type (buildings, roads, water)

    Returns:
        List of extractor IDs to run
    """
    if sources is None and feature_types is None:
        # Run all extractors
        return list(EXTRACTORS.keys())

    extractors = set()

    if sources:
        for source in sources:
            if source in SOURCE_EXTRACTORS:
                extractors.update(SOURCE_EXTRACTORS[source])

    if feature_types:
        for ft in feature_types:
            if ft in FEATURE_TYPE_EXTRACTORS:
                extractors.update(FEATURE_TYPE_EXTRACTORS[ft])

    return list(extractors)


def run_extraction(
    sources: Optional[List[str]] = None,
    feature_types: Optional[List[str]] = None,
    skip_ml: bool = True,
    force: bool = False,
    max_age_hours: float = 24.0
) -> Dict[str, Any]:
    """Run extraction for specified sources and feature types.

    Args:
        sources: Source IDs to extract (osm, nvdb). None = all
        feature_types: Feature types (buildings, roads, water). None = all
        skip_ml: Skip ML extraction (slow, requires model)
        force: Force re-extraction even if recent
        max_age_hours: Max age before extraction is needed

    Returns:
        Dict with results per extractor:
        {
            'osm_buildings': {'success': True, 'count': 1234, ...},
            'nvdb': {'success': True, 'count': 5678, ...},
            ...
            '_summary': {'total': 4, 'succeeded': 4, 'failed': 0}
        }
    """
    # Get extractors to run
    extractor_ids = get_extractors(sources, feature_types)

    if not extractor_ids:
        return {
            '_summary': {
                'total': 0,
                'succeeded': 0,
                'failed': 0,
                'skipped': 0,
                'message': 'No extractors matched the filters'
            }
        }

    print(f"=== Extraction Pipeline ===")
    print(f"Running extractors: {extractor_ids}")
    print()

    results = {}
    succeeded = 0
    failed = 0
    skipped = 0

    for extractor_id in extractor_ids:
        if extractor_id not in EXTRACTORS:
            print(f"Unknown extractor: {extractor_id}")
            continue

        print(f"--- {extractor_id} ---")

        # Create extractor
        extractor = EXTRACTORS[extractor_id]()

        # Check if extraction is needed
        if not force and not extractor.needs_extraction(max_age_hours):
            print(f"  Skipping (extracted within {max_age_hours}h)")
            results[extractor_id] = {'success': True, 'skipped': True}
            skipped += 1
            continue

        # Run extraction
        try:
            result = extractor.run()
            results[extractor_id] = result

            if result.get('success'):
                succeeded += 1
                print(f"  Success: {result.get('count', 0)} features")
            else:
                failed += 1
                print(f"  Failed: {result.get('error', 'Unknown error')}")

        except Exception as e:
            failed += 1
            results[extractor_id] = {
                'success': False,
                'error': str(e)
            }
            print(f"  Exception: {e}")

        print()

    # Add summary
    results['_summary'] = {
        'total': len(extractor_ids),
        'succeeded': succeeded,
        'failed': failed,
        'skipped': skipped,
        'timestamp': datetime.utcnow().isoformat()
    }

    print(f"=== Summary ===")
    print(f"Total: {len(extractor_ids)}, Succeeded: {succeeded}, Failed: {failed}, Skipped: {skipped}")

    return results


def save_extraction_report(results: Dict[str, Any], output_path: Path = None) -> None:
    """Save extraction results to a JSON report.

    Args:
        results: Results from run_extraction()
        output_path: Path to save report (default: data/export/extraction_report.json)
    """
    if output_path is None:
        output_path = EXPORT_DIR / 'extraction_report.json'

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w') as f:
        json.dump(results, f, indent=2, default=str)

    print(f"Report saved to: {output_path}")


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description='Run extraction pipeline to fetch data from external sources'
    )
    parser.add_argument(
        '--sources',
        nargs='+',
        choices=['osm', 'nvdb'],
        help='Sources to extract from (default: all)'
    )
    parser.add_argument(
        '--feature-types',
        nargs='+',
        choices=['buildings', 'roads', 'water'],
        help='Feature types to extract (default: all)'
    )
    parser.add_argument(
        '--skip-ml',
        action='store_true',
        default=True,
        help='Skip ML extraction (default: True)'
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='Force re-extraction even if recent'
    )
    parser.add_argument(
        '--max-age',
        type=float,
        default=24.0,
        help='Max age in hours before re-extraction (default: 24)'
    )
    parser.add_argument(
        '--save-report',
        action='store_true',
        help='Save extraction report to JSON'
    )

    args = parser.parse_args()

    results = run_extraction(
        sources=args.sources,
        feature_types=args.feature_types,
        skip_ml=args.skip_ml,
        force=args.force,
        max_age_hours=args.max_age
    )

    if args.save_report:
        save_extraction_report(results)

    # Exit with error if any extraction failed
    summary = results.get('_summary', {})
    if summary.get('failed', 0) > 0:
        sys.exit(1)


if __name__ == '__main__':
    main()
