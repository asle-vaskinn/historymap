# Backend API

FastAPI app (`app.py`) with a sequential subprocess job queue (`jobs.py`).
Listens on **:5000** inside the docker `backend` container; from the browser
or host it is reached via nginx at **`http://localhost:8080/api/`** — port
5000 is not published.

## Endpoint families

| Family | Endpoints |
|--------|-----------|
| Status & jobs | `GET /api/health`, `GET /api/status`, `GET /api/jobs/{id}`, `WS /api/logs` (live log stream) |
| ML workflow | `POST /api/generate-training`, `/api/train`, `/api/verify`, `/api/apply-annotations`; `GET|POST /api/annotations` |
| Sources CRUD | `GET|POST /api/sources`, `PUT|DELETE /api/sources/{id}` |
| Georeferencing | `POST /api/georeference`; `GET /api/georef/images`, `POST /api/georef/upload`, `GET|POST /api/georef/gcps/{map_id}`, `POST /api/georef/run`, `GET /api/georef/manifest`, `GET /api/georef/output/{map_id}` |
| Water editing | `GET /api/water`, `POST /api/water/add`, `/api/water/update`, `/api/water/delete` |
| Manual edits | `GET|POST /api/manual`, `POST /api/rebuild` (rerun merge+export) |
| Alignment | `POST /api/align`, `GET /api/alignment-report/{source}` |

Only one job runs at a time; job state is in-memory (lost on restart).

## Running

```bash
docker compose up -d          # full stack; backend is volume-mounted
docker compose restart backend  # after code changes (no rebuild needed)
# or standalone:
uvicorn backend.app:app --reload --host 0.0.0.0 --port 5000
```

See `AGENTS.md` §5 for full endpoint details and gotchas.
