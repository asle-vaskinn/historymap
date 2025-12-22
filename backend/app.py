"""
FastAPI backend for ML annotation workflow.

Provides REST API and WebSocket endpoints for:
- Pipeline status monitoring
- Background job execution (training, verification, etc.)
- Annotation management
- Real-time log streaming
"""

import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from backend.jobs import job_manager, JobStatus

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="Trondheim Historical Map - ML Annotation API",
    version="1.0.0"
)

# Enable CORS for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Paths (relative to /app in Docker)
TRAINING_DIR = Path("/app/data/training_1937")
CORRECTED_DIR = Path("/app/data/training_1937_corrected")
MODELS_DIR = Path("/app/models/checkpoints")
PREDICTIONS_DIR = Path("/app/data/sources/ml_detected/ortofoto1937/predictions")
VERIFICATION_FILE = Path("/app/data/sources/ml_detected/ortofoto1937/buildings_1937_verified.geojson")
ANNOTATIONS_FILE = Path("/app/data/annotations/annotations_1937.json")


# Pydantic models
class HealthResponse(BaseModel):
    status: str


class Annotation(BaseModel):
    osm_id: int
    existed: bool
    notes: Optional[str] = None


class AnnotationsRequest(BaseModel):
    annotations: List[Annotation]


class JobResponse(BaseModel):
    job_id: str
    name: str
    status: str
    message: str


# Startup/shutdown events
@app.on_event("startup")
async def startup_event():
    """Start the job manager."""
    await job_manager.start()
    logger.info("FastAPI backend started")


@app.on_event("shutdown")
async def shutdown_event():
    """Stop the job manager."""
    await job_manager.stop()
    logger.info("FastAPI backend stopped")


