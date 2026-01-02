"""
JSON Schema validation for pipeline configuration files.

Validates merge configs, export configs, and other JSON configuration
to catch typos and missing fields early.

Usage:
    from config_schema import validate_merge_config, validate_config

    # Validate a merge config
    config = load_json('merge_config.json')
    result = validate_merge_config(config)
    if not result.success:
        print(f"Config error: {result.error}")

    # Generic validation
    result = validate_config(config, MERGE_CONFIG_SCHEMA)
"""

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Import Result
try:
    from result import Result
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent))
    from result import Result

# Optional: Use jsonschema if available
try:
    import jsonschema
    HAS_JSONSCHEMA = True
except ImportError:
    HAS_JSONSCHEMA = False


# =============================================================================
# Schema Definitions
# =============================================================================

MERGE_CONFIG_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "required": ["version", "feature_type", "sources", "output"],
    "properties": {
        "version": {
            "type": "string",
            "description": "Config version"
        },
        "feature_type": {
            "type": "string",
            "enum": ["building", "road", "water"],
            "description": "Type of features being merged"
        },
        "sources": {
            "type": "object",
            "description": "Source configurations",
            "additionalProperties": {
                "type": "object",
                "required": ["enabled", "path"],
                "properties": {
                    "enabled": {
                        "type": "boolean",
                        "description": "Whether to include this source"
                    },
                    "path": {
                        "type": "string",
                        "description": "Path to normalized GeoJSON"
                    },
                    "priority": {
                        "type": "integer",
                        "minimum": 1,
                        "description": "Merge priority (lower = higher priority)"
                    },
                    "trust_dates": {
                        "type": "boolean",
                        "description": "Whether to trust dates from this source"
                    }
                }
            }
        },
        "matching": {
            "type": "object",
            "description": "Matching algorithm parameters",
            "properties": {
                "iou_threshold": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 1,
                    "description": "Minimum IoU for geometry match"
                },
                "buffer_distance_m": {
                    "type": "number",
                    "minimum": 0,
                    "description": "Buffer distance in meters for matching"
                },
                "hausdorff_threshold_m": {
                    "type": "number",
                    "minimum": 0,
                    "description": "Maximum Hausdorff distance for line matching"
                }
            }
        },
        "date_inference": {
            "type": "object",
            "description": "Date inference parameters",
            "properties": {
                "enabled": {"type": "boolean"},
                "buffer_m": {"type": "number", "minimum": 0},
                "fallback_year": {"type": "integer"}
            }
        },
        "output": {
            "type": "string",
            "description": "Output file path"
        }
    }
}

SOURCE_MANIFEST_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "required": ["source_id"],
    "properties": {
        "source_id": {
            "type": "string",
            "description": "Unique source identifier"
        },
        "feature_type": {
            "type": "string",
            "enum": ["building", "buildings", "road", "roads", "water"]
        },
        "last_extracted": {
            "type": "string",
            "format": "date-time"
        },
        "last_normalized": {
            "type": "string",
            "format": "date-time"
        },
        "stages": {
            "type": "object",
            "properties": {
                "extracted": {
                    "type": "object",
                    "properties": {
                        "success": {"type": "boolean"},
                        "completed_at": {"type": "string"},
                        "count": {"type": "integer"},
                        "files": {"type": "array", "items": {"type": "string"}}
                    }
                },
                "normalized": {
                    "type": "object",
                    "properties": {
                        "success": {"type": "boolean"},
                        "completed_at": {"type": "string"},
                        "count": {"type": "integer"}
                    }
                }
            }
        }
    }
}

EXPORT_MANIFEST_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "properties": {
        "version": {"type": "string"},
        "generated_at": {"type": "string"},
        "files": {
            "type": "object",
            "additionalProperties": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "size": {"type": "integer"},
                    "hash": {"type": "string"},
                    "feature_count": {"type": "integer"}
                }
            }
        }
    }
}


# =============================================================================
# Validation Functions
# =============================================================================

def validate_config(config: Dict, schema: Dict) -> Result[Dict]:
    """Validate a config dictionary against a JSON schema.

    Args:
        config: Configuration dictionary to validate
        schema: JSON schema to validate against

    Returns:
        Result.ok(config) if valid, Result.fail(error) if invalid
    """
    if HAS_JSONSCHEMA:
        try:
            jsonschema.validate(config, schema)
            return Result.ok(config)
        except jsonschema.ValidationError as e:
            return Result.fail(
                f"Config validation failed: {e.message}",
                path=list(e.absolute_path),
                schema_path=list(e.absolute_schema_path)
            )
        except jsonschema.SchemaError as e:
            return Result.fail(f"Invalid schema: {e.message}")
    else:
        # Basic validation without jsonschema
        return _basic_validate(config, schema)


