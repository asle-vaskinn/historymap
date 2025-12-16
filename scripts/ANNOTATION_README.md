# Annotation Tools - Phase 4

Interactive tools for manually annotating historical map tiles to create training data for fine-tuning the segmentation model.

## Overview

These tools help you create 30-50 high-quality training examples by:
1. Loading historical map tiles
2. Running ML predictions as a starting point
3. Allowing manual corrections with an easy-to-use GUI
4. Tracking progress and estimating time remaining

## Files

- `annotation_helper.py` - Interactive annotation GUI tool
- `annotation_progress.py` - Progress tracking and reporting

## Installation

The annotation tools require a few additional dependencies:

```bash
# Install tkinter (if not already installed)
# On macOS:
brew install python-tk

# On Ubuntu/Debian:
sudo apt-get install python3-tk

# On other systems, tkinter usually comes with Python
```

All other dependencies are already included in the project requirements.

## Quick Start

### 1. Prepare Your Tiles

Place historical map tiles in a directory (e.g., `../data/kartverket/tiles/`):

```bash
cd data/kartverket
# Download or copy your historical map tiles here
ls tiles/
# tile_001.png
# tile_002.png
# ...
```

### 2. Run the Annotation Helper

```bash
cd scripts

# With a trained model (recommended - starts with predictions):
python annotation_helper.py \
    --tiles-dir ../data/kartverket/tiles/ \
    --output-dir ../data/annotations/ \
    --model ../models/checkpoints/best_model.pth

# Without a model (starts with blank masks):
python annotation_helper.py \
    --tiles-dir ../data/kartverket/tiles/ \
    --output-dir ../data/annotations/
```

### 3. Annotate Tiles

Use the GUI to label features:

**Keyboard Shortcuts:**
- `1` - Select background class
- `2` - Select building class (red)
- `3` - Select road class (yellow)
- `4` - Select water class (blue)
- `5` - Select forest class (green)
- `A` - Previous tile
- `D` - Next tile
- `S` - Save annotation
- `E` - Reset to model prediction (eraser)
- `M` - Toggle mask visibility
- `Q` - Quit

**Mouse Controls:**
- Click and drag to paint
- Use slider to adjust brush size
- Click "Reset" to start over on current tile

**Workflow:**
1. Load a tile (automatically shows model prediction if available)
2. Select a class (1-5)
3. Paint corrections over any errors
4. Save (automatically advances to next tile)
5. Repeat!

### 4. Track Progress

Check your annotation progress at any time:

```bash
# Basic statistics
python annotation_progress.py --annotations-dir ../data/annotations/

# With completion percentage
python annotation_progress.py \
    --annotations-dir ../data/annotations/ \
    --tiles-dir ../data/kartverket/tiles/

# List unannotated tiles
python annotation_progress.py \
    --annotations-dir ../data/annotations/ \
    --tiles-dir ../data/kartverket/tiles/ \
    --list-unannotated \
    --priority center \
    --limit 10

# Export detailed report
python annotation_progress.py \
    --annotations-dir ../data/annotations/ \
    --tiles-dir ../data/kartverket/tiles/ \
    --export progress_report.txt

# Validate annotations
python annotation_progress.py \
    --annotations-dir ../data/annotations/ \
    --validate
```

## GUI Features

### Navigation
- **Next/Previous buttons** - Move between tiles
- **Go to...** - Jump to specific tile number
- **Progress indicator** - Shows current tile number

### Drawing Tools
- **Class selection** - 5 classes with color coding
- **Brush size slider** - Adjust from 1-50 pixels
- **Eraser** - Reset area to original prediction
- **Reset button** - Start over on current tile

### View Controls
- **Show/hide mask** - Toggle overlay visibility
- **Opacity slider** - Adjust mask transparency (0-100%)

### Auto-Save
- Annotations are saved to `data/annotations/masks/`
- Original tiles are copied to `data/annotations/images/`
- Progress is tracked in `data/annotations/progress.json`

## Output Structure

After annotation, your output directory will look like:

```
data/annotations/
├── progress.json              # Tracking file
├── images/                    # Copies of annotated tiles
│   ├── tile_001.png
│   ├── tile_002.png
│   └── ...
└── masks/                     # Annotation masks
    ├── tile_001_mask.png
    ├── tile_002_mask.png
    └── ...
```

### Mask Format

- PNG images (grayscale)
- Pixel values 0-4 represent classes:
  - `0` - Background
  - `1` - Building
  - `2` - Road
  - `3` - Water
  - `4` - Forest

## Tips for Efficient Annotation

### 1. Start with Model Predictions
If you have a trained model (even from synthetic data), use it! The model predictions provide a good starting point, and you only need to correct errors.

### 2. Focus on Buildings First
Buildings are usually the clearest features and easiest to annotate. Start with 10-15 building-focused tiles before moving to roads or other features.

### 3. Select Diverse Tiles
Annotate tiles from different areas:
- City center (dense buildings)
- Suburbs (scattered buildings)
- Rural areas (sparse features)
- Different map styles or eras

### 4. Quality Over Quantity
30-50 high-quality annotations are better than 100 rushed ones. Take your time to:
- Trace building edges accurately
- Label complete road networks
- Include all visible water bodies

