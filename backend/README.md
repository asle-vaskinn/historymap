# Backend API for ML Annotation Workflow

FastAPI backend that provides REST API and WebSocket endpoints for the ML annotation workflow.

## Features

- **Pipeline Status Monitoring**: Track training data, model metrics, verification stats
- **Background Job Execution**: Run training, verification, and annotation tasks
- **Annotation Management**: Save and apply human annotations
- **Real-time Log Streaming**: WebSocket-based log streaming for job output

## API Endpoints

### Health & Status

- `GET /api/health` - Health check
- `GET /api/status` - Get pipeline status (training tiles, model metrics, verification stats, current job)

### Jobs

- `POST /api/generate-training?tiles=50` - Generate training data from 1937 aerial photos
- `POST /api/train?config=ml/config_1937.yaml` - Train ML model
- `POST /api/verify` - Run verification on ML predictions
- `POST /api/apply-annotations` - Apply annotations and regenerate training data
- `GET /api/jobs/{job_id}` - Get job status by ID

### Annotations

- `GET /api/annotations` - Get current annotations
- `POST /api/annotations` - Save annotations (without applying)

### WebSocket

- `WS /api/logs` - Real-time log streaming

## Architecture

```
FastAPI Application (app.py)
    ├── Job Manager (jobs.py)
    │   ├── Job Queue (one job at a time)
    │   ├── Subprocess Execution
    │   └── WebSocket Broadcasting
    └── API Endpoints
        ├── REST endpoints for job control
        └── WebSocket for log streaming
```

## Job Management

Jobs run as background processes (asyncio subprocess). Only one job can run at a time to prevent resource conflicts. Logs are captured in real-time and broadcast to all connected WebSocket clients.

### Job States

- `pending` - Queued, waiting to run
- `running` - Currently executing
- `completed` - Finished successfully
- `failed` - Failed with error

## Development

### Running Locally

```bash
# Install dependencies
pip install -r requirements.txt

# Run the server
uvicorn backend.app:app --reload --host 0.0.0.0 --port 5000
```

### Running with Docker

```bash
# Build and start
docker compose up backend

# View logs
docker compose logs -f backend
```

## File Paths

All paths are relative to `/app` in the Docker container:

- Training data: `/app/data/training_1937/`
- Corrected data: `/app/data/training_1937_corrected/`
- Model checkpoints: `/app/models/checkpoints/`
- Predictions: `/app/data/sources/ml_detected/ortofoto1937/predictions/`
- Verification: `/app/data/sources/ml_detected/ortofoto1937/buildings_1937_verified.geojson`
- Annotations: `/app/data/annotations/annotations_1937.json`
- Scripts: `/app/scripts/`
- ML code: `/app/ml/`

## Example Usage

### 1. Generate Training Data

```bash
curl -X POST http://localhost:8080/api/generate-training?tiles=50
```

Response:
```json
{
  "job_id": "generate_training_1703001234",
  "name": "generate_training",
  "status": "pending",
  "message": "Training data generation started (50 tiles)"
}
```

### 2. Monitor Job Progress

Connect to WebSocket:
```javascript
const ws = new WebSocket('ws://localhost:8080/api/logs');
ws.onmessage = (event) => {
  const msg = JSON.parse(event.data);
  console.log(msg.message);
};
```

### 3. Train Model

```bash
curl -X POST http://localhost:8080/api/train
```

### 4. Apply Annotations

```bash
curl -X POST http://localhost:8080/api/apply-annotations \
  -H "Content-Type: application/json" \
  -d '{
    "annotations": [
      {"osm_id": 123456, "existed": true, "notes": "Confirmed"},
      {"osm_id": 789012, "existed": false, "notes": "Built after 1937"}
    ]
  }'
```

## CORS

CORS is enabled for all origins in development. For production, update the `allow_origins` in `app.py` to specify the frontend URL.

## Logging

All logs are written to stdout and can be viewed with `docker compose logs -f backend`.

WebSocket clients receive real-time logs from running jobs.
