# Annotation Quick Start Guide

## Setup (One Time)

```bash
# 1. Ensure dependencies are installed
cd /Users/vaskinn/Development/private/historymap
pip install -r ml/requirements.txt

# 2. Install tkinter if needed (macOS)
brew install python-tk

# 3. Prepare your tiles directory
mkdir -p data/kartverket/tiles
# Copy your historical map tiles here
```

## Annotation Workflow

### Start Annotating

```bash
cd scripts

# With a trained model (recommended):
python annotation_helper.py \
    --tiles-dir ../data/kartverket/tiles/ \
    --output-dir ../data/annotations/ \
    --model ../models/checkpoints/best_model.pth

# Without a model (blank masks):
python annotation_helper.py \
    --tiles-dir ../data/kartverket/tiles/ \
    --output-dir ../data/annotations/
```

### Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `1` | Background (transparent) |
| `2` | Building (red) |
| `3` | Road (yellow) |
| `4` | Water (blue) |
| `5` | Forest (green) |
| `A` | Previous tile |
| `D` | Next tile |
| `S` | Save & advance |
| `E` | Reset to prediction |
| `M` | Toggle mask overlay |
| `Q` | Quit |

### Workflow

1. **Load tile** - Tool starts with first unannotated tile
2. **Review prediction** - If model is loaded, see initial prediction
3. **Select class** - Press 1-5 or click class button
4. **Paint corrections** - Click and drag to paint
5. **Adjust brush** - Use slider to change brush size
6. **Save** - Press S or click Save button (auto-advances to next)
7. **Repeat** - Continue until 30-50 tiles are annotated

## Check Progress

```bash
# View statistics
python annotation_progress.py --annotations-dir ../data/annotations/

# With completion percentage
python annotation_progress.py \
    --annotations-dir ../data/annotations/ \
    --tiles-dir ../data/kartverket/tiles/

# List next tiles to annotate
python annotation_progress.py \
    --annotations-dir ../data/annotations/ \
    --tiles-dir ../data/kartverket/tiles/ \
    --list-unannotated --limit 10

# Export report
python annotation_progress.py \
    --annotations-dir ../data/annotations/ \
    --tiles-dir ../data/kartverket/tiles/ \
    --export progress_report.txt
```

## Tips

### Quality Annotations

- **Trace accurately** - Follow building edges carefully
- **Be consistent** - Use same class for similar features
- **Include all features** - Don't skip small buildings or roads
- **Check edges** - Building/road boundaries should be clean

### Efficient Workflow

1. **Start with model** - Let model do initial work
2. **Learn shortcuts** - Use keyboard for speed
3. **Focus first** - Annotate buildings first (easiest)
4. **Vary locations** - Mix city/suburb/rural tiles
5. **Take breaks** - 30-60 min sessions maintain quality

### Time Budget

- **Simple tile**: 2-5 minutes
- **Medium tile**: 5-10 minutes
- **Complex tile**: 10-20 minutes
- **Target**: 30-50 tiles = 5-15 hours total

## Troubleshooting

### GUI won't start
```bash
# Check if tkinter is installed
python3 -c "import tkinter; print('OK')"

# Install if needed
brew install python-tk  # macOS
sudo apt-get install python3-tk  # Ubuntu
```

### Model not loading
- Check model path is correct
- Verify model was trained with same architecture
- Can proceed without model (blank masks)

### Can't see changes
- Check mask visibility is enabled (press M)
- Adjust opacity slider
- Verify brush size isn't too small

## Output Files

After annotation:

```
data/annotations/
├── progress.json              # Tracking
├── images/                    # Original tiles
│   ├── tile_001.png
│   └── ...
└── masks/                     # Annotations (0-4 values)
    ├── tile_001_mask.png
    └── ...
```

## Next Steps

After annotating 30-50 tiles:

1. **Fine-tune model**:
   ```bash
   cd ../ml
   python train.py --config config.yaml \
       --fine-tune \
       --checkpoint checkpoints/best_model.pth \
       --real-data ../data/annotations/
   ```

2. **Process all tiles**:
   ```bash
   python predict.py \
       --checkpoint checkpoints/fine_tuned_model.pth \
       --input-dir ../data/kartverket/tiles/ \
       --output-dir ../data/predictions/
   ```

3. **Vectorize results**:
   ```bash
   python vectorize.py \
       --input-dir ../data/predictions/ \
       --output trondheim_1900.geojson
   ```

## Resources

- Full documentation: `ANNOTATION_README.md`
- Project plan: `../HISTORICAL_MAP_PROJECT_PLAN.md`
- ML documentation: `../ml/README.md`
