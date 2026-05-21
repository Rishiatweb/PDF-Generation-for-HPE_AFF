"""Shared pytest fixtures.

All file I/O in tests must go through ``tmp_path`` (built-in fixture); no
test should mutate the repo working tree.
"""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def data_root(tmp_path: Path) -> Path:
    """An empty ``data/`` root under tmp_path, ready for ingesters to write into."""
    root = tmp_path / "data"
    root.mkdir()
    return root
