"""Classify changed paths for CI without importing the native extension."""

import re
import sys


BUILD_PATH = re.compile(
    r"^containers/linux/"
    r"|^\.github/workflows/"
    r"|(^|/)[^/]+\.(py|pyi|rs)$"
    r"|(^|/)(Cargo\.toml|Cargo\.toml\.orig|Cargo\.lock|pyproject\.toml|"
    r"pytest\.ini|py\.typed|rust-toolchain(?:\.toml)?)$"
    r"|(^|/)\.gitattributes$"
    r"|(^|/)\.cargo/config(?:\.toml)?$"
)


def affects_build(paths):
    return any(
        BUILD_PATH.search(path)
        for path in paths
        if not path.startswith("maintenance/")
    )


if __name__ == "__main__":
    changed = affects_build(line.rstrip("\n") for line in sys.stdin)
    print(f"code_changed={str(changed).lower()}")
