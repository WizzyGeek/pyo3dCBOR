"""Public package version must match installed distribution metadata."""
from importlib import resources
from importlib.metadata import version

import dcbor


def test_public_version_matches_distribution_metadata():
    assert dcbor.__version__ == version("dcbor")


def test_distribution_includes_pep561_typing_files():
    package_files = resources.files("dcbor")
    assert package_files.joinpath("py.typed").is_file()
    assert package_files.joinpath("__init__.pyi").is_file()
