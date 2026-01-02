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
import time
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
WATER_FILE = Path("/app/data/sources/manual/water.geojson")


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


class WaterFeature(BaseModel):
    type: str = "Feature"
    geometry: Dict[str, Any]
    properties: Dict[str, Any]


class WaterUpdate(BaseModel):
    id: str
    name: Optional[str] = None
    wtype: Optional[str] = None
    sd: Optional[int] = None
    ed: Optional[int] = None


class WaterDelete(BaseModel):
    id: str


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


# Map sources catalog
@app.get("/api/sources")
async def get_sources() -> Dict[str, Any]:
    """
    Get catalog of available map sources.

    Returns list of all WMS, vector, and local map sources
    that can be used as overlays or backgrounds.
    """
    sources_file = Path("/app/data/sources/map_sources.json")

    if not sources_file.exists():
        return {"version": "1.0", "sources": []}

    try:
        with open(sources_file) as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        return {"version": "1.0", "sources": [], "error": str(e)}


# ==========================================
# Map Source CRUD endpoints
# ==========================================

SOURCES_FILE = Path("/app/data/sources/map_sources.json")


class SourceCreate(BaseModel):
    name: str
    type: str  # vector-style, wms, image
    category: str  # basemap, historical, aerial
    year: Optional[int] = None
    attribution: Optional[str] = None
    url: Optional[str] = None  # for vector-style, wms
    layer: Optional[str] = None  # for wms
    bounds: Optional[List[float]] = None  # [minLng, minLat, maxLng, maxLat]
    path: Optional[str] = None  # for image


class SourceUpdate(BaseModel):
    name: Optional[str] = None
    type: Optional[str] = None
    category: Optional[str] = None
    year: Optional[int] = None
    attribution: Optional[str] = None
    url: Optional[str] = None
    layer: Optional[str] = None
    bounds: Optional[List[float]] = None
    path: Optional[str] = None


def load_sources_file() -> Dict[str, Any]:
    """Load sources catalog from JSON file."""
    if not SOURCES_FILE.exists():
        return {"version": "1.0", "sources": []}
    with open(SOURCES_FILE) as f:
        return json.load(f)


def save_sources_file(data: Dict[str, Any]):
    """Save sources catalog to JSON file."""
    SOURCES_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(SOURCES_FILE, 'w') as f:
        json.dump(data, f, indent=2)


def slugify(text: str) -> str:
    """Convert text to a valid ID (lowercase, underscores)."""
    return text.lower().replace(' ', '_').replace('(', '').replace(')', '').replace('-', '_')


@app.post("/api/sources")
async def create_source(source: SourceCreate):
    """Create a new map source."""
    data = load_sources_file()

    # Generate ID from name
    source_id = slugify(source.name)

    # Check uniqueness
    existing_ids = [s["id"] for s in data.get("sources", [])]
    if source_id in existing_ids:
        raise HTTPException(status_code=400, detail=f"Source ID already exists: {source_id}")

    # Validate type-specific fields
    if source.type == 'vector-style' and not source.url:
        raise HTTPException(status_code=400, detail="URL required for vector-style")
    if source.type == 'wms' and (not source.url or not source.layer):
        raise HTTPException(status_code=400, detail="URL and layer required for WMS")
    if source.type == 'image' and not source.path:
        raise HTTPException(status_code=400, detail="Path required for image")

    # Validate category
    if source.category not in ['basemap', 'historical', 'aerial']:
        raise HTTPException(status_code=400, detail="Category must be: basemap, historical, or aerial")

    # Build source object
    new_source = {
        "id": source_id,
        "name": source.name,
        "type": source.type,
        "category": source.category,
        "georeferenced": source.type != 'image'  # images start as not georeferenced
    }

    # Add optional fields
    if source.year is not None:
        new_source["year"] = source.year
    if source.attribution:
        new_source["attribution"] = source.attribution
    if source.url:
        new_source["url"] = source.url
    if source.layer:
        new_source["layer"] = source.layer
    if source.bounds:
        new_source["bounds"] = source.bounds
    if source.path:
        new_source["path"] = source.path

    data["sources"].append(new_source)
    save_sources_file(data)

    logger.info(f"Created source: {source_id}")
    return {"message": "Source created", "id": source_id}


