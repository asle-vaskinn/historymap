# CLAUDE.md

This file provides guidance to Claude Code when working with this repository.

## Project Overview

**Trondheim Historical Map** - Interactive web application for exploring Trondheim's development from 1700 to present using ML-extracted features from historical Kartverket maps combined with modern OSM data.

## Workflow System

### Document-Driven Development

All changes follow a structured workflow through documentation layers:

```
docs/need/     → What we want to achieve (requirements, user stories)
docs/spec/     → Product specifications (features, acceptance criteria)
docs/tech/     → Technical decisions (architecture, schemas, instructions)
docs/todo/     → Task tracking (current work, backlog)
```

### Change Request Workflow

**Every request MUST follow this process:**

1. **PROPOSE** (`/propose`) - Analyze request, propose doc changes
2. **APPROVE** - User reviews and approves high-level changes
3. **IMPLEMENT** (`/implement`) - Agents execute approved work
4. **TEST** (`/test`) - Run tests, fix issues
5. **SYNC** (`/sync`) - Ensure docs are aligned with code

### Commands

| Command | Purpose |
|---------|---------|
| `/propose <request>` | Analyze request, show doc changes needed |
| `/implement` | Execute approved changes using agents |
| `/test` | Run tests and fix failures |
| `/sync` | Check doc/code alignment, fix drift |
| `/status` | Show project status |
| `/doctor` | Health check |

### Agent Strategy

Work is split across specialized agents:

- **Research agents** - Explore codebase, gather context
- **Implementation agents** - Write code in parallel
- **Test agents** - Run tests, verify changes
- **Doc agents** - Update documentation

User discusses high-level decisions while agents handle execution.

## Auto-Approval Rules

The following are auto-approved (git protects us):

### Always Approved
- Read operations (Glob, Grep, Read)
- Git operations (status, diff, log, add, commit)
- Docker operations (build, up, down, restart)
- Python/Node execution
- Test running
- Documentation edits in `docs/`

### Require Approval
- New file creation outside established patterns
- Destructive operations (rm, reset --hard)
- External network calls to new domains
- Schema changes

## Architecture

```
Frontend (MapLibre GL JS + PMTiles)
         │
         ▼
Vector Tiles with temporal attributes (sd, ed, ev, src)
         ▲
         │
ML Pipeline (U-Net) ─────► Vectorization
         ▲
         │
Synthetic Training Data (aged OSM + masks)
```

## Data Schema

Normalized building schema (see `docs/tech/DATA_SCHEMA.md`):

| Field | Type | Description |
|-------|------|-------------|
| `src` | string | Source: osm, sef, ml, man, tk, mat |
| `sd` | int | Start date (construction year) |
| `ed` | int/null | End date (demolition year) |
| `ev` | string | Evidence: h (high), m (medium), l (low) |
| `nm` | string | Building name |
| `_raw` | object | Original properties |

## Key Paths

| Path | Purpose |
|------|---------|
| `frontend/` | MapLibre application |
| `ml/` | PyTorch training/inference |
| `scripts/` | Data pipeline scripts |
| `data/sources/` | Normalized data per source |
| `data/merged/` | Merged output |
| `docs/` | All documentation |
| `.claude/commands/` | Workflow commands |

## Common Commands

```bash
# Development
docker compose up                    # Start server
docker compose restart              # Restart after changes

# Data Pipeline
PYTHONPATH=scripts python3 scripts/pipeline.py --stage all
PYTHONPATH=scripts python3 scripts/normalize/normalize_manual.py

# Testing
./scripts/validate_phase1.sh
./scripts/validate_phase5.sh
node --check frontend/app.js        # Validate JS syntax

# ML
python ml/train.py --config ml/config.yaml
python ml/predict.py --checkpoint models/checkpoints/best_model.pth --input image.png
```

## Testing Requirements

Before any PR/commit:
1. `node --check frontend/app.js` - JavaScript syntax
2. `docker compose restart` - Server still works
3. Browser console - No MapLibre errors
4. Relevant validation script

## Documentation Rules

### When Updating Docs

1. **Never delete** without explicit user approval
2. **Mark deprecated** instead of removing
3. **Add changelog** entries for significant changes
4. **Cross-reference** related docs

### Document Types

- `need/*.md` - User-facing requirements (WHY)
- `spec/*.md` - Product specifications (WHAT)
- `spec/feat_*/` - Feature specifications
- `tech/*.md` - Technical architecture (HOW)
- `todo/*.md` - Task tracking

## Git Safety

- All changes protected by git
- Commit frequently with descriptive messages
- Never force push to main
- Use branches for risky changes
