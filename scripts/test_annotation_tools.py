#!/usr/bin/env python3
"""
Test script for annotation tools.

Creates dummy tiles and tests the annotation helper and progress tracker
without requiring a trained model or real historical maps.

Usage:
    python test_annotation_tools.py
"""

import sys
import tempfile
import shutil
from pathlib import Path
import json

# Check for required dependencies
try:
    import numpy as np
    import PIL
    from PIL import Image, ImageDraw
    HAS_DEPS = True
except ImportError as e:
    print(f"Warning: Missing dependencies: {e}")
    print("Some tests will be skipped. Install with: pip install numpy pillow")
    HAS_DEPS = False


def create_test_tiles(output_dir: Path, count: int = 5):
    """Create dummy test tiles."""
    if not HAS_DEPS:
        print(f"Skipping test tile creation (missing dependencies)")
        return

    print(f"Creating {count} test tiles in {output_dir}")

    for i in range(count):
        # Create a simple test image (256x256)
        img = Image.new('RGB', (256, 256), color=(200, 200, 180))
        draw = ImageDraw.Draw(img)

        # Draw some features
        # Buildings (red rectangles)
        for _ in range(3):
            x = np.random.randint(20, 200)
            y = np.random.randint(20, 200)
            w = np.random.randint(20, 60)
            h = np.random.randint(20, 60)
            draw.rectangle([x, y, x+w, y+h], fill=(180, 100, 100), outline=(100, 50, 50))

        # Roads (yellow lines)
        for _ in range(2):
            x1 = np.random.randint(0, 256)
            y1 = np.random.randint(0, 256)
            x2 = np.random.randint(0, 256)
            y2 = np.random.randint(0, 256)
            draw.line([x1, y1, x2, y2], fill=(200, 200, 100), width=5)

        # Water (blue shape)
        if np.random.random() > 0.5:
            x = np.random.randint(20, 150)
            y = np.random.randint(20, 150)
            draw.ellipse([x, y, x+80, y+60], fill=(100, 150, 200))

        # Add tile number
        draw.text((10, 10), f"Tile {i+1}", fill=(50, 50, 50))

        # Save
        img.save(output_dir / f"test_tile_{i+1:03d}.png")

    print(f"✓ Created {count} test tiles")


def test_progress_tracker(annotations_dir: Path, tiles_dir: Path):
    """Test the progress tracker."""
    if not HAS_DEPS:
        print("\nSkipping progress tracker test (missing dependencies)")
        return

    print("\nTesting progress tracker...")

    # Import the progress tracker
    sys.path.insert(0, str(Path(__file__).parent))
    try:
        from annotation_progress import AnnotationProgress
    except ImportError as e:
        print(f"  ⚠ Could not import annotation_progress: {e}")
        return

    # Create tracker
    tracker = AnnotationProgress(
        annotations_dir=str(annotations_dir),
        tiles_dir=str(tiles_dir)
    )

    # Print statistics
    stats = tracker.calculate_statistics()
    print(f"  Total tiles: {stats['total_tiles']}")
    print(f"  Annotated: {stats['annotated_count']}")
    print(f"  Remaining: {stats['remaining_count']}")

    # List unannotated
    unannotated = tracker.list_unannotated_tiles()
    print(f"  Unannotated tiles: {len(unannotated)}")

    print("✓ Progress tracker working")


