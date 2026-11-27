import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def isolated_output(tmp_path, monkeypatch):
    """Every test writes to its own temporary output folder and database."""
    monkeypatch.setenv("PBS_OUTPUT", str(tmp_path / "output"))
    yield tmp_path / "output"


@pytest.fixture
def small_sizes():
    # Small sizes keep the end-to-end tests fast while exercising every code path.
    return {"welcome_screen": [480, 270], "welcome_video": [320, 180], "strip_2x6": [200, 600],
            "overlay_4x6": [600, 400], "gif_overlay": [360, 360], "buttons": [300, 100]}
