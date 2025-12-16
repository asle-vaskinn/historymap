#!/bin/bash
# Deploy Trondheim Historical Map to GitHub Pages
# This script prepares and deploys the application to GitHub Pages

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== GitHub Pages Deployment Script ===${NC}"
echo

# Configuration
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEPLOY_DIR="${REPO_ROOT}/gh-pages-build"
BRANCH_NAME="gh-pages"

# File size limit for GitHub Pages (100MB recommended, 100MB hard limit with LFS)
MAX_FILE_SIZE_MB=95
MAX_FILE_SIZE_BYTES=$((MAX_FILE_SIZE_MB * 1024 * 1024))

# Function to print colored messages
print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if we're in a git repository
if ! git rev-parse --git-dir > /dev/null 2>&1; then
    print_error "Not in a git repository. Please run this from the repository root."
    exit 1
fi

# Check if there are uncommitted changes
if ! git diff-index --quiet HEAD --; then
    print_warn "You have uncommitted changes. Consider committing them first."
    read -p "Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Clean and create deployment directory
print_info "Preparing deployment directory..."
rm -rf "${DEPLOY_DIR}"
mkdir -p "${DEPLOY_DIR}"

# Copy frontend files
print_info "Copying frontend files..."
cp -r "${REPO_ROOT}/frontend/"* "${DEPLOY_DIR}/"

# Create data directory
mkdir -p "${DEPLOY_DIR}/data"

# Check for PMTiles files and their sizes
print_info "Checking data files..."
LARGE_FILES=()