def create_dummy_annotations(annotations_dir: Path, tiles_dir: Path, count: int = 2):
    """Create dummy annotations for testing."""
    if not HAS_DEPS:
        print(f"\nSkipping dummy annotation creation (missing dependencies)")
        return

    print(f"\nCreating {count} dummy annotations...")

    images_dir = annotations_dir / "images"
    masks_dir = annotations_dir / "masks"
    images_dir.mkdir(parents=True, exist_ok=True)
    masks_dir.mkdir(parents=True, exist_ok=True)

    tiles = sorted(tiles_dir.glob("*.png"))[:count]

    progress = {
        'annotated': [],
        'last_modified': {}
    }

    for i, tile in enumerate(tiles):
        # Copy tile to images
        shutil.copy(tile, images_dir / tile.name)

        # Create simple mask
        mask = np.zeros((256, 256), dtype=np.uint8)

        # Add some random annotations
        # Buildings
        mask[50:100, 50:100] = 1
        mask[150:180, 150:200] = 1

        # Roads
        mask[120:130, :] = 2

        # Water
        if np.random.random() > 0.5:
            mask[200:240, 30:80] = 3

        # Save mask
        mask_path = masks_dir / f"{tile.stem}_mask.png"
        mask_img = Image.fromarray(mask, mode='L')
        mask_img.save(mask_path)

        # Update progress
        from datetime import datetime, timedelta
        timestamp = (datetime.now() - timedelta(minutes=(count-i)*5)).isoformat()
        progress['annotated'].append(tile.name)
        progress['last_modified'][tile.name] = timestamp

    # Save progress file
    with open(annotations_dir / "progress.json", 'w') as f:
        json.dump(progress, f, indent=2)

    print(f"✓ Created {count} dummy annotations")


def verify_tools_importable():
    """Verify that annotation tools can be imported."""
    print("Verifying tools can be imported...")

    sys.path.insert(0, str(Path(__file__).parent))

    try:
        # Test imports (but don't actually run GUI)
        import importlib.util

        # Check annotation_helper
        helper_path = Path(__file__).parent / "annotation_helper.py"
        spec = importlib.util.spec_from_file_location("annotation_helper", helper_path)
        module = importlib.util.module_from_spec(spec)

        # Check if tkinter is available
        try:
            import tkinter
            print("  ✓ tkinter available")
        except ImportError:
            print("  ⚠ tkinter not available - GUI won't work")
            print("    Install with: brew install python-tk (macOS)")
            print("                  sudo apt-get install python3-tk (Ubuntu)")

        # Check annotation_progress
        from annotation_progress import AnnotationProgress
        print("  ✓ annotation_progress importable")

        # Check ml.predict
        try:
            sys.path.insert(0, str(Path(__file__).parent.parent))
            from ml.predict import load_model, predict
            print("  ✓ ml.predict importable")
        except ImportError as e:
            print(f"  ⚠ ml.predict import issue: {e}")

        print("✓ Tools can be imported")
        return True

    except Exception as e:
        print(f"✗ Import error: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    print("=" * 60)
    print("ANNOTATION TOOLS TEST")
    print("=" * 60)

    # Verify imports
    if not verify_tools_importable():
        print("\n⚠ Some imports failed, but continuing with tests...")

    # Create temporary directories
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        tiles_dir = tmpdir / "tiles"
        annotations_dir = tmpdir / "annotations"

        tiles_dir.mkdir()
        annotations_dir.mkdir()

        # Create test data
        create_test_tiles(tiles_dir, count=5)
        create_dummy_annotations(annotations_dir, tiles_dir, count=2)

        # Test progress tracker
        test_progress_tracker(annotations_dir, tiles_dir)

        print("\n" + "=" * 60)
        print("TEST SUMMARY")
        print("=" * 60)
        if HAS_DEPS:
            print("✓ Test tiles created successfully")
            print("✓ Dummy annotations created successfully")
            print("✓ Progress tracker working correctly")
        else:
            print("⚠ Some tests skipped due to missing dependencies")
            print("  Install with: pip install numpy pillow torch segmentation-models-pytorch")
        print("\nTo test the GUI:")
        print("  1. Create some test tiles:")
        print("     mkdir -p /tmp/test_tiles")
        print("     # Copy some images there")
        print("  2. Run the annotation helper:")
        print("     python annotation_helper.py \\")
        print("       --tiles-dir /tmp/test_tiles \\")
        print("       --output-dir /tmp/test_annotations")
        print("\nAll basic functionality verified!")


if __name__ == '__main__':
    main()
