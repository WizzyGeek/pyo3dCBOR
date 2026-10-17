"""Classify changed paths for CI without importing the native extension."""

import re
import sys


BUILD_PATH = re.compile(
    r"^\.github/workflows/"
    r"|(^|/)[^/]+\.(py|pyi|rs)$"
    r"|(^|/)(Cargo\.toml|Cargo\.lock|pyproject\.toml|rust-toolchain(?:\.toml)?)$"
    r"|(^|/)\.cargo/config(?:\.toml)?$"
)


def affects_build(paths):
    return any(BUILD_PATH.search(path) for path in paths)


if __name__ == "__main__":
    changed = affects_build(line.rstrip("\n") for line in sys.stdin)
    print(f"code_changed={str(changed).lower()}")
