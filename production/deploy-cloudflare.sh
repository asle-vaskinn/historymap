#!/bin/bash
# Deploy Trondheim Historical Map to Cloudflare R2
# This script uploads PMTiles to Cloudflare R2 for hosting large tile files

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== Cloudflare R2 Deployment Script ===${NC}"
echo

# Configuration
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA_DIR="${REPO_ROOT}/data"

# R2 Configuration (set these as environment variables or edit here)
R2_ACCOUNT_ID="${R2_ACCOUNT_ID:-}"
R2_ACCESS_KEY_ID="${R2_ACCESS_KEY_ID:-}"
R2_SECRET_ACCESS_KEY="${R2_SECRET_ACCESS_KEY:-}"
R2_BUCKET_NAME="${R2_BUCKET_NAME:-trondheim-historical-map}"
R2_ENDPOINT="${R2_ENDPOINT:-https://${R2_ACCOUNT_ID}.r2.cloudflarestorage.com}"
R2_PUBLIC_DOMAIN="${R2_PUBLIC_DOMAIN:-}"  # e.g., tiles.yourdomain.com

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

print_step() {
    echo -e "${BLUE}[STEP]${NC} $1"
}

# Check if AWS CLI is installed (used for R2)
if ! command -v aws &> /dev/null; then
    print_error "AWS CLI is not installed. Cloudflare R2 uses S3-compatible API."
    echo
    echo "Installation instructions:"
    echo "  macOS: brew install awscli"
    echo "  Ubuntu/Debian: sudo apt-get install awscli"
    echo "  Or use pip: pip install awscli"
    echo
    exit 1
fi

# Check configuration
print_step "Checking configuration..."

if [ -z "$R2_ACCOUNT_ID" ]; then
    print_error "R2_ACCOUNT_ID is not set."
    echo "Get your Account ID from Cloudflare dashboard:"
    echo "  1. Go to R2 in Cloudflare dashboard"
    echo "  2. Find Account ID in the right sidebar"
    echo
    read -p "Enter R2 Account ID: " R2_ACCOUNT_ID
    echo
fi

if [ -z "$R2_ACCESS_KEY_ID" ] || [ -z "$R2_SECRET_ACCESS_KEY" ]; then
    print_error "R2 credentials not set."
    echo "Create API tokens in Cloudflare dashboard:"
    echo "  1. Go to R2 > Manage R2 API Tokens"
    echo "  2. Create API Token with Edit permissions"
    echo "  3. Copy Access Key ID and Secret Access Key"
    echo
    read -p "Enter R2 Access Key ID: " R2_ACCESS_KEY_ID
    read -sp "Enter R2 Secret Access Key: " R2_SECRET_ACCESS_KEY
    echo
    echo
fi

# Update R2 endpoint with account ID
R2_ENDPOINT="https://${R2_ACCOUNT_ID}.r2.cloudflarestorage.com"

# Configure AWS CLI for R2
print_info "Configuring AWS CLI for Cloudflare R2..."

export AWS_ACCESS_KEY_ID="$R2_ACCESS_KEY_ID"
export AWS_SECRET_ACCESS_KEY="$R2_SECRET_ACCESS_KEY"
export AWS_DEFAULT_REGION="auto"

# Check if bucket exists
print_step "Checking if bucket exists..."

if aws s3 ls "s3://${R2_BUCKET_NAME}" --endpoint-url "$R2_ENDPOINT" &> /dev/null; then
    print_info "Bucket '${R2_BUCKET_NAME}' exists."
else
    print_warn "Bucket '${R2_BUCKET_NAME}' does not exist."
    read -p "Create bucket now? (y/N) " -n 1 -r
    echo

    if [[ $REPLY =~ ^[Yy]$ ]]; then
        print_info "Creating bucket..."
        aws s3 mb "s3://${R2_BUCKET_NAME}" --endpoint-url "$R2_ENDPOINT"
        print_info "Bucket created successfully."
    else
        print_error "Cannot continue without bucket. Exiting."
        exit 1
    fi
fi

# Set CORS configuration for the bucket
print_step "Configuring CORS..."

CORS_CONFIG=$(cat <<EOF
{
    "CORSRules": [
        {
            "AllowedOrigins": ["*"],
            "AllowedMethods": ["GET", "HEAD"],
            "AllowedHeaders": ["*"],
            "ExposeHeaders": ["Content-Length", "Content-Range", "ETag"],
            "MaxAgeSeconds": 3600
        }
    ]
}
EOF
)

echo "$CORS_CONFIG" > /tmp/r2-cors.json

aws s3api put-bucket-cors \
    --bucket "${R2_BUCKET_NAME}" \
    --cors-configuration file:///tmp/r2-cors.json \
    --endpoint-url "$R2_ENDPOINT"

rm /tmp/r2-cors.json

print_info "CORS configured successfully."

# Find and upload PMTiles files
print_step "Finding PMTiles files..."

PMTILES_FILES=()
if [ -d "$DATA_DIR" ]; then
    while IFS= read -r -d '' file; do
        PMTILES_FILES+=("$file")
    done < <(find "$DATA_DIR" -name "*.pmtiles" -type f -print0)
fi

