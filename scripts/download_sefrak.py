#!/usr/bin/env python3
"""
Download SEFRAK (historic buildings register) data for Trondheim.

SEFRAK contains buildings registered before 1900 (1945 in Finnmark),
with construction year and other historical attributes.
"""

import json
import os
import requests
import time
from pathlib import Path

# Trondheim municipality code
TRONDHEIM_CODE = "5001"

# Output directory
OUTPUT_DIR = Path(__file__).parent.parent / "data" / "sefrak"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# SEFRAK dataset UUID
SEFRAK_UUID = "93f06149-037c-48cf-b294-d166f65b6838"

# Geonorge API
BASE_URL = "https://nedlasting.geonorge.no/api"


def get_capabilities():
    """Get download capabilities for SEFRAK dataset."""
    url = f"{BASE_URL}/capabilities/{SEFRAK_UUID}"
    response = requests.get(url)
    response.raise_for_status()
    return response.json()


def get_areas():
    """Get available municipality areas."""
    url = f"{BASE_URL}/codelists/area/{SEFRAK_UUID}"
    response = requests.get(url)
    if response.status_code == 200:
        return response.json()
    return None


def get_formats():
    """Get available download formats."""
    url = f"{BASE_URL}/codelists/format/{SEFRAK_UUID}"
    response = requests.get(url)
    if response.status_code == 200:
        return response.json()
    return None


def get_projections():
    """Get available projections."""
    url = f"{BASE_URL}/codelists/projection/{SEFRAK_UUID}"
    response = requests.get(url)
    if response.status_code == 200:
        return response.json()
    return None


def order_download(area_code: str, format_code: str = "GML", projection: str = "25832"):
    """Order a download for a specific area."""
    url = f"{BASE_URL}/order"

    payload = {
        "email": "",  # No email notification
        "orderLines": [
            {
                "metadataUuid": SEFRAK_UUID,
                "areas": [
                    {
                        "code": area_code,
                        "type": "kommune"
                    }
                ],
                "formats": [format_code],
                "projections": [projection]
            }
        ]
    }

    response = requests.post(url, json=payload)
    response.raise_for_status()
    return response.json()


def check_order_status(reference_number: str):
    """Check the status of an order."""
    url = f"{BASE_URL}/order/{reference_number}"
    response = requests.get(url)
    response.raise_for_status()
    return response.json()


def download_file(url: str, output_path: Path):
    """Download a file from URL."""
    response = requests.get(url, stream=True)
    response.raise_for_status()

    with open(output_path, 'wb') as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)

    print(f"Downloaded: {output_path}")


def try_direct_download():
    """Try to find and download SEFRAK data directly."""
    # Try WFS endpoint
    wfs_url = "https://wfs.geonorge.no/skwms1/wfs.kulturminner-sefrak"

    # GetCapabilities
    params = {
        "service": "WFS",
        "request": "GetCapabilities"
    }

    try:
        response = requests.get(wfs_url, params=params, timeout=30)
        if response.status_code == 200:
            print("WFS service available!")
            print(f"URL: {wfs_url}")

            # Save capabilities
            cap_file = OUTPUT_DIR / "wfs_capabilities.xml"
            with open(cap_file, 'w') as f:
                f.write(response.text)
            print(f"Saved capabilities to {cap_file}")

            return wfs_url
    except Exception as e:
        print(f"WFS not available: {e}")

    return None


def download_via_wfs(wfs_url: str, bbox: tuple = None):
    """Download SEFRAK data via WFS."""
    # Trondheim bounding box (EPSG:25832 - UTM zone 32N)
    if bbox is None:
        # Approximate Trondheim bbox in UTM32
        bbox = (550000, 7020000, 585000, 7060000)  # xmin, ymin, xmax, ymax

    params = {
        "service": "WFS",
        "version": "2.0.0",
        "request": "GetFeature",
        "typeName": "app:Sefrakminne",  # May need to adjust based on capabilities
        "srsName": "EPSG:25832",
        "bbox": f"{bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]},EPSG:25832",
        "outputFormat": "application/json"
    }

    try:
        response = requests.get(wfs_url, params=params, timeout=120)
        response.raise_for_status()

        # Save GeoJSON
        output_file = OUTPUT_DIR / "sefrak_trondheim.geojson"
        with open(output_file, 'w') as f:
            f.write(response.text)

        # Parse and show summary
        data = response.json()
        features = data.get('features', [])
        print(f"Downloaded {len(features)} SEFRAK buildings")

        if features:
            # Show sample attributes
            print("\nSample attributes from first building:")
            props = features[0].get('properties', {})
            for key, value in list(props.items())[:10]:
                print(f"  {key}: {value}")

        return output_file

    except Exception as e:
        print(f"WFS download failed: {e}")
        return None


def main():
    print("=" * 60)
    print("SEFRAK Data Downloader for Trondheim")
    print("=" * 60)

    # First, check capabilities
    print("\n1. Checking download capabilities...")
    try:
        caps = get_capabilities()
        print(f"   Dataset supports: {caps.keys()}")
    except Exception as e:
        print(f"   Error: {e}")

    # Check available formats
    print("\n2. Checking available formats...")
    formats = get_formats()
    if formats:
        print(f"   Formats: {[f.get('name', f) for f in formats]}")

    # Try WFS first (faster)
    print("\n3. Trying WFS service...")
    wfs_url = try_direct_download()

    if wfs_url:
        print("\n4. Downloading SEFRAK data for Trondheim via WFS...")
        result = download_via_wfs(wfs_url)
        if result:
            print(f"\nSuccess! Data saved to: {result}")
            return

    # Fall back to order-based download
    print("\n4. Ordering download via Geonorge API...")
    try:
        order = order_download(TRONDHEIM_CODE, "GML", "25832")
        print(f"   Order placed: {order}")

        ref = order.get('referenceNumber')
        if ref:
            print(f"\n5. Checking order status (reference: {ref})...")
            for i in range(10):
                status = check_order_status(ref)
                print(f"   Status: {status}")

                files = status.get('files', [])
                if files:
                    for file_info in files:
                        url = file_info.get('downloadUrl')
                        if url:
                            filename = file_info.get('name', 'sefrak_trondheim.gml')
                            download_file(url, OUTPUT_DIR / filename)
                    break

                time.sleep(5)
    except Exception as e:
        print(f"   Error: {e}")

    print("\n" + "=" * 60)
    print("Alternative: Download manually from Geonorge")
    print("https://kartkatalog.geonorge.no/metadata/sefrak-bygninger/93f06149-037c-48cf-b294-d166f65b6838")
    print("=" * 60)


if __name__ == "__main__":
    main()