@app.put("/api/sources/{source_id}")
async def update_source(source_id: str, source: SourceUpdate):
    """Update an existing map source."""
    data = load_sources_file()

    # Find source
    source_list = data.get("sources", [])
    source_idx = next((i for i, s in enumerate(source_list) if s["id"] == source_id), None)

    if source_idx is None:
        raise HTTPException(status_code=404, detail=f"Source not found: {source_id}")

    # Update fields
    existing = source_list[source_idx]
    update_data = source.dict(exclude_unset=True)

    for key, value in update_data.items():
        if value is not None:
            existing[key] = value

    save_sources_file(data)
    logger.info(f"Updated source: {source_id}")
    return {"message": "Source updated"}


@app.delete("/api/sources/{source_id}")
async def delete_source(source_id: str):
    """Delete a map source."""
    data = load_sources_file()

    original_count = len(data.get("sources", []))
    data["sources"] = [s for s in data.get("sources", []) if s["id"] != source_id]

    if len(data["sources"]) == original_count:
        raise HTTPException(status_code=404, detail=f"Source not found: {source_id}")

    save_sources_file(data)
    logger.info(f"Deleted source: {source_id}")
    return {"message": "Source deleted"}


# Georeference endpoint
class GCPPoint(BaseModel):
    img_x: float
    img_y: float
    map_lng: float
    map_lat: float

class AffineTransform(BaseModel):
    a: float
    b: float
    c: float
    d: float
    e: float
    f: float

class GeoreferenceRequest(BaseModel):
    source_id: str
    source_path: str
    image_width: int
    image_height: int
    gcps: List[GCPPoint]
    transform: AffineTransform