if [ -d "${REPO_ROOT}/data" ]; then
    for file in "${REPO_ROOT}/data"/*.pmtiles "${REPO_ROOT}/data"/*.mbtiles "${REPO_ROOT}/data"/*.geojson; do
        if [ -f "$file" ]; then
            filename=$(basename "$file")
            filesize=$(stat -f%z "$file" 2>/dev/null || stat -c%s "$file" 2>/dev/null)
            filesize_mb=$((filesize / 1024 / 1024))

            if [ $filesize -gt $MAX_FILE_SIZE_BYTES ]; then
                print_warn "File $filename is ${filesize_mb}MB (exceeds ${MAX_FILE_SIZE_MB}MB limit)"
                LARGE_FILES+=("$file")
            else
                print_info "Copying $filename (${filesize_mb}MB)..."
                cp "$file" "${DEPLOY_DIR}/data/"
            fi
        fi
    done
fi

# Handle large files
if [ ${#LARGE_FILES[@]} -gt 0 ]; then
    echo
    print_warn "The following files exceed the ${MAX_FILE_SIZE_MB}MB GitHub Pages recommended limit:"
    for file in "${LARGE_FILES[@]}"; do
        filename=$(basename "$file")
        filesize=$(stat -f%z "$file" 2>/dev/null || stat -c%s "$file" 2>/dev/null)
        filesize_mb=$((filesize / 1024 / 1024))
        echo "  - $filename (${filesize_mb}MB)"
    done
    echo
    print_warn "Options for large files:"
    echo "  1. Use GitHub LFS (Git Large File Storage)"
    echo "  2. Host tiles on external storage (Cloudflare R2, AWS S3, etc.)"
    echo "  3. Split tiles into smaller zoom levels"
    echo "  4. Continue without these files (app may not work fully)"
    echo
    read -p "Install Git LFS and track these files? (y/N) " -n 1 -r
    echo

    if [[ $REPLY =~ ^[Yy]$ ]]; then
        # Check if git-lfs is installed
        if ! command -v git-lfs &> /dev/null; then
            print_error "Git LFS is not installed. Please install it first:"
            echo "  macOS: brew install git-lfs"
            echo "  Ubuntu/Debian: sudo apt-get install git-lfs"
            echo "  Then run: git lfs install"
            exit 1
        fi

        # Initialize LFS if not already done
        git lfs install

        # Track large files
        for file in "${LARGE_FILES[@]}"; do
            filename=$(basename "$file")
            print_info "Tracking $filename with Git LFS..."
            cp "$file" "${DEPLOY_DIR}/data/"
            (cd "${DEPLOY_DIR}" && git lfs track "data/$filename")
        done

        print_info "Git LFS configured. .gitattributes file created."
    else
        print_warn "Skipping large files. You'll need to host them externally."
        print_info "Consider using the deploy-cloudflare.sh script for tile hosting."
    fi
fi

# Create a basic README for gh-pages
print_info "Creating gh-pages README..."
cat > "${DEPLOY_DIR}/README.md" << 'EOF'
# Trondheim Historical Map - GitHub Pages Deployment

This branch contains the production build of the Trondheim Historical Map application.

**Live Site**: https://[your-username].github.io/[your-repo-name]/

## About

This is an interactive historical map of the Trondheim region, Norway, showing the evolution of buildings, roads, and other features from 1850 to present.

The application uses:
- MapLibre GL JS for map rendering
- PMTiles for efficient vector tile delivery
- Machine learning to extract features from historical maps

For more information, see the [main repository](../../tree/main).

---
Built with Claude Code
EOF

# Create .nojekyll file (important for GitHub Pages with static files)
touch "${DEPLOY_DIR}/.nojekyll"

# Create a basic 404 page
cat > "${DEPLOY_DIR}/404.html" << 'EOF'
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>404 - Page Not Found</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100vh;
            margin: 0;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
        }
        .container {
            text-align: center;
        }
        h1 {
            font-size: 4em;
            margin: 0;
        }
        p {
            font-size: 1.5em;
        }
        a {
            color: white;
            text-decoration: underline;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>404</h1>
        <p>Page Not Found</p>
        <p><a href="/">Return to Historical Map</a></p>
    </div>
</body>
</html>
EOF

# Initialize git in deployment directory if needed
cd "${DEPLOY_DIR}"

if [ ! -d ".git" ]; then
    print_info "Initializing git repository in deployment directory..."
    git init
    git checkout -b ${BRANCH_NAME}
else
    print_info "Using existing git repository..."
fi

# Add all files
print_info "Adding files to git..."
git add .

# Create commit
print_info "Creating commit..."
COMMIT_MSG="Deploy to GitHub Pages - $(date '+%Y-%m-%d %H:%M:%S')"
git commit -m "$COMMIT_MSG" || print_warn "No changes to commit"

# Get the remote URL from the main repo
cd "${REPO_ROOT}"
REMOTE_URL=$(git config --get remote.origin.url || echo "")

if [ -z "$REMOTE_URL" ]; then
    print_error "No remote origin found. Please set up a remote first:"
    echo "  git remote add origin https://github.com/username/repo.git"
    exit 1
fi

echo
print_info "Repository: $REMOTE_URL"
echo
print_warn "Ready to deploy to GitHub Pages!"
echo
echo "Next steps:"
echo "  1. Review the files in: ${DEPLOY_DIR}"
echo "  2. Push to GitHub Pages branch:"
echo "     cd ${DEPLOY_DIR}"
echo "     git remote add origin ${REMOTE_URL}"
echo "     git push -f origin ${BRANCH_NAME}"
echo
echo "  3. Enable GitHub Pages in repository settings:"
echo "     - Go to: Settings > Pages"
echo "     - Source: Deploy from branch"
echo "     - Branch: ${BRANCH_NAME}"
echo "     - Folder: / (root)"
echo
echo "  4. Your site will be available at:"
echo "     https://[your-username].github.io/[your-repo-name]/"
echo

read -p "Push to GitHub Pages now? (y/N) " -n 1 -r
echo

if [[ $REPLY =~ ^[Yy]$ ]]; then
    cd "${DEPLOY_DIR}"

    # Add remote if it doesn't exist
    if ! git remote get-url origin > /dev/null 2>&1; then
        git remote add origin "${REMOTE_URL}"
    fi

    print_info "Pushing to ${BRANCH_NAME}..."
    git push -f origin ${BRANCH_NAME}

    echo
    print_info "Deployment complete!"
    print_info "Your site should be available shortly at GitHub Pages."
    print_info "Check the Actions tab in GitHub for deployment status."
else
    print_info "Deployment prepared but not pushed."
    print_info "Run the commands above when ready to deploy."
fi

echo
print_info "Done!"
