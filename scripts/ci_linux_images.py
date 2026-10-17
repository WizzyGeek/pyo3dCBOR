"""Configure digest-pinned images for reduced CI; full CI uses upstream images."""

import argparse
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
IMAGE_KEYS = {
    "manylinux_x86_64",
    "musllinux_x86_64",
}


def image_environment(mode, manifest):
    if mode == "upstream":
        return {}
    if mode != "maintained":
        raise ValueError(f"Unsupported Linux image mode: {mode!r}")
    if manifest.get("rust_version") != "1.90.0":
        raise ValueError("Image Rust version must match the CI toolchain")
    images = manifest.get("images", {})
    if set(images) != IMAGE_KEYS:
        raise ValueError("Expected both x86_64 Linux image variants")
    environment = {}
    for key, reference in sorted(images.items()):
        if not isinstance(reference, str) or not re.fullmatch(
            r"ghcr\.io/wizzygeek/pyo3dcbor@sha256:[0-9a-f]{64}", reference
        ):
            raise ValueError(f"Image must use a reviewed registry digest: {key}")
        environment[f"CIBW_{key.upper()}_IMAGE"] = reference
    # Override the upstream Rust installer only when all maintained pins validate.
    environment["CIBW_BEFORE_ALL_LINUX"] = (
        "bash {project}/containers/linux/validate-image.sh"
    )
    return environment


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["upstream", "maintained"])
    args = parser.parse_args()
    manifest = json.loads((ROOT / "containers/linux/images.json").read_text())
    for key, value in image_environment(args.mode, manifest).items():
        print(f"{key}={value}")
