#!/bin/bash
# One-time provisioner for the historymap tenant on the shared Hetzner VPS.
# Invoked over SSH by .github/workflows/provision-vps.yml (manual). Runs as root.
# Idempotent and NON-DESTRUCTIVE to the other tenants (subscribe, nextbrain):
# it only ever creates/touches its own user, dir, nginx vhost and cert.
#
# Env (exported by provision-vps.yml from GitHub secrets/vars):
#   GH_TOKEN            PAT with `repo` scope to clone the private repo
#   LETSENCRYPT_EMAIL   email for the Let's Encrypt account
#   HISTORYMAP_BRANCH   branch to check out (default: main)

set -euo pipefail

APP_USER="historymap"
APP_DIR="/opt/historymap"
REPO="asle-vaskinn/historymap"
BRANCH="${HISTORYMAP_BRANCH:-main}"
GH_TOKEN="${GH_TOKEN:?Set GH_TOKEN to clone the repo}"
LE_EMAIL="${LETSENCRYPT_EMAIL:-}"

echo "=== historymap provision starting ($(date -Iseconds)) ==="

# 1. Packages (no-op if already present from other tenants)
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq git nginx certbot python3-certbot-nginx rsync

# 2. System user
if ! id "$APP_USER" &>/dev/null; then
    useradd --system --shell /bin/bash --create-home --home-dir "/home/$APP_USER" "$APP_USER"
    echo "Created user $APP_USER"
fi

# 3. Clone or update the repo into $APP_DIR
git config --system --get-all safe.directory 2>/dev/null | grep -qFx "$APP_DIR" \
    || git config --system --add safe.directory "$APP_DIR"
if [ ! -d "$APP_DIR/.git" ]; then
    git clone --branch "$BRANCH" \
        "https://x-access-token:${GH_TOKEN}@github.com/${REPO}.git" "$APP_DIR"
else
    git -C "$APP_DIR" remote set-url origin \
        "https://x-access-token:${GH_TOKEN}@github.com/${REPO}.git"
    git -C "$APP_DIR" fetch origin "$BRANCH"
    git -C "$APP_DIR" reset --hard "origin/$BRANCH"
fi

# 4. Data dir (populated separately by scripts/sync_data.sh) + perms
mkdir -p "$APP_DIR/data"
echo "$(git -C "$APP_DIR" rev-parse --short HEAD)" > "$APP_DIR/frontend/version.txt"
chown -R "$APP_USER:$APP_USER" "$APP_DIR"
find "$APP_DIR/frontend" -type d -exec chmod 755 {} +
find "$APP_DIR/frontend" -type f -exec chmod 644 {} +

# 5. nginx vhost
NGINX_SRC="$APP_DIR/scripts/nginx/historymap.conf"
install -m 644 "$NGINX_SRC" /etc/nginx/sites-available/historymap
ln -sf /etc/nginx/sites-available/historymap /etc/nginx/sites-enabled/historymap
nginx -t && systemctl reload nginx
echo "Nginx vhost installed."

# 6. TLS — only if DNS already points here and an email is set. Safe to re-run.
if [ -n "$LE_EMAIL" ]; then
    HOSTNAMES=$(awk '/^[[:space:]]*server_name/ {for(i=2;i<=NF;i++){gsub(";","",$i);print $i}}' "$NGINX_SRC" | sort -u)
    CERT_ARGS=(); for h in $HOSTNAMES; do CERT_ARGS+=(-d "$h"); done
    certbot --nginx --keep-until-expiring --non-interactive --agree-tos --redirect \
        --allow-subset-of-names --email "$LE_EMAIL" "${CERT_ARGS[@]}" \
        || echo "WARNING: certbot failed (DNS not pointing here yet?). Re-run after DNS is live."
    systemctl reload nginx
else
    echo "LETSENCRYPT_EMAIL unset — serving HTTP only. Set it and re-run for HTTPS."
fi

echo "=== historymap provision complete ==="
echo "Next: run scripts/sync_data.sh to upload the map data, then push to main to deploy."
