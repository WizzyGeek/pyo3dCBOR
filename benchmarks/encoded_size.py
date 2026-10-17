"""Measure compact JSON and dcbor wire sizes for equivalent JSON values.

Run from the repository root with the package installed or with ``PYTHONPATH=python``:

    PYTHONPATH=python python benchmarks/encoded_size.py

The default outputs are benchmarks/encoded_size/results.json and the stable
chart path .github/assets/graphs/encoded-size.svg. This script uses only
Python's standard library plus the dcbor package being measured.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import platform
import subprocess
import sys
from pathlib import Path

from chart_style import COMMON_STYLE, PALETTE, sha256_file, xml_text


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = Path(__file__).resolve().parent / "encoded_size"
SVG_PATH = ROOT / ".github" / "assets" / "graphs" / "encoded-size.svg"


def fixtures() -> dict[str, object]:
    """Return documented, ordinary JSON-compatible logical values."""
    return {
        "small_record": {
            "id": 42,
            "name": "Ada",
            "active": True,
            "nickname": None,
        },
        "nested_document": {
            "user": {"id": 731, "name": "Mira"},
            "roles": ["reader", "editor"],
            "settings": {"theme": "dark", "alerts": False},
            "scores": [3, 8, 13],
        },
        "repeated_unicode_strings": [
            {"city": city, "label": "café", "unit": "km"}
            for city in ("Zürich", "Montréal", "Zürich", "Montréal") * 8
        ],
        "numeric_array": [
            -1000000, -257, -24, -1, 0, 1, 23, 256, 65536, 2**32,
            0.25, -1.5, 3.125, 1.1, 1e20,
        ] * 12,
        "compact_scientific_notation": [1e100, 1e-100],
        "large_collection": [
            {
                "item": index,
                "group": f"group-{index % 8}",
                "enabled": index % 3 != 0,
                "values": [index, index + 1, index + 2],
            }
            for index in range(128)
        ],
    }


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git_value(*args: str) -> str | None:
    try:
        return subprocess.check_output(
            ["git", *args], cwd=ROOT, stderr=subprocess.DEVNULL, text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def command_version(command: str) -> str | None:
    try:
        return subprocess.check_output(
            [command, "--version"], cwd=ROOT, stderr=subprocess.STDOUT,
            text=True, timeout=5,
        ).strip()
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None


def equivalent_value(actual: object, expected: object) -> bool:
    """Compare fixtures recursively while preserving exact Python value types."""
    if type(actual) is not type(expected):
        return False
    if isinstance(expected, dict):
        if len(actual) != len(expected):
            return False
        for expected_key, expected_value in expected.items():
            matching_keys = [
                key for key in actual
                if type(key) is type(expected_key) and key == expected_key
            ]
            if not matching_keys:
                return False
            actual_key = matching_keys[0]
            if not equivalent_value(actual[actual_key], expected_value):
                return False
        return True
    if isinstance(expected, list):
        return len(actual) == len(expected) and all(
            equivalent_value(left, right) for left, right in zip(actual, expected)
        )
    if isinstance(expected, float):
        return actual.hex() == expected.hex()
    return actual == expected


def processor_name() -> str | None:
    name = platform.processor()
    if name:
        return name
    # platform.processor() is empty on several Linux distributions.
    cpuinfo = Path("/proc/cpuinfo")
    try:
        for line in cpuinfo.read_text(encoding="utf-8").splitlines():
            key, separator, value = line.partition(":")
            if separator and key.strip().lower() in {"model name", "hardware"}:
                return value.strip()
    except OSError:
        pass
    return None


def source_worktree_dirty() -> bool | None:
    """Report source dirtiness while excluding generated benchmark outputs."""
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=all", "-z"],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None

    report_outputs = {
        b"benchmarks/encoded_size/results.json",
        b"benchmarks/wire_size/results.json",
        b"benchmarks/latency/results.json",
        b".github/assets/graphs/encoded-size.svg",
        b".github/assets/graphs/wire-size.svg",
        b".github/assets/graphs/latency.svg",
    }
    for entry in result.stdout.split(b"\0"):
        if not entry:
            continue
        if entry[3:] not in report_outputs:
            return True
    return False


def build_results(dcbor: object) -> dict[str, object]:
    measured: dict[str, object] = {}
    for name, value in fixtures().items():
        json_bytes = json.dumps(
            value, ensure_ascii=False, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
        wire_bytes = dcbor.dumps(value)  # type: ignore[attr-defined]
        # Guard against accidentally comparing non-equivalent or unsupported values.
        if not equivalent_value(json.loads(json_bytes.decode("utf-8")), value):
            raise ValueError(f"JSON round-trip changed fixture {name}")
        if not equivalent_value(dcbor.loads(wire_bytes), value):  # type: ignore[attr-defined]
            raise ValueError(f"dCBOR round-trip changed fixture {name}")
        measured[name] = {
            "json_utf8_bytes": len(json_bytes),
            "json_sha256": sha256(json_bytes),
            "dcbor_wire_bytes": len(wire_bytes),
            "dcbor_wire_sha256": sha256(wire_bytes),
            "dcbor_vs_json_percent": round(
                (len(wire_bytes) - len(json_bytes)) * 100 / len(json_bytes), 2
            ),
        }

    extension_path = Path(dcbor._dcbor.__file__).resolve()  # type: ignore[attr-defined]
    extension_bytes = extension_path.read_bytes()
    release_artifact = ROOT / "target" / "release" / "lib_dcbor.so"
    release_artifact_hash = (
        sha256(release_artifact.read_bytes()) if release_artifact.is_file() else None
    )
    extension_hash = sha256(extension_bytes)
    release_artifact_matches = (
        extension_hash == release_artifact_hash
        if release_artifact_hash is not None
        else None
    )
    cargo_lock = ROOT / "Cargo.lock"

    return {
        "measurement": "serialized payload bytes; not memory footprint",
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source": {
            "git_commit": git_value("rev-parse", "HEAD"),
            "git_worktree_dirty": source_worktree_dirty(),
            "generator_path": Path(__file__).resolve().relative_to(ROOT).as_posix(),
            "generator_sha256": sha256(Path(__file__).read_bytes()),
            "chart_style_path": "benchmarks/chart_style.py",
            "chart_style_sha256": sha256_file(Path(__file__).with_name("chart_style.py")),
            "chart_path": SVG_PATH.relative_to(ROOT).as_posix(),
        },
        "build": {
            "profile": "release" if release_artifact_matches else "unverified",
            "profile_verification": "imported extension SHA-256 matches the Cargo release artifact",
            "reproduction_command": "CARGO_BUILD_JOBS=2 maturin develop --release --locked",
            "release_artifact_path": (
                release_artifact.relative_to(ROOT).as_posix()
                if release_artifact_hash is not None
                else None
            ),
            "release_artifact_sha256": release_artifact_hash,
            "extension_matches_release_artifact": release_artifact_matches,
            "rustc_version": command_version("rustc"),
            "cargo_version": command_version("cargo"),
            "root_cargo_lock_sha256": (
                sha256(cargo_lock.read_bytes()) if cargo_lock.is_file() else None
            ),
        },
        "environment": {
            "python_version": sys.version,
            "python_implementation": platform.python_implementation(),
            "platform": platform.platform(),
            "machine": platform.machine(),
            "processor": processor_name(),
            "dcbor_version": dcbor.__version__,  # type: ignore[attr-defined]
            "extension_path": str(extension_path),
            "extension_sha256": sha256(extension_bytes),
        },
        "json_encoding": {
            "implementation": "Python standard-library json",
            "utf8": True,
            "ensure_ascii": False,
            "whitespace": "removed with separators=(',', ':')",
            "nonfinite_numbers": "rejected",
        },
        "fixtures": measured,
    }


def svg_chart(results: dict[str, object]) -> str:
    rows = results["fixtures"]
    assert isinstance(rows, dict)
    labels = {
        "small_record": "Small record",
        "nested_document": "Nested document",
        "repeated_unicode_strings": "Repeated Unicode strings",
        "numeric_array": "Numeric array",
        "compact_scientific_notation": "Compact scientific notation",
        "large_collection": "Large collection",
    }
    width, height = 1000, 690
    card_width, card_height = 300, 246
    x_positions = (32, 350, 668)
    y_positions = (116, 380)
    cards = []
    for index, (name, row) in enumerate(rows.items()):
        x = x_positions[index % 3]
        y = y_positions[index // 3]
        maximum = max(row["json_utf8_bytes"], row["dcbor_wire_bytes"])
        plot_width = card_width - 32
        json_width = max(3, plot_width * row["json_utf8_bytes"] / maximum)
        cbor_width = max(3, plot_width * row["dcbor_wire_bytes"] / maximum)
        delta = row["json_utf8_bytes"] - row["dcbor_wire_bytes"]
        note = (
            f'{delta:,} B fewer than JSON' if delta >= 0
            else f'{abs(delta):,} B more than JSON'
        )
        cards.append(
            f'<g aria-label="{xml_text(labels.get(name, name.replace("_", " ")))}">'
            f'<rect x="{x}" y="{y}" width="{card_width}" height="{card_height}" rx="12" class="card" />'
            f'<text x="{x + 16}" y="{y + 28}" class="fixture">{xml_text(labels.get(name, name.replace("_", " ")))}</text>'
            f'<text x="{x + 16}" y="{y + 70}" class="small">Compact JSON</text>'
            f'<text x="{x + card_width - 16}" y="{y + 70}" text-anchor="end" class="value">{row["json_utf8_bytes"]:,} B</text>'
            f'<rect x="{x + 16}" y="{y + 79}" width="{plot_width}" height="9" rx="4.5" fill="{PALETTE["track"]}" />'
            f'<rect x="{x + 16}" y="{y + 79}" width="{json_width:.2f}" height="9" rx="4.5" fill="{PALETTE["json"]}" />'
            f'<text x="{x + 16}" y="{y + 127}" class="small">dCBOR · {row["dcbor_vs_json_percent"]:+.2f}% vs JSON</text>'
            f'<text x="{x + card_width - 16}" y="{y + 127}" text-anchor="end" class="value">{row["dcbor_wire_bytes"]:,} B</text>'
            f'<rect x="{x + 16}" y="{y + 136}" width="{plot_width}" height="9" rx="4.5" fill="{PALETTE["track"]}" />'
            f'<rect x="{x + 16}" y="{y + 136}" width="{cbor_width:.2f}" height="9" rx="4.5" fill="{PALETTE["dcbor"]}" />'
            f'<line x1="{x + 16}" y1="{y + 170}" x2="{x + card_width - 16}" y2="{y + 170}" class="rule" />'
            f'<text x="{x + 16}" y="{y + 195}" class="caption">{xml_text(note)}</text>'
            f'</g>'
        )
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}"
 viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">
  <title id="title">Compact JSON and dCBOR payload sizes</title>
  <desc id="desc">Six fixture cards compare exact compact JSON UTF-8 bytes with dCBOR wire bytes. Each card has its own zero-based scale, plus the exact dCBOR percentage difference versus JSON. The chart measures serialized payload size, not process memory.</desc>
  <style>{COMMON_STYLE}</style>
  <rect width="1000" height="690" fill="{PALETTE["canvas"]}" />
  <text x="32" y="39" class="title">Payload size, fixture by fixture</text>
  <text x="32" y="63" class="subtitle">Compact UTF-8 JSON and dCBOR wire bytes · lower is smaller</text>
  <rect x="32" y="82" width="12" height="12" rx="3" fill="{PALETTE["json"]}" />
  <text x="51" y="92" class="caption">Compact JSON</text>
  <rect x="155" y="82" width="12" height="12" rx="3" fill="{PALETTE["dcbor"]}" />
  <text x="174" y="92" class="caption">dCBOR</text>
  <text x="968" y="92" text-anchor="end" class="caption">Each fixture card uses its own zero-based scale</text>
  {''.join(cards)}
  <text x="32" y="665" class="caption">Difference = (dCBOR bytes − JSON bytes) / JSON bytes. See the report for hashes, fixture definitions, and method.</text>
</svg>
'''


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    args = parser.parse_args()
    import dcbor

    results = build_results(dcbor)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "results.json"
    svg = svg_chart(results)
    results["source"]["chart_sha256"] = sha256(svg.encode("utf-8"))
    json_path.write_text(
        json.dumps(results, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    SVG_PATH.parent.mkdir(parents=True, exist_ok=True)
    SVG_PATH.write_text(svg, encoding="utf-8")
    print(f"Wrote {json_path} and {SVG_PATH}")


if __name__ == "__main__":
    main()