@app.post("/api/georeference")
async def georeference_image(request: GeoreferenceRequest) -> Dict[str, Any]:
    """
    Apply georeferencing transform to an image using GCPs.
    Creates a GeoTIFF, persists GCPs, and updates the source catalog.
    """
    import subprocess
    import math

    # Validate GCPs
    if len(request.gcps) < 3:
        raise HTTPException(status_code=400, detail="Need at least 3 GCPs")

    # Check if image needs resizing (max ~100MB uncompressed for GDAL)
    from PIL import Image
    MAX_DIMENSION = 8000  # Max width or height in pixels

    input_path = Path("/app") / request.source_path
    if not input_path.exists():
        raise HTTPException(status_code=404, detail=f"Input image not found: {input_path}")

    # Check image dimensions and resize if needed
    scale_factor = 1.0
    resized_path = None
    try:
        with Image.open(input_path) as img:
            width, height = img.size
            logger.info(f"Original image size: {width}x{height}")

            if width > MAX_DIMENSION or height > MAX_DIMENSION:
                scale_factor = MAX_DIMENSION / max(width, height)
                new_width = int(width * scale_factor)
                new_height = int(height * scale_factor)
                logger.info(f"Resizing to {new_width}x{new_height} (scale: {scale_factor:.3f})")

                # Resize and save to temp file
                resized_dir = Path("/app/data/georeference/temp")
                resized_dir.mkdir(parents=True, exist_ok=True)
                resized_path = resized_dir / f"{request.source_id}_resized.jpg"

                img_resized = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                img_resized.save(resized_path, "JPEG", quality=95)
                logger.info(f"Saved resized image to {resized_path}")
    except Exception as e:
        logger.error(f"Error checking/resizing image: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to process image: {e}")

    # Use resized image if created
    processing_path = resized_path if resized_path else input_path

    # Persist GCPs to file for future reference
    gcps_dir = Path("/app/data/georeference/gcps")
    gcps_dir.mkdir(parents=True, exist_ok=True)
    gcp_file = gcps_dir / f"{request.source_id}.gcp.json"

    gcp_data = {
        "version": "1.0",
        "map_id": request.source_id,
        "crs": "EPSG:4326",
        "source_file": request.source_path,
        "image_width": request.image_width,
        "image_height": request.image_height,
        "gcps": [
            {
                "id": f"GCP{i+1}",
                "pixel_x": gcp.img_x,
                "pixel_y": gcp.img_y,
                "geo_x": gcp.map_lng,
                "geo_y": gcp.map_lat
            }
            for i, gcp in enumerate(request.gcps)
        ],
        "transform": {
            "a": request.transform.a,
            "b": request.transform.b,
            "c": request.transform.c,
            "d": request.transform.d,
            "e": request.transform.e,
            "f": request.transform.f
        }
    }

    try:
        with open(gcp_file, 'w') as f:
            json.dump(gcp_data, f, indent=2)
        logger.info(f"Saved {len(request.gcps)} GCPs to {gcp_file}")
    except Exception as e:
        logger.error(f"Failed to save GCPs: {e}")
        # Continue anyway - GCP persistence is nice-to-have

    # Paths
    output_dir = Path("/app/data/georeference/output")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{request.source_id}_georef.tif"

    # Build GDAL command with GCPs (scale coordinates if image was resized)
    # gdal_translate -of GTiff -gcp pixel line x y ...
    cmd = ["gdal_translate", "-of", "GTiff"]

    for gcp in request.gcps:
        # Scale pixel coordinates if image was resized
        scaled_x = gcp.img_x * scale_factor
        scaled_y = gcp.img_y * scale_factor
        cmd.extend(["-gcp", str(scaled_x), str(scaled_y), str(gcp.map_lng), str(gcp.map_lat)])

    cmd.extend([str(processing_path), str(output_path)])

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        logger.info(f"gdal_translate output: {result.stdout}")
    except subprocess.CalledProcessError as e:
        logger.error(f"gdal_translate failed: {e.stderr}")
        raise HTTPException(status_code=500, detail=f"GDAL translate failed: {e.stderr}")

    # Apply the warp to create properly georeferenced output
    warped_path = output_dir / f"{request.source_id}_warped.tif"
    warp_cmd = [
        "gdalwarp",
        "-r", "bilinear",
        "-tps",  # Use thin plate spline for now, can switch to polynomial
        "-t_srs", "EPSG:4326",
        str(output_path),
        str(warped_path)
    ]

    try:
        result = subprocess.run(warp_cmd, capture_output=True, text=True, check=True)
        logger.info(f"gdalwarp output: {result.stdout}")
    except subprocess.CalledProcessError as e:
        logger.error(f"gdalwarp failed: {e.stderr}")
        raise HTTPException(status_code=500, detail=f"GDAL warp failed: {e.stderr}")

    # Generate PNG version for browser display (GeoTIFF not directly displayable)
    png_path = output_dir / f"{request.source_id}_display.png"
    try:
        with Image.open(warped_path) as img:
            # Convert to RGB if necessary and save as PNG
            if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
                img = img.convert('RGBA')
            else:
                img = img.convert('RGB')
            img.save(png_path, 'PNG')
            logger.info(f"Generated display PNG: {png_path}")
    except Exception as e:
        logger.error(f"Failed to generate PNG: {e}")
        png_path = warped_path  # Fall back to GeoTIFF

    # Calculate RMS error
    t = request.transform
    rms = 0.0
    for gcp in request.gcps:
        pred_lng = t.a * gcp.img_x + t.b * gcp.img_y + t.c
        pred_lat = t.d * gcp.img_x + t.e * gcp.img_y + t.f
        d_lng = (pred_lng - gcp.map_lng) * 111320 * math.cos(gcp.map_lat * math.pi / 180)
        d_lat = (pred_lat - gcp.map_lat) * 110540
        rms += d_lng * d_lng + d_lat * d_lat
    rms = math.sqrt(rms / len(request.gcps))

    # Update source catalog to add new georeferenced source
    sources_file = Path("/app/data/sources/map_sources.json")
    if sources_file.exists():
        with open(sources_file) as f:
            catalog = json.load(f)

        # Calculate image corner coordinates using the affine transform
        # This is needed for MapLibre image source which requires [topLeft, topRight, bottomRight, bottomLeft]
        t = request.transform
        img_w = request.image_width
        img_h = request.image_height

        # Transform image corners to map coordinates
        def transform_pt(px, py):
            return [
                t.a * px + t.b * py + t.c,  # lng
                t.d * px + t.e * py + t.f   # lat
            ]

        top_left = transform_pt(0, 0)
        top_right = transform_pt(img_w, 0)
        bottom_right = transform_pt(img_w, img_h)
        bottom_left = transform_pt(0, img_h)

        # Also calculate bounds for quick filtering
        all_lngs = [top_left[0], top_right[0], bottom_right[0], bottom_left[0]]
        all_lats = [top_left[1], top_right[1], bottom_right[1], bottom_left[1]]

        # Find and update original source or add new
        new_source = {
            "id": f"{request.source_id}_georef",
            "name": f"{request.source_id} (georeferenced)",
            "type": "georeferenced-image",
            "path": str(png_path.relative_to("/app")),
            "geotiff_path": str(warped_path.relative_to("/app")),
            "year": None,  # Will inherit from original
            "georeferenced": True,
            "category": "historical",
            "bounds": [min(all_lngs), min(all_lats), max(all_lngs), max(all_lats)],
            "corners": [top_left, top_right, bottom_right, bottom_left],
            "gcps_file": f"data/georeference/gcps/{request.source_id}.gcp.json"
        }

        # Copy year from original if available
        for src in catalog.get("sources", []):
            if src["id"] == request.source_id:
                new_source["year"] = src.get("year")
                new_source["name"] = f"{src.get('name', request.source_id)} (georeferenced)"
                break

        # Add if not exists
        existing_ids = [s["id"] for s in catalog.get("sources", [])]
        if new_source["id"] not in existing_ids:
            catalog["sources"].append(new_source)
            with open(sources_file, "w") as f:
                json.dump(catalog, f, indent=2)

    return {
        "success": True,
        "output_path": str(warped_path.relative_to("/app")),
        "gcps_path": f"data/georeference/gcps/{request.source_id}.gcp.json",
        "rms": rms,
        "gcps_count": len(request.gcps),
        "scale_factor": scale_factor,
        "resized": scale_factor < 1.0
    }


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


