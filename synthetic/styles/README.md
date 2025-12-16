# Historical Map Styles

This directory contains MapLibre GL style definitions that mimic historical Norwegian cartography from different eras. These styles are designed for generating synthetic training data for machine learning models.

## Available Styles

### 1. Military Survey Map 1880 (`military_1880.json`)

Mimics Norwegian military survey maps from the 1880s.

**Characteristics:**
- **Color Palette**: Muted earth tones (beige/tan backgrounds)
- **Background**: Light cream/beige (#e8e0d0)
- **Buildings**: Solid dark fills (#3d3530), no outline glow, dense appearance
- **Roads**: Brown/tan lines (#a89578 to #7a6542), varying width by class
- **Water**: Steel blue (#5f7a8a) with fine hatching pattern effect
- **Forests**: Stippled green pattern (#a8c3a0), semi-transparent
- **Typography**: Serif font, uppercase for cities
- **Appearance**: Hand-drawn, somewhat rough style

**Best for**: Extracting buildings and major roads from military cartographic sources

### 2. Cadastral Map 1900 (`cadastral_1900.json`)

Mimics Norwegian property/cadastral maps from around 1900.

**Characteristics:**
- **Color Palette**: Clean, technical colors
- **Background**: Very light cream (#faf8f5)
- **Buildings**: Traditional cadastral pink/red fills (#e6b8b8) with darker outlines (#b08080)
- **Roads**: Simple black lines (#3a3a3a to #1a1a1a), no styling
- **Water**: Light blue (#c5e3f0) with subtle outlines
- **Property Boundaries**: Emphasized with dashed lines
- **Typography**: Sans-serif, clean appearance
- **Appearance**: Precise, technical, emphasizes boundaries

**Best for**: Property boundary detection, precise building extraction

### 3. Topographic Map 1920 (`topographic_1920.json`)

Mimics Norwegian topographic maps from the 1920s.

**Characteristics:**
- **Color Palette**: Natural tones with red highways
- **Background**: Off-white (#f5f3ed)
- **Buildings**: Black outlines (#2a2520) with light fill (#d8d0c0)
- **Roads**: Red for main roads (#c84030), black for minor roads (#1a1510)
- **Water**: Blue (#b8d9e8) with distinct shore lines (#5a8ca8)
- **Forests/Vegetation**: Light green tints (#d5e5c8)
- **Contours**: Visual emphasis on terrain representation
- **Typography**: Bold sans-serif for cities, italic for water features
- **Appearance**: Contour-like, emphasizes topography

**Best for**: Road classification, terrain feature extraction

## Using the Styles

### Direct Usage

Load any style in a MapLibre GL application:

```javascript
const map = new maplibregl.Map({
  container: 'map',
  style: 'styles/military_1880.json',
  center: [10.4, 63.43], // Trondheim
  zoom: 12
});
```

### Generating Variations

Use the `generate_styles.py` script to create color variations for domain randomization:

```bash
# Generate a single variation
python ../generate_styles.py military_1880.json \
  --palette military_1880 \
  --variation 0.1 \
  --output military_1880_var001.json

# Generate 20 variations
python ../generate_styles.py military_1880.json \
  --palette military_1880 \
  --variation 0.15 \
  --output-dir ./variations/ \
  --count 20
```

**Variation parameters:**
- `--variation 0.05`: Very subtle changes (5% color variation)
- `--variation 0.1`: Moderate changes (10%, default)
- `--variation 0.2`: Significant changes (20%, good for training diversity)

### Batch Generation for All Styles

Generate variations for all three base styles:

```bash
# Military style variations
python ../generate_styles.py military_1880.json \
  --palette military_1880 \
  --output-dir ./variations/military/ \
  --count 10

# Cadastral style variations
python ../generate_styles.py cadastral_1900.json \
  --palette cadastral_1900 \
  --output-dir ./variations/cadastral/ \
  --count 10

# Topographic style variations
python ../generate_styles.py topographic_1920.json \
  --palette topographic_1920 \
  --output-dir ./variations/topographic/ \
  --count 10
```

## Style Architecture

All styles follow the OpenMapTiles schema and include layers for:

1. **Background**: Base map color
2. **Water**: Polygons for water bodies
3. **Waterway**: Lines for rivers and streams
4. **Landuse**: Forest, grass, residential areas
5. **Building**: Building footprints
6. **Transportation**: Roads, railways with classification
7. **Boundaries**: Administrative boundaries
8. **Labels**: Place names, road names

## Technical Notes

### Vector Tile Source

All styles expect a vector tile source named `openmaptiles` following the OpenMapTiles schema. Update the source URL to match your tile server:

```json
"sources": {
  "openmaptiles": {
    "type": "vector",
    "url": "http://localhost:8080/data/trondheim.pmtiles"
  }
}
```

### Zoom Levels

Styles are optimized for zoom levels:
- **8-12**: Overview, major features
- **13-16**: City detail, buildings appear
- **17-20**: Street level detail

### Missing Patterns

Some layers reference fill patterns (e.g., `water_hatching`, `forest_stipple`) that are currently placeholders. For production use, either:

1. Remove pattern layers
2. Provide actual pattern sprites
3. Replace with alternative rendering (opacity, dashed lines)

## Color Palettes

Each style has an associated color palette in `generate_styles.py` for programmatic variation. View all palettes:

```bash
python ../generate_styles.py --palette-reference
```

This creates `palette_reference.json` with all available colors.

## Historical Accuracy

These styles are approximations based on:
- Norwegian Mapping Authority (Kartverket) historical maps
- Statens Kartverk military survey maps (1880s-1920s)
- Traditional European cadastral cartography conventions
- Topographic map standards from early 20th century

Colors and styling choices are informed by actual historical maps but simplified for vector rendering and ML training purposes.

## License

These style definitions are released under MIT License. Note that:
- Base map data (OSM) is ODbL licensed
- Historical map sources may have different licenses
- Generated training data inherits source data licenses

## Further Reading

- [MapLibre GL Style Specification](https://maplibre.org/maplibre-style-spec/)
- [OpenMapTiles Schema](https://openmaptiles.org/schema/)
- [Kartverket Historical Maps](https://www.kartverket.no/en/about-kartverket/history)
