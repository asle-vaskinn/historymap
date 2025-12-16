# Historical Map Styles - Quick Start Guide

Get started with the historical Norwegian map styles in 5 minutes.

## What's Included

✅ **3 Historical Map Styles**
- `military_1880.json` - Norwegian military survey maps (1880s)
- `cadastral_1900.json` - Property/cadastral maps (1900s)
- `topographic_1920.json` - Topographic maps (1920s)

✅ **Style Generation Script**
- `../generate_styles.py` - Create color variations for training

✅ **Documentation**
- `README.md` - Full documentation
- `STYLE_COMPARISON.md` - Detailed comparison
- `example_usage.sh` - Example script

## Quick Test

Verify everything works:

```bash
cd /Users/vaskinn/Development/private/historymap/synthetic
python3 test_styles.py
```

Expected output: ✓ All historical styles are valid!

## Basic Usage

### 1. Use a Style in MapLibre GL

```javascript
const map = new maplibregl.Map({
  container: 'map',
  style: 'styles/military_1880.json',
  center: [10.4, 63.43],  // Trondheim
  zoom: 12
});
```

### 2. Generate a Single Variation

```bash
python3 generate_styles.py styles/military_1880.json \
  --palette military_1880 \
  --variation 0.15 \
  --output my_variation.json
```

### 3. Generate Training Dataset Variations

```bash
# Generate 20 variations of each style
python3 generate_styles.py styles/military_1880.json \
  --palette military_1880 \
  --output-dir variations/military \
  --count 20 \
  --variation 0.15

python3 generate_styles.py styles/cadastral_1900.json \
  --palette cadastral_1900 \
  --output-dir variations/cadastral \
  --count 20 \
  --variation 0.15

python3 generate_styles.py styles/topographic_1920.json \
  --palette topographic_1920 \
  --output-dir variations/topographic \
  --count 20 \
  --variation 0.15
```

Result: 60 total style variations ready for ML training!

## Which Style Should I Use?

### For Building Extraction
→ Use **military_1880.json**
- High contrast dark buildings
- Simple, solid fills
- Best for dense urban areas

### For Property Boundaries
→ Use **cadastral_1900.json**
- Traditional cadastral pink buildings
- Clear boundary emphasis
- Precise technical appearance

### For Multi-Feature Extraction
→ Use **topographic_1920.json**
- Red main roads (easy to detect)
- Outlined buildings
- Best overall feature variety

## Next Steps

1. **Test the styles** - Run test_styles.py
2. **Generate variations** - Run example_usage.sh
3. **Read the comparison** - See STYLE_COMPARISON.md
4. **Integrate with rendering** - Use with render_tiles.py

## Integration with Phase 2 Pipeline

These styles are designed to work with the synthetic data generation pipeline:

```bash
# Generate synthetic training images
cd /Users/vaskinn/Development/private/historymap/synthetic

# Use a historical style
python3 render_tiles.py \
  --style styles/military_1880.json \
  --output-dir data/synthetic/images

# Generate ground truth masks
python3 create_masks.py \
  --output-dir data/synthetic/masks

# Apply aging effects
python3 age_effects.py \
  --input-dir data/synthetic/images \
  --output-dir data/synthetic/aged
```

## Style Variation Parameters

| Variation | Use Case | Example |
|-----------|----------|---------|
| 0.05 | Very subtle, period-accurate | Testing |
| 0.10 | Moderate changes | Default |
| 0.15 | Good diversity | **Recommended for training** |
| 0.20 | High variation | Domain randomization |
| 0.25+ | Extreme changes | Robustness testing |

## Common Issues

### Style doesn't load in MapLibre

**Problem:** Source URL is incorrect

**Solution:** Update the source URL in the style JSON:
```json
"sources": {
  "openmaptiles": {
    "type": "vector",
    "url": "YOUR_TILE_SERVER_URL_HERE"
  }
}
```

### Colors look wrong

**Problem:** Variation factor too high

**Solution:** Use variation between 0.10-0.15 for historical accuracy

### Missing patterns

**Problem:** Some layers reference fill patterns that don't exist

**Solution:** Either:
1. Remove pattern layers from the style
2. Provide sprite sheets with patterns
3. Replace with solid fills

## File Structure

```
synthetic/
├── styles/
│   ├── military_1880.json          ← Base style
│   ├── cadastral_1900.json         ← Base style
│   ├── topographic_1920.json       ← Base style
│   ├── README.md                   ← Full docs
│   ├── STYLE_COMPARISON.md         ← Detailed comparison
│   ├── QUICKSTART.md               ← This file
│   └── example_usage.sh            ← Example script
├── generate_styles.py              ← Variation generator
├── test_styles.py                  ← Validation script
└── variations/                     ← Generated variations
    ├── military/
    ├── cadastral/
    └── topographic/
```

## Examples

### Example 1: Generate 10 variations with different seeds

```bash
for i in {1..10}; do
  python3 generate_styles.py styles/military_1880.json \
    --palette military_1880 \
    --variation 0.15 \
    --seed $i \
    --output variations/military_var_${i}.json
done
```

### Example 2: View palette colors

```bash
python3 generate_styles.py --palette-reference
cat palette_reference.json
```

### Example 3: Run the example script

```bash
cd styles/
./example_usage.sh
```

This generates 20 total variations (2 examples + 15 training + 3 base styles).

## Resources

- [MapLibre GL Style Spec](https://maplibre.org/maplibre-style-spec/)
- [OpenMapTiles Schema](https://openmaptiles.org/schema/)
- [Historical Map Project Plan](../../HISTORICAL_MAP_PROJECT_PLAN.md)

## Support

For issues or questions:
1. Check STYLE_COMPARISON.md for style details
2. Run test_styles.py to validate files
3. Review the project plan for context

## License

MIT License - See project root for details

---

**Ready to start?** Run `python3 test_styles.py` to verify your setup!
