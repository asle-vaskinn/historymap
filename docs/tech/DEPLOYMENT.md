# Deployment Runbook

> Authoritative guide for deploying historymap. Supersedes the deprecated
> `production/deploy-cloudflare.sh` and `production/deploy-github-pages.sh`
> (neither was ever the live deploy path).

## Where it runs

historymap is deployed as **tenant #3** on a shared **Hetzner VPS**, alongside
`subscribe` (`permen.studenterhytta.org`) and `nextbrain` (`brain.vaskinn.eu`),
following the tenant pattern documented in `nextbrain/DEPLOY.md`.

| Piece | Value |
|---|---|
| Public URL | `https://historymap.vaskinn.eu` |
| Staging URL | `https://stage.historymap.vaskinn.eu` |
| App dir (prod) | `/opt/historymap` |
| App dir (stage) | `/opt/historymap-stage` |
| System user | `historymap` |
| Serving | **nginx static** — frontend + `/data/` + `/wms/` proxy. No app server. |
| TLS | certbot `--nginx` per hostname |
| Deploy trigger | push to `main` → `.github/workflows/deploy-prod.yml` |
| Staging trigger | PR labeled `staging` → `.github/workflows/deploy-stage.yml` |
| Provision | `.github/workflows/provision-vps.yml` (manual, one-time) |

> **Migration note:** until cutover, the live site historically ran on a
> dedicated box `77.42.33.192` (bare nginx, manual deploy). The consolidation
> repoints DNS to the shared VPS and retires that box.

## Architecture

```
push to main
  → test.yml         CI: node --check + pytest + docker compose config
  → deploy-prod.yml  SSH → scripts/deploy_vps.sh main
        git reset --hard origin/main
        frontend/version.txt = short SHA      (served at /version)
        chmod frontend 644/755                (nginx-readable)
        apply scripts/nginx/historymap.conf + certbot, reload nginx
  → verify: GET /version == pushed SHA
```

Prod is **static-only**: the FastAPI backend (`/api/`) and the editing tools
(`source_manager`, `feature_extraction`, the `:5001` manual-edit server) are
**dev-only** and intentionally not exposed publicly.

## Data sync (separate from code deploy)

Map data (PMTiles + GeoJSON in `data/export/`) is large and changes rarely, so
it is NOT part of the per-push deploy. After regenerating data locally:

```bash
VPS_HOST=<vps-ip> ./scripts/sync_data.sh
```

`sync_data.sh` rsyncs with `--chmod=D755,F644` so every file lands
world-readable. **This is the permanent fix for the `roads_temporal.geojson`
403** (a hand-uploaded file had mode 600 and nginx could not read it).

## Files

| File | Role |
|---|---|
| `scripts/setup_vps.sh` | one-time provisioner (user, dir, clone, nginx, certbot) |
| `scripts/deploy_vps.sh` | per-deploy (pull, stamp version, perms, nginx+TLS, reload). Env-overridable: `APP_DIR`, `APP_USER`, `SITE` |
| `scripts/sync_data.sh` | rsync `data/export/` → VPS with safe perms |
| `scripts/nginx/historymap.conf` | prod vhost |
| `scripts/nginx/historymap-stage.conf` | staging vhost |
| `rollback.sh` | reset the tenant to a prior commit, reload nginx |
| `.github/workflows/test.yml` | CI |
| `.github/workflows/deploy-prod.yml` | prod deploy on push to main |
| `.github/workflows/deploy-stage.yml` | staging deploy on `staging`-labeled PR |
| `.github/workflows/provision-vps.yml` | manual one-time provision |

## First-time setup (operator — needs creds I can't access)

1. **Secrets** (`asle-vaskinn/historymap` → Settings → Secrets and variables → Actions):
   - `VPS_SSH_KEY` — private key that can `ssh root@<vps>` (reuse the subscribe/nextbrain deploy key)
   - `VPS_HOST` — the shared VPS IP
   - `VPS_USER` — `root`
   - `GH_TOKEN` — PAT with `repo` scope (clone the private repo)
   - `LETSENCRYPT_EMAIL` — email for the LE account
2. **Environments**: create `production` and `staging` GitHub Environments (name only).
3. **DNS**: `historymap.vaskinn.eu  A  <vps-ip>` and `stage.historymap.vaskinn.eu  A  <vps-ip>`.
4. **Provision**: Actions → *Provision VPS* → type `provision`.
5. **Data**: `VPS_HOST=<vps-ip> ./scripts/sync_data.sh`.
6. **Verify** AC1–AC9, confirm subscribe + brain still serve 200, then
   decommission the old box `77.42.33.192`.

## Routine deploy

Just merge to `main`. `deploy-prod.yml` runs and the verify step confirms
`/version` matches the pushed SHA. Use the `staging` PR label to preview first.

## Rollback

```bash
ssh root@<vps> 'cd /opt/historymap && ./rollback.sh HEAD~1'
```

## Hotfix: a single data file 403s

Symptom: one `/data/...` file returns 403 while siblings return 200 → that file
is present but unreadable by nginx (wrong perms/owner). Fix:

```bash
ssh root@<vps> 'f=/opt/historymap/data/<file>; chmod 644 "$f"; chown historymap:historymap "$f"'
```

Prevent it by always uploading data via `scripts/sync_data.sh` (never `scp` a
single file by hand).
