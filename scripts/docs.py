#!/usr/bin/env python3
"""Build the public documentation with pinned Sphinx dependencies."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys
import sysconfig


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs"
BUILD_ROOT = SOURCE / "_build"
BUILDERS = ("html", "epub", "singlehtml")


def has_native_extension(directory: Path) -> bool:
    return any(
        candidate.is_file()
        for pattern in ("_dcbor*.so", "_dcbor*.pyd", "_dcbor*.dylib")
        for candidate in directory.glob(pattern)
    )


def run_builder(builder: str) -> int:
    output = BUILD_ROOT / builder
    doctrees = BUILD_ROOT / "doctrees" / builder
    command = [
        sys.executable,
        "-m",
        "sphinx",
        "-b",
        builder,
        "-W",
        "--keep-going",
        "-n",
        "-E",
        "-a",
        "-d",
        str(doctrees),
        str(SOURCE),
        str(output),
    ]
    environment = os.environ.copy()
    if builder == "doctest":
        package_source = ROOT / "python"
        configured_paths = sysconfig.get_paths()
        site_packages = {
            Path(configured_paths[key])
            for key in ("platlib", "purelib")
            if configured_paths.get(key)
        }
        installed_extension = any(
            has_native_extension(directory / "dcbor")
            for directory in site_packages
        )
        source_extension = has_native_extension(package_source / "dcbor")
        if not installed_extension and source_extension:
            existing_pythonpath = environment.get("PYTHONPATH")
            environment["PYTHONPATH"] = os.pathsep.join(
                filter(None, (str(package_source), existing_pythonpath))
            )
    return subprocess.run(
        command, cwd=ROOT, env=environment, check=False
    ).returncode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "builder",
        choices=(*BUILDERS, "doctest", "all"),
        help="Sphinx builder to run; 'all' builds HTML, EPUB, and singlehtml",
    )
    args = parser.parse_args()

    selected = BUILDERS if args.builder == "all" else (args.builder,)
    for builder in selected:
        result = run_builder(builder)
        if result:
            return result
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