# ==========================================
# Water feature API endpoints
# ==========================================

def load_water_geojson() -> Dict[str, Any]:
    """Load water GeoJSON file."""
    if not WATER_FILE.exists():
        return {"type": "FeatureCollection", "features": []}
    try:
        with open(WATER_FILE) as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading water file: {e}")
        return {"type": "FeatureCollection", "features": []}


def save_water_geojson(data: Dict[str, Any]):
    """Save water GeoJSON file."""
    WATER_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(WATER_FILE, 'w') as f:
        json.dump(data, f, indent=2)


@app.post("/api/water/add")
async def add_water_feature(feature: WaterFeature):
    """
    Add a new water feature.
    """
    data = load_water_geojson()

    # Ensure feature has an ID
    if '_src_id' not in feature.properties:
        feature.properties['_src_id'] = f"water_{int(time.time() * 1000)}"

    # Add source metadata
    feature.properties['_src'] = 'manual'
    feature.properties['_ingested'] = time.strftime('%Y-%m-%d')

    # Add to features list
    data['features'].append(feature.dict())

    # Save
    try:
        save_water_geojson(data)
        logger.info(f"Added water feature: {feature.properties.get('_src_id')}")
        return {"message": "Water feature added", "id": feature.properties.get('_src_id')}
    except Exception as e:
        logger.error(f"Error saving water feature: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to save: {str(e)}")


@app.post("/api/water/update")
async def update_water_feature(update: WaterUpdate):
    """
    Update an existing water feature.
    """
    data = load_water_geojson()

    # Find and update feature
    found = False
    for feature in data['features']:
        props = feature.get('properties', {})
        feature_id = props.get('osm_id') or props.get('_src_id')
        if str(feature_id) == str(update.id):
            # Update properties
            if update.name is not None:
                props['name'] = update.name
                props['nm'] = update.name
            if update.wtype is not None:
                props['wtype'] = update.wtype
            if update.sd is not None:
                props['sd'] = update.sd
            if update.ed is not None:
                props['ed'] = update.ed
            props['_modified'] = time.strftime('%Y-%m-%d')
            found = True
            break

    if not found:
        raise HTTPException(status_code=404, detail=f"Water feature not found: {update.id}")

    # Save
    try:
        save_water_geojson(data)
        logger.info(f"Updated water feature: {update.id}")
        return {"message": "Water feature updated"}
    except Exception as e:
        logger.error(f"Error updating water feature: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update: {str(e)}")


