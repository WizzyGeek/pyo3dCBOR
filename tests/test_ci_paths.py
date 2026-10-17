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
    "crates/dcbor/Cargo.toml", "crates/dcbor/Cargo.lock",
    "rust-toolchain", "rust-toolchain.toml",
    "crates/dcbor/rust-toolchain.toml",
    ".cargo/config", ".cargo/config.toml",
    "crates/dcbor/.cargo/config", "crates/dcbor/.cargo/config.toml",
    "src/lib.rs", "build.rs", "python/dcbor/__init__.pyi",
    "tests/test_dcbor.py", "scripts/ci_paths.py", ".github/workflows/ci.yml",
])
def test_build_inputs_trigger_ci(path):
    assert affects_build([path])


@pytest.mark.parametrize("path", [
    "README.md", "docs/build.md", "PERF_REVIEW.md", "",
    "docs/Cargo.toml.md", "docs/rust-toolchain.toml.txt",
])
def test_docs_only_changes_skip_ci(path):
    assert not affects_build([path])


def test_cli_emits_actions_output_for_mixed_changes():
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        input="README.md\ncrates/dcbor/Cargo.lock\n",
        text=True, capture_output=True, check=True,
    )
    assert result.stdout == "code_changed=true\n"
