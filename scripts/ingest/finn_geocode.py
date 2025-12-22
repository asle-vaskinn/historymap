#!/usr/bin/env python3
"""
Geocode Finn.no addresses and match to OSM building polygons.

Takes scraped Finn data with addresses, geocodes them using Nominatim,
and finds the matching building polygon in OSM data.

Usage:
    python finn_geocode.py
    python finn_geocode.py --input data/sources/finn/raw/buildings.json
"""

import argparse
import json
import time
import random
from pathlib import Path
from typing import Optional, Tuple, List
from urllib.parse import urlencode

import requests
from shapely.geometry import shape, Point
from shapely.strtree import STRtree


class FinnGeocoder:
    """Geocode Finn addresses and match to OSM buildings."""

    # Nominatim API (be respectful - 1 req/sec max)
    NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"

    # Rate limiting
    MIN_DELAY = 1.1  # Nominatim requires max 1 req/sec
    MAX_DELAY = 2.0

    def __init__(
        self,
        finn_path: Path,
        osm_path: Path,
        output_path: Path
    ):
        self.finn_path = finn_path
        self.osm_path = osm_path
        self.output_path = output_path
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'TrondheimHistoricalMap/1.0 (research project)'
        })

        # Load OSM buildings and build spatial index
        self.osm_buildings = []
        self.osm_geometries = []
        self.spatial_index = None

    def load_osm_buildings(self):
        """Load OSM buildings and create spatial index."""
        print(f"Loading OSM buildings from {self.osm_path}...")

        with open(self.osm_path) as f:
            data = json.load(f)

        for feature in data.get('features', []):
            try:
                geom = shape(feature['geometry'])
                self.osm_buildings.append(feature)
                self.osm_geometries.append(geom)
            except Exception as e:
                continue

        # Build spatial index for fast lookup
        self.spatial_index = STRtree(self.osm_geometries)
        print(f"  Loaded {len(self.osm_buildings)} buildings")

    def geocode_address(self, address: str) -> Optional[Tuple[float, float]]:
        """Geocode an address using Nominatim."""
        params = {
            'q': address,
            'format': 'json',
            'limit': 1,
            'countrycodes': 'no',
            'addressdetails': 1
        }

        try:
            response = self.session.get(
                self.NOMINATIM_URL,
                params=params,
                timeout=10
            )
            response.raise_for_status()
            results = response.json()

            if results:
                lat = float(results[0]['lat'])
                lon = float(results[0]['lon'])
                return (lon, lat)  # Return as (lon, lat) for GeoJSON compatibility

        except Exception as e:
            print(f"    Geocoding error: {e}")

        return None

    def find_building_at_point(
        self,
        lon: float,
        lat: float,
        search_radius: float = 0.0005  # ~50m in degrees
    ) -> Optional[dict]:
        """Find OSM building containing or nearest to the point."""
        point = Point(lon, lat)

        # First try: find building containing the point
        for i, geom in enumerate(self.osm_geometries):
            if geom.contains(point):
                return self.osm_buildings[i]

        # Second try: find nearest building within search radius
        search_buffer = point.buffer(search_radius)
        candidates = self.spatial_index.query(search_buffer)

        if len(candidates) > 0:
            # Find the closest one
            # STRtree.query() returns indices into the geometry array
            min_dist = float('inf')
            closest = None
            for idx in candidates:
                geom = self.osm_geometries[idx]
                dist = point.distance(geom)
                if dist < min_dist:
                    min_dist = dist
                    closest = self.osm_buildings[idx]

            return closest

        return None

    def load_existing_matches(self) -> set:
        """Load finn_codes that have already been geocoded."""
        if not self.output_path.exists():
            return set()

        try:
            with open(self.output_path) as f:
                existing = json.load(f)

            matched_codes = {m['finn'].get('finn_code')
                           for m in existing.get('matches', [])
                           if m.get('finn', {}).get('finn_code')}
            unmatched_codes = {m['finn'].get('finn_code')
                             for m in existing.get('unmatched', [])
                             if m.get('finn', {}).get('finn_code')}

            return matched_codes.union(unmatched_codes)
        except Exception as e:
            print(f"  Warning: Could not load existing matches: {e}")
            return set()

    def process(self):
        """Process all Finn listings."""
        # Load data
        self.load_osm_buildings()

        print(f"\nLoading Finn data from {self.finn_path}...")
        with open(self.finn_path) as f:
            finn_data = json.load(f)

        all_listings = finn_data.get('listings', [])
        print(f"  Found {len(all_listings)} total listings")

        # Filter to only new listings
        already_processed = self.load_existing_matches()
        listings = [l for l in all_listings if l.get('finn_code') not in already_processed]
        print(f"  Already processed: {len(already_processed)}")
        print(f"  New to process: {len(listings)}")

        # Process each listing
        results = {
            'metadata': {
                'source': 'finn_geocoded',
                'finn_source': str(self.finn_path),
                'osm_source': str(self.osm_path),
                'total_listings': len(listings)
            },
            'matches': [],
            'unmatched': [],
            'matched': 0,
            'geocode_failed': 0
        }

        for i, listing in enumerate(listings):
            address = listing.get('address', '')
            year = listing.get('year_built')

            print(f"\n[{i+1}/{len(listings)}] {address}")

            # Geocode
            coords = self.geocode_address(address)

            if not coords:
                print(f"    Failed to geocode")
                results['geocode_failed'] += 1
                results['unmatched'].append({
                    'finn': listing,
                    'reason': 'geocode_failed'
                })
                time.sleep(random.uniform(self.MIN_DELAY, self.MAX_DELAY))
                continue

            lon, lat = coords
            print(f"    Geocoded: {lat:.6f}, {lon:.6f}")

            # Find matching building
            building = self.find_building_at_point(lon, lat)

            if building:
                osm_id = building['properties'].get('_src_id', '')
                osm_name = building['properties'].get('nm', '')
                print(f"    Matched: {osm_id} ({osm_name or 'unnamed'})")

                results['matches'].append({
                    'finn': listing,
                    'osm_id': osm_id,
                    'osm_name': osm_name,
                    'geocoded_coords': [lon, lat],
                    'year_built': year
                })
                results['matched'] += 1
            else:
                print(f"    No building found at location")
                results['unmatched'].append({
                    'finn': listing,
                    'geocoded_coords': [lon, lat],
                    'reason': 'no_building_at_location'
                })
                results['unmatched_count'] = results.get('unmatched_count', 0) + 1

            # Rate limit
            time.sleep(random.uniform(self.MIN_DELAY, self.MAX_DELAY))

        # Merge with existing results
        if self.output_path.exists():
            try:
                with open(self.output_path) as f:
                    existing = json.load(f)
                existing_matches = existing.get('matches', [])
                existing_unmatched = existing.get('unmatched', [])
                print(f"\n  Merging with {len(existing_matches)} existing matches")
                results['matches'] = existing_matches + results['matches']
                results['unmatched'] = existing_unmatched + results['unmatched']
            except Exception as e:
                print(f"  Warning: Could not merge with existing: {e}")

        # Update metadata
        results['metadata']['matched'] = len(results['matches'])
        results['metadata']['unmatched'] = len(results['unmatched'])
        results['metadata']['geocode_failed'] = results['geocode_failed']
        results['metadata']['total_listings'] = len(all_listings)

        # Save results
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.output_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)

        print(f"\n{'='*50}")
        print("GEOCODING COMPLETE")
        print(f"{'='*50}")
        print(f"New listings processed: {len(listings)}")
        print(f"Total matched to OSM: {results['metadata']['matched']}")
        print(f"Geocode failed: {results['geocode_failed']}")
        print(f"No building found: {len(results['unmatched']) - results['geocode_failed']}")
        print(f"Output: {self.output_path}")


def main():
    parser = argparse.ArgumentParser(
        description='Geocode Finn addresses and match to OSM buildings'
    )
    parser.add_argument(
        '--input', '-i',
        type=Path,
        default=Path('data/sources/finn/raw/buildings.json'),
        help='Input Finn scraped data'
    )
    parser.add_argument(
        '--osm', '-o',
        type=Path,
        default=Path('data/sources/osm/normalized/buildings.geojson'),
        help='OSM buildings GeoJSON'
    )
    parser.add_argument(
        '--output',
        type=Path,
        default=Path('data/sources/finn/geocoded/matches.json'),
        help='Output matched data'
    )

    args = parser.parse_args()

    geocoder = FinnGeocoder(
        finn_path=args.input,
        osm_path=args.osm,
        output_path=args.output
    )
    geocoder.process()


if __name__ == '__main__':
    main()