@app.post("/api/water/delete")
async def delete_water_feature(delete: WaterDelete):
    """
    Delete a water feature.
    """
    data = load_water_geojson()

    # Find and remove feature
    original_count = len(data['features'])
    data['features'] = [
        f for f in data['features']
        if str(f.get('properties', {}).get('osm_id') or f.get('properties', {}).get('_src_id')) != str(delete.id)
    ]

    if len(data['features']) == original_count:
        raise HTTPException(status_code=404, detail=f"Water feature not found: {delete.id}")

    # Save
    try:
        save_water_geojson(data)
        logger.info(f"Deleted water feature: {delete.id}")
        return {"message": "Water feature deleted"}
    except Exception as e:
        logger.error(f"Error deleting water feature: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete: {str(e)}")


@app.get("/api/water")
async def get_water_features():
    """
    Get all water features.
    """
    return load_water_geojson()


# ==========================================
# Alignment API endpoint
# ==========================================

class AlignmentRequest(BaseModel):
    source: str = "ortofoto1937"
    method: str = "tps"
    smoothing: float = 0.1
    min_iou: float = 0.3
    max_rounds: int = 10


@app.post("/api/align", response_model=JobResponse)
async def run_alignment(request: AlignmentRequest):
    """
    Run georeferencing alignment on ML-detected buildings.

    Matches ML buildings to OSM using IoU, fits spatial transform (TPS/TIN/Affine),
    and outputs aligned buildings/roads.

    Args:
        source: Source name (e.g., ortofoto1937)
        method: Transform method - tps, tin, or affine
        smoothing: TPS smoothing parameter (0.0-1.0)
        min_iou: Minimum IoU for matching (0.1-0.8)
        max_rounds: Maximum iterations (1-20)
    """
    # Check if job is already running
    current_job = job_manager.get_current_job()
    if current_job:
        raise HTTPException(
            status_code=409,
            detail=f"Job already running: {current_job.name}"
        )

    # Validate parameters
    if request.method not in ['tps', 'tin', 'affine']:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid method: {request.method}. Use tps, tin, or affine."
        )

    if not (0.0 <= request.smoothing <= 1.0):
        raise HTTPException(
            status_code=400,
            detail=f"Smoothing must be between 0.0 and 1.0"
        )

    if not (0.1 <= request.min_iou <= 0.8):
        raise HTTPException(
            status_code=400,
            detail=f"min_iou must be between 0.1 and 0.8"
        )

    # Check if ML buildings exist
    ml_buildings_path = Path(f"/app/data/sources/ml_detected/{request.source}/buildings.geojson")
    if not ml_buildings_path.exists():
        raise HTTPException(
            status_code=400,
            detail=f"ML buildings not found for source: {request.source}"
        )

    # Build command
    cmd = [
        "python3",
        "/app/scripts/align_to_osm.py",
        "--source", request.source,
        "--method", request.method,
        "--smoothing", str(request.smoothing),
        "--min-iou", str(request.min_iou),
        "--max-rounds", str(request.max_rounds)
    ]

    # Submit job
    job = await job_manager.submit_job(
        name="alignment",
        command=cmd
    )

    return {
        "job_id": job.job_id,
        "name": job.name,
        "status": job.status,
        "message": f"Alignment started for {request.source} using {request.method}"
    }


@app.get("/api/alignment-report/{source}")
async def get_alignment_report(source: str):
    """Get alignment report for a source."""
    report_path = Path(f"/app/data/sources/ml_detected/{source}/alignment_report.json")

    if not report_path.exists():
        return {"exists": False, "report": None}

    try:
        with open(report_path) as f:
            report = json.load(f)
        return {"exists": True, "report": report}
    except Exception as e:
        logger.error(f"Error reading alignment report: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to read report: {str(e)}")


