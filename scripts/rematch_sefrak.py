#!/usr/bin/env python3
"""Re-match SEFRAK to existing OSM buildings with proper coordinate transform."""

import json
from math import sqrt
from pathlib import Path
from pyproj import Transformer

data_dir = Path(__file__).parent.parent / 'data'

# Load SEFRAK
print("Loading SEFRAK...")
with open(data_dir / 'sefrak' / 'sefrak_trondheim.geojson', 'r') as f:
    sefrak_data = json.load(f)
sefrak_features = sefrak_data['features']
print(f"Loaded {len(sefrak_features)} SEFRAK buildings")

# Load existing OSM buildings
print("Loading OSM buildings...")
with open(data_dir / 'buildings_temporal.geojson', 'r') as f:
    osm_data = json.load(f)
osm_features = osm_data['features']
print(f"Loaded {len(osm_features)} OSM buildings")

# Transform SEFRAK from EPSG:25832 to EPSG:4326
transformer = Transformer.from_crs("EPSG:25832", "EPSG:4326", always_xy=True)

sefrak_points = []
for f in sefrak_features:
    coords = f['geometry']['coordinates']
    lon, lat = transformer.transform(coords[0], coords[1])
    sefrak_points.append({
        'lon': lon,
        'lat': lat,
        'start_date': f['properties'].get('start_date'),
        'end_date': f['properties'].get('end_date'),
        'period': f['properties'].get('period_description'),
        'name': f['properties'].get('name', ''),
    })

# Show sample SEFRAK coordinates to verify transform
print("\nSample SEFRAK points (WGS84):")
for i, p in enumerate(sefrak_points[:3]):
    print(f"  {p['name'][:40]:40} lon={p['lon']:.4f} lat={p['lat']:.4f}")

# Show sample OSM building centroids
print("\nSample OSM building centroids:")
for i, f in enumerate(osm_features[:3]):
    coords = f['geometry']['coordinates'][0]
    cx = sum(c[0] for c in coords) / len(coords)
    cy = sum(c[1] for c in coords) / len(coords)
    print(f"  OSM {f['properties'].get('osm_id', 'unknown'):12} lon={cx:.4f} lat={cy:.4f}")

# Match SEFRAK to OSM buildings
print("\nMatching SEFRAK to OSM buildings...")
max_distance = 30  # meters

matched = 0
for osm_f in osm_features:
    coords = osm_f['geometry']['coordinates'][0]
    cx = sum(c[0] for c in coords) / len(coords)
    cy = sum(c[1] for c in coords) / len(coords)

    # Find nearest SEFRAK point
    best_dist = float('inf')
    best_sefrak = None

    for sefrak in sefrak_points:
        # Distance in meters (approximate at this latitude)
        dx = (sefrak['lon'] - cx) * 111320 * 0.5  # cos(63°) ≈ 0.45
        dy = (sefrak['lat'] - cy) * 111320
        dist = sqrt(dx*dx + dy*dy)

        if dist < best_dist:
            best_dist = dist
            best_sefrak = sefrak

    if best_sefrak and best_dist < max_distance:
        if best_sefrak['start_date']:
            osm_f['properties']['start_date'] = best_sefrak['start_date']
            osm_f['properties']['end_date'] = best_sefrak.get('end_date', 2025)
            osm_f['properties']['source'] = 'sefrak'
            osm_f['properties']['sefrak_period'] = best_sefrak['period']
            matched += 1

print(f"Matched {matched} buildings")

# Update non-matched buildings
for osm_f in osm_features:
    if osm_f['properties'].get('source') != 'sefrak':
        if not osm_f['properties'].get('start_date') or osm_f['properties'].get('start_date') == 1950:
            osm_f['properties']['start_date'] = 1950
            osm_f['properties']['end_date'] = 2025
            osm_f['properties']['source'] = 'osm_assumed'

# Save
output_path = data_dir / 'buildings_temporal.geojson'
with open(output_path, 'w') as f:
    json.dump(osm_data, f)

print(f"\nSaved to: {output_path}")

# Statistics
sources = {}
for f in osm_features:
    src = f['properties'].get('source', 'unknown')
    sources[src] = sources.get(src, 0) + 1

print("\nBuildings by source:")
for src, count in sorted(sources.items(), key=lambda x: -x[1]):
    print(f"  {src}: {count}")
