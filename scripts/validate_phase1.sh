#!/bin/bash

# Phase 1 Validation Script for Trondheim Historical Map Project
# Checks that all required files exist and the setup is working

set -e  # Exit on error

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Counters
PASSED=0
FAILED=0

# Helper functions
pass() {
    echo -e "${GREEN}[PASS]${NC} $1"
    ((PASSED++))
}

fail() {
    echo -e "${RED}[FAIL]${NC} $1"
    ((FAILED++))
}

warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

info() {
    echo -e "   [INFO] $1"
}

section() {
    echo ""
    echo "======================================"
    echo "$1"
    echo "======================================"
}

# Get the project root directory (parent of scripts/)
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

echo "Trondheim Historical Map - Phase 1 Validation"
echo "Project root: $PROJECT_ROOT"
echo ""

# 1. Check directory structure
section "1. Directory Structure"

if [ -d "frontend" ]; then
    pass "frontend/ directory exists"
else
    fail "frontend/ directory missing"
fi

if [ -d "data" ]; then
    pass "data/ directory exists"
else
    fail "data/ directory missing"
fi

if [ -d "scripts" ]; then
    pass "scripts/ directory exists"
else
    fail "scripts/ directory missing"
fi

# 2. Check required files
section "2. Required Files"

if [ -f "frontend/index.html" ]; then
    pass "frontend/index.html exists"
else
    fail "frontend/index.html missing"
fi

if [ -f "docker-compose.yml" ]; then
    pass "docker-compose.yml exists"
else
    fail "docker-compose.yml missing"
fi

if [ -f "nginx.conf" ]; then
    pass "nginx.conf exists"
else
    fail "nginx.conf missing"
fi

if [ -f "README.md" ]; then
    pass "README.md exists"
else
    fail "README.md missing"
fi

# 3. Check PMTiles file
section "3. Data Files"

if [ -f "data/trondheim.pmtiles" ]; then
    pass "data/trondheim.pmtiles exists"

    # Check file size (should be > 1KB for valid PMTiles)
    FILE_SIZE=$(stat -f%z "data/trondheim.pmtiles" 2>/dev/null || stat -c%s "data/trondheim.pmtiles" 2>/dev/null)
    if [ "$FILE_SIZE" -gt 1024 ]; then
        pass "PMTiles file size is valid ($(numfmt --to=iec-i --suffix=B $FILE_SIZE 2>/dev/null || echo "$FILE_SIZE bytes"))"
    else
        fail "PMTiles file is too small ($FILE_SIZE bytes)"
    fi

    # Check PMTiles header (magic bytes: 0x504D54696C6573)
    # PMTiles v3 starts with 0x504D54696C6573 (PMTiles in hex)
    HEADER=$(xxd -p -l 8 "data/trondheim.pmtiles" 2>/dev/null | tr -d '\n')
    if [[ "$HEADER" == "504d54696c657333"* ]] || [[ "$HEADER" == "1f8b"* ]]; then
        pass "PMTiles header appears valid"
        info "Header: $HEADER"
    else
        warn "PMTiles header may be invalid or compressed"
        info "Header: $HEADER (expected 504d54696c657333 or 1f8b for gzip)"
    fi
else
    fail "data/trondheim.pmtiles missing"
    info "Run data download/generation script to create this file"
fi

# 4. Check Docker availability
section "4. Docker Environment"

if command -v docker &> /dev/null; then
    pass "Docker is installed"
    DOCKER_VERSION=$(docker --version)
    info "$DOCKER_VERSION"

    if docker info &> /dev/null; then
        pass "Docker daemon is running"
    else
        fail "Docker daemon is not running"
        info "Start Docker Desktop or run: sudo systemctl start docker"
    fi

    if command -v docker-compose &> /dev/null || docker compose version &> /dev/null; then
        pass "Docker Compose is available"
        if command -v docker-compose &> /dev/null; then
            COMPOSE_VERSION=$(docker-compose --version)
        else
            COMPOSE_VERSION=$(docker compose version)
        fi
        info "$COMPOSE_VERSION"
    else
        fail "Docker Compose not found"
    fi
