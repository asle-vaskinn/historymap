#!/bin/bash
# Roll the historymap tenant back to a previous commit. Run ON the VPS as root.
#
# Usage:
#   ./rollback.sh <git-ref>     e.g. ./rollback.sh HEAD~1   or   ./rollback.sh abc123f
#
# historymap prod is static (no DB), so rollback is purely: check out the older
# code, re-stamp /version, fix perms, and reload nginx. Data lives outside git
# and is unaffected.

set -euo pipefail

APP_DIR="${APP_DIR:-/opt/historymap}"
APP_USER="${APP_USER:-historymap}"
GIT_REF="${1:-}"

if [ -z "$GIT_REF" ]; then
    echo "Usage: ./rollback.sh <git-ref>"
    echo ""
    cd "$APP_DIR" 2>/dev/null && {
        echo "Recent commits:"
        git log --oneline -10
    }
    exit 1
fi

cd "$APP_DIR"
git config --system --get-all safe.directory 2>/dev/null | grep -qFx "$APP_DIR" \
    || git config --system --add safe.directory "$APP_DIR"

echo "Current: $(git log -1 --format='%h %s')"
echo "Target:  $(git log -1 --format='%h %s' "$GIT_REF")"
read -r -p "Roll back to the target above? [y/N] " ans
[ "$ans" = "y" ] || { echo "Aborted."; exit 1; }

git reset --hard "$GIT_REF"
git rev-parse --short HEAD > frontend/version.txt
chown -R "$APP_USER:$APP_USER" "$APP_DIR/frontend"
find "$APP_DIR/frontend" -type d -exec chmod 755 {} +
find "$APP_DIR/frontend" -type f -exec chmod 644 {} +
nginx -t && systemctl reload nginx

echo "Rolled back to $(git rev-parse --short HEAD). nginx reloaded."
echo "NOTE: this is a local reset; origin/main still has the newer commit."
echo "To make it stick, revert/force the branch on GitHub too, or the next"
echo "deploy-prod run will roll forward again."
