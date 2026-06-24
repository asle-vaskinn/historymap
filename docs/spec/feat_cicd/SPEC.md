# Feature Spec: CI/CD + VPS Consolidation

**Status:** Proposed (awaiting `/implement`)
**Date:** 2026-06-20
**Owner:** vaskinn

## Why

historymap currently has **no CI and no automated deploy**. The live site
(`historymap.vaskinn.eu`) runs on a **dedicated Hetzner box `77.42.33.192`** as
bare nginx, updated by hand. Meanwhile the user already operates a **mature
multi-tenant Hetzner VPS (`62.238.25.113`)** hosting `subscribe`
(`permen.studenterhytta.org`) and `nextbrain` (`brain.vaskinn.eu`) with a proven
GitHub-Actions-driven deploy harness and a documented tenant-onboarding pattern
(`nextbrain/DEPLOY.md`).

**Goal:** Adopt that harness for historymap and consolidate the site onto the
shared VPS as **tenant #3**, retiring the dedicated box.

## Decisions (approved)

| Decision | Choice |
|---|---|
| Hosting | Consolidate onto shared VPS `62.238.25.113`, following `nextbrain/DEPLOY.md` |
| Harness reuse | Full: CI (`test`) + `deploy-prod` + `deploy-stage` + rollback |
| Prod app shape | **Static-only** (frontend + `/data/` + `/wms/` proxy). Confirmed: live site is bare nginx with no backend. `/api/` (FastAPI job queue) is a **dev/admin tool**, not exposed in public prod |
| Port block | historymap = **8200–8299** (subscribe 8000s, nextbrain 8100s). Reserved only if/when a backend service is ever added; static-only prod needs no app port |
| App dir / user | `/opt/historymap`, system user `historymap` (isolated from other tenants) |
| Domain | `historymap.vaskinn.eu` — repoint A record `77.42.33.192` → `62.238.25.113` |
| TLS | certbot `--nginx` for `historymap.vaskinn.eu` |
| Staging | `stage.historymap.vaskinn.eu` (or PR-label deploy, matching subscribe's `staging` label convention) |

## Architecture (tenant model)

```
GitHub push to main
  → .github/workflows/test.yml         (CI: node --check, pytest, validate scripts)
  → .github/workflows/deploy-prod.yml  (SSH to VPS → scripts/deploy_vps.sh)
       on VPS:
         /opt/historymap            git checkout (code: frontend/ + nginx conf)
         /opt/historymap/data       PMTiles/GeoJSON/raster (synced separately — large, rarely changes)
         nginx vhost historymap.vaskinn.eu:
            /            → static frontend
            /data/       → static, HTTP Range enabled, gzip OFF (PMTiles requirement)
            /wms/        → proxy_pass to Trondheim kommune + Geonorge (mirror dev nginx.conf)
         certbot TLS
  → verify step: GET https://historymap.vaskinn.eu/version returns deployed SHA
```

### Data-sync strategy (the heavy part)

historymap is the **heaviest tenant**: `data/export/` holds PMTiles + raster
tiles that can be hundreds of MB–GBs and are produced by a slow pipeline
(tippecanoe, ML). Therefore:

- **Code** (frontend, nginx conf, scripts) deploys on every push to `main` —
  small, fast, git-tracked.
- **Data** syncs via a **separate `rsync` step** (manual `workflow_dispatch` or a
  local `scripts/sync_data.sh`), NOT on every push. Data is generated locally
  (or on a build runner), then rsynced to `/opt/historymap/data`. It is **never
  committed to git**.

## Acceptance Criteria

- **AC1 — CI gate:** Every PR to `main` runs `node --check frontend/app.js`,
  `PYTHONPATH=scripts pytest tests/`, and `docker compose config`. A failure
  blocks merge.
- **AC2 — Version endpoint:** Prod serves `/version` returning the deployed git
  SHA (so the deploy workflow can verify convergence, matching subscribe).
- **AC3 — Auto prod deploy:** Push to `main` → site updates on the shared VPS,
  and the workflow's verify step confirms `/version` == pushed SHA within 60s.
- **AC4 — Tenant isolation:** historymap touches only its own
  user/dir/service/nginx-vhost/cert. A historymap deploy or data sync **cannot**
  break subscribe or nextbrain. Verified: subscribe + brain still serve 200 after
  a historymap deploy.
- **AC5 — PMTiles integrity:** `/data/*.pmtiles` served with HTTP Range support
  and **no gzip**; map renders with no MapLibre/PMTiles console errors.
- **AC6 — WMS proxy:** `/wms/` paths the frontend uses resolve in prod (mirrors
  dev `nginx.conf`).
- **AC7 — Staging:** A `staging`-labelled PR (or push to a stage branch) deploys
  to `stage.historymap.vaskinn.eu` for manual smoke testing.
- **AC8 — Rollback:** A documented one-command rollback restores the previous
  release (adapt subscribe's `rollback.sh`).
- **AC9 — Docs:** `docs/tech/DEPLOYMENT.md` is the authoritative runbook; a fresh
  session could deploy from it. Dead `production/deploy-cloudflare.sh` and
  `deploy-github-pages.sh` are removed or marked deprecated.
- **AC10 — Headroom:** Before cutover, the VPS is confirmed to have CPU/RAM/disk
  headroom for historymap's data footprint; if not, document the mitigation
  (e.g. serve PMTiles from object storage / external volume).

## Out of Scope

- Exposing the FastAPI backend / job queue (`/api/`) or the editing tools
  (`source_manager`, `feature_extraction`) in public prod — these stay dev-only.
- ML training/inference automation in CI.
- Re-architecting the data pipeline.

## Items only the user can do (no creds in this env)

1. Repoint DNS `historymap.vaskinn.eu A 62.238.25.113` (+ `stage.` record).
2. Add GitHub Actions secrets to `asle-vaskinn/historymap`: `VPS_SSH_KEY`,
   `VPS_HOST`, `VPS_USER=root` (reuse the same deploy key as subscribe/nextbrain),
   `GH_TOKEN`.
3. Create the `production` GitHub Environment.
4. Run the one-time **Provision VPS** workflow after secrets + DNS are set.
5. Decommission `77.42.33.192` only after AC1–AC10 pass on the shared VPS.
