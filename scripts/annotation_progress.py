#!/usr/bin/env python3
"""
Track annotation progress for historical map tiles.

Shows statistics, estimates time remaining, lists tiles by priority,
and exports progress reports.

Usage:
    python annotation_progress.py --annotations-dir ../data/annotations/
    python annotation_progress.py --annotations-dir ../data/annotations/ --tiles-dir ../data/kartverket/tiles/
    python annotation_progress.py --annotations-dir ../data/annotations/ --export report.txt
"""

import argparse
import json
import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
import statistics


class AnnotationProgress:
    """Track and report on annotation progress."""

    def __init__(self, annotations_dir: str, tiles_dir: Optional[str] = None):
        """
        Initialize progress tracker.

        Args:
            annotations_dir: Directory containing annotations
            tiles_dir: Optional directory containing all available tiles
        """
        self.annotations_dir = Path(annotations_dir)
        self.tiles_dir = Path(tiles_dir) if tiles_dir else None

        # Load progress data
        self.progress_file = self.annotations_dir / "progress.json"
        self.progress = self.load_progress()

        # Load annotations
        self.masks_dir = self.annotations_dir / "masks"
        self.annotated_tiles = self.get_annotated_tiles()

        # Load available tiles if directory provided
        self.available_tiles = []
        if self.tiles_dir and self.tiles_dir.exists():
            self.available_tiles = self.get_available_tiles()

    def load_progress(self) -> Dict:
        """Load progress from JSON file."""
        if self.progress_file.exists():
            with open(self.progress_file, 'r') as f:
                return json.load(f)
        return {'annotated': [], 'last_modified': {}}

    def get_annotated_tiles(self) -> List[Path]:
        """Get list of annotated mask files."""
        if not self.masks_dir.exists():
            return []

        masks = []
        for ext in ['.png', '.PNG']:
            masks.extend(self.masks_dir.glob(f'*_mask{ext}'))
        return sorted(masks)

    def get_available_tiles(self) -> List[Path]:
        """Get list of all available tile images."""
        extensions = ['.png', '.jpg', '.jpeg', '.tif', '.tiff']
        tiles = []
        for ext in extensions:
            tiles.extend(self.tiles_dir.glob(f'*{ext}'))
            tiles.extend(self.tiles_dir.glob(f'*{ext.upper()}'))
        return sorted(tiles)

    def calculate_statistics(self) -> Dict:
        """Calculate annotation statistics."""
        stats = {
            'total_tiles': len(self.available_tiles) if self.available_tiles else 0,
            'annotated_count': len(self.annotated_tiles),
            'remaining_count': 0,
            'completion_percentage': 0.0,
            'annotation_times': [],
            'avg_time_per_tile': None,
            'estimated_remaining_time': None,
        }

        # Calculate remaining and percentage
        if stats['total_tiles'] > 0:
            stats['remaining_count'] = stats['total_tiles'] - stats['annotated_count']
            stats['completion_percentage'] = (stats['annotated_count'] / stats['total_tiles']) * 100
        elif stats['annotated_count'] > 0:
            # If we don't know total, just show what we have
            stats['remaining_count'] = 'Unknown'
            stats['completion_percentage'] = 'Unknown'

        # Calculate annotation times
        last_modified = self.progress.get('last_modified', {})
        if len(last_modified) >= 2:
            times = []
            sorted_times = sorted(last_modified.items(), key=lambda x: x[1])

            for i in range(1, len(sorted_times)):
                prev_time = datetime.fromisoformat(sorted_times[i-1][1])
                curr_time = datetime.fromisoformat(sorted_times[i][1])
                delta = (curr_time - prev_time).total_seconds() / 60  # minutes
                # Filter out unrealistic times (> 2 hours)
                if 0 < delta < 120:
                    times.append(delta)

            if times:
                stats['annotation_times'] = times
                stats['avg_time_per_tile'] = statistics.mean(times)

                # Estimate remaining time
                if isinstance(stats['remaining_count'], int) and stats['avg_time_per_tile']:
                    total_minutes = stats['remaining_count'] * stats['avg_time_per_tile']
                    stats['estimated_remaining_time'] = total_minutes

        return stats

    def format_time(self, minutes: float) -> str:
        """Format minutes into human-readable time."""
        if minutes < 60:
            return f"{minutes:.1f} minutes"
        elif minutes < 1440:  # Less than 24 hours
            hours = minutes / 60
            return f"{hours:.1f} hours"
        else:
            days = minutes / 1440
            return f"{days:.1f} days"

    def print_statistics(self):
        """Print progress statistics."""
        stats = self.calculate_statistics()

        print("=" * 60)
        print("ANNOTATION PROGRESS REPORT")
        print("=" * 60)
        print()

        print("OVERVIEW")
        print("-" * 60)
        if stats['total_tiles'] > 0:
            print(f"  Total tiles available: {stats['total_tiles']}")
            print(f"  Annotated tiles:       {stats['annotated_count']}")
            print(f"  Remaining tiles:       {stats['remaining_count']}")
            print(f"  Completion:            {stats['completion_percentage']:.1f}%")
        else:
            print(f"  Annotated tiles:       {stats['annotated_count']}")
            print(f"  Total tiles:           Unknown (use --tiles-dir to specify)")
        print()

        if stats['avg_time_per_tile']:
            print("TIME ESTIMATES")
            print("-" * 60)
            print(f"  Average time per tile: {self.format_time(stats['avg_time_per_tile'])}")

            if stats['estimated_remaining_time']:
                print(f"  Estimated remaining:   {self.format_time(stats['estimated_remaining_time'])}")

                # Show annotation rate
                total_minutes = sum(stats['annotation_times'])
                if total_minutes > 0:
                    rate = len(stats['annotation_times']) / (total_minutes / 60)
                    print(f"  Annotation rate:       {rate:.2f} tiles/hour")
            print()

        # Show recent annotations
        if self.progress.get('last_modified'):
            print("RECENT ANNOTATIONS")
            print("-" * 60)
            recent = sorted(
                self.progress['last_modified'].items(),
                key=lambda x: x[1],
                reverse=True
            )[:5]

            for tile_name, timestamp in recent:
                dt = datetime.fromisoformat(timestamp)
                time_str = dt.strftime("%Y-%m-%d %H:%M")
                print(f"  {time_str}  {tile_name}")
            print()

    def list_unannotated_tiles(self, priority: str = 'name') -> List[Tuple[Path, str]]:
        """
        List tiles that haven't been annotated yet.

        Args:
            priority: Sorting method - 'name', 'random', or 'center'

        Returns:
            List of (tile_path, reason) tuples
        """
        if not self.available_tiles:
            return []

        # Get names of annotated tiles
        annotated_names = set()
        for mask_path in self.annotated_tiles:
            # Remove '_mask' suffix to get original tile name
            name = mask_path.stem.replace('_mask', '')
            # Try different extensions
            for ext in ['.png', '.jpg', '.jpeg', '.tif', '.tiff']:
                annotated_names.add(f"{name}{ext}")
                annotated_names.add(f"{name}{ext.upper()}")

        # Find unannotated tiles
        unannotated = []
        for tile in self.available_tiles:
            if tile.name not in annotated_names:
                reason = "Not yet annotated"
                unannotated.append((tile, reason))

        # Sort by priority
        if priority == 'random':
            import random
            random.shuffle(unannotated)
        elif priority == 'center':
            # Assume tiles with lower numbers are more central
            # This is a simple heuristic - adjust based on your naming scheme
            unannotated.sort(key=lambda x: x[0].stem)
        else:  # 'name'
            unannotated.sort(key=lambda x: x[0].name)

        return unannotated

    def print_unannotated_tiles(self, priority: str = 'name', limit: int = 20):
        """Print list of unannotated tiles."""
        unannotated = self.list_unannotated_tiles(priority)

        if not unannotated:
            print("All available tiles have been annotated!")
            return

        print("UNANNOTATED TILES")
        print("-" * 60)
        print(f"Priority: {priority}")
        print(f"Showing {min(limit, len(unannotated))} of {len(unannotated)} unannotated tiles")
        print()

        for i, (tile, reason) in enumerate(unannotated[:limit], 1):
            print(f"  {i:3d}. {tile.name:40s} ({reason})")

        if len(unannotated) > limit:
            print(f"  ... and {len(unannotated) - limit} more")
        print()

    def export_report(self, output_path: str):
        """Export detailed progress report to file."""
        stats = self.calculate_statistics()

        with open(output_path, 'w') as f:
            f.write("ANNOTATION PROGRESS REPORT\n")
            f.write("=" * 60 + "\n")
            f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Annotations directory: {self.annotations_dir}\n")
            if self.tiles_dir:
                f.write(f"Tiles directory: {self.tiles_dir}\n")
            f.write("\n")

            # Statistics
            f.write("STATISTICS\n")
            f.write("-" * 60 + "\n")
            if stats['total_tiles'] > 0:
                f.write(f"Total tiles:       {stats['total_tiles']}\n")
                f.write(f"Annotated:         {stats['annotated_count']}\n")
                f.write(f"Remaining:         {stats['remaining_count']}\n")
                f.write(f"Completion:        {stats['completion_percentage']:.1f}%\n")
            else:
                f.write(f"Annotated:         {stats['annotated_count']}\n")
                f.write(f"Total tiles:       Unknown\n")
            f.write("\n")

            if stats['avg_time_per_tile']:
                f.write("TIME ESTIMATES\n")
                f.write("-" * 60 + "\n")
                f.write(f"Average time per tile: {self.format_time(stats['avg_time_per_tile'])}\n")
                if stats['estimated_remaining_time']:
                    f.write(f"Estimated remaining:   {self.format_time(stats['estimated_remaining_time'])}\n")
                f.write("\n")

            # Annotated tiles
            f.write("ANNOTATED TILES\n")
            f.write("-" * 60 + "\n")
            annotated_list = sorted(
                self.progress.get('last_modified', {}).items(),
                key=lambda x: x[1]
            )
            for tile_name, timestamp in annotated_list:
                dt = datetime.fromisoformat(timestamp)
                time_str = dt.strftime("%Y-%m-%d %H:%M")
                f.write(f"{time_str}  {tile_name}\n")
            f.write("\n")

            # Unannotated tiles
            if self.available_tiles:
                unannotated = self.list_unannotated_tiles()
                f.write("UNANNOTATED TILES\n")
                f.write("-" * 60 + "\n")
                for tile, reason in unannotated:
                    f.write(f"{tile.name}\n")
                f.write("\n")

        print(f"Report exported to: {output_path}")

    def validate_annotations(self) -> Dict:
        """Validate annotations and report any issues."""
        issues = {
            'missing_images': [],
            'missing_masks': [],
            'mismatched_sizes': [],
            'orphaned_masks': [],
        }

        # Check for missing corresponding files
        images_dir = self.annotations_dir / "images"

        for mask_path in self.annotated_tiles:
            # Find corresponding image
            image_name = mask_path.stem.replace('_mask', '') + mask_path.suffix.replace('_mask', '')
            # Try common extensions
            found = False
            for ext in ['.png', '.jpg', '.jpeg', '.tif', '.tiff']:
                for case_ext in [ext, ext.upper()]:
                    image_path = images_dir / (mask_path.stem.replace('_mask', '') + case_ext)
                    if image_path.exists():
                        found = True
                        # Check size match
                        from PIL import Image
                        try:
                            img = Image.open(image_path)
                            mask = Image.open(mask_path)
                            if img.size != mask.size:
                                issues['mismatched_sizes'].append(
                                    (str(image_path), str(mask_path), img.size, mask.size)
                                )
                        except Exception as e:
                            print(f"Warning: Could not validate {mask_path.name}: {e}")
                        break
                if found:
                    break

            if not found:
                issues['orphaned_masks'].append(str(mask_path))

        return issues

    def print_validation(self):
        """Print validation results."""
        print("VALIDATION")
        print("-" * 60)

        issues = self.validate_annotations()

        total_issues = sum(len(v) for v in issues.values())

        if total_issues == 0:
            print("  ✓ All annotations valid")
            print()
            return

        print(f"  Found {total_issues} issue(s):")
        print()

        if issues['orphaned_masks']:
            print(f"  Orphaned masks (no corresponding image):")
            for mask in issues['orphaned_masks'][:5]:
                print(f"    - {Path(mask).name}")
            if len(issues['orphaned_masks']) > 5:
                print(f"    ... and {len(issues['orphaned_masks']) - 5} more")
            print()

        if issues['mismatched_sizes']:
            print(f"  Size mismatches:")
            for img, mask, img_size, mask_size in issues['mismatched_sizes'][:5]:
                print(f"    - {Path(img).name}: {img_size} vs {mask_size}")
            if len(issues['mismatched_sizes']) > 5:
                print(f"    ... and {len(issues['mismatched_sizes']) - 5} more")
            print()


