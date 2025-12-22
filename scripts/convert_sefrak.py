#!/usr/bin/env python3
"""
Convert SEFRAK GML to GeoJSON with proper time period interpretation.

SEFRAK time codes (tidsangivelse):
- 166: 1660s (before 1700)
- 17X: 17XX decade
- 18X: 18XX decade
- 190: 1900-1920 (Finnmark only)
"""

import json
import re
from pathlib import Path
from xml.etree import ElementTree as ET

# Namespaces in SEFRAK GML
NS = {
    'gml': 'http://www.opengis.net/gml/3.2',
    'app': 'http://skjema.geonorge.no/SOSI/produktspesifikasjon/SEFRAK/20160503',
}

# SEFRAK time period codes to approximate years
TIME_CODE_MAP = {
    '166': (1660, 1700, 'before 1700'),
    '170': (1700, 1710, '1700-1710'),
    '171': (1710, 1720, '1710-1720'),
    '172': (1720, 1730, '1720-1730'),
    '173': (1730, 1740, '1730-1740'),
    '174': (1740, 1750, '1740-1750'),
    '175': (1750, 1760, '1750-1760'),
    '176': (1760, 1770, '1760-1770'),
    '177': (1770, 1780, '1770-1780'),
    '178': (1780, 1790, '1780-1790'),
    '179': (1790, 1800, '1790-1800'),
    '180': (1800, 1810, '1800-1810'),
    '181': (1810, 1820, '1810-1820'),
    '182': (1820, 1830, '1820-1830'),
    '183': (1830, 1840, '1830-1840'),
    '184': (1840, 1850, '1840-1850'),
    '185': (1850, 1860, '1850-1860'),
    '186': (1860, 1870, '1860-1870'),
    '187': (1870, 1880, '1870-1880'),
    '188': (1880, 1890, '1880-1890'),
    '189': (1890, 1900, '1890-1900'),
    '190': (1900, 1920, '1900-1920'),  # Finnmark
    '191': (1920, 1945, '1920-1945'),  # Finnmark
}

# SEFRAK function codes (common ones)
FUNCTION_CODES = {
    '000': 'Ukjent/uregistrert',
    '111': 'Våningshus',
    '115': 'Seterbu',
    '121': 'Fritidsbolig',
    '153': 'Fjøs',
    '161': 'Løe/høyløe',
    '163': 'Stabbur',
    '171': 'Seterfjøs',
    '181': 'Smie',
    '211': 'Industribygning',
    '311': 'Kontor/forretning',
    '411': 'Skole',
    '511': 'Hotell',
    '611': 'Kultur/forsamling',
    '711': 'Kirke',
    '811': 'Sykehus',
    '911': 'Annen bygning',
}


