"""Release checks. Run with Python 3.11+; distributions also needs packaging."""

import ast
import hashlib
import os
from pathlib import Path
import re
import sys
import tarfile
import tomllib
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PYTHONS = {"cp39", "cp310", "cp311", "cp312", "cp313", "cp314"}
PLATFORMS = {
    "manylinux_x86_64", "manylinux_aarch64",
    "musllinux_x86_64", "musllinux_aarch64",
    "macosx_x86_64", "macosx_arm64", "win_amd64",
}


def versions(root=ROOT):
    project = tomllib.loads((root / "pyproject.toml").read_text())["project"]
    cargo = tomllib.loads((root / "Cargo.toml").read_text())["package"]
    version = project["version"]
    if cargo["version"] != version:
        raise ValueError("Cargo.toml and pyproject.toml versions must match")
    package_tree = ast.parse((root / "python/dcbor/__init__.py").read_text())
    package_version = None
    for statement in package_tree.body:
        if isinstance(statement, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "__version__"
            for target in statement.targets
        ):
            if isinstance(statement.value, ast.Constant) and isinstance(
                statement.value.value, str
            ):
                package_version = statement.value.value
            break
    if package_version != version:
        raise ValueError(
            "pyproject.toml and python/dcbor/__init__.py versions must match"
        )
    tag = os.environ.get("RELEASE_TAG", "")
    if tag and (not re.fullmatch(r"v\d+\.\d+\.\d+", tag) or tag != f"v{version}"):
        raise ValueError(f"Release tag must be v{version}, got {tag!r}")
    print(f"Package version: {version}")
    return version


def distributions(directory):
    from packaging.utils import parse_wheel_filename

    version = versions()
    paths = sorted(directory.glob("*.whl"))
    expected = {(py, platform) for py in PYTHONS for platform in PLATFORMS}
    seen = set()
    for path in paths:
        name, wheel_version, _, tags = parse_wheel_filename(path.name)
        if name != "dcbor" or str(wheel_version) != version:
            raise ValueError(f"Unexpected wheel name/version: {path.name}")
        wheel_pairs = set()
        for tag in tags:
            platform = tag.platform
            if platform.startswith(("manylinux", "musllinux", "macosx")):
                family = platform.split("_")[0]
                arch = "x86_64" if platform.endswith("x86_64") else "aarch64" if platform.endswith("aarch64") else "arm64" if platform.endswith("arm64") else "unknown"
                platform = f"{family}_{arch}"
            if tag.abi != tag.interpreter:
                raise ValueError(f"Unexpected ABI in {path.name}: {tag}")
            wheel_pairs.add((tag.interpreter, platform))
        if len(wheel_pairs) != 1 or not wheel_pairs <= expected or wheel_pairs & seen:
            raise ValueError(f"Unexpected or duplicate wheel: {path.name}")
        with zipfile.ZipFile(path) as wheel:
            if not any("license" in name.lower() for name in wheel.namelist()):
                raise ValueError(f"Missing license in {path.name}")
        seen.update(wheel_pairs)
    if seen != expected:
        raise ValueError(f"Missing wheels: {sorted(expected - seen)}")
    archives = list(directory.glob("*.tar.gz"))
    if len(archives) != 1 or archives[0].name != f"dcbor-{version}.tar.gz":
        raise ValueError("Expected exactly one version-matched source distribution")
    with tarfile.open(archives[0]) as archive:
        names = archive.getnames()
        for suffix in ["/Cargo.lock", "/src/direct_decode.rs", "/src/wire.rs", "/tests/test_dcbor.py"]:
            if not any(name.endswith(suffix) for name in names):
                raise ValueError(f"Missing required source file: {suffix}")
    files = sorted([*paths, *archives])
    checksums = "".join(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n" for path in files)
    (directory / "SHA256SUMS").write_text(checksums)
    print(f"Validated {len(paths)} wheels and one sdist; wrote SHA256SUMS")


if __name__ == "__main__":
    if sys.argv[1:] == ["versions"]:
        versions()
    elif len(sys.argv) == 3 and sys.argv[1] == "distributions":
        distributions(Path(sys.argv[2]))
    else:
        sys.exit("Usage: python scripts/ci.py versions | distributions DIST_DIR")
