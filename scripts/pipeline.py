#!/usr/bin/env python3
"""
Main pipeline orchestrator.

Runs the full data pipeline:
1. Ingest - Download/extract raw data for each source
2. Normalize - Convert to common schema
3. Merge - Combine sources according to config
4. Export - Generate frontend-ready output
"""

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional


def run_stage(stage: str, sources: Optional[List[str]] = None,
              data_dir: Optional[Path] = None, pmtiles: bool = True,
              feature_type: str = 'buildings') -> bool:
    """
    Run a pipeline stage.

    Args:
        stage: One of 'ingest', 'normalize', 'merge', 'export', 'all'
        sources: List of source IDs to process (None = all enabled)
        data_dir: Base data directory
        pmtiles: Generate PMTiles during export (default: True)
        feature_type: 'buildings', 'roads', or 'all'

    Returns:
        True if successful
    """
    data_dir = data_dir or Path(__file__).parent.parent / 'data'

    # Handle 'all' feature types by running both
    if feature_type == 'all':
        success = True
        for ft in ['buildings', 'roads']:
            print(f"\n{'#'*60}")
            print(f"FEATURE TYPE: {ft.upper()}")
            print('#'*60)
            if not run_stage(stage, sources, data_dir, pmtiles, ft):
                success = False
        return success

    if stage == 'ingest':
        return run_ingest(sources, data_dir, feature_type)
    elif stage == 'normalize':
        return run_normalize(sources, data_dir, feature_type)
    elif stage == 'merge':
        return run_merge(data_dir, feature_type)
    elif stage == 'export':
        return run_export(data_dir, pmtiles=pmtiles, feature_type=feature_type)
    elif stage == 'all':
        success = True
        for s in ['ingest', 'normalize', 'merge', 'export']:
            print(f"\n{'='*60}")
            print(f"STAGE: {s.upper()}")
            print('='*60)
            if not run_stage(s, sources, data_dir, pmtiles=pmtiles, feature_type=feature_type):
                print(f"Stage {s} failed!")
                success = False
                # Continue anyway for now
        return success
    else:
        print(f"Unknown stage: {stage}")
        return False


def discover_sources(sources_dir: Path) -> dict:
    """
    Recursively discover all sources by finding manifest.json files.

    Returns:
        Dict mapping source_id -> source_path
    """
    sources = {}

    # Recursively find all manifest.json files
    for manifest_path in sources_dir.rglob('manifest.json'):
        with open(manifest_path) as f:
            manifest = json.load(f)

        source_id = manifest.get('source_id')
        if source_id:
            # Source directory is the parent of manifest.json
            source_path = manifest_path.parent
            sources[source_id] = source_path

    return sources


def run_ingest(sources: Optional[List[str]], data_dir: Path, feature_type: str = 'buildings') -> bool:
    """Run ingestion for specified sources."""
    print(f"\nRunning ingestion for {feature_type}...")

    # Define sources for each feature type
    ROAD_SOURCES = ['nvdb', 'osm_roads', 'kulturminner']
    BUILDING_SOURCES = ['osm', 'sefrak']

    # Get list of sources to process
    sources_dir = data_dir / 'sources'
    all_sources = discover_sources(sources_dir)

    if sources:
        source_ids = sources
    else:
        # Default sources based on feature type
        if feature_type == 'roads':
            source_ids = ROAD_SOURCES
        else:
            source_ids = list(all_sources.keys())

    success = True
    for source_id in source_ids:
        print(f"\n--- {source_id} ---")

        # Try to import and run source-specific ingestor
        try:
            module_name = f"ingest.{source_id}"
            module = __import__(module_name, fromlist=[''])
            if hasattr(module, 'Ingestor'):
                ingestor = module.Ingestor(data_dir=data_dir)
                if not ingestor.run():
                    success = False
            else:
                print(f"  No Ingestor class found in {module_name}")
        except ImportError:
            print(f"  No ingestor module found for {source_id}")
            if source_id.startswith('ml_'):
                print(f"  For ML sources: Use scripts/ingest/ml_extract.py --source {source_id.replace('ml_', '')}")
            else:
                print(f"  Create: scripts/ingest/{source_id}.py")

    return success