if [ ${#PMTILES_FILES[@]} -eq 0 ]; then
    print_warn "No PMTiles files found in ${DATA_DIR}"
    print_info "Make sure you've generated tiles using generate_tiles.sh"
    exit 1
fi

print_info "Found ${#PMTILES_FILES[@]} PMTiles file(s):"
for file in "${PMTILES_FILES[@]}"; do
    filename=$(basename "$file")
    filesize=$(stat -f%z "$file" 2>/dev/null || stat -c%s "$file" 2>/dev/null)
    filesize_mb=$((filesize / 1024 / 1024))
    echo "  - $filename (${filesize_mb}MB)"
done

echo
read -p "Upload these files to R2? (y/N) " -n 1 -r
echo

if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    print_info "Upload cancelled."
    exit 0
fi

# Upload files
print_step "Uploading files to R2..."

for file in "${PMTILES_FILES[@]}"; do
    filename=$(basename "$file")
    print_info "Uploading $filename..."

    # Upload with appropriate content type and cache headers
    aws s3 cp "$file" \
        "s3://${R2_BUCKET_NAME}/${filename}" \
        --endpoint-url "$R2_ENDPOINT" \
        --content-type "application/octet-stream" \
        --metadata-directive REPLACE \
        --cache-control "public, max-age=2592000, immutable" \
        --acl public-read

    print_info "Uploaded $filename successfully."
done

# Get public URL
print_step "Configuring public access..."

if [ -z "$R2_PUBLIC_DOMAIN" ]; then
    print_warn "No custom domain configured."
    echo
    echo "To access your tiles, you need to:"
    echo "  1. Set up a custom domain in Cloudflare R2 settings"
    echo "  2. Or use R2.dev subdomain (if enabled)"
    echo
    echo "In Cloudflare dashboard:"
    echo "  1. Go to R2 > Your Bucket > Settings"
    echo "  2. Enable 'Public Access' or set up custom domain"
    echo
    read -p "Enter your public R2 domain (e.g., tiles.yourdomain.com): " R2_PUBLIC_DOMAIN
fi

# Generate updated frontend configuration
print_step "Generating frontend configuration..."

echo
print_info "To use R2-hosted tiles, update your frontend/app.js:"
echo

for file in "${PMTILES_FILES[@]}"; do
    filename=$(basename "$file")
    if [ -n "$R2_PUBLIC_DOMAIN" ]; then
        echo "Tile URL: https://${R2_PUBLIC_DOMAIN}/${filename}"
    else
        echo "Tile URL: https://${R2_BUCKET_NAME}.r2.dev/${filename}"
    fi
done

# Create a configuration file
CONFIG_FILE="${REPO_ROOT}/production/r2-config.json"
cat > "$CONFIG_FILE" << EOF
{
    "r2_account_id": "${R2_ACCOUNT_ID}",
    "r2_bucket": "${R2_BUCKET_NAME}",
    "r2_endpoint": "${R2_ENDPOINT}",
    "r2_public_domain": "${R2_PUBLIC_DOMAIN}",
    "tiles": [
EOF

first=true
for file in "${PMTILES_FILES[@]}"; do
    filename=$(basename "$file")
    if [ "$first" = true ]; then
        first=false
    else
        echo "," >> "$CONFIG_FILE"
    fi
    if [ -n "$R2_PUBLIC_DOMAIN" ]; then
        tile_url="https://${R2_PUBLIC_DOMAIN}/${filename}"
    else
        tile_url="https://${R2_BUCKET_NAME}.r2.dev/${filename}"
    fi
    echo -n "        {\"name\": \"${filename}\", \"url\": \"${tile_url}\"}" >> "$CONFIG_FILE"
done

cat >> "$CONFIG_FILE" << EOF

    ],
    "uploaded_at": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
}
EOF

print_info "Configuration saved to ${CONFIG_FILE}"

echo
print_info "Deployment complete!"
echo
print_step "Next steps:"
echo "  1. Update frontend/app.js to use R2 tile URLs"
echo "  2. Test the application locally"
echo "  3. Deploy frontend to GitHub Pages or other hosting"
echo
echo "Example code for app.js:"
echo

cat << 'EOF'
// R2-hosted PMTiles
map.addSource('pmtiles', {
    type: 'vector',
    url: 'pmtiles://https://your-domain.r2.dev/trondheim.pmtiles',
    attribution: '© OpenStreetMap contributors'
});
EOF

echo
print_info "For troubleshooting, check:"
echo "  - CORS is properly configured in R2 bucket settings"
echo "  - Public access is enabled for the bucket"
echo "  - Custom domain DNS is properly configured"
echo

# Save credentials reminder
print_warn "Remember to save your credentials securely!"
echo "You can set them as environment variables:"
echo
echo "export R2_ACCOUNT_ID='${R2_ACCOUNT_ID}'"
echo "export R2_ACCESS_KEY_ID='${R2_ACCESS_KEY_ID}'"
echo "export R2_SECRET_ACCESS_KEY='[your-secret-key]'"
echo "export R2_BUCKET_NAME='${R2_BUCKET_NAME}'"
echo "export R2_PUBLIC_DOMAIN='${R2_PUBLIC_DOMAIN}'"
echo

print_info "Done!"
