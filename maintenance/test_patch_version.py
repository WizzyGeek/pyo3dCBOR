"""Behavioral checks for the patch version bump utility."""

import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/bump_patch_version.py"
SPEC = importlib.util.spec_from_file_location("bump_patch_version", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
BUMP = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUMP)


def make_project(root: Path, version: str = "2.4.9") -> None:
    files = {
        "pyproject.toml": f'[project]\nname = "dcbor"\nversion = "{version}"\n',
        "Cargo.toml": f'[package]\nname = "dcbor-py"\nversion = "{version}"\n',
        "python/dcbor/__init__.py": f'__version__ = "{version}"\n',
        "Cargo.lock": (
            'version = 4\n\n[[package]]\nname = "dcbor-py"\n'
            f'version = "{version}"\ndependencies = []\n'
        ),
    }
    for relative, content in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def read_files(root: Path) -> dict[str, bytes]:
    return {relative: (root / relative).read_bytes() for relative in BUMP.FILES}


def test_bumps_patch_consistently_in_all_four_files(tmp_path):
    make_project(tmp_path)

    assert BUMP.bump(tmp_path) == "2.4.10"
    updated = read_files(tmp_path)
    assert all(b'2.4.10' in content for content in updated.values())
    assert all(b'2.4.9' not in content for content in updated.values())


@pytest.mark.parametrize("bad_version", ["2.4", "v2.4.9", "02.4.9", "2.4.9rc1"])
def test_refuses_non_stable_or_malformed_version_without_writes(tmp_path, bad_version):
    make_project(tmp_path, bad_version)
    before = read_files(tmp_path)

    with pytest.raises(ValueError, match="stable X.Y.Z"):
        BUMP.bump(tmp_path)

    assert read_files(tmp_path) == before


def test_refuses_mismatched_metadata_without_writes(tmp_path):
    make_project(tmp_path)
    lockfile = tmp_path / "Cargo.lock"
    lockfile.write_text(lockfile.read_text().replace('version = "2.4.9"', 'version = "2.4.8"'))
    before = read_files(tmp_path)

    with pytest.raises(ValueError, match="metadata disagree"):
        BUMP.bump(tmp_path)

    assert read_files(tmp_path) == before


def test_rolls_back_already_replaced_file_if_later_replace_fails(tmp_path, monkeypatch):
    make_project(tmp_path)
    before = read_files(tmp_path)
    real_replace = BUMP.os.replace
    failed_once = False

    def fail_second_destination(source, destination):
        nonlocal failed_once
        if Path(destination).name == "Cargo.toml" and not failed_once:
            failed_once = True
            raise OSError("simulated replacement failure")
        return real_replace(source, destination)

    monkeypatch.setattr(BUMP.os, "replace", fail_second_destination)
    with pytest.raises(RuntimeError, match="prior files restored"):
        BUMP.bump(tmp_path)

    assert read_files(tmp_path) == before
    assert not list(tmp_path.rglob("*.tmp"))
