"""Validate and package the versioned distribution bundle for GitHub Releases."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import zipfile

if __package__:
    from . import ci
else:  # Support ``python scripts/ci_release.py``.
    import ci


TAG_RE = re.compile(r"v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\Z")
COMMIT_RE = re.compile(r"[0-9a-f]{40}\Z")


def artifact_name(tag: str) -> str:
    """Return the exact build artifact name for a supported release tag."""
    if not TAG_RE.fullmatch(tag):
        raise ValueError("release tag must be vX.Y.Z")
    return f"release-{tag}"


def _read_manifest(path: Path, distribution_names: set[str]) -> bytes:
    manifest_path = path / "SHA256SUMS"
    try:
        content = manifest_path.read_bytes()
        rows = content.decode("utf-8").splitlines()
    except (OSError, UnicodeError) as error:
        raise ValueError(f"could not read SHA256SUMS: {error}") from error

    checksums: dict[str, str] = {}
    for row in rows:
        digest, separator, name = row.partition("  ")
        if not separator or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("SHA256SUMS has an invalid row")
        if not name or Path(name).name != name or name in checksums:
            raise ValueError("SHA256SUMS has an invalid or duplicate filename")
        checksums[name] = digest

    if set(checksums) != distribution_names:
        raise ValueError("SHA256SUMS does not cover exactly the distribution files")
    for name, expected in checksums.items():
        actual = hashlib.sha256((path / name).read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError(f"checksum mismatch for {name}")
    return content


def validate_bundle(
    directory: Path, tag: str, commit_sha: str, expected_run_id: int | None = None
) -> str:
    """Validate tag, provenance, exact distribution set, and recorded checksums."""
    match = TAG_RE.fullmatch(tag)
    if not match:
        raise ValueError("release tag must be vX.Y.Z")
    if not COMMIT_RE.fullmatch(commit_sha):
        raise ValueError("release commit must be a full lowercase Git SHA")

    had_release_tag = "RELEASE_TAG" in os.environ
    previous_release_tag = os.environ.get("RELEASE_TAG")
    os.environ["RELEASE_TAG"] = tag
    try:
        version = ci.versions()
    finally:
        if had_release_tag:
            assert previous_release_tag is not None
            os.environ["RELEASE_TAG"] = previous_release_tag
        else:
            os.environ.pop("RELEASE_TAG", None)

    if tag != f"v{version}":
        raise ValueError("release tag does not match the checked-out package version")

    provenance_path = directory / "BUILD-PROVENANCE.json"
    try:
        provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"could not read BUILD-PROVENANCE.json: {error}") from error
    if not isinstance(provenance, dict):
        raise ValueError("BUILD-PROVENANCE.json must contain an object")
    if provenance.get("version") != version:
        raise ValueError("bundle provenance version does not match the release tag")
    if provenance.get("commit_sha") != commit_sha:
        raise ValueError("bundle provenance commit does not match the release tag")
    if not isinstance(provenance.get("run_id"), int) or provenance["run_id"] <= 0:
        raise ValueError("bundle provenance is missing a valid run_id")
    if expected_run_id is not None and provenance["run_id"] != expected_run_id:
        raise ValueError("bundle provenance run_id does not match the selected build run")

    distribution_paths = [*directory.glob("*.whl"), *directory.glob("*.tar.gz")]
    distribution_names = {path.name for path in distribution_paths}
    expected_files = distribution_names | {"SHA256SUMS", "BUILD-PROVENANCE.json"}
    actual_paths = list(directory.iterdir())
    if any(path.is_symlink() or not path.is_file() for path in actual_paths):
        raise ValueError("bundle contains a non-file or symlink entry")
    if {path.name for path in actual_paths} != expected_files:
        raise ValueError("bundle contains missing or unexpected files")

    original_manifest = _read_manifest(directory, distribution_names)
    had_release_tag = "RELEASE_TAG" in os.environ
    previous_release_tag = os.environ.get("RELEASE_TAG")
    os.environ["RELEASE_TAG"] = tag
    try:
        ci.distributions(directory)
    finally:
        if had_release_tag:
            assert previous_release_tag is not None
            os.environ["RELEASE_TAG"] = previous_release_tag
        else:
            os.environ.pop("RELEASE_TAG", None)
    if (directory / "SHA256SUMS").read_bytes() != original_manifest:
        raise ValueError("distribution validation produced different checksums")
    return version


def create_bundle_archive(directory: Path, archive_path: Path) -> None:
    """Create a ZIP release asset containing the validated bundle files."""
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    files = sorted(path for path in directory.iterdir() if path.is_file())
    with zipfile.ZipFile(archive_path, "w") as archive:
        for path in files:
            entry = zipfile.ZipInfo(path.name, date_time=(1980, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = 0o100644 << 16
            archive.writestr(entry, path.read_bytes())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    name = commands.add_parser("artifact-name", help="print the exact artifact name for a tag")
    name.add_argument("tag")
    validate = commands.add_parser("validate", help="validate a release bundle")
    validate.add_argument("directory", type=Path)
    validate.add_argument("tag")
    validate.add_argument("commit_sha")
    validate.add_argument("--expected-run-id", type=int)
    archive = commands.add_parser("archive", help="zip a validated release bundle")
    archive.add_argument("directory", type=Path)
    archive.add_argument("archive_path", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "artifact-name":
            print(artifact_name(args.tag))
        elif args.command == "validate":
            version = validate_bundle(
                args.directory, args.tag, args.commit_sha, args.expected_run_id
            )
            print(f"Validated release bundle for {version}")
        else:
            create_bundle_archive(args.directory, args.archive_path)
    except (OSError, ValueError, zipfile.BadZipFile) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