def parse_gml(gml_path: Path) -> list:
    """Parse SEFRAK GML file and extract buildings."""
    tree = ET.parse(gml_path)
    root = tree.getroot()

    buildings = []

    for member in root.findall('.//gml:featureMember', NS):
        building = member.find('app:KulturminneBygning', NS)
        if building is None:
            continue

        # Extract properties
        props = {}

        # Building number
        bn = building.find('app:bygningsnummer', NS)
        if bn is not None:
            props['bygningsnummer'] = bn.text

        # Building type
        bt = building.find('app:bygningstype', NS)
        if bt is not None:
            props['bygningstype'] = bt.text

        # SEFRAK ID
        sefrak_id = building.find('.//app:SefrakId', NS)
        if sefrak_id is not None:
            kommune = sefrak_id.find('app:sefrakKommune', NS)
            krets = sefrak_id.find('app:registreringKretsnr', NS)
            hus = sefrak_id.find('app:husLøpenr', NS)
            if kommune is not None and krets is not None and hus is not None:
                props['sefrak_id'] = f"{kommune.text}-{krets.text}-{hus.text}"

        # Status
        status = building.find('app:sefrakStatus', NS)
        if status is not None:
            props['sefrak_status'] = status.text

        # Name
        name = building.find('.//app:objektnavn', NS)
        if name is not None:
            props['name'] = name.text

        # Time period
        time_code = building.find('.//app:tidsangivelse', NS)
        if time_code is not None:
            code = time_code.text
            props['time_code'] = code
            if code in TIME_CODE_MAP:
                start, end, period = TIME_CODE_MAP[code]
                props['start_date'] = start
                props['end_date'] = end
                props['period_description'] = period

        # Functions (original and current)
        for func in building.findall('.//app:SefrakFunksjon', NS):
            func_code = func.find('app:sefrakFunksjonskode', NS)
            func_status = func.find('app:sefrakFunksjonsstatus', NS)
            if func_code is not None and func_status is not None:
                status_key = func_status.text
                code = func_code.text
                if status_key == 'OP':  # Original
                    props['original_function'] = code
                    props['original_function_name'] = FUNCTION_CODES.get(code, code)
                elif status_key == 'NÅ':  # Current
                    props['current_function'] = code
                    props['current_function_name'] = FUNCTION_CODES.get(code, code)

        # Extract coordinates
        point = building.find('.//gml:Point', NS)
        if point is not None:
            pos = point.find('gml:pos', NS)
            if pos is not None:
                coords = pos.text.split()
                if len(coords) >= 2:
                    # GML is easting, northing (x, y)
                    x, y = float(coords[0]), float(coords[1])

                    buildings.append({
                        'type': 'Feature',
                        'properties': props,
                        'geometry': {
                            'type': 'Point',
                            'coordinates': [x, y]  # EPSG:25832
                        }
                    })

    return buildings


def create_geojson(buildings: list) -> dict:
    """Create GeoJSON FeatureCollection."""
    return {
        'type': 'FeatureCollection',
        'name': 'SEFRAK Trondheim',
        'crs': {
            'type': 'name',
            'properties': {
                'name': 'urn:ogc:def:crs:EPSG::25832'
            }
        },
        'features': buildings
    }


def analyze_buildings(buildings: list):
    """Print analysis of the buildings."""
    print(f"\nTotal buildings: {len(buildings)}")

    # Count by time period
    periods = {}
    for b in buildings:
        period = b['properties'].get('period_description', 'Unknown')
        periods[period] = periods.get(period, 0) + 1

    print("\nBuildings by time period:")
    for period, count in sorted(periods.items()):
        print(f"  {period}: {count}")

    # Count by function
    functions = {}
    for b in buildings:
        func = b['properties'].get('original_function_name', 'Unknown')
        functions[func] = functions.get(func, 0) + 1

    print("\nBuildings by original function (top 10):")
    for func, count in sorted(functions.items(), key=lambda x: -x[1])[:10]:
        print(f"  {func}: {count}")

    # Count by status
    statuses = {}
    for b in buildings:
        status = b['properties'].get('sefrak_status', 'Unknown')
        status_name = {
            '0': 'Demolished/gone',
            '1': 'Standing',
            '2': 'Moved',
            '3': 'Unknown',
        }.get(status, status)
        statuses[status_name] = statuses.get(status_name, 0) + 1

    print("\nBuildings by status:")
    for status, count in sorted(statuses.items(), key=lambda x: -x[1]):
        print(f"  {status}: {count}")


def main():
    # Input/output paths
    gml_path = Path(__file__).parent.parent / 'data' / 'sefrak' / 'Kulturminner_5001_Trondheim_25832_Sefrakbygninger_GML.gml'
    output_path = Path(__file__).parent.parent / 'data' / 'sefrak' / 'sefrak_trondheim.geojson'

    print(f"Reading: {gml_path}")
    buildings = parse_gml(gml_path)

    print(f"Parsed {len(buildings)} buildings")

    # Analyze
    analyze_buildings(buildings)

    # Create GeoJSON
    geojson = create_geojson(buildings)

    # Save
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(geojson, f, ensure_ascii=False, indent=2)

    print(f"\nSaved to: {output_path}")
    print(f"File size: {output_path.stat().st_size / 1024:.1f} KB")


if __name__ == '__main__':
    main()
