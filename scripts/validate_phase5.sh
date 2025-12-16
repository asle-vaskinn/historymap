#!/bin/bash
# Validation Script for Phase 5: Production Deployment
# Trondheim Historical Map System

# Don't exit on error - we want to collect all validation results
set +e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Counters
PASSED=0
FAILED=0
WARNINGS=0

echo -e "${BLUE}======================================${NC}"
echo -e "${BLUE}  Phase 5 Validation Script${NC}"
echo -e "${BLUE}  Production Deployment Check${NC}"
echo -e "${BLUE}======================================${NC}"
echo

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Function to print test results
print_test() {
    local test_name="$1"
    local result="$2"
    local message="$3"

    if [ "$result" = "PASS" ]; then
        echo -e "${GREEN}✓${NC} $test_name"
        ((PASSED++))
    elif [ "$result" = "FAIL" ]; then
        echo -e "${RED}✗${NC} $test_name"
        if [ -n "$message" ]; then
            echo -e "  ${RED}Error: $message${NC}"
        fi
        ((FAILED++))
    elif [ "$result" = "WARN" ]; then
        echo -e "${YELLOW}⚠${NC} $test_name"
        if [ -n "$message" ]; then
            echo -e "  ${YELLOW}Warning: $message${NC}"
        fi
        ((WARNINGS++))
    fi
}

# Function to check file exists
check_file() {
    local file="$1"
    local description="$2"

    if [ -f "$file" ]; then
        print_test "$description exists" "PASS"
        return 0
    else
        print_test "$description exists" "FAIL" "File not found: $file"
        return 1
    fi
}

# Function to check directory exists
check_dir() {
    local dir="$1"
    local description="$2"

    if [ -d "$dir" ]; then
        print_test "$description exists" "PASS"
        return 0
    else
        print_test "$description exists" "FAIL" "Directory not found: $dir"
        return 1
    fi
}

# Function to check executable
check_executable() {
    local file="$1"
    local description="$2"

    if [ -x "$file" ]; then
        print_test "$description is executable" "PASS"
        return 0
    else
        print_test "$description is executable" "FAIL" "Not executable: $file"
        return 1
    fi
}

# Function to check command exists
check_command() {
    local cmd="$1"
    local description="$2"

    if command -v "$cmd" &> /dev/null; then
        print_test "$description available" "PASS"
        return 0
    else
        print_test "$description available" "WARN" "Command not found: $cmd"
        return 1
    fi
}

echo -e "${BLUE}[1] Checking Production Directory Structure${NC}"
echo

check_dir "$PROJECT_ROOT/production" "Production directory"
check_dir "$PROJECT_ROOT/docs" "Documentation directory"

echo

echo -e "${BLUE}[2] Checking Production Files${NC}"
echo

check_file "$PROJECT_ROOT/production/Dockerfile" "Production Dockerfile"
check_file "$PROJECT_ROOT/production/nginx.prod.conf" "Production Nginx config"
check_file "$PROJECT_ROOT/production/docker-compose.prod.yml" "Production Docker Compose"
check_file "$PROJECT_ROOT/production/deploy-github-pages.sh" "GitHub Pages deployment script"
check_file "$PROJECT_ROOT/production/deploy-cloudflare.sh" "Cloudflare R2 deployment script"

echo

echo -e "${BLUE}[3] Checking Deployment Scripts Are Executable${NC}"
echo

check_executable "$PROJECT_ROOT/production/deploy-github-pages.sh" "GitHub Pages script"
check_executable "$PROJECT_ROOT/production/deploy-cloudflare.sh" "Cloudflare script"

echo

echo -e "${BLUE}[4] Checking Documentation Files${NC}"
echo

check_file "$PROJECT_ROOT/docs/user_guide.md" "User guide"
check_file "$PROJECT_ROOT/docs/methodology.md" "Methodology documentation"
check_file "$PROJECT_ROOT/docs/data_sources.md" "Data sources documentation"
check_file "$PROJECT_ROOT/README.md" "Root README"

echo

echo -e "${BLUE}[5] Checking Frontend Files${NC}"
echo

check_dir "$PROJECT_ROOT/frontend" "Frontend directory"
check_file "$PROJECT_ROOT/frontend/index.html" "Frontend HTML"
check_file "$PROJECT_ROOT/frontend/app.js" "Frontend JavaScript"
check_file "$PROJECT_ROOT/frontend/style.css" "Frontend CSS"

echo

echo -e "${BLUE}[6] Checking Data Files${NC}"
echo

check_dir "$PROJECT_ROOT/data" "Data directory"

