"""Test setup shared by every test file."""

import os

# Qt draws on an invisible platform, so the suite needs no screen. This has to be set
# before any test creates a Qt application.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