else
    warn "Docker not installed (optional - can use Python HTTP server)"
fi

# 5. Check Python availability (alternative to Docker)
section "5. Alternative Runtime (Python)"

if command -v python3 &> /dev/null; then
    pass "Python 3 is installed"
    PYTHON_VERSION=$(python3 --version)
    info "$PYTHON_VERSION"
elif command -v python &> /dev/null; then
    pass "Python is installed"
    PYTHON_VERSION=$(python --version)
    info "$PYTHON_VERSION"
else
    warn "Python not found (needed if not using Docker)"
fi

# 6. Test server startup (if Docker is available)
section "6. Server Startup Test"

if command -v docker &> /dev/null && docker info &> /dev/null; then
    # Check if container is already running
    if docker ps | grep -q historymap-web; then
        warn "Container historymap-web is already running"
        info "Testing connection to existing container..."

        if curl -s -o /dev/null -w "%{http_code}" http://localhost:8080 | grep -q "200"; then
            pass "Server responds successfully (HTTP 200)"
        else
            fail "Server not responding on http://localhost:8080"
        fi
    else
        info "Starting Docker container for testing..."

        # Try to start the container
        if docker-compose up -d 2>&1 | grep -q "Started\|running"; then
            pass "Docker container started"

            # Wait for server to be ready
            info "Waiting for server to be ready..."
            sleep 3

            # Test HTTP response
            HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8080)
            if [ "$HTTP_CODE" = "200" ]; then
                pass "Server responds successfully (HTTP 200)"
            else
                fail "Server returned HTTP $HTTP_CODE"
            fi

            # Test if data directory is accessible
            HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8080/data/)
            if [ "$HTTP_CODE" = "200" ] || [ "$HTTP_CODE" = "403" ]; then
                pass "Data directory is mounted and accessible"
            else
                warn "Data directory may not be accessible (HTTP $HTTP_CODE)"
            fi

            # Cleanup - stop the container
            info "Stopping test container..."
            docker-compose down > /dev/null 2>&1
            pass "Test container stopped"
        else
            fail "Could not start Docker container"
            info "Run 'docker-compose up' to see detailed error logs"
        fi
    fi
else
    warn "Skipping server test (Docker not available)"
    info "You can manually test with: python3 -m http.server -d frontend 8080"
fi

# 7. Check nginx configuration syntax
section "7. Configuration Validation"

if [ -f "nginx.conf" ]; then
    # Try to validate nginx config using docker
    if command -v docker &> /dev/null && docker info &> /dev/null; then
        if docker run --rm -v "$PROJECT_ROOT/nginx.conf:/etc/nginx/conf.d/default.conf:ro" nginx:alpine nginx -t 2>&1 | grep -q "successful"; then
            pass "nginx.conf syntax is valid"
        else
            warn "Could not validate nginx.conf syntax"
        fi
    else
        info "Skipping nginx config validation (Docker not available)"
    fi
fi

# Summary
section "Validation Summary"

TOTAL=$((PASSED + FAILED))
echo ""
echo "Passed: $PASSED/$TOTAL"
echo "Failed: $FAILED/$TOTAL"
echo ""

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}All checks passed! Phase 1 setup is complete.${NC}"
    echo ""
    echo "Next steps:"
    echo "  1. If you haven't already, generate the PMTiles data:"
    echo "     ./scripts/download_osm.sh"
    echo "     ./scripts/generate_tiles.sh"
    echo ""
    echo "  2. Start the development server:"
    echo "     docker-compose up"
    echo "     # or without Docker:"
    echo "     cd frontend && python3 -m http.server 8080"
    echo ""
    echo "  3. Open http://localhost:8080 in your browser"
    exit 0
else
    echo -e "${RED}Some checks failed. Please fix the issues above.${NC}"
    exit 1
fi
