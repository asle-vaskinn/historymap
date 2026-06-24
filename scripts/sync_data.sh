#!/bin/bash
# Sync generated map data (PMTiles + GeoJSON) to the historymap tenant on the
# shared Hetzner VPS. Run this from a workstation AFTER regenerating data
# (e.g. `./rebuild.sh` or `pipeline.py --stage export`). Data is large and
# changes rarely, so it is intentionally NOT part of the per-push deploy.
#
# Usage:
#   VPS_HOST=<ip-or-host> ./scripts/sync_data.sh
#   VPS_HOST=<host> VPS_USER=root SRC=data/export ./scripts/sync_data.sh
#
# WHY --chmod=D755,F644 (do not remove): historymap had a production 403 on
# data/roads_temporal.geojson because a hand-uploaded file landed mode 600 /
# root-owned and the nginx worker could not read it. --chmod forces every synced
# directory to 755 and every file to 644 regardless of local perms, so nginx can
# always read them. This is the permanent fix for that bug class.

set -euo pipefail

VPS_USER="${VPS_USER:-root}"
VPS_HOST="${VPS_HOST:?Set VPS_HOST (the VPS IP or hostname)}"
SRC="${SRC:-data/export}"
DEST="${DEST:-/opt/historymap/data}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$SCRIPT_DIR"

if [ ! -d "$SRC" ]; then
    echo "ERROR: source dir '$SRC' not found. Generate data first (./rebuild.sh)." >&2
    exit 1
fi

echo "Syncing $SRC/ -> $VPS_USER@$VPS_HOST:$DEST/ (files 644, dirs 755)"
rsync -avz --delete \
      --chmod=D755,F644 \
      --rsync-path="mkdir -p $DEST && rsync" \
      "$SRC/" "$VPS_USER@$VPS_HOST:$DEST/"

# Belt-and-suspenders: re-assert ownership/perms remotely so the nginx worker
# can read everything even if rsync ran as a non-owner.
ssh "$VPS_USER@$VPS_HOST" "chown -R historymap:historymap $DEST && \
    find $DEST -type d -exec chmod 755 {} + && \
    find $DEST -type f -exec chmod 644 {} +"

echo "Data sync complete."
