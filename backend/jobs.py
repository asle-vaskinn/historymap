"""
Background job management for ML pipeline tasks.

Handles running scripts as background jobs, capturing output, and broadcasting
logs to WebSocket clients.
"""

import asyncio
import json
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional, List, Set
import logging

logger = logging.getLogger(__name__)


class JobStatus(str, Enum):
    """Job status enum."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class Job:
    """Represents a background job."""
    job_id: str
    name: str
    command: List[str]
    status: JobStatus
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    exit_code: Optional[int] = None
    output: List[str] = None
    error: Optional[str] = None

    def __post_init__(self):
        if self.output is None:
            self.output = []

    def to_dict(self):
        """Convert to dictionary."""
        return asdict(self)


class JobManager:
    """
    Manages background jobs.

    Supports:
    - Queue of jobs (one at a time)
    - Running subprocess, capturing output
    - Broadcasting logs to WebSocket clients
    """

    def __init__(self):
        self.jobs: dict[str, Job] = {}
        self.current_job: Optional[Job] = None
        self.job_queue: asyncio.Queue = asyncio.Queue()
        self.ws_clients: Set[asyncio.Queue] = set()
        self._worker_task: Optional[asyncio.Task] = None

    async def start(self):
        """Start the job worker."""
        if self._worker_task is None:
            self._worker_task = asyncio.create_task(self._job_worker())
            logger.info("Job worker started")

    async def stop(self):
        """Stop the job worker."""
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
            self._worker_task = None
            logger.info("Job worker stopped")

    def get_job(self, job_id: str) -> Optional[Job]:
        """Get job by ID."""
        return self.jobs.get(job_id)

    def get_all_jobs(self) -> List[Job]:
        """Get all jobs."""
        return list(self.jobs.values())

    def get_current_job(self) -> Optional[Job]:
        """Get currently running job."""
        return self.current_job

    async def submit_job(self, name: str, command: List[str]) -> Job:
        """Submit a new job to the queue."""
        job_id = f"{name}_{int(time.time())}"
        job = Job(
            job_id=job_id,
            name=name,
            command=command,
            status=JobStatus.PENDING,
            created_at=datetime.now().isoformat()
        )
        self.jobs[job_id] = job
        await self.job_queue.put(job)
        logger.info(f"Submitted job {job_id}: {' '.join(command)}")
        await self._broadcast_log(f"[JOB] Queued: {name}")
        return job

    async def _job_worker(self):
        """Worker that processes jobs from the queue."""
        logger.info("Job worker running")
        while True:
            try:
                job = await self.job_queue.get()
                await self._run_job(job)
                self.job_queue.task_done()
            except asyncio.CancelledError:
                logger.info("Job worker cancelled")
                break
            except Exception as e:
                logger.error(f"Job worker error: {e}", exc_info=True)

    async def _run_job(self, job: Job):
        """Run a job as a subprocess."""
        self.current_job = job
        job.status = JobStatus.RUNNING
        job.started_at = datetime.now().isoformat()

        await self._broadcast_log(f"[JOB] Starting: {job.name}")
        logger.info(f"Running job {job.job_id}: {' '.join(job.command)}")

        try:
            # Create subprocess
            process = await asyncio.create_subprocess_exec(
                *job.command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd="/app"
            )

            # Stream output
            while True:
                line = await process.stdout.readline()
                if not line:
                    break

                line_text = line.decode('utf-8').rstrip()
                job.output.append(line_text)
                await self._broadcast_log(line_text)

            # Wait for completion
            await process.wait()
            job.exit_code = process.returncode

            if process.returncode == 0:
                job.status = JobStatus.COMPLETED
                await self._broadcast_log(f"[JOB] Completed: {job.name}")
                logger.info(f"Job {job.job_id} completed successfully")
            else:
                job.status = JobStatus.FAILED
                job.error = f"Process exited with code {process.returncode}"
                await self._broadcast_log(f"[JOB] Failed: {job.name} (exit code {process.returncode})")
                logger.error(f"Job {job.job_id} failed with exit code {process.returncode}")

        except Exception as e:
            job.status = JobStatus.FAILED
            job.error = str(e)
            await self._broadcast_log(f"[JOB] Error: {job.name} - {str(e)}")
            logger.error(f"Job {job.job_id} error: {e}", exc_info=True)

        finally:
            job.completed_at = datetime.now().isoformat()
            self.current_job = None

    async def _broadcast_log(self, message: str):
        """Broadcast log message to all WebSocket clients."""
        if not self.ws_clients:
            return

        # Create log message
        log_msg = {
            "type": "log",
            "message": message,
            "timestamp": datetime.now().isoformat()
        }

        # Send to all clients (iterate over copy to avoid modification during iteration)
        disconnected = set()
        for client_queue in list(self.ws_clients):
            try:
                await asyncio.wait_for(
                    client_queue.put(log_msg),
                    timeout=1.0
                )
            except asyncio.TimeoutError:
                # Client queue is full, mark for removal
                disconnected.add(client_queue)
            except Exception as e:
                logger.error(f"Error broadcasting to client: {e}")
                disconnected.add(client_queue)

        # Remove disconnected clients
        self.ws_clients -= disconnected

    def add_ws_client(self) -> asyncio.Queue:
        """Add a WebSocket client and return its queue."""
        client_queue = asyncio.Queue(maxsize=100)
        self.ws_clients.add(client_queue)
        logger.info(f"WebSocket client connected (total: {len(self.ws_clients)})")
        return client_queue

    def remove_ws_client(self, client_queue: asyncio.Queue):
        """Remove a WebSocket client."""
        self.ws_clients.discard(client_queue)
        logger.info(f"WebSocket client disconnected (total: {len(self.ws_clients)})")


# Global job manager instance
job_manager = JobManager()
