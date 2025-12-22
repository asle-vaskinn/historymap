#!/usr/bin/env python3
"""
Semi-manual FINN.no listing entry.

Extracts byggeår (construction year) and address from a FINN listing URL.
Appends to existing raw data with deduplication.

Usage:
    python finn_manual.py --url https://www.finn.no/realestate/homes/ad.html?finnkode=431202654
    python finn_manual.py --url 431202654  # Just the finn_code works too
"""

import argparse
import json
import re
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse, parse_qs

import requests
from bs4 import BeautifulSoup


class FinnManualEntry:
    """Extract listing data from FINN.no URLs."""

    FINN_AD_URL = "https://www.finn.no/realestate/homes/ad.html"

    def __init__(self, output_path: Path):
        self.output_path = output_path
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        })

    def extract_finn_code(self, url_or_code: str) -> str:
        """Extract finn_code from URL or return as-is if already a code."""
        # If it's just digits, it's already a code
        if url_or_code.isdigit():
            return url_or_code

        # Try to parse as URL
        parsed = urlparse(url_or_code)
        params = parse_qs(parsed.query)

        if 'finnkode' in params:
            return params['finnkode'][0]

        # Try to find in path (some URL formats)
        match = re.search(r'(\d{9,})', url_or_code)
        if match:
            return match.group(1)

        raise ValueError(f"Could not extract finn_code from: {url_or_code}")

    def fetch_listing(self, finn_code: str) -> dict:
        """Fetch and parse a FINN listing."""
        url = f"{self.FINN_AD_URL}?finnkode={finn_code}"
        print(f"Fetching: {url}")

        response = self.session.get(url, timeout=15)
        if response.status_code == 404:
            print(f"  Listing not found (404): {finn_code}")
            print(f"  This may be a new development or expired listing")
            return None
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')

        # Extract data
        data = {
            'finn_code': finn_code,
            'url': url,
            'scraped_at': datetime.now().isoformat()
        }

        # Address - try multiple selectors
        address_parts = []

        # Method 1: Look for address in structured data
        script_ld = soup.find('script', type='application/ld+json')
        if script_ld:
            try:
                ld_data = json.loads(script_ld.string)
                if isinstance(ld_data, list):
                    for item in ld_data:
                        if item.get('@type') == 'Product':
                            addr = item.get('address', {})
                            if addr:
                                street = addr.get('streetAddress', '')
                                postal = addr.get('postalCode', '')
                                city = addr.get('addressLocality', '')
                                if street:
                                    address_parts = [street, postal, city]
                                    break
            except (json.JSONDecodeError, TypeError):
                pass

        # Method 2: Look for visible address elements
        if not address_parts:
            # Try various common class patterns
            for selector in ['[data-testid="object-address"]', '.u-t2', 'h1']:
                elem = soup.select_one(selector)
                if elem:
                    text = elem.get_text(strip=True)
                    if text and ('veg' in text.lower() or 'gate' in text.lower() or
                                'vei' in text.lower() or re.search(r'\d{4}', text)):
                        data['address'] = text
                        break

        if address_parts:
            data['address'] = ', '.join(filter(None, address_parts))

        # Year built - look for "Byggeår"
        year_built = None

        # Method 1: Look in key-value pairs
        for dt in soup.find_all(['dt', 'th', 'span', 'div']):
            text = dt.get_text(strip=True).lower()
            if 'byggeår' in text:
                # Get the next sibling or associated value
                next_elem = dt.find_next(['dd', 'td', 'span'])
                if next_elem:
                    year_text = next_elem.get_text(strip=True)
                    year_match = re.search(r'(\d{4})', year_text)
                    if year_match:
                        year_built = int(year_match.group(1))
                        break

        # Method 2: Regex search in full text
        if not year_built:
            text = soup.get_text()
            match = re.search(r'[Bb]ygge[aå]r[:\s]+(\d{4})', text)
            if match:
                year_built = int(match.group(1))

        if year_built:
            data['year_built'] = year_built

        # Property type
        for elem in soup.select('[data-testid="info-property-type"], .property-type'):
            data['property_type'] = elem.get_text(strip=True)
            break

        return data

    def load_existing(self) -> dict:
        """Load existing raw data."""
        if not self.output_path.exists():
            return {
                'metadata': {
                    'source': 'finn_manual',
                    'created': datetime.now().isoformat()
                },
                'listings': []
            }

        with open(self.output_path) as f:
            return json.load(f)

    def save(self, data: dict):
        """Save raw data."""
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def add_listing(self, url_or_code: str) -> dict:
        """Add a listing by URL or finn_code."""
        finn_code = self.extract_finn_code(url_or_code)

        # Load existing
        data = self.load_existing()
        existing_codes = {l.get('finn_code') for l in data['listings']}

        if finn_code in existing_codes:
            print(f"  Already exists: {finn_code}")
            return None

        # Fetch new listing
        listing = self.fetch_listing(finn_code)

        if listing is None:
            return None

        if not listing.get('year_built'):
            print(f"  Warning: No year_built found for {finn_code}")
        if not listing.get('address'):
            print(f"  Warning: No address found for {finn_code}")

        # Add to data
        data['listings'].append(listing)
        data['metadata']['updated'] = datetime.now().isoformat()
        data['metadata']['count'] = len(data['listings'])

        # Save
        self.save(data)

        print(f"  Added: {finn_code}")
        print(f"    Address: {listing.get('address', 'N/A')}")
        print(f"    Year: {listing.get('year_built', 'N/A')}")

        return listing


def main():
    parser = argparse.ArgumentParser(
        description='Add FINN listings manually by URL'
    )
    parser.add_argument(
        '--url', '-u',
        type=str,
        required=True,
        help='FINN listing URL or finn_code'
    )
    parser.add_argument(
        '--output', '-o',
        type=Path,
        default=Path('data/sources/finn/raw/buildings.json'),
        help='Output file path'
    )

    args = parser.parse_args()

    entry = FinnManualEntry(output_path=args.output)
    result = entry.add_listing(args.url)

    if result:
        print(f"\nSuccess! Run geocoding next:")
        print(f"  python scripts/ingest/finn_geocode.py")


if __name__ == '__main__':
    main()
