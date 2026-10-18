"""CI must rebuild when manifests or compiler configuration change."""

from pathlib import Path
import runpy
import subprocess
import sys

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/ci_paths.py"
affects_build = runpy.run_path(str(SCRIPT))["affects_build"]


@pytest.mark.parametrize("path", [
    "Cargo.toml", "Cargo.lock", "pyproject.toml",
    "rust-toolchain", "rust-toolchain.toml",
    ".cargo/config", ".cargo/config.toml",
    "src/lib.rs", "build.rs", "python/dcbor/__init__.pyi",
    "python/dcbor/py.typed", "pytest.ini", ".gitattributes",
    "tests/test_dcbor.py", "scripts/ci_paths.py", "scripts/ci.py",
    ".github/workflows/ci.yml",
    "containers/linux/images.json", "containers/linux/validate-image.sh",
    "containers/linux/Dockerfile.manylinux", "containers/linux/Dockerfile.musllinux",
])
def test_build_inputs_trigger_ci(path):
    assert affects_build([path])


def test_native_decoder_sources_trigger_ci():
    assert affects_build([
        "src/direct_decode.rs",
        "tests/test_direct_decoder.py",
        "python/dcbor/__init__.py",
    ])


@pytest.mark.parametrize("path", [
    "README.md", "docs/build.md",
    "docs/reviews/PERF_REVIEW.md", "docs/reviews/SPEC_REVIEW.md",
    "docs/allocation-plan.md", "",
    "docs/Cargo.toml.md", "docs/rust-toolchain.toml.txt",
    "maintenance/test_ci_paths.py",
    "maintenance/test_foo.py",
])
def test_docs_only_changes_skip_ci(path):
    assert not affects_build([path])


def test_cli_emits_actions_output_for_mixed_changes():
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        input="README.md\nCargo.lock\n",
        text=True, capture_output=True, check=True,
    )
    assert result.stdout == "code_changed=true\n"
