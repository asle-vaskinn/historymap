#!/usr/bin/env python3
"""
Finn.no property scraper for building construction years.

Uses Playwright for headless browser scraping since Finn.no loads content via JavaScript.

Usage:
    python finn_scraper.py --start-year 1900 --end-year 2025
    python finn_scraper.py --resume  # Resume from last saved state
"""

import argparse
import json
import random
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urlencode

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout


class FinnScraper:
    """Scraper for Finn.no real estate listings using Playwright."""

    BASE_URL = "https://www.finn.no/realestate/homes/search.html"

    # Trondheim location code
    TRONDHEIM_LOCATION = "1.20016.20318"

    # Human-like delays (seconds)
    MIN_DELAY = 3.0
    MAX_DELAY = 7.0
    PAGE_DELAY_MIN = 2.0
    PAGE_DELAY_MAX = 4.0

    def __init__(self, output_path: Path, state_path: Optional[Path] = None):
        self.output_path = output_path
        self.state_path = state_path or output_path.with_suffix('.state.json')
        self.results = []
        self.current_year = None
        self.years_completed = set()
        self.browser = None
        self.context = None
        self.page = None

    def human_delay(self, min_delay: float = None, max_delay: float = None):
        """Sleep for a random human-like duration."""
        min_d = min_delay or self.MIN_DELAY
        max_d = max_delay or self.MAX_DELAY
        delay = random.uniform(min_d, max_d)
        # Add occasional longer pauses (simulating human distraction)
        if random.random() < 0.1:
            delay += random.uniform(3, 8)
        print(f"    Waiting {delay:.1f}s...")
        time.sleep(delay)

    def build_url(self, year: int, page: int = 1) -> str:
        """Build search URL for a specific year."""
        params = {
            "location": self.TRONDHEIM_LOCATION,
            "construction_year_from": year,
            "construction_year_to": year,
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

    def parse_listing(self, article) -> Optional[dict]:
        """Parse a single property listing element."""
        try:
            # Get the link
            link_elem = article.query_selector('a[href*="/realestate/homes/ad.html"]')
            if not link_elem:
                return None

            href = link_elem.get_attribute('href') or ''

            # Get the actual street address (in sf-realestate-location div)
            location_elem = article.query_selector('.sf-realestate-location span, [class*="location"] span')
            address = location_elem.inner_text().strip() if location_elem else ''

            if not address:
                # Fallback: try to find address pattern in text
                text = article.inner_text()
                # Look for patterns like "Streetname 123, Trondheim"
                addr_match = re.search(r'([A-ZÆØÅ][a-zæøå]+(?:\s+[A-ZÆØÅ]?[a-zæøå]+)*\s+\d+[A-Za-z]?),\s*Trondheim', text)
                if addr_match:
                    address = addr_match.group(0)

            if not address:
                return None

            # Get listing title (for reference)
            heading = article.query_selector('h2, [class*="heading"]')
            title = heading.inner_text().strip() if heading else ''

            # Extract finn code from URL
            finn_code_match = re.search(r'finnkode=(\d+)', href)
            finn_code = finn_code_match.group(1) if finn_code_match else None

            # Get all text content for parsing details
            text_content = article.inner_text()

            details = {'title': title} if title else {}

            # Extract price
            price_match = re.search(r'(\d[\d\s]*)\s*kr', text_content.replace('\xa0', ' '))
            if price_match:
                price_str = price_match.group(1).replace(' ', '').replace('\xa0', '')
                try:
                    details['price'] = int(price_str)
                except ValueError:
                    pass

            # Extract size
            size_match = re.search(r'(\d+)\s*m²', text_content)
            if size_match:
                details['size_m2'] = int(size_match.group(1))

            # Extract bedrooms
            rooms_match = re.search(r'(\d+)\s*soverom', text_content)
            if rooms_match:
                details['bedrooms'] = int(rooms_match.group(1))

            # Extract property type
            type_patterns = ['Leilighet', 'Enebolig', 'Rekkehus', 'Tomannsbolig']
            for ptype in type_patterns:
                if ptype.lower() in text_content.lower():
                    details['property_type'] = ptype
                    break

            return {
                'address': address,
                'finn_code': finn_code,
                'link': f"https://www.finn.no{href}" if href.startswith('/') else href,
                **details
            }
        except Exception as e:
            print(f"    Error parsing listing: {e}")
            return None

    def scrape_year(self, year: int) -> list:
        """Scrape all listings for a specific year."""
        print(f"\n{'='*50}")
        print(f"Scraping year: {year}")
        print('='*50)

        listings = []
        page_num = 1
        max_pages = 20  # Safety limit

        while page_num <= max_pages:
            url = self.build_url(year, page_num)
            print(f"  Page {page_num}: {url}")

            try:
                self.page.goto(url, wait_until='networkidle', timeout=30000)

                # Wait for results to load
                try:
                    self.page.wait_for_selector('article, [class*="ads__unit"]', timeout=10000)
                except PlaywrightTimeout:
                    print(f"    No listings found (timeout)")
                    break

                # Small delay for dynamic content
                time.sleep(1)

                # Find all listing articles
                articles = self.page.query_selector_all('article')

                if not articles:
                    print(f"    No articles found on page {page_num}")
                    break

                page_listings = []
                for article in articles:
                    listing = self.parse_listing(article)
                    if listing:
                        listing['year_built'] = year
                        listing['scraped_at'] = datetime.now(timezone.utc).isoformat()
                        page_listings.append(listing)

                print(f"    Found {len(page_listings)} listings")
                listings.extend(page_listings)

                # Check for next page
                next_button = self.page.query_selector('a[rel="next"], button:has-text("Neste")')
                if not next_button or len(page_listings) == 0:
                    break

                page_num += 1

                # Human-like delay between pages
                self.human_delay(self.PAGE_DELAY_MIN, self.PAGE_DELAY_MAX)

            except Exception as e:
                print(f"    Error: {e}")
                break

        print(f"  Total for {year}: {len(listings)} listings")
        return listings

    def save_state(self):
        """Save current progress."""
        state = {
            'current_year': self.current_year,
            'years_completed': sorted(list(self.years_completed)),
            'total_results': len(self.results),
            'saved_at': datetime.now(timezone.utc).isoformat()
        }
        with open(self.state_path, 'w') as f:
            json.dump(state, f, indent=2)

        # Also save results so far
        self.save_results()

    def load_state(self) -> bool:
        """Load previous progress if exists."""
        if not self.state_path.exists():
            return False

        try:
            with open(self.state_path) as f:
                state = json.load(f)

            self.years_completed = set(state.get('years_completed', []))

            # Load existing results
            if self.output_path.exists():
                with open(self.output_path) as f:
                    data = json.load(f)
                    self.results = data.get('listings', [])

            print(f"Resumed: {len(self.years_completed)} years done, {len(self.results)} listings")
            return True
        except Exception as e:
            print(f"Failed to load state: {e}")
            return False

    def deduplicate_results(self):
        """Remove duplicate listings based on finn_code."""
        seen = set()
        unique = []
        duplicates = 0

        for listing in self.results:
            finn_code = listing.get('finn_code')
            if finn_code and finn_code in seen:
                duplicates += 1
                continue
            if finn_code:
                seen.add(finn_code)
            unique.append(listing)

        if duplicates > 0:
            print(f"  Removed {duplicates} duplicate listings")

        self.results = unique

    def merge_with_existing(self):
        """Merge new results with existing data, avoiding duplicates."""
        if not self.output_path.exists():
            return

        try:
            with open(self.output_path) as f:
                existing = json.load(f)

            existing_listings = existing.get('listings', [])
            existing_codes = {l.get('finn_code') for l in existing_listings if l.get('finn_code')}

            # Filter new results to only include new finn_codes
            new_listings = [l for l in self.results if l.get('finn_code') not in existing_codes]

            print(f"\n  Existing listings: {len(existing_listings)}")
            print(f"  New unique listings: {len(new_listings)}")

            # Merge: existing + new
            self.results = existing_listings + new_listings

            # Update years completed
            existing_years = set(existing.get('metadata', {}).get('years_scraped', []))
            self.years_completed = self.years_completed.union(existing_years)

        except Exception as e:
            print(f"  Warning: Could not merge with existing: {e}")

    def save_results(self):
        """Save results to JSON file, merging with existing data."""
        # Merge with existing and deduplicate
        self.merge_with_existing()
        self.deduplicate_results()

        output = {
            'metadata': {
                'source': 'finn.no',
                'location': 'Trondheim',
                'scraped_at': datetime.now(timezone.utc).isoformat(),
                'total_listings': len(self.results),
                'years_scraped': sorted(list(self.years_completed))
            },
            'listings': self.results
        }

        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.output_path, 'w', encoding='utf-8') as f:
            json.dump(output, f, indent=2, ensure_ascii=False)

        print(f"\nSaved {len(self.results)} listings to {self.output_path}")

    def run(self, start_year: int, end_year: int, resume: bool = False):
        """Run the scraper for a range of years."""
        if resume:
            self.load_state()

        years_to_scrape = [y for y in range(start_year, end_year + 1)
                          if y not in self.years_completed]

        print(f"\nScraping {len(years_to_scrape)} years: {start_year} to {end_year}")
        print(f"Already completed: {len(self.years_completed)} years")
        print(f"Output: {self.output_path}")

        with sync_playwright() as playwright:
            self.start_browser(playwright)

            try:
                for i, year in enumerate(years_to_scrape):
                    self.current_year = year

                    listings = self.scrape_year(year)
                    self.results.extend(listings)
                    self.years_completed.add(year)

                    # Save progress after each year
                    self.save_state()

                    # Progress report
                    progress = (i + 1) / len(years_to_scrape) * 100
                    print(f"\nProgress: {progress:.1f}% ({i + 1}/{len(years_to_scrape)} years)")
                    print(f"Total listings: {len(self.results)}")

                    # Human-like delay between years
                    if i < len(years_to_scrape) - 1:
                        self.human_delay()

            except KeyboardInterrupt:
                print("\n\nInterrupted! Saving progress...")
                self.save_state()
                print("Run with --resume to continue.")
            finally:
                self.stop_browser()

        # Final save
        self.save_results()

        # Clean up state file on completion
        if len(self.years_completed) == len(range(start_year, end_year + 1)):
            if self.state_path.exists():
                self.state_path.unlink()

        print(f"\n{'='*50}")
        print("SCRAPING COMPLETE")
        print(f"{'='*50}")
        print(f"Total listings: {len(self.results)}")
        print(f"Years covered: {min(self.years_completed)} - {max(self.years_completed)}")
        print(f"Output: {self.output_path}")


def main():
    parser = argparse.ArgumentParser(
        description='Scrape Finn.no for building construction years in Trondheim'
    )
    parser.add_argument('--start-year', type=int, default=1900,
                        help='Start year (default: 1900)')
    parser.add_argument('--end-year', type=int, default=2025,
                        help='End year (default: 2025)')
    parser.add_argument('--output', '-o', type=Path,
                        default=Path('data/sources/finn/raw/buildings.json'),
                        help='Output JSON file')
    parser.add_argument('--resume', '-r', action='store_true',
                        help='Resume from previous state')

    args = parser.parse_args()

    scraper = FinnScraper(output_path=args.output)
    scraper.run(args.start_year, args.end_year, resume=args.resume)


if __name__ == '__main__':
    main()
