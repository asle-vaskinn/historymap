"""Contract test for the deploy /version endpoint.

The prod deploy script writes the current git SHA into frontend/version.txt,
and nginx serves it at /version so the deploy-prod workflow can verify that the
live site converged to the pushed commit (SPEC AC2/AC3). This test guards the
repo-side half of that contract: the placeholder file must exist and be a single
short token.
"""
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
VERSION_FILE = REPO_ROOT / "frontend" / "version.txt"


def test_version_file_exists():
    assert VERSION_FILE.exists(), "frontend/version.txt must ship as a placeholder"


def test_version_file_is_single_short_token():
    content = VERSION_FILE.read_text().strip()
    assert content, "version.txt must not be empty"
    assert len(content.split()) == 1, "version.txt must contain exactly one token"
    assert len(content) <= 40, "version.txt should hold a short SHA or 'dev'"