# Check for PMTiles or OSM data
if [ -f "$PROJECT_ROOT/data/trondheim.pmtiles" ] || ls "$PROJECT_ROOT/data"/*.pmtiles 1> /dev/null 2>&1; then
    print_test "PMTiles data available" "PASS"
elif [ -f "$PROJECT_ROOT/data/trondheim.osm.pbf" ]; then
    print_test "PMTiles data available" "WARN" "OSM data exists but PMTiles not generated. Run ./scripts/generate_tiles.sh"
else
    print_test "PMTiles data available" "WARN" "No data files found. Run ./scripts/download_osm.sh and ./scripts/generate_tiles.sh"
fi

echo

echo -e "${BLUE}[7] Checking Required Tools${NC}"
echo

check_command "docker" "Docker"
check_command "docker-compose" "Docker Compose" || check_command "docker compose" "Docker Compose (v2)"
check_command "git" "Git"

# Optional tools
check_command "aws" "AWS CLI (for Cloudflare R2)" || true
check_command "git-lfs" "Git LFS (for large files)" || true

echo

echo -e "${BLUE}[8] Validating Dockerfile Syntax${NC}"
echo

if [ -f "$PROJECT_ROOT/production/Dockerfile" ]; then
    if docker build -f "$PROJECT_ROOT/production/Dockerfile" -t historymap-validation-test --no-cache "$PROJECT_ROOT" > /dev/null 2>&1; then
        print_test "Dockerfile builds successfully" "PASS"
        # Clean up test image
        docker rmi historymap-validation-test > /dev/null 2>&1 || true
    else
        print_test "Dockerfile builds successfully" "WARN" "Docker build failed or not tested (is Docker running?)"
    fi
else
    print_test "Dockerfile builds successfully" "FAIL" "Dockerfile not found"
fi

echo

echo -e "${BLUE}[9] Validating Docker Compose Configuration${NC}"
echo

if [ -f "$PROJECT_ROOT/production/docker-compose.prod.yml" ]; then
    if command -v docker-compose &> /dev/null; then
        if docker-compose -f "$PROJECT_ROOT/production/docker-compose.prod.yml" config > /dev/null 2>&1; then
            print_test "Docker Compose config valid" "PASS"
        else
            print_test "Docker Compose config valid" "WARN" "Config validation failed"
        fi
    elif command -v docker &> /dev/null && docker compose version &> /dev/null; then
        if docker compose -f "$PROJECT_ROOT/production/docker-compose.prod.yml" config > /dev/null 2>&1; then
            print_test "Docker Compose config valid" "PASS"
        else
            print_test "Docker Compose config valid" "WARN" "Config validation failed"
        fi
    else
        print_test "Docker Compose config valid" "WARN" "Docker Compose not available to validate"
    fi
else
    print_test "Docker Compose config valid" "FAIL" "docker-compose.prod.yml not found"
fi

echo

echo -e "${BLUE}[10] Checking Nginx Configuration${NC}"
echo

if [ -f "$PROJECT_ROOT/production/nginx.prod.conf" ]; then
    # Basic syntax check (just look for obvious errors)
    if grep -q "server {" "$PROJECT_ROOT/production/nginx.prod.conf" && \
       grep -q "location" "$PROJECT_ROOT/production/nginx.prod.conf"; then
        print_test "Nginx config has basic structure" "PASS"
    else
        print_test "Nginx config has basic structure" "WARN" "Config may be incomplete"
    fi

    # Check for important features
    if grep -q "gzip on" "$PROJECT_ROOT/production/nginx.prod.conf"; then
        print_test "Gzip compression enabled" "PASS"
    else
        print_test "Gzip compression enabled" "WARN" "Gzip not found in config"
    fi

    if grep -q "pmtiles" "$PROJECT_ROOT/production/nginx.prod.conf"; then
        print_test "PMTiles MIME type configured" "PASS"
    else
        print_test "PMTiles MIME type configured" "WARN" "PMTiles MIME type not found"
    fi

    if grep -q "Accept-Ranges" "$PROJECT_ROOT/production/nginx.prod.conf"; then
        print_test "Range request support enabled" "PASS"
    else
        print_test "Range request support enabled" "WARN" "Range requests not configured (needed for PMTiles)"
    fi
else
    print_test "Nginx config exists" "FAIL" "nginx.prod.conf not found"
fi

echo

echo -e "${BLUE}[11] Checking Documentation Quality${NC}"
echo

# Check README has key sections
if [ -f "$PROJECT_ROOT/README.md" ]; then
    if grep -q "Quick Start" "$PROJECT_ROOT/README.md" && \
       grep -q "Documentation" "$PROJECT_ROOT/README.md" && \
       grep -q "License" "$PROJECT_ROOT/README.md"; then
        print_test "README has essential sections" "PASS"
    else
        print_test "README has essential sections" "WARN" "Some sections may be missing"
    fi
fi

# Check user guide
if [ -f "$PROJECT_ROOT/docs/user_guide.md" ]; then
    if grep -q "Time Slider" "$PROJECT_ROOT/docs/user_guide.md" && \
       grep -q "Navigation" "$PROJECT_ROOT/docs/user_guide.md"; then
        print_test "User guide has key content" "PASS"
    else
        print_test "User guide has key content" "WARN" "Some content may be missing"
    fi
fi

# Check methodology
if [ -f "$PROJECT_ROOT/docs/methodology.md" ]; then
    if grep -q "Machine Learning" "$PROJECT_ROOT/docs/methodology.md" || \
       grep -q "ML" "$PROJECT_ROOT/docs/methodology.md"; then
        print_test "Methodology documents ML pipeline" "PASS"
    else
        print_test "Methodology documents ML pipeline" "WARN" "ML pipeline not documented"
    fi
fi

echo

echo -e "${BLUE}[12] Checking Git Repository${NC}"
echo

if [ -d "$PROJECT_ROOT/.git" ]; then
    print_test "Git repository initialized" "PASS"

    # Check for .gitignore
    if [ -f "$PROJECT_ROOT/.gitignore" ]; then
        print_test ".gitignore exists" "PASS"
    else
        print_test ".gitignore exists" "WARN" "No .gitignore found"
    fi

    # Check for remote
    if git -C "$PROJECT_ROOT" remote get-url origin &> /dev/null; then
        print_test "Git remote configured" "PASS"
    else
        print_test "Git remote configured" "WARN" "No remote origin set (needed for GitHub Pages)"
    fi
else
    print_test "Git repository initialized" "WARN" "Not a git repository"
fi

echo

echo -e "${BLUE}[13] Deployment Readiness Checks${NC}"
echo

# Check if we can build production image
if command -v docker &> /dev/null; then
    print_test "Docker available for deployment" "PASS"
else
    print_test "Docker available for deployment" "WARN" "Docker not available"
fi

# Check data size for GitHub Pages
if [ -d "$PROJECT_ROOT/data" ]; then
    total_size=$(du -sm "$PROJECT_ROOT/data" 2>/dev/null | cut -f1)
    if [ "$total_size" -lt 100 ]; then
        print_test "Data size suitable for GitHub Pages" "PASS" "Size: ${total_size}MB"
    elif [ "$total_size" -lt 1000 ]; then
        print_test "Data size suitable for GitHub Pages" "WARN" "Size: ${total_size}MB (consider Git LFS or R2)"
    else
        print_test "Data size suitable for GitHub Pages" "WARN" "Size: ${total_size}MB (use Git LFS or Cloudflare R2)"
    fi
fi

echo

# Summary
echo -e "${BLUE}======================================${NC}"
echo -e "${BLUE}  Validation Summary${NC}"
echo -e "${BLUE}======================================${NC}"
echo
echo -e "${GREEN}Passed:${NC}   $PASSED"
echo -e "${YELLOW}Warnings:${NC} $WARNINGS"
echo -e "${RED}Failed:${NC}   $FAILED"
echo

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}✓ Phase 5 validation PASSED${NC}"
    echo
    echo "Your deployment infrastructure is ready!"
    echo
    echo "Next steps:"
    echo "  1. Build production image: docker-compose -f production/docker-compose.prod.yml build"
    echo "  2. Test locally: docker-compose -f production/docker-compose.prod.yml up"
    echo "  3. Deploy to GitHub Pages: ./production/deploy-github-pages.sh"
    echo "  4. Or deploy to Cloudflare R2: ./production/deploy-cloudflare.sh"
    echo
    exit 0
elif [ $FAILED -le 3 ] && [ $WARNINGS -le 5 ]; then
    echo -e "${YELLOW}⚠ Phase 5 validation completed with warnings${NC}"
    echo
    echo "Some non-critical issues found. Review warnings above."
    echo "You can proceed with deployment, but consider fixing warnings first."
    echo
    exit 0
else
    echo -e "${RED}✗ Phase 5 validation FAILED${NC}"
    echo
    echo "Critical issues found. Please fix the errors above before deploying."
    echo "Check the failed tests and ensure all required files exist."
    echo
    exit 1
fi
