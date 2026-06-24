# Archive — Frozen Historical Reports

These files are **stale snapshots** from earlier development phases, kept only for
historical reference. **Do not treat anything here as current truth.** Most of it
predates the working pipeline, the `source_viewer`→`feature_extraction` rename, and the
move of `dataprep.*` into `frontend/legacy/`.

For the current state of the project, read instead:

| Topic | Authoritative source |
|-------|----------------------|
| What the project is + how to run it | [`/README.md`](../../README.md) |
| Session rules for agents | [`/CLAUDE.md`](../../CLAUDE.md) |
| Full codebase map (architecture, ports, schemas, gotchas) | [`/AGENTS.md`](../../AGENTS.md) |
| What's in flight right now | [`../todo/current_work.md`](../todo/current_work.md) |
| Known loose ends | [`../tech/IMPLEMENTATION_STATUS.md`](../tech/IMPLEMENTATION_STATUS.md) |
| Testing | [`/TESTING.md`](../../TESTING.md) |

## What's here

- `HISTORICAL_MAP_PROJECT_PLAN.md` — original 5-phase development roadmap.
- `PHASE2..5_*.md` — per-phase completion summaries and quickstarts (synthetic data,
  ML training, real-data integration, production deployment).
- `QUICKSTART.md` — early getting-started guide (superseded by the root README + AGENTS.md §2).
- `PMTILES_IMPLEMENTATION.md` — notes from the initial PMTiles integration (now standard;
  see AGENTS.md §6).
- `SOURCE_FILTER_FIX.md` — notes from a one-off source-filter bug fix.

These were moved here from the repo root on 2026-06-14 to declutter the working tree.