# ==========================================
# Georeferencing API endpoints
# ==========================================

GEOREF_INPUT_DIR = Path("/app/data/georeference/input")
GEOREF_GCPS_DIR = Path("/app/data/georeference/gcps")
GEOREF_OUTPUT_DIR = Path("/app/data/georeference/output")
GEOREF_MANIFEST = Path("/app/data/georeference/manifest.json")


class GcpPoint(BaseModel):
    id: str
    pixel_x: float
    pixel_y: float
    geo_x: float
    geo_y: float
    description: Optional[str] = ""


class GcpData(BaseModel):
    version: str = "1.0"
    map_id: str
    map_date: Optional[int] = None
    crs: str = "EPSG:4326"
    source_file: str
    gcps: List[GcpPoint]


class GeorefRequest(BaseModel):
    map_id: str
    transform_order: int = 1  # 1=affine, 2=2nd order polynomial, 3=3rd order


@app.get("/api/georef/images")
async def list_georef_images():
    """
    List available images for georeferencing.
    Returns images from data/georeference/input/ directory.
    """
    images = []

    if GEOREF_INPUT_DIR.exists():
        for ext in ['*.jpg', '*.jpeg', '*.png', '*.tif', '*.tiff']:
            for path in GEOREF_INPUT_DIR.glob(ext):
                images.append({
                    "filename": path.name,
                    "path": str(path.relative_to(Path("/app"))),
                    "size": path.stat().st_size
                })
            for path in GEOREF_INPUT_DIR.glob(ext.upper()):
                images.append({
                    "filename": path.name,
                    "path": str(path.relative_to(Path("/app"))),
                    "size": path.stat().st_size
                })

    # Also check kartverket rasters
    kartverket_dir = Path("/app/data/sources/ml_detected/kartverket_1904/rasters")
    if kartverket_dir.exists():
        for ext in ['*.jpg', '*.jpeg', '*.png']:
            for path in kartverket_dir.glob(ext):
                images.append({
                    "filename": path.name,
                    "path": str(path.relative_to(Path("/app"))),
                    "size": path.stat().st_size
                })

    return {"images": images}


from fastapi import File, UploadFile, Form


@app.post("/api/georef/upload")
async def upload_georef_image(
    file: UploadFile = File(...),
    map_id: str = Form(None),
    year: int = Form(None)
):
    """
    Upload a new image for georeferencing.
    """
    GEOREF_INPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Use original filename or generate from map_id
    filename = file.filename
    filepath = GEOREF_INPUT_DIR / filename

    try:
        contents = await file.read()
        with open(filepath, 'wb') as f:
            f.write(contents)
        logger.info(f"Uploaded georef image: {filename} ({len(contents)} bytes)")
        return {
            "message": "Image uploaded",
            "filename": filename,
            "path": str(filepath.relative_to(Path("/app"))),
            "size": len(contents)
        }
    except Exception as e:
        logger.error(f"Error uploading image: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to upload: {str(e)}")


@app.get("/api/georef/gcps/{map_id}")
async def get_gcps(map_id: str):
    """
    Get GCPs for a map.
    """
    gcp_file = GEOREF_GCPS_DIR / f"{map_id}.gcp.json"

    if not gcp_file.exists():
        return {"exists": False, "data": None}

    try:
        with open(gcp_file) as f:
            data = json.load(f)
        return {"exists": True, "data": data}
    except Exception as e:
        logger.error(f"Error reading GCPs: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to read GCPs: {str(e)}")


@app.post("/api/georef/gcps/{map_id}")
async def save_gcps(map_id: str, gcp_data: GcpData):
    """
    Save GCPs for a map.
    """
    GEOREF_GCPS_DIR.mkdir(parents=True, exist_ok=True)

    gcp_file = GEOREF_GCPS_DIR / f"{map_id}.gcp.json"

    try:
        data = gcp_data.dict()
        data['map_id'] = map_id  # Ensure map_id matches URL

        with open(gcp_file, 'w') as f:
            json.dump(data, f, indent=2)

        logger.info(f"Saved {len(gcp_data.gcps)} GCPs for {map_id}")
        return {"message": f"Saved {len(gcp_data.gcps)} GCPs", "path": str(gcp_file)}
    except Exception as e:
        logger.error(f"Error saving GCPs: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to save GCPs: {str(e)}")


