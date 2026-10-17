#!/usr/bin/env python3
"""Verify and maintain the pinned local dcbor crate patch scope."""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import tarfile
import tempfile
import urllib.request


ROOT = pathlib.Path(__file__).resolve().parents[1]
VENDOR = ROOT / "crates" / "dcbor"
PATCH = VENDOR / "local.patch"
VERSION = "0.25.2"
ARCHIVE_SHA256 = "fcf662b6347d10dd5ab7370287b76923eb88818d46434de8c424b091523f5e54"
UPSTREAM_REVISION = "c76a15a3729b5753824d0b08b95a08d7c7d8998d"
ARCHIVE_URL = f"https://static.crates.io/crates/dcbor/dcbor-{VERSION}.crate"
UPSTREAM_ROOT = f"dcbor-{VERSION}"
LOCAL_ONLY_FILES = {"PATCHES.md", "local.patch"}
MAINTAINED_FILES = {".gitignore", "Cargo.toml", "Cargo.lock", "LICENSE.md"}
MAINTAINED_DIRECTORIES = ("src/", "tests/", "examples/")


def _archive_bytes(override: pathlib.Path | None) -> bytes:
    if override is not None:
        return override.read_bytes()

    cache_root = pathlib.Path.home() / ".cargo" / "registry" / "cache"
    for candidate in cache_root.glob(f"*/dcbor-{VERSION}.crate"):
        data = candidate.read_bytes()
        if hashlib.sha256(data).hexdigest() == ARCHIVE_SHA256:
            return data

    request = urllib.request.Request(
        ARCHIVE_URL,
        headers={"User-Agent": "AIdCBOR-vendor-verifier"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


def _safe_extract(archive_data: bytes, destination: pathlib.Path) -> pathlib.Path:
    archive_path = destination / "upstream.crate"
    archive_path.write_bytes(archive_data)
    extracted = destination / "extracted"
    extracted.mkdir()
    with tarfile.open(archive_path, "r:gz") as archive:
        members = archive.getmembers()
        for member in members:
            path = pathlib.PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts or not path.parts:
                raise ValueError(f"unsafe crates.io archive member: {member.name}")
            if path.parts[0] != UPSTREAM_ROOT:
                raise ValueError(f"unexpected crates.io archive root: {member.name}")
        archive.extractall(extracted, members=members)
    return extracted / UPSTREAM_ROOT


def _checked_upstream(archive_override: pathlib.Path | None, destination: pathlib.Path) -> pathlib.Path:
    data = _archive_bytes(archive_override)
    actual = hashlib.sha256(data).hexdigest()
    if actual != ARCHIVE_SHA256:
        raise ValueError(
            f"crates.io archive checksum mismatch: expected {ARCHIVE_SHA256}, got {actual}"
        )
    upstream = _safe_extract(data, destination)
    metadata = json.loads((upstream / ".cargo_vcs_info.json").read_text(encoding="utf-8"))
    revision = metadata.get("git", {}).get("sha1")
    if revision != UPSTREAM_REVISION:
        raise ValueError(
            f"upstream revision mismatch: expected {UPSTREAM_REVISION}, got {revision!r}"
        )
    return upstream


def _files(directory: pathlib.Path) -> dict[str, bytes]:
    result: dict[str, bytes] = {}
    for path in directory.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(directory).as_posix()
        if relative in LOCAL_ONLY_FILES:
            continue
        if relative not in MAINTAINED_FILES and not relative.startswith(MAINTAINED_DIRECTORIES):
            continue
        result[relative] = path.read_bytes()
    return result


def _patch_bytes(upstream: pathlib.Path, vendor: pathlib.Path = VENDOR) -> bytes:
    upstream_files = _files(upstream)
    vendor_files = _files(vendor)
    if upstream_files.keys() != vendor_files.keys():
        missing = sorted(upstream_files.keys() - vendor_files.keys())
        extra = sorted(vendor_files.keys() - upstream_files.keys())
        details = []
        if missing:
            details.append(f"missing vendor files: {', '.join(missing)}")
        if extra:
            details.append(f"files absent upstream: {', '.join(extra)}")
        raise ValueError("file list differs from pinned upstream (" + "; ".join(details) + ")")

    chunks: list[str] = []
    for name in sorted(upstream_files):
        old = upstream_files[name]
        new = vendor_files[name]
        if old == new:
            continue
        try:
            old_text = old.decode("utf-8").splitlines(keepends=True)
            new_text = new.decode("utf-8").splitlines(keepends=True)
        except UnicodeDecodeError as error:
            raise ValueError(f"cannot represent binary vendor difference in {name}") from error
        chunks.extend(
            difflib.unified_diff(
                old_text,
                new_text,
                fromfile=f"a/{name}",
                tofile=f"b/{name}",
            )
        )
    return "".join(chunks).encode("utf-8")


def _apply_and_compare(upstream: pathlib.Path) -> None:
    import shutil

    with tempfile.TemporaryDirectory(prefix="dcbor-patched-", dir=upstream.parent) as temporary:
        temporary_repo = pathlib.Path(temporary)
        for source in upstream.iterdir():
            destination = temporary_repo / source.name
            if source.is_dir():
                shutil.copytree(source, destination)
            else:
                destination.write_bytes(source.read_bytes())

        subprocess.run(["git", "init", "--quiet", str(temporary_repo)], check=True)
        subprocess.run(
            ["git", "-C", str(temporary_repo), "apply", "-p1", str(PATCH)],
            check=True,
        )

        expected = _files(VENDOR)
        actual = _files(temporary_repo)
        if expected != actual:
            differing = sorted(
                name
                for name in expected.keys() | actual.keys()
                if expected.get(name) != actual.get(name)
            )
            raise ValueError(
                "patched archive does not match the vendor tree: " + ", ".join(differing)
            )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=("verify", "diff", "update-patch"),
        help="verify the maintained file scope, print its diff, or regenerate local.patch",
    )
    parser.add_argument("--archive", type=pathlib.Path, help="use a local crates.io archive")
    parser.add_argument(
        "--tests",
        action="store_true",
        help="run the vendored Rust tests in a temporary Cargo target directory",
    )
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="dcbor-vendor-") as temporary:
        upstream = _checked_upstream(args.archive, pathlib.Path(temporary))
        if args.command == "verify":
            if not PATCH.is_file():
                raise FileNotFoundError(PATCH)
            _apply_and_compare(upstream)
            print(
                f"Verified crates.io dcbor {VERSION} ({ARCHIVE_SHA256[:12]}…, "
                f"upstream {UPSTREAM_REVISION[:12]}…) and exact local patch."
            )
            if args.tests:
                environment = os.environ.copy()
                environment["CARGO_TARGET_DIR"] = str(pathlib.Path(temporary) / "cargo-target")
                subprocess.run(
                    [
                        "cargo",
                        "test",
                        "--manifest-path",
                        str(VENDOR / "Cargo.toml"),
                        "--locked",
                    ],
                    cwd=ROOT,
                    env=environment,
                    check=True,
                )
            return 0

        patch = _patch_bytes(upstream)
        if args.command == "diff":
            sys.stdout.buffer.write(patch)
            return 0

        PATCH.write_bytes(patch)
        print(f"Updated {PATCH.relative_to(ROOT)} ({len(patch)} bytes).")
        return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, subprocess.CalledProcessError, tarfile.TarError) as error:
        print(f"vendor verification failed: {error}", file=sys.stderr)
        raise SystemExit(1)
