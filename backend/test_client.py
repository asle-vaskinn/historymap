#!/usr/bin/env python3
"""
Test client for the backend API.

Demonstrates how to interact with the FastAPI backend.
"""

import asyncio
import json
import requests
import websockets
from typing import List, Dict


BASE_URL = "http://localhost:8080/api"
WS_URL = "ws://localhost:8080/api/logs"


def health_check():
    """Test health check endpoint."""
    print("Testing health check...")
    response = requests.get(f"{BASE_URL}/health")
    print(f"  Status: {response.status_code}")
    print(f"  Response: {response.json()}")
    print()


def get_status():
    """Test status endpoint."""
    print("Getting pipeline status...")
    response = requests.get(f"{BASE_URL}/status")
    print(f"  Status: {response.status_code}")
    data = response.json()
    print(f"  Training tiles: {data.get('training_tiles', 0)}")
    print(f"  Corrected tiles: {data.get('corrected_tiles', 0)}")
    print(f"  Model exists: {data.get('model_exists', False)}")
    print(f"  Annotations: {data.get('annotations_count', 0)}")
    current_job = data.get('current_job')
    if current_job:
        print(f"  Current job: {current_job['name']} ({current_job['status']})")
    print()


def generate_training(tiles: int = 10):
    """Test training data generation."""
    print(f"Generating training data ({tiles} tiles)...")
    response = requests.post(f"{BASE_URL}/generate-training", params={"tiles": tiles})
    print(f"  Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"  Job ID: {data['job_id']}")
        print(f"  Message: {data['message']}")
    else:
        print(f"  Error: {response.text}")
    print()


def train_model():
    """Test model training."""
    print("Starting model training...")
    response = requests.post(f"{BASE_URL}/train")
    print(f"  Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"  Job ID: {data['job_id']}")
        print(f"  Message: {data['message']}")
    else:
        print(f"  Error: {response.text}")
    print()


def verify_predictions():
    """Test verification."""
    print("Running verification...")
    response = requests.post(f"{BASE_URL}/verify")
    print(f"  Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"  Job ID: {data['job_id']}")
        print(f"  Message: {data['message']}")
    else:
        print(f"  Error: {response.text}")
    print()


def save_annotations(annotations: List[Dict]):
    """Test saving annotations."""
    print(f"Saving {len(annotations)} annotations...")
    response = requests.post(
        f"{BASE_URL}/annotations",
        json={"annotations": annotations}
    )
    print(f"  Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"  Message: {data['message']}")
    else:
        print(f"  Error: {response.text}")
    print()


def get_annotations():
    """Test getting annotations."""
    print("Getting annotations...")
    response = requests.get(f"{BASE_URL}/annotations")
    print(f"  Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        annotations = data.get('annotations', [])
        print(f"  Count: {len(annotations)}")
        if annotations:
            print(f"  First annotation: {annotations[0]}")
    else:
        print(f"  Error: {response.text}")
    print()


def apply_annotations(annotations: List[Dict]):
    """Test applying annotations."""
    print(f"Applying {len(annotations)} annotations...")
    response = requests.post(
        f"{BASE_URL}/apply-annotations",
        json={"annotations": annotations}
    )
    print(f"  Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"  Job ID: {data['job_id']}")
        print(f"  Message: {data['message']}")
    else:
        print(f"  Error: {response.text}")
    print()


async def stream_logs(duration: int = 10):
    """Test WebSocket log streaming."""
    print(f"Streaming logs for {duration} seconds...")
    try:
        async with websockets.connect(WS_URL) as websocket:
            print("  Connected to log stream")

            # Receive messages for specified duration
            start = asyncio.get_event_loop().time()
            while asyncio.get_event_loop().time() - start < duration:
                try:
                    message = await asyncio.wait_for(websocket.recv(), timeout=1.0)
                    data = json.loads(message)
                    msg_type = data.get('type')
                    msg_text = data.get('message', '')

                    if msg_type == 'connected':
                        print(f"  [{msg_type.upper()}] {msg_text}")
                    elif msg_type == 'log':
                        print(f"  {msg_text}")
                    elif msg_type == 'job_status':
                        job = data.get('job', {})
                        print(f"  [JOB STATUS] {job.get('name')} - {job.get('status')}")

                except asyncio.TimeoutError:
                    continue

            print("  Stream ended")

    except Exception as e:
        print(f"  Error: {e}")
    print()


def main():
    """Run all tests."""
    print("=" * 60)
    print("Backend API Test Client")
    print("=" * 60)
    print()

    # Test basic endpoints
    health_check()
    get_status()

    # Test annotations
    test_annotations = [
        {"osm_id": 123456, "existed": True, "notes": "Test annotation 1"},
        {"osm_id": 789012, "existed": False, "notes": "Test annotation 2"}
    ]
    save_annotations(test_annotations)
    get_annotations()

    # Uncomment to test job submission (requires backend running)
    # generate_training(tiles=5)
    # verify_predictions()
    # apply_annotations(test_annotations)

    # Test WebSocket streaming
    print("To test WebSocket streaming, run:")
    print("  python -c 'import asyncio; from test_client import stream_logs; asyncio.run(stream_logs(30))'")
    print()


if __name__ == "__main__":
    main()