@app.post("/api/georef/run", response_model=JobResponse)
async def run_georeferencing(request: GeorefRequest):
    """
    Run georeferencing for a map using saved GCPs.

    Uses scripts/georeference_map.py to transform the image.
    """
    # Check if job is already running
    current_job = job_manager.get_current_job()
    if current_job:
        raise HTTPException(
            status_code=409,
            detail=f"Job already running: {current_job.name}"
        )

    # Check if GCPs exist
    gcp_file = GEOREF_GCPS_DIR / f"{request.map_id}.gcp.json"
    if not gcp_file.exists():
        raise HTTPException(
            status_code=400,
            detail=f"No GCPs found for map: {request.map_id}"
        )

    # Load GCPs to get source file
    try:
        with open(gcp_file) as f:
            gcp_data = json.load(f)
        source_file = gcp_data.get('source_file')
        gcps = gcp_data.get('gcps', [])

        if len(gcps) < 3:
            raise HTTPException(
                status_code=400,
                detail=f"Need at least 3 GCPs, found {len(gcps)}"
            )
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid GCP file format")

    # Find input image
    input_path = GEOREF_INPUT_DIR / source_file
    if not input_path.exists():
        # Try kartverket rasters
        input_path = Path(f"/app/data/sources/ml_detected/kartverket_1904/rasters/{source_file}")
        if not input_path.exists():
            raise HTTPException(
                status_code=400,
                detail=f"Source image not found: {source_file}"
            )

    # Output path
    GEOREF_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = GEOREF_OUTPUT_DIR / f"{request.map_id}.tif"

    # Build command
    cmd = [
        "python3",
        "/app/scripts/georeference_map.py",
        "--input", str(input_path),
        "--gcps", str(gcp_file),
        "--output", str(output_path)
    ]

    # Submit job
    job = await job_manager.submit_job(
        name="georeference",
        command=cmd
    )

    return {
        "job_id": job.job_id,
        "name": job.name,
        "status": job.status,
        "message": f"Georeferencing started for {request.map_id}"
    }


@app.get("/api/georef/manifest")
async def get_georef_manifest():
    """
    Get georeferencing manifest with available maps and their status.
    """
    manifest = {"maps": []}

    if GEOREF_MANIFEST.exists():
        try:
            with open(GEOREF_MANIFEST) as f:
                manifest = json.load(f)
        except Exception as e:
            logger.error(f"Error reading manifest: {e}")

    # Enrich with status info
    for map_info in manifest.get("maps", []):
        map_id = map_info.get("id") or map_info.get("filename", "").replace(".jpg", "").replace(".png", "")
        gcp_file = GEOREF_GCPS_DIR / f"{map_id}.gcp.json"
        output_file = GEOREF_OUTPUT_DIR / f"{map_id}.tif"

        map_info["has_gcps"] = gcp_file.exists()
        map_info["is_georeferenced"] = output_file.exists()

        if gcp_file.exists():
            try:
                with open(gcp_file) as f:
                    gcp_data = json.load(f)
                map_info["gcp_count"] = len(gcp_data.get("gcps", []))
            except:
                map_info["gcp_count"] = 0

    return manifest


@app.get("/api/georef/output/{map_id}")
async def get_georef_output(map_id: str):
    """
    Get info about georeferenced output for a map.
    """
    output_file = GEOREF_OUTPUT_DIR / f"{map_id}.tif"

    if not output_file.exists():
        return {"exists": False, "path": None}

    # Try to get bounds from the GeoTIFF
    bounds = None
    try:
        import rasterio
        with rasterio.open(output_file) as src:
            bounds = list(src.bounds)
    except ImportError:
        logger.warning("rasterio not available, cannot read bounds")
    except Exception as e:
        logger.error(f"Error reading GeoTIFF bounds: {e}")

    return {
        "exists": True,
        "path": f"data/georeference/output/{map_id}.tif",
        "bounds": bounds,
        "size": output_file.stat().st_size
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)