def _basic_validate(config: Dict, schema: Dict) -> Result[Dict]:
    """Basic validation without jsonschema library.

    Checks required fields and basic types.
    """
    errors = []

    # Check required fields
    required = schema.get('required', [])
    for field in required:
        if field not in config:
            errors.append(f"Missing required field: {field}")

    # Check property types
    properties = schema.get('properties', {})
    for field, value in config.items():
        if field in properties:
            prop_schema = properties[field]
            expected_type = prop_schema.get('type')

            if expected_type == 'string' and not isinstance(value, str):
                errors.append(f"Field '{field}' should be string, got {type(value).__name__}")
            elif expected_type == 'integer' and not isinstance(value, int):
                errors.append(f"Field '{field}' should be integer, got {type(value).__name__}")
            elif expected_type == 'number' and not isinstance(value, (int, float)):
                errors.append(f"Field '{field}' should be number, got {type(value).__name__}")
            elif expected_type == 'boolean' and not isinstance(value, bool):
                errors.append(f"Field '{field}' should be boolean, got {type(value).__name__}")
            elif expected_type == 'object' and not isinstance(value, dict):
                errors.append(f"Field '{field}' should be object, got {type(value).__name__}")
            elif expected_type == 'array' and not isinstance(value, list):
                errors.append(f"Field '{field}' should be array, got {type(value).__name__}")

            # Check enum
            if 'enum' in prop_schema and value not in prop_schema['enum']:
                errors.append(f"Field '{field}' must be one of {prop_schema['enum']}, got '{value}'")

    if errors:
        return Result.fail(
            f"Config validation failed: {errors[0]}",
            all_errors=errors
        )

    return Result.ok(config)


def validate_merge_config(config: Dict) -> Result[Dict]:
    """Validate a merge configuration.

    Args:
        config: Merge config dictionary

    Returns:
        Result.ok(config) if valid
    """
    return validate_config(config, MERGE_CONFIG_SCHEMA)


def validate_source_manifest(manifest: Dict) -> Result[Dict]:
    """Validate a source manifest.

    Args:
        manifest: Manifest dictionary

    Returns:
        Result.ok(manifest) if valid
    """
    return validate_config(manifest, SOURCE_MANIFEST_SCHEMA)


def load_and_validate(path: Path, schema: Dict) -> Result[Dict]:
    """Load a JSON file and validate against schema.

    Args:
        path: Path to JSON file
        schema: JSON schema

    Returns:
        Result.ok(config) if valid, Result.fail(error) otherwise
    """
    try:
        with open(path) as f:
            config = json.load(f)
    except FileNotFoundError:
        return Result.fail(f"File not found: {path}")
    except json.JSONDecodeError as e:
        return Result.fail(f"Invalid JSON: {e.msg} at line {e.lineno}")

    result = validate_config(config, schema)
    if not result.success:
        result.details['file'] = str(path)

    return result


def load_merge_config(path: Path) -> Result[Dict]:
    """Load and validate a merge config file.

    Args:
        path: Path to merge config JSON

    Returns:
        Result with validated config
    """
    return load_and_validate(path, MERGE_CONFIG_SCHEMA)


# =============================================================================
# CLI
# =============================================================================

def main():
    """CLI for validating config files."""
    import argparse

    parser = argparse.ArgumentParser(description='Validate pipeline config files')
    parser.add_argument('file', type=Path, help='Config file to validate')
    parser.add_argument(
        '--type',
        choices=['merge', 'manifest', 'export'],
        default='merge',
        help='Config type'
    )

    args = parser.parse_args()

    schemas = {
        'merge': MERGE_CONFIG_SCHEMA,
        'manifest': SOURCE_MANIFEST_SCHEMA,
        'export': EXPORT_MANIFEST_SCHEMA,
    }

    result = load_and_validate(args.file, schemas[args.type])

    if result.success:
        print(f"✓ {args.file} is valid")
    else:
        print(f"✗ {args.file} is invalid")
        print(f"  Error: {result.error}")
        if result.details.get('all_errors'):
            for err in result.details['all_errors']:
                print(f"  - {err}")
        sys.exit(1)


if __name__ == '__main__':
    main()
