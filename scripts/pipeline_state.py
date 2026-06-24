"""
Pipeline State Management.

Tracks the completion status of pipeline stages for each source,
enabling resumable pipelines and stale data detection.

Each source has a manifest.json with stage information:
{
    "source_id": "osm",
    "stages": {
        "extracted": {
            "completed_at": "2026-01-01T12:00:00Z",
            "input_checksum": "sha256:abc123...",
            "output_checksum": "sha256:def456...",
            "count": 1234
        },
        "normalized": {...},
        "merged": {...}
    }
}

Usage:
    from pipeline_state import PipelineState, StageInfo

    state = PipelineState('osm')

    # Check if stage needs processing
    if state.needs_processing('normalized'):
        result = run_normalization()
        state.mark_completed('normalized', count=result.count)

    # Force reprocessing
    state.invalidate('normalized')
"""

import hashlib
import json
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# Import constants
try:
    from constants import DATA_DIR, SOURCES_DIR
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent))
    from constants import DATA_DIR, SOURCES_DIR


# Pipeline stages in order
PIPELINE_STAGES = ['extracted', 'normalized', 'merged', 'exported']


@dataclass
class StageInfo:
    """Information about a completed pipeline stage.

    Attributes:
        completed_at: When the stage completed
        success: Whether it succeeded
        count: Number of features processed
        files: Output files created
        input_checksum: Hash of input files
        output_checksum: Hash of output files
        duration_seconds: Processing time
        error: Error message if failed
    """
    completed_at: Optional[str] = None
    success: bool = False
    count: int = 0
    files: List[str] = field(default_factory=list)
    input_checksum: Optional[str] = None
    output_checksum: Optional[str] = None
    duration_seconds: Optional[float] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary, excluding None values."""
        d = asdict(self)
        return {k: v for k, v in d.items() if v is not None and v != []}

    @classmethod
    def from_dict(cls, data: Dict) -> 'StageInfo':
        """Create from dictionary."""
        return cls(
            completed_at=data.get('completed_at'),
            success=data.get('success', False),
            count=data.get('count', 0),
            files=data.get('files', []),
            input_checksum=data.get('input_checksum'),
            output_checksum=data.get('output_checksum'),
            duration_seconds=data.get('duration_seconds'),
            error=data.get('error')
        )


class PipelineState:
    """Manages pipeline state for a source.

    Tracks which pipeline stages have been completed and enables
    resumable pipeline runs.
    """

    def __init__(self, source_id: str, data_dir: Path = None):
        """Initialize pipeline state for a source.

        Args:
            source_id: Source identifier (e.g., 'osm', 'nvdb')
            data_dir: Base data directory
        """
        self.source_id = source_id
        self.data_dir = data_dir or DATA_DIR
        self.source_dir = self.data_dir / 'sources' / source_id
        self.manifest_path = self.source_dir / 'manifest.json'
        self._manifest: Optional[Dict] = None

    @property
    def manifest(self) -> Dict:
        """Load manifest, creating if needed."""
        if self._manifest is None:
            self._manifest = self._load_manifest()
        return self._manifest

    def _load_manifest(self) -> Dict:
        """Load manifest from disk."""
        if self.manifest_path.exists():
            try:
                with open(self.manifest_path) as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                pass
        return {'source_id': self.source_id, 'stages': {}}

    def _save_manifest(self) -> None:
        """Save manifest to disk."""
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.manifest_path, 'w') as f:
            json.dump(self.manifest, f, indent=2)

    def get_stage(self, stage: str) -> Optional[StageInfo]:
        """Get info for a pipeline stage.

        Args:
            stage: Stage name ('extracted', 'normalized', 'merged', 'exported')

        Returns:
            StageInfo or None if not completed
        """
        stages = self.manifest.get('stages', {})
        if stage in stages:
            return StageInfo.from_dict(stages[stage])
        return None

    def mark_completed(
        self,
        stage: str,
        count: int = 0,
        files: List[str] = None,
        input_checksum: str = None,
        output_checksum: str = None,
        duration_seconds: float = None,
        **extra
    ) -> StageInfo:
        """Mark a stage as successfully completed.

        Args:
            stage: Stage name
            count: Number of features processed
            files: Output files created
            input_checksum: Hash of inputs
            output_checksum: Hash of outputs
            duration_seconds: Processing time
            **extra: Additional metadata

        Returns:
            The created StageInfo
        """
        info = StageInfo(
            completed_at=datetime.utcnow().isoformat(),
            success=True,
            count=count,
            files=files or [],
            input_checksum=input_checksum,
            output_checksum=output_checksum,
            duration_seconds=duration_seconds
        )

        if 'stages' not in self.manifest:
            self.manifest['stages'] = {}

        stage_dict = info.to_dict()
        stage_dict.update(extra)
        self.manifest['stages'][stage] = stage_dict

        # Update source-level timestamps
        self.manifest[f'last_{stage}'] = info.completed_at

        self._save_manifest()
        return info

    def mark_failed(self, stage: str, error: str, **extra) -> StageInfo:
        """Mark a stage as failed.

        Args:
            stage: Stage name
            error: Error message
            **extra: Additional metadata

        Returns:
            The created StageInfo
        """
        info = StageInfo(
            completed_at=datetime.utcnow().isoformat(),
            success=False,
            error=error
        )

        if 'stages' not in self.manifest:
            self.manifest['stages'] = {}

        stage_dict = info.to_dict()
        stage_dict.update(extra)
        self.manifest['stages'][stage] = stage_dict

        self._save_manifest()
        return info

    def invalidate(self, stage: str, cascade: bool = True) -> None:
        """Invalidate a stage, forcing reprocessing.

        Args:
            stage: Stage to invalidate
            cascade: Also invalidate downstream stages
        """
        stages = self.manifest.get('stages', {})

        if cascade:
            # Invalidate this stage and all downstream stages
            stage_idx = PIPELINE_STAGES.index(stage) if stage in PIPELINE_STAGES else -1
            for i, s in enumerate(PIPELINE_STAGES):
                if i >= stage_idx and s in stages:
                    del stages[s]
        else:
            # Just invalidate this stage
            if stage in stages:
                del stages[stage]

        self._save_manifest()

    def needs_processing(
        self,
        stage: str,
        max_age_hours: float = None,
        check_inputs: bool = False
    ) -> bool:
        """Check if a stage needs (re)processing.

        Args:
            stage: Stage to check
            max_age_hours: Max age before refresh (None = don't check age)
            check_inputs: Compare input checksums (expensive)

        Returns:
            True if processing is needed
        """
        info = self.get_stage(stage)

        # Never processed
        if info is None:
            return True

        # Last run failed
        if not info.success:
            return True

        # Check age
        if max_age_hours is not None and info.completed_at:
            try:
                completed = datetime.fromisoformat(info.completed_at)
                age_hours = (datetime.utcnow() - completed).total_seconds() / 3600
                if age_hours > max_age_hours:
                    return True
            except ValueError:
                return True

        # Check if inputs changed
        if check_inputs and info.input_checksum:
            current_checksum = self._compute_input_checksum(stage)
            if current_checksum != info.input_checksum:
                return True

        return False

    def _compute_input_checksum(self, stage: str) -> Optional[str]:
        """Compute checksum of input files for a stage.

        Args:
            stage: Stage name

        Returns:
            SHA256 hash of input files
        """
        # Determine input files based on stage
        if stage == 'normalized':
            input_dir = self.source_dir / 'raw'
        elif stage == 'merged':
            input_dir = self.source_dir / 'normalized'
        else:
            return None

        if not input_dir.exists():
            return None

        # Hash all files in input directory
        hasher = hashlib.sha256()
        for path in sorted(input_dir.rglob('*')):
            if path.is_file():
                hasher.update(path.name.encode())
                hasher.update(str(path.stat().st_mtime).encode())

        return f"sha256:{hasher.hexdigest()[:16]}"

    def get_status(self) -> Dict[str, Any]:
        """Get current status of all stages.

        Returns:
            Dict with stage statuses
        """
        status = {
            'source_id': self.source_id,
            'stages': {}
        }

        for stage in PIPELINE_STAGES:
            info = self.get_stage(stage)
            if info:
                status['stages'][stage] = {
                    'completed': info.success,
                    'completed_at': info.completed_at,
                    'count': info.count
                }
            else:
                status['stages'][stage] = {
                    'completed': False
                }

        return status

    def __repr__(self) -> str:
        stages = self.manifest.get('stages', {})
        completed = [s for s in PIPELINE_STAGES if stages.get(s, {}).get('success')]
        return f"PipelineState('{self.source_id}', completed={completed})"


def get_all_source_states(data_dir: Path = None) -> Dict[str, PipelineState]:
    """Get pipeline states for all sources.

    Args:
        data_dir: Base data directory

    Returns:
        Dict mapping source_id to PipelineState
    """
    data_dir = data_dir or DATA_DIR
    sources_dir = data_dir / 'sources'

    states = {}
    if sources_dir.exists():
        for source_dir in sources_dir.iterdir():
            if source_dir.is_dir():
                state = PipelineState(source_dir.name, data_dir)
                states[source_dir.name] = state

    return states


def print_pipeline_status(data_dir: Path = None) -> None:
    """Print pipeline status for all sources."""
    states = get_all_source_states(data_dir)

    print("Pipeline Status")
    print("=" * 60)

    for source_id, state in sorted(states.items()):
        status = state.get_status()
        stages = status['stages']

        stage_str = ""
        for s in PIPELINE_STAGES:
            if stages[s]['completed']:
                stage_str += f"[✓{s[:3]}]"
            else:
                stage_str += f"[_{s[:3]}_]"

        print(f"{source_id:20} {stage_str}")


# CLI
if __name__ == '__main__':
    print_pipeline_status()
