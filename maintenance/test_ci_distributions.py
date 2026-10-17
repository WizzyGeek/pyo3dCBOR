"""Behavioral regressions for the release artifact checks in scripts/ci.py."""
import hashlib
import importlib.util
import io
from pathlib import Path
import tarfile
import zipfile

import pytest

if importlib.util.find_spec("tomllib") is None:
    pytest.skip("scripts/ci.py requires Python 3.11+", allow_module_level=True)

import tomllib

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "dcbor_ci_distributions", ROOT / "scripts/ci.py"
)
assert SPEC is not None and SPEC.loader is not None
CI = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CI)

VERSION = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
EXPECTED_PYTHONS = ("cp39", "cp310", "cp311", "cp312", "cp313", "cp314")
PLATFORM_TAGS = {
    "manylinux_x86_64": "manylinux_2_17_x86_64",
    "manylinux_aarch64": "manylinux_2_17_aarch64",
    "musllinux_x86_64": "musllinux_1_2_x86_64",
    "musllinux_aarch64": "musllinux_1_2_aarch64",
    "macosx_x86_64": "macosx_10_9_x86_64",
    "macosx_arm64": "macosx_11_0_arm64",
    "win_amd64": "win_amd64",
}
SOURCE_FILES = (
    "Cargo.lock",
    "crates/dcbor/src/float.rs",
    "crates/dcbor/PATCHES.md",
    "crates/dcbor/LICENSE.md",
    "tests/test_dcbor.py",
)


def _wheel_name(py, platform, *, version=VERSION, abi=None):
    return f"dcbor-{version}-{py}-{abi or py}-{PLATFORM_TAGS[platform]}.whl"


def _write_wheel(path, *, include_license=True):
    with zipfile.ZipFile(path, "w") as wheel:
        wheel.writestr("dcbor/__init__.py", "# synthetic wheel\n")
        if include_license:
            wheel.writestr("dcbor-0.dist-info/licenses/LICENSE.md", "synthetic license\n")


def _write_sdist(path, *, missing_source=None, top_level=None):
    root = top_level or f"dcbor-{VERSION}"
    with tarfile.open(path, "w:gz") as archive:
        for relative_path in SOURCE_FILES:
            if relative_path == missing_source:
                continue
            content = f"synthetic {relative_path}\n".encode()
            info = tarfile.TarInfo(f"{root}/{relative_path}")
            info.size = len(content)
            archive.addfile(info, io.BytesIO(content))


def _write_complete_distribution(
    directory,
    *,
    missing_wheel=None,
    include_license=True,
    missing_source=None,
    archive_name=None,
    archive_top_level=None,
):
    directory.mkdir(parents=True, exist_ok=True)
    for py in EXPECTED_PYTHONS:
        for platform in PLATFORM_TAGS:
            if (py, platform) == missing_wheel:
                continue
            wheel_path = directory / _wheel_name(py, platform)
            _write_wheel(wheel_path, include_license=include_license)
    sdist_path = directory / (archive_name or f"dcbor-{VERSION}.tar.gz")
    _write_sdist(
        sdist_path,
        missing_source=missing_source,
        top_level=archive_top_level,
    )
    return sdist_path


def test_distributions_accepts_all_42_wheels_and_hashes_every_artifact(tmp_path):
    directory = tmp_path / "dist"
    _write_complete_distribution(directory)

    CI.distributions(directory)

    artifacts = sorted([*directory.glob("*.whl"), *directory.glob("*.tar.gz")])
    assert len(artifacts) == 43
    expected = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in artifacts
    }
    checksum_rows = (directory / "SHA256SUMS").read_text().splitlines()
    assert len(checksum_rows) == 43
    actual = {
        name: digest
        for digest, name in (row.split("  ", 1) for row in checksum_rows)
    }
    assert actual == expected


def test_distributions_rejects_missing_and_duplicate_wheel_pairs(tmp_path):
    missing_dir = tmp_path / "missing"
    _write_complete_distribution(missing_dir, missing_wheel=("cp314", "win_amd64"))
    with pytest.raises(ValueError, match="Missing wheels"):
        CI.distributions(missing_dir)

    duplicate_dir = tmp_path / "duplicate"
    _write_complete_distribution(duplicate_dir)
    duplicate = duplicate_dir / _wheel_name("cp39", "manylinux_x86_64").replace(
        "-cp39-cp39-", "-1-cp39-cp39-"
    )
    _write_wheel(duplicate)
    with pytest.raises(ValueError, match="Unexpected or duplicate wheel"):
        CI.distributions(duplicate_dir)


def test_distributions_rejects_wrong_wheel_version_and_abi(tmp_path):
    version_dir = tmp_path / "wrong-version"
    _write_complete_distribution(version_dir)
    wheel = version_dir / _wheel_name("cp39", "win_amd64")
    wheel.rename(wheel.with_name(wheel.name.replace(VERSION, "99.99.99", 1)))
    with pytest.raises(ValueError, match="Unexpected wheel name/version"):
        CI.distributions(version_dir)

    abi_dir = tmp_path / "wrong-abi"
    _write_complete_distribution(abi_dir)
    wheel = abi_dir / _wheel_name("cp39", "win_amd64")
    wheel.rename(wheel.with_name(wheel.name.replace("-cp39-cp39-", "-cp39-abi3-")))
    with pytest.raises(ValueError, match="Unexpected ABI"):
        CI.distributions(abi_dir)


def test_distributions_requires_license_in_each_wheel(tmp_path):
    directory = tmp_path / "missing-license"
    _write_complete_distribution(directory)
    wheel = directory / _wheel_name("cp314", "macosx_arm64")
    _write_wheel(wheel, include_license=False)

    with pytest.raises(ValueError, match="Missing license"):
        CI.distributions(directory)


def test_distributions_requires_vendored_sources_and_matching_sdist_name(tmp_path):
    source_dir = tmp_path / "missing-source"
    _write_complete_distribution(source_dir, missing_source="crates/dcbor/src/float.rs")
    with pytest.raises(
        ValueError,
        match="Missing required source file: /crates/dcbor/src/float.rs",
    ):
        CI.distributions(source_dir)

    archive_dir = tmp_path / "wrong-archive-name"
    _write_complete_distribution(archive_dir, archive_name=f"dcbor-{VERSION}-other.tar.gz")
    with pytest.raises(ValueError, match="exactly one version-matched source distribution"):
        CI.distributions(archive_dir)
