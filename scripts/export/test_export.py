#!/usr/bin/env python3
"""
Test script for export_geojson.py

Creates sample merged data and verifies the export transformation.
"""

import json
import tempfile
from pathlib import Path

from export_geojson import transform_feature, generate_bid


def test_generate_bid():
    """Test building ID generation."""
    print("Testing generate_bid()...")

    tests = [
        ('sefrak', 'SEFRAK-12345', 'sef-12345'),
        ('osm', 'way/123456', 'osm-123456'),
        ('ml_kartverket_1880', 'detected-001', 'ml-detected-001'),
    ]

    for src, src_id, expected in tests:
        result = generate_bid(src, src_id)
        assert result == expected, f"Expected {expected}, got {result}"
        print(f"  ✓ {src} + {src_id} → {result}")

    print("  All generate_bid tests passed!\n")


def test_transform_feature():
    """Test feature transformation."""
    print("Testing transform_feature()...")

    # Test 1: Simple SEFRAK building
    merged_feat = {
        'type': 'Feature',
        'properties': {
            '_src': 'sefrak',
            '_src_id': 'SEFRAK-12345',
            '_ingested': '2024-01-20',
            'sd': 1850,
            'ev': 'h',
            'bt': 'residential',
            'nm': 'Stiftsgården',
            '_raw': {'original': 'data'}
        },
        'geometry': {
            'type': 'Polygon',
            'coordinates': [[[10.0, 63.0], [10.1, 63.0], [10.1, 63.1], [10.0, 63.1], [10.0, 63.0]]]
        }
    }

    frontend_feat = transform_feature(merged_feat)

    # Check required fields
    assert frontend_feat['properties']['bid'] == 'sef-12345'
    assert frontend_feat['properties']['src'] == 'sef'
    assert frontend_feat['properties']['sd'] == 1850
    assert frontend_feat['properties']['ev'] == 'h'
    assert frontend_feat['properties']['bt'] == 'residential'
    assert frontend_feat['properties']['nm'] == 'Stiftsgården'

    # Check stripped fields
    assert '_src' not in frontend_feat['properties']
    assert '_src_id' not in frontend_feat['properties']
    assert '_ingested' not in frontend_feat['properties']
    assert '_raw' not in frontend_feat['properties']

    print("  ✓ SEFRAK building transformed correctly")

    # Test 2: Multi-source building
    merged_feat_multi = {
        'type': 'Feature',
        'properties': {
            '_src': 'sefrak',
            '_src_id': 'SEFRAK-99999',
            '_ingested': '2024-01-20',
            'sd': 1875,
            'ev': 'h',
            'src_all': ['sefrak', 'osm'],
            '_merge_info': {
                'matched_at': '2024-01-20',
                'sources': {
                    'osm': {'src_id': 'way/123456', 'sd': None}
                }
            }
        },
        'geometry': {
            'type': 'Polygon',
            'coordinates': [[[10.0, 63.0], [10.1, 63.0], [10.1, 63.1], [10.0, 63.1], [10.0, 63.0]]]
        }
    }

    frontend_feat_multi = transform_feature(merged_feat_multi)

    assert 'src_all' in frontend_feat_multi['properties']
    assert frontend_feat_multi['properties']['src_all'] == ['sef', 'osm']
    assert '_merge_info' not in frontend_feat_multi['properties']

    print("  ✓ Multi-source building transformed correctly")

    # Test 3: ML-detected building
    merged_feat_ml = {
        'type': 'Feature',
        'properties': {
            '_src': 'ml_kartverket_1880',
            '_src_id': 'ml-001',
            '_ingested': '2024-01-20',
            'sd': 1880,
            'ev': 'h',
            'mlc': 0.92
        },
        'geometry': {
            'type': 'Polygon',
            'coordinates': [[[10.0, 63.0], [10.1, 63.0], [10.1, 63.1], [10.0, 63.1], [10.0, 63.0]]]
        }
    }

    frontend_feat_ml = transform_feature(merged_feat_ml)

    assert frontend_feat_ml['properties']['src'] == 'ml'
    assert frontend_feat_ml['properties']['ml_src'] == 'kv1880'
    assert frontend_feat_ml['properties']['mlc'] == 0.92

    print("  ✓ ML-detected building transformed correctly")

    # Test 4: Replaced building
    merged_feat_replaced = {
        'type': 'Feature',
        'properties': {
            '_src': 'sefrak',
            '_src_id': 'SEFRAK-OLD',
            '_ingested': '2024-01-20',
            'sd': 1750,
            'ed': 1965,
            'ev': 'h',
            'rep_by': 'way/567890',
            'rep_ev': 'h'
        },
        'geometry': {
            'type': 'Polygon',
            'coordinates': [[[10.0, 63.0], [10.1, 63.0], [10.1, 63.1], [10.0, 63.1], [10.0, 63.0]]]
        }
    }

    frontend_feat_replaced = transform_feature(merged_feat_replaced)

    assert frontend_feat_replaced['properties']['ed'] == 1965
    assert frontend_feat_replaced['properties']['rep_by'] == 'way/567890'
    assert frontend_feat_replaced['properties']['rep_ev'] == 'h'

    print("  ✓ Replaced building transformed correctly")

    print("  All transform_feature tests passed!\n")


