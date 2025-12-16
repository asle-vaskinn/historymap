#!/usr/bin/env python3
"""
Test script to verify all historical map styles are valid and complete.
"""

import json
from pathlib import Path


def validate_style(style_path: Path) -> dict:
    """Validate a MapLibre style JSON file."""
    errors = []
    warnings = []
    
    try:
        with open(style_path, 'r') as f:
            style = json.load(f)
    except json.JSONDecodeError as e:
        return {
            'valid': False,
            'errors': [f"Invalid JSON: {e}"],
            'warnings': []
        }
    
    # Check required top-level fields
    required_fields = ['version', 'sources', 'layers']
    for field in required_fields:
        if field not in style:
            errors.append(f"Missing required field: {field}")
    
    # Check version
    if style.get('version') != 8:
        warnings.append(f"Expected version 8, got {style.get('version')}")
    
    # Check sources
    if 'sources' in style and not style['sources']:
        errors.append("No sources defined")
    
    # Check layers
    if 'layers' in style:
        if not style['layers']:
            errors.append("No layers defined")
        else:
            layer_ids = [layer.get('id') for layer in style['layers']]
            if len(layer_ids) != len(set(layer_ids)):
                errors.append("Duplicate layer IDs found")
            
            # Check for essential layers
            essential_types = ['background', 'water', 'building', 'road']
            layer_types_present = []
            for layer in style['layers']:
                layer_id = layer.get('id', '').lower()
                for essential in essential_types:
                    if essential in layer_id:
                        layer_types_present.append(essential)
                        break
            
            missing_types = set(essential_types) - set(layer_types_present)
            if missing_types:
                warnings.append(f"Missing layer types: {', '.join(missing_types)}")
    
    return {
        'valid': len(errors) == 0,
        'errors': errors,
        'warnings': warnings
    }


def main():
    """Test all historical map styles."""
    styles_dir = Path(__file__).parent / 'styles'
    
    # Historical styles to test
    historical_styles = [
        'military_1880.json',
        'cadastral_1900.json',
        'topographic_1920.json'
    ]
    
    print("=" * 60)
    print("Historical Map Styles - Validation Test")
    print("=" * 60)
    print()
    
    all_valid = True
    
    for style_name in historical_styles:
        style_path = styles_dir / style_name
        
        print(f"Testing: {style_name}")
        print("-" * 60)
        
        if not style_path.exists():
            print(f"  ✗ ERROR: File not found")
            all_valid = False
            print()
            continue
        
        result = validate_style(style_path)
        
        if result['valid']:
            print(f"  ✓ Valid MapLibre GL style")
            
            # Show style info
            with open(style_path, 'r') as f:
                style = json.load(f)
                print(f"  Name: {style.get('name', 'N/A')}")
                print(f"  Layers: {len(style.get('layers', []))}")
                print(f"  Sources: {len(style.get('sources', {}))}")
                
                if 'metadata' in style:
                    meta = style['metadata']
                    print(f"  Era: {meta.get('era', 'N/A')}")
                    print(f"  Type: {meta.get('type', 'N/A')}")
        else:
            print(f"  ✗ INVALID")
            all_valid = False
        
        if result['errors']:
            print(f"  Errors:")
            for error in result['errors']:
                print(f"    - {error}")
        
        if result['warnings']:
            print(f"  Warnings:")
            for warning in result['warnings']:
                print(f"    - {warning}")
        
        print()
    
    print("=" * 60)
    if all_valid:
        print("✓ All historical styles are valid!")
        print()
        print("You can now:")
        print("  1. Use these styles directly in MapLibre GL")
        print("  2. Generate variations with generate_styles.py")
        print("  3. Use them for synthetic training data generation")
        return 0
    else:
        print("✗ Some styles have errors - please fix them")
        return 1


if __name__ == '__main__':
    exit(main())
