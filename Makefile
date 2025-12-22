# Trondheim Historical Map - Makefile
# Convenience targets for build and deployment

.PHONY: all build build-quick install serve deploy clean help test test-frontend test-python

# Default target
all: build deploy

# Full build pipeline
build:
	@./build.sh

# Quick build (skip PMTiles)
build-quick:
	@./build.sh --quick

# Install Python dependencies
install:
	@python3 -m venv venv
	@. venv/bin/activate && pip install -r requirements.txt

# Local development server (requires npx/Node.js for Range request support)
# Note: Python's http.server does NOT support Range requests needed for PMTiles
# Use 'make deploy' for full functionality with Docker/nginx
serve:
	@echo "Starting local server at http://localhost:8080"
	@echo "Note: Using 'npx serve' for Range request support (PMTiles)"
	@cd frontend && npx serve -l 8080 -s

# Fallback: Python server (no PMTiles support - use for GeoJSON only)
serve-simple:
	@echo "Starting Python server (WARNING: PMTiles will not work)"
	@cd frontend && python3 -m http.server 8080

# Deploy with Docker
deploy:
	@docker compose up -d
	@echo "Deployed at http://localhost:8080"

# Stop Docker
stop:
	@docker compose down

# Run specific pipeline stage
ingest:
	@. venv/bin/activate && python3 scripts/pipeline.py --stage ingest

normalize:
	@. venv/bin/activate && python3 scripts/pipeline.py --stage normalize

merge:
	@. venv/bin/activate && python3 scripts/pipeline.py --stage merge

export:
	@. venv/bin/activate && python3 scripts/pipeline.py --stage export

# Run all tests
test: test-frontend test-python
	@echo "All tests passed!"

# Frontend validation tests
test-frontend:
	@echo "Running frontend tests..."
	@node scripts/test_frontend.js

# Python syntax validation
test-python:
	@echo "Checking Python syntax..."
	@python3 -m py_compile scripts/extract/extract_roads.py
	@python3 -m py_compile scripts/merge/match_roads.py
	@python3 -m py_compile scripts/merge/infer_road_dates.py
	@python3 -m py_compile scripts/merge/merge_roads.py
	@python3 -m py_compile scripts/merge/merge_sources.py
	@echo "Python syntax: OK"

# Clean generated files
clean:
	@rm -rf data/merged/buildings_merged.*
	@rm -rf data/export/*
	@rm -rf frontend/data/buildings.*
	@echo "Cleaned generated files"

# Clean everything including venv
clean-all: clean
	@rm -rf venv
	@rm -rf __pycache__ **/__pycache__
	@echo "Cleaned all generated files and virtual environment"

# Help
help:
	@echo "Trondheim Historical Map - Build Targets"
	@echo ""
	@echo "  make install      - Install Python dependencies"
	@echo "  make build        - Run full build pipeline"
	@echo "  make build-quick  - Build without PMTiles"
	@echo "  make serve        - Start local dev server (npx serve)"
	@echo "  make serve-simple - Python server (no PMTiles support)"
	@echo "  make deploy       - Deploy with Docker"
	@echo "  make stop         - Stop Docker containers"
	@echo ""
	@echo "Testing:"
	@echo "  make test         - Run all tests"
	@echo "  make test-frontend - Validate frontend JS/CSS"
	@echo "  make test-python  - Validate Python syntax"
	@echo ""
	@echo "Pipeline stages:"
	@echo "  make ingest       - Download/extract raw data"
	@echo "  make normalize    - Convert to common schema"
	@echo "  make merge        - Combine sources"
	@echo "  make export       - Generate frontend files"
	@echo ""
	@echo "  make clean        - Remove generated files"
	@echo "  make clean-all    - Remove all generated files + venv"
