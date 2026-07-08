# CI/CD + VPS Consolidation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to
> implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.
> NOTE: This is infrastructure work — not all tasks are TDD-shaped. Where a task
> changes app code (e.g. the `/version` endpoint), write the test first.

**Goal:** Give historymap automated CI + deploy by reusing the `subscribe`/`nextbrain`
GitHub-Actions harness, and consolidate the live site onto the shared Hetzner VPS
(`62.238.25.113`) as tenant #3.

**Architecture:** Static-only nginx tenant (frontend + `/data/` + `/wms/` proxy) on
the shared VPS, following `nextbrain/DEPLOY.md`. Code deploys on push to `main`;
heavy tile data syncs separately via rsync.

**Tech Stack:** GitHub Actions, nginx, certbot, rsync, bash; Python/pytest + Node
syntax checks for CI. Reference repos: `/Users/vaskinn/Development/NTNUI/subscribe`,
`/Users/vaskinn/Development/personlig/nextbrain`.

**Spec:** `docs/spec/feat_cicd/SPEC.md` (acceptance criteria AC1–AC10).

---

## Phase 0 — Discovery & headroom (do first; some steps need the user)

### Task 0.1: Confirm VPS headroom (USER + agent)
- [ ] Get SSH access to `62.238.25.113` (user provides key/host).
- [ ] Run: `ssh root@62.238.25.113 'df -h /; free -m; nproc; du -sh /opt/* 2>/dev/null'`
- [ ] Record free disk vs. local `du -sh data/export` footprint in `docs/tech/DEPLOYMENT.md`.
- [ ] Decision gate: if free disk < (data footprint × 2), document mitigation (external volume / object storage) before proceeding. (AC10)

### Task 0.2: Capture current prod topology
- [ ] On the **old** box `77.42.33.192`: `ssh ... 'nginx -T 2>/dev/null | sed -n "1,120p"; ls -la /usr/share/nginx/html /var/www 2>/dev/null'`
- [ ] Note where the frontend + data live and whether `/wms/` is proxied. Write findings to `docs/tech/DEPLOYMENT.md`.

---

## Phase 1 — CI (no secrets needed; ship first, AC1)

### Task 1.1: Add the `/version` endpoint for deploy verification (AC2)
**Files:**
- Create: `frontend/version.txt` (placeholder `dev`; deploy script writes the real SHA)
- nginx serves `location = /version` from this file (Task 2.1)
- Test: `tests/test_version_contract.py`

- [ ] **Step 1 — failing test:**
```python
# tests/test_version_contract.py
from pathlib import Path
def test_version_placeholder_exists():
    assert Path("frontend/version.txt").exists()
```
- [ ] **Step 2 — run, expect FAIL** (file missing): `PYTHONPATH=scripts pytest tests/test_version_contract.py -v`
- [ ] **Step 3 — create** `frontend/version.txt` containing `dev`.
- [ ] **Step 4 — run, expect PASS.**
- [ ] **Step 5 — commit:** `git add frontend/version.txt tests/test_version_contract.py && git commit -m "feat: add /version contract for deploy verification"`

### Task 1.2: Create `.github/workflows/test.yml`
**Files:** Create `.github/workflows/test.yml` (adapt from `subscribe/.github/workflows/test.yml`).
- [ ] CI runs on `pull_request` + `push` to non-main branches.
- [ ] Jobs: `node --check frontend/app.js`; `PYTHONPATH=scripts python -m pytest tests/`; `docker compose config -q`.
- [ ] Push branch, open PR, confirm the check appears and gates merge (AC1).
- [ ] Commit.

---

## Phase 2 — Tenant provisioning scripts (mirror nextbrain conventions)

### Task 2.1: nginx vhost
**Files:** Create `scripts/nginx/historymap.conf` (model on `nextbrain/scripts/nginx/nextbrain.conf` + dev `nginx.conf`).
- [ ] `server_name historymap.vaskinn.eu;`
- [ ] `location /` → `root /opt/historymap/frontend;` static.
- [ ] `location /data/` → static; **`gzip off;`** and ensure Range requests pass (direct file serving). (AC5)
- [ ] `location = /version` → serves `/opt/historymap/frontend/version.txt`. (AC2)
- [ ] `location /wms/` → copy the two `proxy_pass` blocks (Trondheim kommune + Geonorge) verbatim from dev `nginx.conf:73-103`. (AC6)
- [ ] Commit.

