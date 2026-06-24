# Phase 5 Quick Start Guide

**Deployment Infrastructure and Documentation**

## What Was Created

Phase 5 added production deployment infrastructure and complete documentation:

- Production Docker container (nginx-based)
- GitHub Pages deployment script
- Cloudflare R2 deployment script
- Production Docker Compose configuration
- Comprehensive user guide
- Technical methodology documentation
- Data sources and attribution guide
- Production-ready README

## Validate Your Setup

```bash
./scripts/validate_phase5.sh
```

Expected output: ✓ Passed (with some warnings OK)

## Deployment Options

### Option 1: Local Docker (Testing)

```bash
# Build production image
docker-compose -f production/docker-compose.prod.yml build

# Run locally
docker-compose -f production/docker-compose.prod.yml up

# Access at http://localhost:80
```

### Option 2: GitHub Pages (Free Hosting)

```bash
# Run deployment script
./production/deploy-github-pages.sh

# Follow prompts to:
# - Check file sizes
# - Configure Git LFS (if needed)
# - Push to gh-pages branch
# - Enable GitHub Pages in repo settings
```

**Note**: If PMTiles files >100MB, use Git LFS or Option 3.

### Option 3: Cloudflare R2 (Large Files)

```bash
# Set credentials (get from Cloudflare dashboard)
export R2_ACCOUNT_ID="your-account-id"
export R2_ACCESS_KEY_ID="your-access-key"
export R2_SECRET_ACCESS_KEY="your-secret-key"

# Run deployment
./production/deploy-cloudflare.sh

# Follow prompts to upload tiles to R2
# Then deploy frontend via GitHub Pages
```

## File Locations

```
production/
├── Dockerfile                   # Production container
├── nginx.prod.conf              # Nginx config
├── docker-compose.prod.yml      # Production compose
├── deploy-github-pages.sh       # Deploy to GH Pages
└── deploy-cloudflare.sh         # Deploy to R2

docs/
├── user_guide.md                # How to use the map
├── methodology.md               # Technical details
└── data_sources.md              # Attribution info

scripts/
└── validate_phase5.sh           # Validation script

README.md                        # Updated main README
```

## Documentation

### For End Users
Read: `docs/user_guide.md`
- How to use the map interface
- Time slider explanation
- Mobile tips
- Troubleshooting

### For Developers
Read: `docs/methodology.md`
- ML pipeline details
- Model architecture
- Training process
- Accuracy metrics

### For Data Use
Read: `docs/data_sources.md`
- OpenStreetMap attribution
- Kartverket licensing
- How to cite the project

## Common Issues

### PMTiles files too large for GitHub Pages
**Solution**: Use Cloudflare R2 or Git LFS
```bash
# Option A: Deploy to R2
./production/deploy-cloudflare.sh

# Option B: Use Git LFS
git lfs install
git lfs track "data/*.pmtiles"
```

### Docker not running
**Solution**: Start Docker Desktop or Docker daemon
```bash
# macOS: Open Docker Desktop app
# Linux: sudo systemctl start docker
```

### Port 80 already in use
**Solution**: Change port in docker-compose.prod.yml
```yaml
ports:
  - "8080:80"  # Use 8080 instead
```

## Next Steps After Deployment

1. ✅ Validate deployment: `./scripts/validate_phase5.sh`
2. ✅ Build/deploy using chosen method
3. ✅ Test in browser
4. ✅ Check mobile responsiveness
5. ✅ Verify attribution displays
6. [ ] Add live demo URL to README
7. [ ] Share project!

## Quick Commands

```bash
# Validate everything
./scripts/validate_phase5.sh

# Build production Docker
docker-compose -f production/docker-compose.prod.yml build

# Run production Docker
docker-compose -f production/docker-compose.prod.yml up -d

# Deploy to GitHub Pages
./production/deploy-github-pages.sh

# Deploy to Cloudflare R2
./production/deploy-cloudflare.sh

# View logs (Docker)
docker-compose -f production/docker-compose.prod.yml logs -f

# Stop production Docker
docker-compose -f production/docker-compose.prod.yml down
```

## Need Help?

- User questions: See `docs/user_guide.md`
- Technical questions: See `docs/methodology.md`
- Deployment issues: Run `./scripts/validate_phase5.sh`
- Data attribution: See `docs/data_sources.md`

---

**Phase 5 Status**: ✅ COMPLETE
**Ready to Deploy**: YES

For full project plan, see: `HISTORICAL_MAP_PROJECT_PLAN.md`