### 5. Use Keyboard Shortcuts
Learn the keyboard shortcuts (1-5 for classes, A/D for navigation, S for save) to speed up your workflow significantly.

### 6. Take Breaks
Annotating is tedious work. Take breaks every 30-60 minutes to maintain quality.

## Time Estimates

Based on typical annotation tasks:

- **Simple tile** (few buildings): 2-5 minutes
- **Medium tile** (city block): 5-10 minutes
- **Complex tile** (dense city): 10-20 minutes

**For 30-50 tiles:** Budget 5-15 hours total annotation time over multiple sessions.

The progress tracker will estimate remaining time based on your actual annotation rate.

## Troubleshooting

### "No module named 'tkinter'"

Install tkinter for your platform:

```bash
# macOS
brew install python-tk

# Ubuntu/Debian
sudo apt-get install python3-tk

# Windows
# Tkinter is usually included with Python
```

### "Model file not found"

If you haven't trained a model yet, you can still annotate:

```bash
# Run without --model flag
python annotation_helper.py \
    --tiles-dir ../data/kartverket/tiles/ \
    --output-dir ../data/annotations/
```

This will start with blank masks instead of predictions.

### GUI is too small/large

The canvas size adapts to your tile size. If tiles are very large, they may extend beyond the screen. Consider:
1. Resizing tiles before annotation (e.g., 512x512 or 1024x1024)
2. Using a larger monitor
3. The canvas supports scrolling for large images

### Accidentally saved wrong annotation

Simply navigate back to that tile and re-annotate it. The save will overwrite the previous annotation.

## Next Steps

After completing annotations:

1. **Fine-tune the model:**
   ```bash
   cd ../ml
   python train.py \
       --config config.yaml \
       --fine-tune \
       --checkpoint checkpoints/best_model.pth \
       --data ../data/annotations/
   ```

2. **Evaluate on annotated data:**
   ```bash
   python evaluate.py \
       --checkpoint checkpoints/fine_tuned_model.pth \
       --data-dir ../data/annotations/
   ```

3. **Process historical maps:**
   ```bash
   python predict.py \
       --checkpoint checkpoints/fine_tuned_model.pth \
       --input-dir ../data/kartverket/tiles/ \
       --output-dir ../data/predictions/
   ```

## Progress Tracking Features

The `annotation_progress.py` tool provides:

### Statistics
- Total tiles available
- Number annotated
- Remaining tiles
- Completion percentage

### Time Estimates
- Average time per tile
- Estimated time remaining
- Annotation rate (tiles/hour)

### Prioritization
Choose which tiles to annotate next:
- `--priority name` - Alphabetical order
- `--priority center` - Assumes lower numbers = more central
- `--priority random` - Random order for variety

### Validation
- Check for missing images/masks
- Verify size mismatches
- Find orphaned files

## Class Definitions

| Class | ID | Color | Description | Keyboard |
|-------|----|----|-------------|----------|
| Background | 0 | Transparent | Everything else | `1` |
| Building | 1 | Red | Houses, structures | `2` |
| Road | 2 | Yellow | Roads, paths, streets | `3` |
| Water | 3 | Blue | Rivers, lakes, ocean | `4` |
| Forest | 4 | Green | Wooded areas | `5` |

## Advanced Usage

### Batch Processing Multiple Directories

If you have tiles organized by era or region:

```bash
# Process each directory
for dir in tiles_1900 tiles_1920 tiles_1950; do
    python annotation_helper.py \
        --tiles-dir ../data/kartverket/$dir/ \
        --output-dir ../data/annotations/$dir/ \
        --model ../models/checkpoints/best_model.pth
done
```

### Custom Model Size

If your tiles are a different size than what the model was trained on, the tool will automatically resize during inference and back for saving.

### Exporting for Other Tools

The mask format (grayscale PNG with values 0-4) is compatible with most annotation and training tools. You can:

1. Import into QGIS for further editing
2. Use with other ML frameworks
3. Convert to COCO format if needed

## FAQ

**Q: How many tiles should I annotate?**
A: Start with 30. If model performance is good, you're done. If not, annotate 10-20 more focused on problem areas.

**Q: Can I annotate in multiple sessions?**
A: Yes! Progress is saved automatically. Just restart the tool and it will remember where you left off.

**Q: Can multiple people annotate?**
A: Yes, but avoid concurrent annotation of the same tiles. Use `--list-unannotated --priority random` to assign different tiles to different annotators.

**Q: What if I disagree with the model prediction?**
A: That's exactly why we're annotating! Paint over any errors with the correct class. That's what fine-tuning is for.

**Q: Should I annotate every single building?**
A: Yes, for best results. But if a building is very small or unclear in the historical map, it's okay to skip it (leave as background).

**Q: Can I change annotations later?**
A: Yes, just navigate back to that tile and re-annotate. Save will overwrite.

## Support

For issues or questions:
1. Check this README
2. Review the project plan: `../HISTORICAL_MAP_PROJECT_PLAN.md`
3. Check model documentation: `../ml/README.md`

Happy annotating!