def run_normalize(sources: Optional[List[str]], data_dir: Path, feature_type: str = 'buildings') -> bool:
    """Run normalization for specified sources."""
    print(f"\nRunning normalization for {feature_type}...")

    # Define sources for each feature type
    ROAD_SOURCES = ['nvdb', 'osm_roads', 'kulturminner']

    sources_dir = data_dir / 'sources'
    all_sources = discover_sources(sources_dir)

    if sources:
        source_ids = sources
    else:
        if feature_type == 'roads':
            source_ids = ROAD_SOURCES
        else:
            source_ids = list(all_sources.keys())

    success = True
    for source_id in source_ids:
        print(f"\n--- {source_id} ---")

        # Determine which normalizer to use
        if feature_type == 'roads':
            # Use road-specific normalizers
            normalizer_name = source_id
            if source_id == 'osm_roads':
                normalizer_name = 'osm_roads'
            elif source_id.startswith('ml_'):
                normalizer_name = 'ml_roads'
        else:
            normalizer_name = source_id

        # Try to import and run source-specific normalizer
        try:
            module_name = f"normalize.normalize_{normalizer_name}"
            module = __import__(module_name, fromlist=[''])
            if hasattr(module, 'Normalizer'):
                normalizer = module.Normalizer(data_dir=data_dir)
                if not normalizer.run():
                    success = False
            else:
                print(f"  No Normalizer class found in {module_name}")
        except ImportError:
            print(f"  No normalizer module found for {normalizer_name}")
            if source_id.startswith('ml_'):
                if feature_type == 'roads':
                    print(f"  For ML road sources: Use scripts/normalize/normalize_ml_roads.py --source {source_id.replace('ml_', '')}")
                else:
                    print(f"  For ML sources: Use scripts/normalize/normalize_ml.py --source {source_id.replace('ml_', '')}")
            else:
                print(f"  Create: scripts/normalize/normalize_{normalizer_name}.py")

    return success


def run_merge(data_dir: Path, feature_type: str = 'buildings') -> bool:
    """Run merge stage."""
    print(f"\nRunning merge for {feature_type}...")

    if feature_type == 'roads':
        config_path = data_dir / 'merged' / 'roads_merge_config.json'
        if not config_path.exists():
            print(f"  Roads merge config not found: {config_path}")
            print(f"  Creating default config...")
            # Create will be done by merge_roads.py
        from merge.merge_roads import merge_roads
        return merge_roads(config_path)
    else:
        config_path = data_dir / 'merged' / 'merge_config.json'
        if not config_path.exists():
            print(f"  Merge config not found: {config_path}")
            return False
        from merge.merge_sources import merge_sources
        return merge_sources(config_path)


def run_export(data_dir: Path, pmtiles: bool = True, feature_type: str = 'buildings') -> bool:
    """
    Run export stage.

    Args:
        data_dir: Base data directory
        pmtiles: Generate PMTiles in addition to GeoJSON (default: True)
        feature_type: 'buildings' or 'roads'

    Returns:
        True if successful
    """
    print(f"\nRunning export for {feature_type}...")

    if feature_type == 'roads':
        return run_export_roads(data_dir, pmtiles)
    else:
        return run_export_buildings(data_dir, pmtiles)


def run_export_roads(data_dir: Path, pmtiles: bool = True) -> bool:
    """Export road data."""
    merged_path = data_dir / 'merged' / 'roads_merged.geojson'
    if not merged_path.exists():
        print(f"  Merged road data not found: {merged_path}")
        return False

    # Export to frontend-ready GeoJSON
    frontend_data = data_dir.parent / 'frontend' / 'data'
    frontend_data.mkdir(parents=True, exist_ok=True)
    output_path = frontend_data / 'roads_temporal.geojson'

    from export.export_roads import export_roads, generate_pmtiles

    print(f"\nExporting roads GeoJSON...")
    if not export_roads(merged_path, output_path):
        print("  Road export failed!")
        return False

    # Optionally convert to PMTiles
    if pmtiles:
        pmtiles_path = frontend_data / 'roads.pmtiles'
        print(f"\nExporting roads PMTiles...")
        if not generate_pmtiles(output_path, pmtiles_path):
            print("  Roads PMTiles generation failed (tippecanoe may not be installed)")
            # Don't fail, GeoJSON is enough

    return True


