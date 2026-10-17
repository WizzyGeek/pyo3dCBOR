"""Release metadata guard regressions."""
import importlib.util
from pathlib import Path

import pytest

if importlib.util.find_spec("tomllib") is None:
    pytest.skip("scripts/ci.py requires Python 3.11+", allow_module_level=True)

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("dcbor_ci", ROOT / "scripts/ci.py")
assert SPEC is not None and SPEC.loader is not None
CI = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CI)


def test_version_check_rejects_mismatched_python_package(tmp_path):
    for relative_path in ("pyproject.toml", "Cargo.toml", "python/dcbor/__init__.py"):
        target = tmp_path / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / relative_path).read_bytes())

    package_init = tmp_path / "python/dcbor/__init__.py"
    source = package_init.read_text()
    current_version = CI.versions()
    mismatched_version = "0.0.0" if current_version != "0.0.0" else "0.0.1"
    package_init.write_text(
        source.replace(
            f'__version__ = "{current_version}"',
            f'__version__ = "{mismatched_version}"',
        )
    )

    with pytest.raises(ValueError, match="python/dcbor/__init__.py versions"):
        CI.versions(tmp_path)
