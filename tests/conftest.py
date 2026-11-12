"""Test setup shared by every test file."""

import os
from pathlib import Path

import pytest

# Qt draws on an invisible platform, so the suite needs no screen. This has to be set
# before any test creates a Qt application.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from homelab_maker.model import Project
from homelab_maker.storage import load

EXAMPLES = Path(__file__).parent.parent / "examples"


@pytest.fixture
def sample() -> Project:
    """The shipped example: invented devices that use every part of the model."""
    return load(EXAMPLES / "small-homelab.homelab.json")