def run_export_buildings(data_dir: Path, pmtiles: bool = True) -> bool:
    """Export building data (original function)."""
    merged_path = data_dir / 'merged' / 'buildings_merged.geojson'
    if not merged_path.exists():
        print(f"  Merged data not found: {merged_path}")
        return False

    export_dir = data_dir / 'export'
    export_dir.mkdir(exist_ok=True)

    # Export to frontend-ready GeoJSON
    from export.export_geojson import export_geojson

    geojson_path = export_dir / 'buildings.geojson'
    print(f"\nExporting GeoJSON...")
    if not export_geojson(merged_path, geojson_path, stats=True):
        print("  GeoJSON export failed!")
        return False

    # Export sources manifest for frontend inspection mode
    from export.export_sources_manifest import discover_ml_sources, export_manifest

    print(f"\nExporting sources manifest...")
    sources_dir = data_dir / 'sources'
    ml_sources = discover_ml_sources(sources_dir)
    if ml_sources:
        frontend_data = data_dir.parent / 'frontend' / 'data'
        frontend_data.mkdir(parents=True, exist_ok=True)
        manifest_path = frontend_data / 'sources_manifest.json'
        export_manifest(ml_sources, manifest_path)
    else:
        print("  No ML sources found, skipping manifest")

    # Optionally convert to PMTiles
    if pmtiles:
        from export.export_pmtiles import export_pmtiles, check_tippecanoe

        if not check_tippecanoe():
            print("\n" + "="*60)
            print("WARNING: tippecanoe not found, skipping PMTiles generation")
            print("="*60)
            print("\nTo generate PMTiles, install tippecanoe:")
            print("  macOS:  brew install tippecanoe")
            print("  Linux:  Build from https://github.com/felt/tippecanoe")
            print("\nYou can manually generate PMTiles later with:")
            print(f"  python scripts/export/export_pmtiles.py -i {geojson_path}")
            print("="*60)
            return True

        pmtiles_path = export_dir / 'buildings.pmtiles'
        print(f"\nExporting PMTiles...")
        if not export_pmtiles(
            input_path=geojson_path,
            output_path=pmtiles_path,
            min_zoom=10,
            max_zoom=16,
            layer_name='buildings',
            name='Trondheim Historical Buildings',
            description='Building footprints from 1700 to present with temporal attributes',
            attribution='© Kartverket, SEFRAK, OpenStreetMap contributors',
            force=True,
            verbose=True
        ):
            print("  PMTiles export failed!")
            print("  GeoJSON export was successful, continuing...")
            # Don't fail the whole export just because PMTiles failed
            return True

    return True


def list_sources(data_dir: Path) -> None:
    """List all available sources and their status."""
    sources_dir = data_dir / 'sources'
    all_sources = discover_sources(sources_dir)

    print("\nAvailable sources:")
    print("-" * 60)

    for source_id in sorted(all_sources.keys()):
        source_path = all_sources[source_id]
        manifest_path = source_path / 'manifest.json'
        raw_dir = source_path / 'raw'
        normalized_dir = source_path / 'normalized'

        status = []
        if manifest_path.exists():
            with open(manifest_path) as f:
                manifest = json.load(f)
            if manifest.get('ingested_at'):
                status.append('ingested')
            if manifest.get('normalized_at'):
                status.append('normalized')

        has_raw = raw_dir.exists() and any(raw_dir.iterdir()) if raw_dir.exists() else False
        has_normalized = (normalized_dir / 'buildings.geojson').exists()

        # Show relative path for nested sources
        rel_path = source_path.relative_to(sources_dir)
        print(f"  {source_id} ({rel_path}):")
        print(f"    Raw data: {'yes' if has_raw else 'no'}")
        print(f"    Normalized: {'yes' if has_normalized else 'no'}")
        if status:
            print(f"    Status: {', '.join(status)}")


def main():
    parser = argparse.ArgumentParser(
        description='Run the historical map data pipeline',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python pipeline.py --stage all              # Run full pipeline for buildings
  python pipeline.py --stage all --feature-type roads  # Run full pipeline for roads
  python pipeline.py --stage all --feature-type all    # Run for both buildings and roads
  python pipeline.py --stage ingest           # Run only ingestion
  python pipeline.py --stage normalize -s osm # Normalize only OSM
  python pipeline.py --stage export           # Export GeoJSON + PMTiles
  python pipeline.py --stage export --no-pmtiles  # Export GeoJSON only
  python pipeline.py --list                   # List sources and status

Road pipeline example:
  python pipeline.py --stage all --feature-type roads
  python pipeline.py --stage ingest -s nvdb,osm_roads --feature-type roads
  python pipeline.py --stage merge --feature-type roads
"""
    )

    parser.add_argument('--stage', '-t', type=str, default='all',
                        choices=['ingest', 'normalize', 'merge', 'export', 'all'],
                        help='Pipeline stage to run')
    parser.add_argument('--sources', '-s', type=str, nargs='+',
                        help='Source IDs to process (default: all)')
    parser.add_argument('--data-dir', '-d', type=Path,
                        default=Path(__file__).parent.parent / 'data',
                        help='Base data directory')
    parser.add_argument('--feature-type', '-f', type=str, default='buildings',
                        choices=['buildings', 'roads', 'all'],
                        help='Feature type to process: buildings, roads, or all')
    parser.add_argument('--no-pmtiles', action='store_true',
                        help='Skip PMTiles generation during export')
    parser.add_argument('--list', '-l', action='store_true',
                        help='List available sources and exit')

    args = parser.parse_args()

    if args.list:
        list_sources(args.data_dir)
        return

    success = run_stage(args.stage, args.sources, args.data_dir,
                        pmtiles=not args.no_pmtiles,
                        feature_type=args.feature_type)
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
