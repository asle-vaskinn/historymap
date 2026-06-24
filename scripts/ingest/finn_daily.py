#!/usr/bin/env python3
"""
Finn.no daily listings scraper for building construction years.

Scrapes today's new listings from Trondheim and extracts construction years
by visiting each listing's detail page.

Usage:
    python finn_daily.py                    # Scrape today's listings
    python finn_daily.py --dry-run          # Preview without saving
    python finn_daily.py --limit 5          # Only scrape first 5 listings
"""

import argparse
import json
import random
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict
from urllib.parse import urlencode

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout


class FinnDailyScraper:
    """Scraper for today's new Finn.no listings using Playwright."""

    BASE_URL = "https://www.finn.no/realestate/homes/search.html"

    # Trondheim location code
    TRONDHEIM_LOCATION = "1.20016.20318"

    # Human-like delays (seconds)
    MIN_DELAY = 2.0
    MAX_DELAY = 5.0
    DETAIL_PAGE_DELAY_MIN = 1.5
    DETAIL_PAGE_DELAY_MAX = 3.5

    def __init__(self, output_path: Path, dry_run: bool = False, limit: Optional[int] = None):
        self.output_path = output_path
        self.dry_run = dry_run
        self.limit = limit
        self.results = []
        self.browser = None
        self.context = None
        self.page = None

    def human_delay(self, min_delay: float = None, max_delay: float = None):
        """Sleep for a random human-like duration."""
        min_d = min_delay or self.MIN_DELAY
        max_d = max_delay or self.MAX_DELAY
        delay = random.uniform(min_d, max_d)
        # Add occasional longer pauses
        if random.random() < 0.1:
            delay += random.uniform(2, 5)
        print(f"    Waiting {delay:.1f}s...")
        time.sleep(delay)

    def build_search_url(self, page: int = 1) -> str:
        """Build search URL for today's listings."""
        params = {
            "location": self.TRONDHEIM_LOCATION,
            "published": 1,  # Recently published
            "is_new_property": "false",  # Existing buildings only
        }
        if page > 1:
            params["page"] = page
        return f"{self.BASE_URL}?{urlencode(params)}"

    def start_browser(self, playwright):
        """Start the browser with human-like settings."""
        self.browser = playwright.chromium.launch(
            headless=True,
            args=['--disable-blink-features=AutomationControlled']
        )
        self.context = self.browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            locale='nb-NO',
            timezone_id='Europe/Oslo'
        )
        self.page = self.context.new_page()

    def stop_browser(self):
        """Stop the browser."""
        if self.context:
            self.context.close()
        if self.browser:
            self.browser.close()

    def extract_finn_code(self, url: str) -> Optional[str]:
        """Extract finn code from URL."""
        match = re.search(r'finnkode=(\d+)', url)
        return match.group(1) if match else None

    def parse_search_listing(self, article) -> Optional[dict]:
        """Parse a listing from search results (basic info only)."""
        try:
            # Get the link
            link_elem = article.query_selector('a[href*="/realestate/homes/ad.html"]')
            if not link_elem:
                return None

            href = link_elem.get_attribute('href') or ''
            full_url = f"https://www.finn.no{href}" if href.startswith('/') else href

            # Get address
            location_elem = article.query_selector('.sf-realestate-location span, [class*="location"] span')
            address = location_elem.inner_text().strip() if location_elem else ''

            if not address:
                # Fallback: try to find address pattern
                text = article.inner_text()
                addr_match = re.search(r'([A-ZÆØÅ][a-zæøå]+(?:\s+[A-ZÆØÅ]?[a-zæøå]+)*\s+\d+[A-Za-z]?),\s*Trondheim', text)
                if addr_match:
                    address = addr_match.group(0)

            finn_code = self.extract_finn_code(href)

            return {
                'address': address,
                'finn_code': finn_code,
                'link': full_url,
            }
        except Exception as e:
            print(f"    Error parsing search listing: {e}")
            return None

    def get_construction_year_from_detail(self, url: str) -> Optional[dict]:
        """Visit detail page and extract construction year and other details."""
        try:
            self.page.goto(url, wait_until='networkidle', timeout=30000)
            time.sleep(1)  # Wait for dynamic content

            details = {}

            # Look for construction year in various formats
            page_text = self.page.inner_text('body')

            # Pattern 1: "Byggeår: 1950" or "Byggeår 1950"
            year_match = re.search(r'[Bb]ygge[åa]r[:\s]+(\d{4})', page_text)
            if year_match:
                details['year_built'] = int(year_match.group(1))

            # Pattern 2: Look in key facts section
            if 'year_built' not in details:
                # Try finding in structured data
                key_facts = self.page.query_selector_all('[class*="key-info"], [class*="facts"] dt, [class*="facts"] dd')
                for i, elem in enumerate(key_facts):
                    text = elem.inner_text().strip().lower()
                    if 'byggeår' in text:
                        # Check next element or same element for year
                        year_match = re.search(r'(\d{4})', text)
                        if year_match:
                            details['year_built'] = int(year_match.group(1))
                        elif i + 1 < len(key_facts):
                            next_text = key_facts[i + 1].inner_text().strip()
                            year_match = re.search(r'(\d{4})', next_text)
                            if year_match:
                                details['year_built'] = int(year_match.group(1))

            # Extract property type
            type_patterns = ['Leilighet', 'Enebolig', 'Rekkehus', 'Tomannsbolig', 'Hybel']
            for ptype in type_patterns:
                if ptype.lower() in page_text.lower():
                    details['property_type'] = ptype
                    break

            # Extract size
            size_match = re.search(r'[Pp]rimærrom[:\s]+(\d+)\s*m²', page_text)
            if size_match:
                details['size_m2'] = int(size_match.group(1))
            else:
                size_match = re.search(r'(\d+)\s*m²\s*[Pp]rimærrom', page_text)
                if size_match:
                    details['size_m2'] = int(size_match.group(1))

            # Extract bedrooms
            rooms_match = re.search(r'(\d+)\s*soverom', page_text)
            if rooms_match:
                details['bedrooms'] = int(rooms_match.group(1))

            # Extract price
            price_match = re.search(r'[Pp]risantydning[:\s]+(\d[\d\s]*)\s*kr', page_text.replace('\xa0', ' '))
            if price_match:
                price_str = price_match.group(1).replace(' ', '').replace('\xa0', '')
                try:
                    details['price'] = int(price_str)
                except ValueError:
                    pass

            # Get OSM ref (matrikkel number) if available
            matrikkel_match = re.search(r'[Gg]nr[.:\s]+(\d+)[,\s]+[Bb]nr[.:\s]+(\d+)', page_text)
            if matrikkel_match:
                details['gnr'] = int(matrikkel_match.group(1))
                details['bnr'] = int(matrikkel_match.group(2))

            return details

        except Exception as e:
            print(f"    Error getting detail page: {e}")
            return None

    def scrape_search_results(self) -> List[dict]:
        """Scrape all listings from search results."""
        listings = []
        page_num = 1
        max_pages = 10  # Safety limit

        while page_num <= max_pages:
            url = self.build_search_url(page_num)
            print(f"\nPage {page_num}: {url}")

            try:
                self.page.goto(url, wait_until='networkidle', timeout=30000)

                # Wait for results
                try:
                    self.page.wait_for_selector('article', timeout=10000)
                except PlaywrightTimeout:
                    print("  No listings found")
                    break

                time.sleep(1)

                # Find all articles
                articles = self.page.query_selector_all('article')
                if not articles:
                    print("  No articles on page")
                    break

                page_listings = []
                for article in articles:
                    listing = self.parse_search_listing(article)
                    if listing and listing.get('finn_code'):
                        page_listings.append(listing)

                print(f"  Found {len(page_listings)} listings")
                listings.extend(page_listings)

                # Check limit
                if self.limit and len(listings) >= self.limit:
                    listings = listings[:self.limit]
                    print(f"  Reached limit of {self.limit}")
                    break

                # Check for next page
                next_button = self.page.query_selector('a[rel="next"], button:has-text("Neste")')
                if not next_button or len(page_listings) == 0:
                    break

                page_num += 1
                self.human_delay()

            except Exception as e:
                print(f"  Error: {e}")
                break

        return listings

    def enrich_with_details(self, listings: List[dict]) -> List[dict]:
        """Visit each listing's detail page to get construction year."""
        enriched = []
        total = len(listings)

        for i, listing in enumerate(listings):
            print(f"\n[{i+1}/{total}] Getting details for {listing.get('address', 'unknown')}...")

            details = self.get_construction_year_from_detail(listing['link'])
            if details:
                listing.update(details)

            listing['scraped_at'] = datetime.now(timezone.utc).isoformat()
            enriched.append(listing)

            if i < total - 1:
                self.human_delay(self.DETAIL_PAGE_DELAY_MIN, self.DETAIL_PAGE_DELAY_MAX)

        return enriched

    def load_existing(self) -> List[dict]:
        """Load existing listings from output file."""
        if not self.output_path.exists():
            return []

        try:
            with open(self.output_path) as f:
                data = json.load(f)
            return data.get('listings', [])
        except Exception as e:
            print(f"Warning: Could not load existing data: {e}")
            return []

    def merge_results(self, new_listings: List[dict]) -> List[dict]:
        """Merge new listings with existing, avoiding duplicates."""
        existing = self.load_existing()
        existing_codes = {l.get('finn_code') for l in existing if l.get('finn_code')}

        # Filter out duplicates
        truly_new = [l for l in new_listings if l.get('finn_code') not in existing_codes]

        print(f"\n  Existing listings: {len(existing)}")
        print(f"  New unique listings: {len(truly_new)}")

        # Return merged list (new first, then existing)
        return truly_new + existing

    def save_results(self, listings: List[dict]):
        """Save results to JSON file."""
        # Count listings with construction years
        with_year = sum(1 for l in listings if l.get('year_built'))

        output = {
            'metadata': {
                'source': 'finn.no',
                'location': 'Trondheim',
                'scraped_at': datetime.now(timezone.utc).isoformat(),
                'total_listings': len(listings),
                'with_construction_year': with_year,
                'scrape_type': 'daily_new_listings'
            },
            'listings': listings
        }

        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.output_path, 'w', encoding='utf-8') as f:
            json.dump(output, f, indent=2, ensure_ascii=False)

        print(f"\nSaved {len(listings)} listings to {self.output_path}")
        print(f"  With construction year: {with_year}")

    def run(self):
        """Run the scraper."""
        print("="*60)
        print("FINN.NO DAILY LISTINGS SCRAPER")
        print("="*60)
        print(f"Output: {self.output_path}")
        print(f"Dry run: {self.dry_run}")
        print(f"Limit: {self.limit or 'none'}")
        print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

        with sync_playwright() as playwright:
            self.start_browser(playwright)

            try:
                # Step 1: Get search results
                print("\n" + "="*60)
                print("STEP 1: Scraping search results")
                print("="*60)
                listings = self.scrape_search_results()
                print(f"\nFound {len(listings)} listings in search")

                if not listings:
                    print("No new listings found today.")
                    return

                # Step 2: Enrich with details
                print("\n" + "="*60)
                print("STEP 2: Getting construction years from detail pages")
                print("="*60)
                enriched = self.enrich_with_details(listings)

                # Step 3: Merge and save
                print("\n" + "="*60)
                print("STEP 3: Merging with existing data")
                print("="*60)

                if self.dry_run:
                    print("\nDRY RUN - Not saving results")
                    print("\nNew listings found:")
                    for l in enriched:
                        year = l.get('year_built', '?')
                        print(f"  - {l.get('address', 'unknown')}: {year}")
                else:
                    merged = self.merge_results(enriched)
                    self.save_results(merged)

            except KeyboardInterrupt:
                print("\n\nInterrupted!")
            finally:
                self.stop_browser()

        print("\n" + "="*60)
        print("DONE")
        print("="*60)


def main():
    parser = argparse.ArgumentParser(
        description="Scrape today's new Finn.no listings in Trondheim"
    )
    parser.add_argument('--output', '-o', type=Path,
                        default=Path('data/sources/finn/raw/buildings.json'),
                        help='Output JSON file')
    parser.add_argument('--dry-run', '-n', action='store_true',
                        help='Preview without saving')
    parser.add_argument('--limit', '-l', type=int,
                        help='Limit number of listings to scrape')

    args = parser.parse_args()

    scraper = FinnDailyScraper(
        output_path=args.output,
        dry_run=args.dry_run,
        limit=args.limit
    )
    scraper.run()


if __name__ == '__main__':
    main()