def main():
    parser = argparse.ArgumentParser(
        description='Track annotation progress for historical map tiles'
    )

    parser.add_argument(
        '--annotations-dir',
        required=True,
        help='Directory containing annotations (with progress.json)'
    )

    parser.add_argument(
        '--tiles-dir',
        help='Directory containing all available tiles (for calculating completion %)'
    )

    parser.add_argument(
        '--export',
        help='Export detailed report to file'
    )

    parser.add_argument(
        '--list-unannotated',
        action='store_true',
        help='List tiles that need annotation'
    )

    parser.add_argument(
        '--priority',
        choices=['name', 'random', 'center'],
        default='name',
        help='Priority sorting for unannotated tiles (default: name)'
    )

    parser.add_argument(
        '--limit',
        type=int,
        default=20,
        help='Maximum number of unannotated tiles to show (default: 20)'
    )

    parser.add_argument(
        '--validate',
        action='store_true',
        help='Validate annotations for issues'
    )

    args = parser.parse_args()

    # Validate inputs
    annotations_dir = Path(args.annotations_dir)
    if not annotations_dir.exists():
        print(f"Error: Annotations directory does not exist: {annotations_dir}")
        sys.exit(1)

    if args.tiles_dir:
        tiles_dir = Path(args.tiles_dir)
        if not tiles_dir.exists():
            print(f"Error: Tiles directory does not exist: {tiles_dir}")
            sys.exit(1)

    # Create progress tracker
    try:
        tracker = AnnotationProgress(
            annotations_dir=args.annotations_dir,
            tiles_dir=args.tiles_dir
        )

        # Print statistics
        tracker.print_statistics()

        # List unannotated tiles if requested
        if args.list_unannotated:
            tracker.print_unannotated_tiles(
                priority=args.priority,
                limit=args.limit
            )

        # Validate if requested
        if args.validate:
            tracker.print_validation()

        # Export report if requested
        if args.export:
            tracker.export_report(args.export)

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
