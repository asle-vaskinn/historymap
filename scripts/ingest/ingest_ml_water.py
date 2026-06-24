#!/usr/bin/env python3
"""
Ingest ML-detected water features from vectorized segmentation output.

This script reads water polygons vectorized from ML segmentation masks
and prepares them for normalization.

The ML pipeline produces water polygons from historical maps:
1. U-Net model predicts water class (class 3) on map tiles
2. ml/vectorize.py converts masks to GeoJSON polygons
3. This script ingests those polygons into the data pipeline

Expected input structure:
    results/{year}/water/*.geojson
    or
    results/{year}/water_{year}.geojson

Usage:
    python scripts/ingest/ingest_ml_water.py
    python scripts/ingest/ingest_ml_water.py --input results/1880/water/
    python scripts/ingest/ingest_ml_water.py --years 1880,1904,1937
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

# Import base class
try:
    from ingest.base import BaseIngestor
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from ingest.base import BaseIngestor


class MLWaterIngestor(BaseIngestor):
    """Ingest ML-detected water features."""

    def __init__(self, data_dir: Optional[Path] = None, years: Optional[List[str]] = None):
        super().__init__(source_id='ml_water', data_dir=data_dir)
        self.years = years or ['1880', '1904', '1937', '1947', '2006']
        self.ml_results_dir = self.data_dir.parent / 'results'

    def find_water_files(self) -> Dict[str, List[Path]]:
        """
        Find all water GeoJSON files from ML vectorization.

        Returns:
            Dict mapping year to list of GeoJSON paths
        """
        water_files = {}

        for year in self.years:
            year_files = []

            # Check various possible locations
            possible_paths = [
                # Per-year water directory
                self.ml_results_dir / year / 'water',
                # Direct water file
                self.ml_results_dir / year / f'water_{year}.geojson',
                # Combined output
                self.ml_results_dir / 'water' / f'{year}.geojson',
                # Alternative structure
                self.data_dir / 'ml_output' / year / 'water',
            ]

            for path in possible_paths:
                if path.is_file() and path.suffix == '.geojson':
                    year_files.append(path)
                elif path.is_dir():
                    year_files.extend(path.glob('*.geojson'))

            if year_files:
                water_files[year] = list(set(year_files))  # Remove duplicates

        return water_files

    def load_geojson(self, path: Path) -> List[Dict]:
        """Load features from a GeoJSON file."""
        try:
            with open(path) as f:
                data = json.load(f)

            if data.get('type') == 'FeatureCollection':
                return data.get('features', [])
            elif data.get('type') == 'Feature':
                return [data]
            else:
                return []
        except Exception as e:
            print(f"    Error loading {path}: {e}")
            return []

    def ingest(self) -> Dict:
        """
        Ingest ML water features from all years.

        Returns:
            Result dict with success status and counts
        """
        water_files = self.find_water_files()

        if not water_files:
            # No ML water files yet - this is expected before ML runs
            print("  No ML water files found yet")
            print(f"  Expected locations:")
            print(f"    - {self.ml_results_dir}/{{year}}/water/")
            print(f"    - {self.ml_results_dir}/{{year}}/water_{{year}}.geojson")

            # Create empty output to allow pipeline to continue
            output = {
                'type': 'FeatureCollection',
                'features': [],
                'metadata': {
                    'source': 'ml_water',
                    'years': self.years,
                    'ingested_at': datetime.utcnow().isoformat() + 'Z',
                    'status': 'no_ml_output_yet'
                }
            }

            output_path = self.raw_dir / 'ml_water.geojson'
            with open(output_path, 'w') as f:
                json.dump(output, f, indent=2)

            return {
                'success': True,
                'files': ['ml_water.geojson'],
                'count': 0,
                'message': 'No ML water files found (run ML pipeline first)',
                'notes': 'Placeholder created - run ML extraction to populate'
            }

        # Collect all features with year metadata
        all_features = []
        files_processed = []

        for year, paths in sorted(water_files.items()):
            year_count = 0

            for path in paths:
                features = self.load_geojson(path)

                for feat in features:
                    # Add year metadata if not present
                    props = feat.get('properties', {})
                    if 'year' not in props:
                        props['year'] = int(year)
                    if 'source_file' not in props:
                        props['source_file'] = path.name

                    feat['properties'] = props
                    all_features.append(feat)
                    year_count += 1

                files_processed.append(str(path.relative_to(self.data_dir.parent)))

            print(f"  Year {year}: {year_count} features from {len(paths)} files")

        # Save combined output
        output = {
            'type': 'FeatureCollection',
            'features': all_features,
            'metadata': {
                'source': 'ml_water',
                'years': list(water_files.keys()),
                'ingested_at': datetime.utcnow().isoformat() + 'Z',
                'files_processed': files_processed
            }
        }

        output_path = self.raw_dir / 'ml_water.geojson'
        with open(output_path, 'w') as f:
            json.dump(output, f)

        return {
            'success': True,
            'files': ['ml_water.geojson'],
            'count': len(all_features),
            'message': f'Ingested {len(all_features)} water features from {len(files_processed)} files',
            'version': datetime.utcnow().strftime('%Y-%m-%d')
        }


# Alias for pipeline discovery
Ingestor = MLWaterIngestor


def main():
    parser = argparse.ArgumentParser(description='Ingest ML water features')
    parser.add_argument(
        '--years', '-y',
        type=str,
        default=None,
        help='Comma-separated years to process (default: 1880,1904,1937,1947,2006)'
    )
    parser.add_argument(
        '--data-dir', '-d',
        type=Path,
        default=None,
        help='Data directory (default: data/)'
    )

    args = parser.parse_args()

    years = None
    if args.years:
        years = [y.strip() for y in args.years.split(',')]

    ingestor = MLWaterIngestor(data_dir=args.data_dir, years=years)
    success = ingestor.run()

    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