### Task 2.2: Provisioner `scripts/setup_vps.sh`
**Files:** Create `scripts/setup_vps.sh` (model on `nextbrain/scripts/setup_vps.sh`).
- [ ] Idempotent, non-destructive to other tenants. Creates user `historymap`, dir `/opt/historymap`, installs the nginx vhost, runs `certbot --nginx -d historymap.vaskinn.eu`.
- [ ] No systemd app unit (static-only). If a backend is later needed, reserve port 8200.
- [ ] Commit.

### Task 2.3: Deploy script `scripts/deploy_vps.sh`
**Files:** Create `scripts/deploy_vps.sh` (model on `nextbrain/scripts/deploy_vps.sh`).
- [ ] `cd /opt/historymap && git fetch origin <ref> && git reset --hard origin/<ref>`
- [ ] Write SHA: `git rev-parse --short HEAD > frontend/version.txt`
- [ ] Re-apply nginx vhost if changed; `nginx -t && systemctl reload nginx`.
- [ ] Does NOT touch `/opt/historymap/data` (data synced separately).
- [ ] Commit.

### Task 2.4: Data sync `scripts/sync_data.sh`
**Files:** Create `scripts/sync_data.sh`.
- [ ] `rsync -avz --delete data/export/ root@<VPS_HOST>:/opt/historymap/data/`
- [ ] Document that this runs manually / on data regeneration, not per push.
- [ ] Commit.

---

## Phase 3 — Deploy workflows (adapt subscribe)

### Task 3.1: `.github/workflows/deploy-prod.yml`
**Files:** Create `.github/workflows/deploy-prod.yml` (adapt `subscribe/.github/workflows/deploy-prod.yml`).
- [ ] Trigger: push to `main` + `workflow_dispatch`; `concurrency: deploy-prod`; `environment: production`.
- [ ] SSH heredoc → `git config --global --add safe.directory /opt/historymap` → `cd /opt/historymap` → `bash scripts/deploy_vps.sh main`.
- [ ] Verify step: poll `https://historymap.vaskinn.eu/version` until it equals `${GITHUB_SHA:0:7}` (60s budget). (AC3)
- [ ] Commit.

### Task 3.2: `.github/workflows/deploy-stage.yml`
**Files:** Create `.github/workflows/deploy-stage.yml` (adapt subscribe's `staging`-label deploy).
- [ ] Trigger on PRs carrying the `staging` label; deploy head branch to `stage.historymap.vaskinn.eu`. (AC7)
- [ ] Commit.

### Task 3.3: `.github/workflows/provision-vps.yml`
**Files:** Create `.github/workflows/provision-vps.yml` (adapt `nextbrain/.github/workflows/provision-vps.yml`).
- [ ] Manual `workflow_dispatch` (type `provision`) → SSH → `bash scripts/setup_vps.sh`.
- [ ] Commit.

### Task 3.4: Rollback
**Files:** Create `rollback.sh` (adapt `subscribe/rollback.sh`).
- [ ] `./rollback.sh HEAD~1` resets `/opt/historymap` to a prior SHA and reloads nginx. (AC8)
- [ ] Commit.

---

## Phase 4 — Cleanup, docs, cutover

### Task 4.1: Retire dead scaffolding (AC9)
- [x] Delete or mark deprecated: `production/deploy-cloudflare.sh`, `production/deploy-github-pages.sh` — entire `production/` dir removed 2026-07-04.
- [x] Fix or remove the broken `production/Dockerfile` — removed with the directory.
- [x] Commit.

### Task 4.2: `docs/tech/DEPLOYMENT.md` (AC9)
- [ ] Authoritative runbook: VPS, tenant layout, port block, the workflows, the data-sync step, rollback, and the user-only steps (DNS, secrets, provision).
- [ ] Commit.

### Task 4.3: Cutover (USER)
- [ ] Add GitHub secrets (`VPS_SSH_KEY`, `VPS_HOST`, `VPS_USER`, `GH_TOKEN`) + `production` Environment.
- [ ] Run Provision VPS workflow once; sync data with `scripts/sync_data.sh`.
- [ ] Repoint DNS `historymap.vaskinn.eu A 62.238.25.113` (+ `stage.`).
- [ ] Verify AC1–AC9 pass; confirm subscribe + brain still 200 (AC4).
- [ ] Decommission `77.42.33.192`.

---

## Self-review notes
- Spec AC1–AC10 each map to a task: AC1→1.2, AC2→1.1, AC3→3.1, AC4→4.3 verify, AC5/AC6→2.1, AC7→3.2, AC8→3.4, AC9→4.1/4.2, AC10→0.1.
- Naming is consistent: `version.txt`, `scripts/deploy_vps.sh`, `scripts/setup_vps.sh`, `/opt/historymap`.
- User-only blockers (DNS/secrets/SSH) are isolated in Tasks 0.1, 4.3.
