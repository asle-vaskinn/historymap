#!/bin/bash
# Per-deploy script for the shared Hetzner VPS — invoked over SSH by
# .github/workflows/deploy-prod.yml on push to main. Runs as root. Idempotent.
#
# Usage:
#   bash scripts/deploy_vps.sh           # deploys main (default)
#   bash scripts/deploy_vps.sh <ref>     # deploys the given branch/ref
#
# historymap prod is STATIC: nginx serves frontend/ + data/ directly. There is
# no app server, venv, or DB — so deploy = pull code, stamp the version, and
# (re)apply the nginx vhost + TLS. Data is NOT touched here; it is synced
# separately by scripts/sync_data.sh (large, changes rarely).

set -euo pipefail

REF="${1:-main}"
# Env-overridable so prod and stage share this one script (DRY). Defaults = prod.
#   prod  : (defaults)
#   stage : APP_DIR=/opt/historymap-stage SITE=historymap-stage
APP_DIR="${APP_DIR:-/opt/historymap}"
APP_USER="${APP_USER:-historymap}"
SITE="${SITE:-historymap}"          # picks scripts/nginx/<SITE>.conf + sites-available/<SITE>
STATE_DIR="$APP_DIR/.deploy-state"
LE_EMAIL="${LETSENCRYPT_EMAIL:-}"

echo "$(date -Iseconds) deploy_vps.sh starting (user=$(id -un), ref=$REF)"

# Repo owned by $APP_USER but we run as root — register safe.directory (system
# scope so it's read regardless of HOME). Idempotent.
git config --system --get-all safe.directory 2>/dev/null | grep -qFx "$APP_DIR" \
    || git config --system --add safe.directory "$APP_DIR"

mkdir -p "$STATE_DIR"
cd "$APP_DIR"

echo "$(date -Iseconds) Fetching origin/$REF"
git fetch origin "$REF"
git reset --hard "origin/$REF"
SHA="$(git rev-parse --short HEAD)"
echo "$(date -Iseconds) Deploying $SHA"

# Stamp the version the /version endpoint serves (AC2/AC3).
echo "$SHA" > frontend/version.txt

# Ensure nginx can read the freshly-pulled frontend (code only — data handled
# by sync_data.sh). Prevents the class of 403 that bit roads_temporal.geojson.
chown -R "$APP_USER:$APP_USER" "$APP_DIR/frontend"
find "$APP_DIR/frontend" -type d -exec chmod 755 {} +
find "$APP_DIR/frontend" -type f -exec chmod 644 {} +

# Apply nginx vhost from the repo only when it changed. certbot --nginx adds the
# :443 blocks on first issuance; re-applying only on change preserves them.
NGINX_SRC="$APP_DIR/scripts/nginx/${SITE}.conf"
NGINX_DST="/etc/nginx/sites-available/${SITE}"
NGINX_LAST="$STATE_DIR/.nginx-applied.conf"

if [ -f "$NGINX_SRC" ] && ! cmp -s "$NGINX_SRC" "$NGINX_LAST" 2>/dev/null; then
    echo "$(date -Iseconds) Nginx config changed — applying."
    install -m 644 "$NGINX_SRC" "$NGINX_DST"
    ln -sf "$NGINX_DST" "/etc/nginx/sites-enabled/${SITE}"
    nginx -t
    systemctl reload nginx
    HOSTNAMES=$(awk '/^[[:space:]]*server_name/ {for(i=2;i<=NF;i++){gsub(";","",$i);print $i}}' "$NGINX_SRC" | sort -u)
    if [ -n "$LE_EMAIL" ]; then
        CERT_ARGS=()
        for h in $HOSTNAMES; do CERT_ARGS+=(-d "$h"); done
        echo "$(date -Iseconds) Ensuring TLS for: $HOSTNAMES"
        if certbot --nginx --expand --keep-until-expiring --non-interactive \
                --agree-tos --redirect --allow-subset-of-names \
                --email "$LE_EMAIL" "${CERT_ARGS[@]}"; then
            systemctl reload nginx
            cp "$NGINX_SRC" "$NGINX_LAST"
        else
            echo "$(date -Iseconds) WARNING: certbot --expand failed — HTTP still serving. Not saving snapshot so next deploy retries."
        fi
    else
        echo "$(date -Iseconds) LETSENCRYPT_EMAIL unset — skipping TLS (HTTP only). Set it in the deploy env to enable HTTPS."
        cp "$NGINX_SRC" "$NGINX_LAST"
    fi
else
    systemctl reload nginx
fi

echo "$(date -Iseconds) deploy_vps.sh finished: $SHA"