# Health check
@app.get("/api/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    return {"status": "ok"}


# Status endpoint
@app.get("/api/status")
async def get_status() -> Dict[str, Any]:
    """
    Get pipeline status.

    Returns:
    - training_tiles: count of training tiles
    - model_exists: whether trained model exists
    - model_metrics: latest model metrics (if available)
    - verification_stats: building verification statistics
    - annotations_count: number of annotations
    - current_job: currently running job (if any)
    - recent_jobs: list of recent jobs
    """
    status = {}

    # Training tiles
    if TRAINING_DIR.exists():
        images_dir = TRAINING_DIR / "images"
        if images_dir.exists():
            status["training_tiles"] = len(list(images_dir.glob("*.png")))
        else:
            status["training_tiles"] = 0
    else:
        status["training_tiles"] = 0

    # Corrected tiles
    if CORRECTED_DIR.exists():
        images_dir = CORRECTED_DIR / "images"
        if images_dir.exists():
            status["corrected_tiles"] = len(list(images_dir.glob("*.png")))
        else:
            status["corrected_tiles"] = 0
    else:
        status["corrected_tiles"] = 0

    # Model
    best_model = MODELS_DIR / "best_model.pth"
    status["model_exists"] = best_model.exists()

    # Model metrics (from training logs if available)
    log_file = Path("/app/results/training_logs/metrics.json")
    if log_file.exists():
        try:
            with open(log_file) as f:
                metrics = json.load(f)
                status["model_metrics"] = metrics
        except Exception as e:
            logger.error(f"Error reading metrics: {e}")
            status["model_metrics"] = None
    else:
        status["model_metrics"] = None

    # Verification stats
    if VERIFICATION_FILE.exists():
        try:
            with open(VERIFICATION_FILE) as f:
                data = json.load(f)
                features = data.get("features", [])
                status["verification_stats"] = {
                    "total_buildings": len(features),
                    "needs_verification": sum(
                        1 for f in features
                        if f.get("properties", {}).get("needs_verification", False)
                    )
                }
        except Exception as e:
            logger.error(f"Error reading verification file: {e}")
            status["verification_stats"] = None
    else:
        status["verification_stats"] = None

    # Annotations
    if ANNOTATIONS_FILE.exists():
        try:
            with open(ANNOTATIONS_FILE) as f:
                data = json.load(f)
                annotations = data.get("annotations", [])
                status["annotations_count"] = len(annotations)
        except Exception as e:
            logger.error(f"Error reading annotations: {e}")
            status["annotations_count"] = 0
    else:
        status["annotations_count"] = 0

    # Current job
    current_job = job_manager.get_current_job()
    if current_job:
        status["current_job"] = current_job.to_dict()
    else:
        status["current_job"] = None

    # Recent jobs (last 10)
    all_jobs = job_manager.get_all_jobs()
    recent_jobs = sorted(all_jobs, key=lambda j: j.created_at, reverse=True)[:10]
    status["recent_jobs"] = [job.to_dict() for job in recent_jobs]

    return status


# Generate training data
@app.post("/api/generate-training", response_model=JobResponse)
async def generate_training(tiles: int = 50):
    """
    Generate training data from 1937 aerial photos.

    Args:
        tiles: Number of training tiles to generate (default: 50)
    """
    # Check if job is already running
    current_job = job_manager.get_current_job()
    if current_job:
        raise HTTPException(
            status_code=409,
            detail=f"Job already running: {current_job.name}"
        )

    # Submit job
    job = await job_manager.submit_job(
        name="generate_training",
        command=[
            "python3",
            "/app/scripts/generate_1937_training_data.py",
            "--output", str(TRAINING_DIR),
            "--tiles", str(tiles)
        ]
    )

    return {
        "job_id": job.job_id,
        "name": job.name,
        "status": job.status,
        "message": f"Training data generation started ({tiles} tiles)"
    }


# Train model
@app.post("/api/train", response_model=JobResponse)
async def train_model(config: str = "ml/config_1937.yaml"):
    """
    Train ML model on training data.

    Args:
        config: Path to training configuration (default: ml/config_1937.yaml)
    """
    # Check if job is already running
    current_job = job_manager.get_current_job()
    if current_job:
        raise HTTPException(
            status_code=409,
            detail=f"Job already running: {current_job.name}"
        )

    # Check if training data exists
    if not TRAINING_DIR.exists() or not (TRAINING_DIR / "images").exists():
        raise HTTPException(
            status_code=400,
            detail="Training data not found. Generate training data first."
        )

    # Submit job
    job = await job_manager.submit_job(
        name="train",
        command=[
            "python3",
            "/app/ml/train.py",
            "--config", f"/app/{config}"
        ]
    )

    return {
        "job_id": job.job_id,
        "name": job.name,
        "status": job.status,
        "message": "Model training started"
    }


# Apply annotations
@app.post("/api/apply-annotations", response_model=JobResponse)
async def apply_annotations(request: AnnotationsRequest):
    """
    Apply human annotations to training data.

    This will:
    1. Save annotations to file
    2. Run apply_annotations.py to update training masks
    3. Run verify_1937_buildings.py to regenerate verification data
    """
    # Check if job is already running
    current_job = job_manager.get_current_job()
    if current_job:
        raise HTTPException(
            status_code=409,
            detail=f"Job already running: {current_job.name}"
        )

    # Save annotations
    ANNOTATIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    annotations_data = {
        "annotations": [ann.dict() for ann in request.annotations],
        "updated_at": None  # Will be set by job
    }

    try:
        with open(ANNOTATIONS_FILE, 'w') as f:
            json.dump(annotations_data, f, indent=2)
        logger.info(f"Saved {len(request.annotations)} annotations to {ANNOTATIONS_FILE}")
    except Exception as e:
        logger.error(f"Error saving annotations: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to save annotations: {str(e)}")

    # Submit job to apply annotations and verify
    job = await job_manager.submit_job(
        name="apply_annotations",
        command=[
            "sh", "-c",
            f"python3 /app/scripts/apply_annotations.py --annotations {ANNOTATIONS_FILE} --output {CORRECTED_DIR} && "
            f"python3 /app/scripts/verify_1937_buildings.py"
        ]
    )

    return {
        "job_id": job.job_id,
        "name": job.name,
        "status": job.status,
        "message": f"Applying {len(request.annotations)} annotations"
    }


# Verify predictions
@app.post("/api/verify", response_model=JobResponse)
async def verify_predictions():
    """
    Run verification on ML predictions.

    Compares ML predictions with modern OSM to flag suspicious buildings.
    """
    # Check if job is already running
    current_job = job_manager.get_current_job()
    if current_job:
        raise HTTPException(
            status_code=409,
            detail=f"Job already running: {current_job.name}"
        )

    # Submit job
    job = await job_manager.submit_job(
        name="verify",
        command=[
            "python3",
            "/app/scripts/verify_1937_buildings.py"
        ]
    )

    return {
        "job_id": job.job_id,
        "name": job.name,
        "status": job.status,
        "message": "Verification started"
    }


# Get annotations
@app.get("/api/annotations")
async def get_annotations():
    """Get current annotations."""
    if not ANNOTATIONS_FILE.exists():
        return {"annotations": [], "updated_at": None}

    try:
        with open(ANNOTATIONS_FILE) as f:
            data = json.load(f)
            return data
    except Exception as e:
        logger.error(f"Error reading annotations: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to read annotations: {str(e)}")


# Save annotations
@app.post("/api/annotations")
async def save_annotations(request: AnnotationsRequest):
    """
    Save annotations (without applying them).

    This just saves the annotations file for later use.
    To apply annotations to training data, use /api/apply-annotations.
    """
    ANNOTATIONS_FILE.parent.mkdir(parents=True, exist_ok=True)

    annotations_data = {
        "annotations": [ann.dict() for ann in request.annotations],
        "updated_at": None  # Could add timestamp here
    }

    try:
        with open(ANNOTATIONS_FILE, 'w') as f:
            json.dump(annotations_data, f, indent=2)
        logger.info(f"Saved {len(request.annotations)} annotations")
        return {"message": f"Saved {len(request.annotations)} annotations"}
    except Exception as e:
        logger.error(f"Error saving annotations: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to save annotations: {str(e)}")


# Get job status
@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str):
    """Get job details by ID."""
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job.to_dict()


# WebSocket for real-time logs
@app.websocket("/api/logs")
async def websocket_logs(websocket: WebSocket):
    """
    WebSocket endpoint for streaming job logs.

    Clients can connect to receive real-time log messages from running jobs.
    """
    await websocket.accept()
    client_queue = job_manager.add_ws_client()

    try:
        # Send initial connection message
        await websocket.send_json({
            "type": "connected",
            "message": "Connected to log stream"
        })

        # Send current job status if any
        current_job = job_manager.get_current_job()
        if current_job:
            await websocket.send_json({
                "type": "job_status",
                "job": current_job.to_dict()
            })

        # Stream logs
        while True:
            # Get log message from queue
            log_msg = await client_queue.get()
            await websocket.send_json(log_msg)

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}", exc_info=True)
    finally:
        job_manager.remove_ws_client(client_queue)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)