def test_full_export():
    """Test full export process with sample data."""
    print("Testing full export process...")

    from export_geojson import export_geojson

    # Create sample merged data
    sample_data = {
        'type': 'FeatureCollection',
        'features': [
            {
                'type': 'Feature',
                'properties': {
                    '_src': 'sefrak',
                    '_src_id': 'SEFRAK-001',
                    '_ingested': '2024-01-20',
                    'sd': 1850,
                    'ev': 'h',
                    'bt': 'residential'
                },
                'geometry': {
                    'type': 'Polygon',
                    'coordinates': [[[10.0, 63.0], [10.1, 63.0], [10.1, 63.1], [10.0, 63.1], [10.0, 63.0]]]
                }
            },
            {
                'type': 'Feature',
                'properties': {
                    '_src': 'osm',
                    '_src_id': 'way/123456',
                    '_ingested': '2024-01-20',
                    'ev': 'l'
                },
                'geometry': {
                    'type': 'Polygon',
                    'coordinates': [[[10.2, 63.2], [10.3, 63.2], [10.3, 63.3], [10.2, 63.3], [10.2, 63.2]]]
                }
            },
            {
                'type': 'Feature',
                'properties': {
                    '_src': 'ml_kartverket_1880',
                    '_src_id': 'ml-001',
                    '_ingested': '2024-01-20',
                    'sd': 1880,
                    'ev': 'h',
                    'mlc': 0.95
                },
                'geometry': {
                    'type': 'Polygon',
                    'coordinates': [[[10.4, 63.4], [10.5, 63.4], [10.5, 63.5], [10.4, 63.5], [10.4, 63.4]]]
                }
            }
        ]
    }

    # Create temp directory for test
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Write sample input
        input_path = tmpdir / 'merged.geojson'
        with open(input_path, 'w') as f:
            json.dump(sample_data, f)

        # Run export
        output_path = tmpdir / 'export.geojson'
        success = export_geojson(input_path, output_path, stats=False)

        assert success, "Export failed"

        # Read output
        with open(output_path) as f:
            output_data = json.load(f)

        # Verify output
        assert output_data['type'] == 'FeatureCollection'
        assert len(output_data['features']) == 3

        # Check first feature (SEFRAK)
        feat1 = output_data['features'][0]
        assert feat1['properties']['bid'] == 'sef-001'
        assert feat1['properties']['src'] == 'sef'
        assert '_src' not in feat1['properties']

        # Check second feature (OSM)
        feat2 = output_data['features'][1]
        assert feat2['properties']['bid'] == 'osm-123456'
        assert feat2['properties']['src'] == 'osm'

        # Check third feature (ML)
        feat3 = output_data['features'][2]
        assert feat3['properties']['bid'] == 'ml-ml-001'
        assert feat3['properties']['src'] == 'ml'
        assert feat3['properties']['ml_src'] == 'kv1880'
        assert feat3['properties']['mlc'] == 0.95

        print("  ✓ Full export completed successfully")
        print(f"  ✓ Output file created: {output_path}")
        print(f"  ✓ Exported {len(output_data['features'])} features\n")


def main():
    """Run all tests."""
    print("="*60)
    print("EXPORT SCRIPT TESTS")
    print("="*60 + "\n")

    try:
        test_generate_bid()
        test_transform_feature()
        test_full_export()

        print("="*60)
        print("ALL TESTS PASSED!")
        print("="*60)

    except AssertionError as e:
        print(f"\n✗ Test failed: {e}")
        return 1
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == '__main__':
    import sys
    sys.exit(main())
