#!/usr/bin/env python3
"""Increment the project's patch version in all authoritative metadata files."""

from __future__ import annotations

import argparse
import os
import re
import stat
import tempfile
from pathlib import Path


VERSION_RE = re.compile(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\Z")
FILES = ("pyproject.toml", "Cargo.toml", "python/dcbor/__init__.py", "Cargo.lock")


def _extract(text: str, path: str) -> tuple[str, tuple[int, int]]:
    if path == "pyproject.toml":
        pattern = re.compile(r'(?m)^version = "([^"\n]+)"\s*(?:#.*)?$')
        section = re.search(r"(?ms)^\[project\]\s*$.*?(?=^\[|\Z)", text)
        local_match = pattern.search(section.group()) if section else None
        match = (local_match, section.start()) if local_match and section else None
    elif path == "Cargo.toml":
        pattern = re.compile(r'(?m)^version = "([^"\n]+)"\s*(?:#.*)?$')
        section = re.search(r"(?ms)^\[package\]\s*$.*?(?=^\[|\Z)", text)
        local_match = pattern.search(section.group()) if section else None
        match = (local_match, section.start()) if local_match and section else None
    elif path == "python/dcbor/__init__.py":
        pattern = re.compile(r'(?m)^__version__ = "([^"\n]+)"\s*$')
        local_match = pattern.search(text)
        match = (local_match, 0) if local_match else None
    elif path == "Cargo.lock":
        package = re.search(r'(?ms)^\[\[package\]\]\s*\nname = "dcbor-py"\s*\nversion = "([^"\n]+)"\s*$', text)
        if not package:
            raise ValueError(f"could not find dcbor-py package version in {path}")
        return package.group(1), package.span(1)
    else:  # pragma: no cover - internal invariant
        raise ValueError(f"unsupported version file: {path}")

    if not match:
        raise ValueError(f"could not find project version in {path}")
    local_match, offset = match
    start, end = local_match.span(1)
    return local_match.group(1), (start + offset, end + offset)


def _replace(text: str, span: tuple[int, int], version: str) -> str:
    start, end = span
    return text[:start] + version + text[end:]


def _write_temp(destination: Path, content: bytes, mode: int) -> Path:
    fd, name = tempfile.mkstemp(prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent)
    temp_path = Path(name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temp_path, stat.S_IMODE(mode))
    except BaseException:
        temp_path.unlink(missing_ok=True)
        raise
    return temp_path


def bump(root: Path) -> str:
    originals: dict[Path, bytes] = {}
    texts: dict[Path, str] = {}
    current_versions: list[str] = []
    for relative in FILES:
        path = root / relative
        data = path.read_bytes()
        text = data.decode("utf-8")
        version, _ = _extract(text, relative)
        if not VERSION_RE.fullmatch(version):
            raise ValueError(f"{relative} has unsupported version {version!r}; expected stable X.Y.Z")
        originals[path] = data
        texts[path] = text
        current_versions.append(version)

    if len(set(current_versions)) != 1:
        details = ", ".join(f"{relative}={version}" for relative, version in zip(FILES, current_versions))
        raise ValueError(f"project version metadata disagree: {details}")

    major, minor, patch = map(int, current_versions[0].split("."))
    next_version = f"{major}.{minor}.{patch + 1}"
    replacements: dict[Path, bytes] = {}
    for relative in FILES:
        path = root / relative
        _, span = _extract(texts[path], relative)
        replacements[path] = _replace(texts[path], span, next_version).encode("utf-8")

    staged: dict[Path, Path] = {}
    backups: dict[Path, Path] = {}
    replaced: list[Path] = []
    preserve_backups: set[Path] = set()
    try:
        for path in originals:
            mode = path.stat().st_mode
            staged[path] = _write_temp(path, replacements[path], mode)
            backups[path] = _write_temp(path, originals[path], mode)
        for path in originals:
            os.replace(staged[path], path)
            replaced.append(path)
    except BaseException as error:
        rollback_errors = []
        for path in reversed(replaced):
            try:
                os.replace(backups[path], path)
            except OSError as rollback_error:
                rollback_errors.append(f"{path}: {rollback_error}")
                preserve_backups.add(path)
        detail = f"; rollback also failed for {', '.join(rollback_errors)}" if rollback_errors else ""
        raise RuntimeError(f"version update failed; prior files restored{detail}") from error
    finally:
        for temp_path in staged.values():
            temp_path.unlink(missing_ok=True)
        for path, temp_path in backups.items():
            if path not in preserve_backups:
                temp_path.unlink(missing_ok=True)
    return next_version


def main() -> int:
    parser = argparse.ArgumentParser(description="Increment the stable patch version in project metadata.")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent,
                        help="repository root (defaults to the parent of scripts/)")
    args = parser.parse_args()
    try:
        version = bump(args.root.resolve())
    except (OSError, UnicodeError, ValueError, RuntimeError) as error:
        parser.error(str(error))
    print(version)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
