# Trondheim Historical Map

> An interactive web application for exploring the historical development of Trondheim, Norway, from 1850 to the present day.

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.11+-green.svg)
![MapLibre](https://img.shields.io/badge/maplibre-3.x-orange.svg)

[Live Demo](#) | [Documentation](docs/) | [Methodology](docs/methodology.md) | [User Guide](docs/user_guide.md)

## Overview

The Trondheim Historical Map is an interactive web-based system that visualizes the evolution of the Trondheim region over nearly 175 years. Using a combination of modern OpenStreetMap data and machine learning-extracted features from historical maps, you can travel through time and see how buildings, roads, railways, and other features appeared and changed.

### Key Features

- **Time Travel Interface**: Interactive slider to explore any year from 1850 to present
- **Multi-Source Data**: Combines modern OpenStreetMap with historical Kartverket maps
- **Machine Learning**: Automated feature extraction from historical map images
- **High Performance**: Efficient PMTiles format for instant tile delivery
- **Mobile Friendly**: Fully responsive design works on all devices
- **Open Source**: Complete pipeline from data to deployment

### Coverage

**Geographic Area**: Trondheim++ region (~3,000 km²)
- Trondheim
- Malvik, Stjørdal, Meråker
- Melhus, Skaun, Klæbu

**Temporal Range**: 1850 - 2025

**Features Extracted**:
- Buildings and structures
- Road network
- Railway lines
- Water bodies
- Land use patterns

## Quick Start

### Option 1: Docker (Recommended)

```bash
# Clone the repository
git clone https://github.com/yourusername/historymap.git
cd historymap

# Download OSM data
./scripts/download_osm.sh

# Generate tiles (if not already available)
./scripts/generate_tiles.sh

# Start the application
docker-compose up

# Open in browser
open http://localhost:8080
```

### Option 2: Local Development

```bash
# Navigate to frontend
cd frontend

# Start a local server
python3 -m http.server 8080

# Open in browser
open http://localhost:8080
```

### Option 3: Production Deployment

```bash
# Build production Docker image
docker-compose -f production/docker-compose.prod.yml build

# Run production container
docker-compose -f production/docker-compose.prod.yml up -d

# Or deploy to GitHub Pages
./production/deploy-github-pages.sh

# Or deploy to Cloudflare R2
./production/deploy-cloudflare.sh
```

## Documentation

Comprehensive documentation is available in the `docs/` directory:

- **[User Guide](docs/user_guide.md)** - How to use the map interface
- **[Methodology](docs/methodology.md)** - Technical details of the ML pipeline
- **[Data Sources](docs/data_sources.md)** - Data attribution and licensing
- **[Project Plan](HISTORICAL_MAP_PROJECT_PLAN.md)** - Complete development roadmap

## Project Structure

```
historymap/
├── frontend/              # Web application
│   ├── index.html        # Main page
│   ├── app.js           # Map logic and time slider
│   └── style.css        # Styling
├── synthetic/            # Synthetic data generation (Phase 2)
│   ├── styles/          # Historical map styles
│   ├── render_tiles.py  # Map rendering
│   └── age_effects.py   # Aging simulation
├── ml/                   # Machine learning pipeline (Phase 3)
│   ├── model.py         # U-Net architecture
│   ├── train.py         # Training script
│   ├── predict.py       # Inference
│   └── vectorize.py     # Raster to vector conversion
├── scripts/              # Utility scripts (Phase 4)
│   ├── download_osm.sh           # Get OSM data
│   ├── download_kartverket.py    # Get historical maps
│   ├── georeference.py           # Align maps
│   └── annotation_helper.py      # Manual annotation tool
├── production/           # Deployment infrastructure (Phase 5)
│   ├── Dockerfile               # Production container
│   ├── docker-compose.prod.yml  # Production compose
│   ├── deploy-github-pages.sh   # GitHub Pages deployment
│   └── deploy-cloudflare.sh     # Cloudflare R2 deployment
├── docs/                 # Documentation
│   ├── user_guide.md
│   ├── methodology.md
│   └── data_sources.md
└── data/                 # Map data and tiles
    ├── trondheim.osm.pbf      # OSM extract
    ├── trondheim.pmtiles      # Generated tiles
    └── kartverket/            # Historical maps
```

## Development Phases

This is a multi-phase project. Each phase builds on the previous:

| Phase | Status | Description |
|-------|--------|-------------|
| **Phase 1** | ✅ Complete | Infrastructure + Frontend - Working map viewer |
| **Phase 2** | ✅ Complete | Synthetic Data Pipeline - Training data generation |
| **Phase 3** | ✅ Complete | ML Training - U-Net segmentation model |
| **Phase 4** | ✅ Complete | Real Data Integration - Historical map processing |
| **Phase 5** | ✅ Complete | Production - Deployment infrastructure |

See [HISTORICAL_MAP_PROJECT_PLAN.md](HISTORICAL_MAP_PROJECT_PLAN.md) for detailed phase descriptions.

## Technology Stack

### Frontend
- **MapLibre GL JS** - Open-source map rendering
- **PMTiles** - Serverless vector tiles
- **Vanilla JavaScript** - No framework dependencies
- **Responsive CSS** - Mobile-first design

### Backend / Data Processing
- **Python 3.11+** - Data processing and ML
- **PyTorch** - Machine learning framework
- **GDAL/Rasterio** - Geospatial data handling
- **Pillow** - Image processing
- **NumPy/Pandas** - Data manipulation

### Infrastructure
- **Docker** - Containerization
- **Nginx** - Web server (production)
- **GitHub Pages** - Static hosting option
- **Cloudflare R2** - Tile storage option

### Machine Learning
- **U-Net** - Segmentation architecture
- **ResNet34** - Encoder backbone (pretrained)
- **segmentation_models_pytorch** - Model implementation
- **Albumentations** - Data augmentation

## Data Sources and Attribution

### Modern Data
**OpenStreetMap contributors**
- License: Open Database License (ODbL)
- © OpenStreetMap contributors
- https://www.openstreetmap.org/copyright

### Historical Maps
**Kartverket** (Norwegian Mapping Authority)
- License: CC BY 4.0 (maps <100 years) / Public Domain (maps >100 years)
- © Kartverket
- https://www.kartverket.no/

See [docs/data_sources.md](docs/data_sources.md) for complete attribution details.

## Machine Learning Pipeline

The project uses a sophisticated ML pipeline to extract features from historical maps:

1. **Synthetic Data Generation**: Modern OSM data styled to look historical
2. **U-Net Training**: Semantic segmentation on synthetic data
3. **Manual Annotation**: 30-50 real historical map tiles
4. **Fine-Tuning**: Transfer learning on real annotated data
5. **Batch Processing**: Extract all historical map features
6. **Vectorization**: Convert predictions to vector geometries

**Model Performance**:
- Buildings: 70-85% IoU
- Roads: 60-80% IoU
- Water: 80-95% IoU

See [docs/methodology.md](docs/methodology.md) for technical details.

## Deployment Options

### 1. GitHub Pages (Free, Simple)
```bash
./production/deploy-github-pages.sh
```
- Zero cost for hosting
- Works for tiles <100MB
- Use Git LFS for larger files

### 2. Cloudflare R2 (Scalable)
```bash
./production/deploy-cloudflare.sh
```
- Store large PMTiles in R2
- Free tier: 10GB storage
- Global CDN delivery

### 3. Self-Hosted Docker (Full Control)
```bash
docker-compose -f production/docker-compose.prod.yml up -d
```
- Run on any server (VPS, cloud, local)
- Complete control over infrastructure
- Resource limits and health checks configured

See deployment scripts for detailed instructions.

## Contributing

This is a personal project, but contributions are welcome!

### How to Contribute

1. **Report Issues**: Found a bug or incorrect data? Open an issue
2. **Improve Annotations**: Help annotate historical maps
3. **Add Historical Maps**: Know of additional map sources? Let us know
4. **Code Improvements**: Submit pull requests for features or fixes

### Development Setup

```bash
# Clone repository
git clone https://github.com/yourusername/historymap.git
cd historymap

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows

# Install dependencies
pip install -r requirements.txt

# Install ML dependencies (if working on Phase 3)
pip install -r ml/requirements.txt

# Run validation
./scripts/validate_phase1.sh
```

### Code Style
- Python: PEP 8
- JavaScript: StandardJS style
- Comments: Explain "why", not "what"
- Error handling: Extensive logging and user feedback

## Validation

Validate your setup with included scripts:

```bash
# Phase 1: Frontend and data
./scripts/validate_phase1.sh

# Phase 2: Synthetic data pipeline
./synthetic/validate_synthetic.sh

# Phase 3: ML training
./ml/validate_model.sh

# Phase 5: Production deployment
./production/validate_phase5.sh
```

## Performance

### Frontend
- **Initial load**: ~500KB-2MB (depends on tile size)
- **Tile loading**: <100ms per tile
- **Time slider**: 60 FPS smooth animation
- **Mobile**: Optimized for 3G+ connections

### Backend
- **Tile generation**: ~5-10 minutes for full region
- **ML inference**: ~10 images/second on RTX 3060
- **Docker image**: ~50MB (nginx:alpine based)

## Browser Support

- ✅ Chrome/Edge 79+
- ✅ Firefox 70+
- ✅ Safari 13.1+
- ✅ Mobile browsers (iOS Safari, Chrome Mobile)
- ⚠️ Requires WebGL support

## Known Limitations

### Data Coverage
- Not all years have available historical maps
- Some rural areas have limited historical documentation
- Temporal accuracy depends on source map metadata

### ML Accuracy
- Building detection: 70-85% accurate
- Road detection: 60-80% accurate
- Small features may be missed
- Complex geometries simplified

### Geographic Accuracy
- Historical maps: ±5-100m positional error (depending on age)
- Georeferencing introduces additional error
- Not suitable for legal/cadastral purposes

See [docs/methodology.md](docs/methodology.md) for detailed accuracy discussion.

## Roadmap

### Completed ✅
- [x] Phase 1: Infrastructure and frontend
- [x] Phase 2: Synthetic data pipeline
- [x] Phase 3: ML model training
- [x] Phase 4: Historical data processing
- [x] Phase 5: Production deployment

### Future Enhancements 🚀
- [ ] Additional historical maps (1700s-1800s if available)
- [ ] Forest/vegetation extraction
- [ ] Railway station identification
- [ ] Street name OCR extraction
- [ ] 3D building reconstruction
- [ ] Historical photo integration
- [ ] Crowd-sourced correction interface
- [ ] Mobile app (iOS/Android)
- [ ] API for programmatic access

## FAQ

**Q: Is this data accurate enough for legal/property purposes?**
A: No. This is for historical exploration and education only. Use official cadastral maps for legal purposes.

**Q: Why aren't all buildings from 1850 shown?**
A: Historical map availability varies. We can only extract features from maps that exist and have been digitized.

**Q: Can I use this for my research project?**
A: Yes! Just follow the attribution requirements (see [data_sources.md](docs/data_sources.md)).

**Q: How can I add data for my town?**
A: The pipeline is designed for Trondheim, but could be adapted. See methodology for details.

**Q: The ML extracted something wrong, how do I fix it?**
A: Report issues via GitHub. We're working on a correction interface.

## Troubleshooting

### Map Not Loading
1. Check browser console for errors (F12)
2. Verify PMTiles file exists in `data/`
3. Check CORS headers (if serving from different domain)
4. Try different browser

### Docker Issues
```bash
# View logs
docker-compose logs

# Rebuild
docker-compose up --build

# Check if port in use
lsof -i :8080  # macOS/Linux
```

### Performance Issues
1. Reduce visible layers
2. Close other browser tabs
3. Use Chrome/Firefox (best performance)
4. Check network connection

See [docs/user_guide.md](docs/user_guide.md) for more troubleshooting.

## License

### Code
**MIT License** - See [LICENSE](LICENSE) file

### Data
- **OpenStreetMap data**: ODbL
- **Kartverket maps**: CC BY 4.0 (recent) / Public Domain (old)
- **ML extractions**: Inherit source license

See [docs/data_sources.md](docs/data_sources.md) for complete licensing.

## Acknowledgments

- **OpenStreetMap contributors** - Modern map data
- **Kartverket** - Historical maps and geospatial infrastructure
- **MapLibre** - Open-source map rendering engine
- **PyTorch** - Machine learning framework
- **Protomaps** - PMTiles format
- **Claude Code** - Development assistance

## Contact

- **Repository**: https://github.com/yourusername/historymap
- **Issues**: https://github.com/yourusername/historymap/issues
- **Discussions**: https://github.com/yourusername/historymap/discussions

## Citation

If you use this project in academic work, please cite:

```bibtex
@software{trondheim_historical_map,
  title = {Trondheim Historical Map: Interactive Temporal Visualization of Urban Development},
  author = {Your Name},
  year = {2025},
  url = {https://github.com/yourusername/historymap},
  note = {Machine learning-based extraction of historical map features}
}
```

---

**Built with Claude Code** 🤖

**Last Updated**: 2025-12-16

For more information, see the [complete project plan](HISTORICAL_MAP_PROJECT_PLAN.md) and [documentation](docs/).
