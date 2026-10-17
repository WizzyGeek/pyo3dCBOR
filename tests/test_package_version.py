"""Public package version must match installed distribution metadata."""
from importlib.metadata import version

import dcbor


def test_public_version_matches_distribution_metadata():
    assert dcbor.__version__ == version("dcbor")
