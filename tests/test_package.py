import re
from importlib import metadata

import homelab_maker


def test_version_has_the_expected_shape() -> None:
    assert re.fullmatch(r"\d+\.\d+\.\d+(\.dev\d+)?", homelab_maker.__version__)


def test_installed_metadata_agrees_with_the_module_version() -> None:
    # pyproject.toml reads the version from the package, so the two cannot differ unless
    # someone hard-codes a second copy.
    assert metadata.version("homelab-maker") == homelab_maker.__version__
