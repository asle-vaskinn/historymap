# Backend Quick Start Guide

## Prerequisites

- Docker and Docker Compose installed
- Project already has `docker-compose.yml` configured
- FastAPI dependencies in `requirements.txt`

## Quick Start

### 1. Start the Backend

```bash
# From project root
cd /Users/vaskinn/Development/private/historymap

# Start backend service
docker compose up backend

# Or start in background
docker compose up -d backend
```

The backend will be available at `http://localhost:8080/api/` (through nginx proxy).

### 2. Verify It's Running

```bash
# Health check
curl http://localhost:8080/api/health
# Should return: {"status":"ok"}

# Get status
curl http://localhost:8080/api/status
# Should return pipeline status with counts
```

### 3. Test with Client

```bash
# Run test client
python3 backend/test_client.py
```

## Common Operations

### Generate Training Data

```bash
curl -X POST "http://localhost:8080/api/generate-training?tiles=50"
```

Returns:
```json
{
  "job_id": "generate_training_1703001234",
  "name": "generate_training",
  "status": "pending",
  "message": "Training data generation started (50 tiles)"
}
```

### Monitor Progress

**Option 1: View logs**
```bash
docker compose logs -f backend
```

**Option 2: WebSocket (Browser Console)**
```javascript
const ws = new WebSocket('ws://localhost:8080/api/logs');
ws.onmessage = (e) => console.log(JSON.parse(e.data).message);
```

**Option 3: Check status**
```bash
watch -n 2 'curl -s http://localhost:8080/api/status | jq .current_job'
```

### Train Model

```bash
# After training data is generated
curl -X POST http://localhost:8080/api/train
```

### Apply Annotations

```bash
curl -X POST http://localhost:8080/api/apply-annotations \
  -H "Content-Type: application/json" \
  -d '{
    "annotations": [
      {"osm_id": 123456, "existed": true, "notes": "Verified in 1937 photo"},
      {"osm_id": 789012, "existed": false, "notes": "Built after 1937"}
    ]
  }'
```

## Development

### Restart After Code Changes

```bash
docker compose restart backend
```

### View Logs

```bash
# Follow logs
docker compose logs -f backend

# Last 100 lines
docker compose logs --tail=100 backend
```

### Rebuild After Dependency Changes

```bash
docker compose build backend
docker compose up backend
```

## Troubleshooting

### Backend container exits immediately

```bash
# Check logs
docker compose logs backend

# Common issues:
# - Import errors: rebuild with `docker compose build backend`
# - Port conflicts: ensure port 5000 is available
```

### API returns 502 Bad Gateway

```bash
# Check if backend is running
docker compose ps

# Restart services
docker compose restart backend web
```

### Jobs fail silently

```bash
# Check backend logs
docker compose logs -f backend

# Verify script paths
docker compose exec backend ls /app/scripts/

# Test script manually
docker compose exec backend python3 /app/scripts/generate_1937_training_data.py --help
```

### WebSocket disconnects

```bash
# Check nginx logs
docker compose logs web

# Verify nginx config has WebSocket support
docker compose exec web cat /etc/nginx/conf.d/default.conf | grep -A5 "/api/"
```

## API Endpoints Reference

### Status & Health
- `GET /api/health` - Health check
- `GET /api/status` - Complete pipeline status

### Jobs
- `POST /api/generate-training?tiles=N` - Generate training data (default N=50)
- `POST /api/train?config=path` - Train model (default config=ml/config_1937.yaml)
- `POST /api/verify` - Verify predictions against modern OSM
- `POST /api/apply-annotations` - Apply annotations + verify
- `GET /api/jobs/{job_id}` - Get job details

### Annotations
- `GET /api/annotations` - Get saved annotations
- `POST /api/annotations` - Save annotations

### WebSocket
- `WS /api/logs` - Real-time log streaming

## File Locations

Inside the backend container:
- Scripts: `/app/scripts/`
- ML code: `/app/ml/`
- Training data: `/app/data/training_1937/`
- Corrected data: `/app/data/training_1937_corrected/`
- Models: `/app/models/checkpoints/`
- Annotations: `/app/data/annotations/annotations_1937.json`

These are mounted from the host via Docker volumes.

## Next Steps

1. **Generate training data**: `POST /api/generate-training?tiles=10` (start small)
2. **Monitor via WebSocket**: Connect to `/api/logs`
3. **Check status**: `GET /api/status` should show training tiles
4. **Train model**: `POST /api/train`
5. **Verify predictions**: `POST /api/verify`
6. **Apply annotations**: Use frontend UI or API directly

## Architecture

```
Client Request
    ↓
Nginx (port 8080)
    ↓ proxy to backend:5000
FastAPI Backend
    ↓
Job Manager (queue)
    ↓
Python Scripts (subprocess)
    ↓
File System (mounted volumes)
```

## Production Considerations

Before deploying to production:

1. **Update CORS settings** in `backend/app.py`:
   ```python
   allow_origins=["https://your-domain.com"]
   ```

2. **Add authentication** (API keys or OAuth)

3. **Enable HTTPS** in nginx

4. **Add rate limiting**

5. **Configure logging** to persistent storage

6. **Set up monitoring** (health checks, metrics)

7. **Add database** for job persistence

8. **Configure backups** for data directory

## Help

For detailed documentation, see:
- `backend/README.md` - Full API documentation
- `backend/IMPLEMENTATION.md` - Implementation details
- `backend/test_client.py` - Example usage

For issues, check:
- Backend logs: `docker compose logs backend`
- Web logs: `docker compose logs web`
- Job output: Connect to WebSocket at `/api/logs`
