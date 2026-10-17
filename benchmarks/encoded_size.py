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
from fixtures import fixtures


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = Path(__file__).resolve().parent / "encoded_size"
SVG_PATH = ROOT / ".github" / "assets" / "graphs" / "encoded-size.svg"


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
            "fixtures_sha256": sha256(Path(__file__).with_name("fixtures.py").read_bytes()),
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
        "telemetry_batch": "Telemetry batch",
        "ascii_article": "ASCII article",
    }
    height = max(510, 258 + len(rows) * 42)
    width = 1100
    count = len(rows)
    smaller = sum(row["dcbor_wire_bytes"] < row["json_utf8_bytes"] for row in rows.values())
    top = 169
    row_pitch = 42
    row_end = top + count * row_pitch
    percentages = [row["dcbor_wire_bytes"] * 100 / row["json_utf8_bytes"] for row in rows.values()]
    low = min(50, int(min(percentages) // 25) * 25)
    high = max(150, ((int(max(percentages)) + 24) // 25) * 25)
    if high <= low:
        high = low + 100
    plot_x, plot_width = 322, 380

    def x_for_percent(percent: float) -> float:
        return plot_x + (percent - low) / (high - low) * plot_width

    grid = []
    ticks = list(range(low, high + 1, 25))
    for tick in ticks:
        x = x_for_percent(tick)
        baseline = tick == 100
        grid.append(
            f'<line x1="{x:.2f}" y1="{top - 8}" x2="{x:.2f}" y2="{row_end - 7}" '
            f'stroke="{PALETTE["ink"] if baseline else PALETTE["line"]}" '
            f'stroke-width="{2 if baseline else 1}" stroke-dasharray="{"0" if baseline else "2 5"}" />'
            f'<text x="{x:.2f}" y="{row_end + 19}" text-anchor="middle" class="axis">{tick}%</text>'
        )
    chart_rows = []
    for index, (name, row) in enumerate(rows.items()):
        label = xml_text(labels.get(name, name.replace("_", " ")))
        y = top + index * row_pitch + row_pitch / 2
        json_x = x_for_percent(100)
        dcbor_percent = row["dcbor_wire_bytes"] * 100 / row["json_utf8_bytes"]
        dcbor_x = x_for_percent(dcbor_percent)
        improved = dcbor_percent < 100
        accent = PALETTE["dcbor"] if improved else PALETTE["coral"]
        signed_delta = dcbor_percent - 100
        delta = f'{"−" if signed_delta < 0 else "+"}{abs(signed_delta):.2f}%'
        title = xml_text(f'{labels.get(name, name.replace("_", " "))}: JSON {row["json_utf8_bytes"]:,} B, dCBOR {row["dcbor_wire_bytes"]:,} B, {delta}')
        chart_rows.append(
            f'<line x1="48" y1="{y + 20}" x2="1052" y2="{y + 20}" class="rule" />'
            f'<text x="48" y="{y + 6}" class="row-label">{label}</text>'
            f'<line x1="{min(json_x, dcbor_x):.2f}" y1="{y}" x2="{max(json_x, dcbor_x):.2f}" y2="{y}" stroke="{PALETTE["line_strong"]}" stroke-width="3" />'
            f'<circle cx="{json_x:.2f}" cy="{y}" r="7" fill="{PALETTE["json"]}" />'
            f'<circle cx="{dcbor_x:.2f}" cy="{y}" r="8" fill="{accent}" stroke="#FFFFFF" stroke-width="2"><title>{title}</title></circle>'
            f'<text x="728" y="{y + 6}" class="bytes">{row["json_utf8_bytes"]:,} B <tspan class="muted">→</tspan> {row["dcbor_wire_bytes"]:,} B</text>'
            f'<text x="1052" y="{y + 7}" text-anchor="end" class="delta" fill="{accent}">{delta}</text>'
        )
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">
  <title id="title">Compact JSON and dCBOR payload size comparison</title>
  <desc id="desc">A normalized dumbbell plot compares dCBOR with compact UTF-8 JSON across {count} fixtures. JSON is 100 percent; dCBOR points left when it uses fewer bytes and right when it uses more. Exact byte counts and percentage differences are printed for every fixture. {smaller} of {count} fixtures are smaller with dCBOR.</desc>
  <style>{COMMON_STYLE}
    .hero {{ font-size: 30px; font-weight: 760; letter-spacing: -0.55px; }}
    .dek {{ font-size: 16px; fill: {PALETTE["muted"]}; }}
    .row-label {{ font-size: 16px; font-weight: 620; }}
    .bytes {{ font-size: 15px; font-variant-numeric: tabular-nums; }}
    .delta {{ font-size: 20px; font-weight: 750; font-variant-numeric: tabular-nums; }}
    .axis {{ font-size: 13px; fill: {PALETTE["muted"]}; }}
  </style>
  <rect width="{width}" height="{height}" fill="{PALETTE["paper"]}" />
  <text x="48" y="51" class="hero">dCBOR uses fewer bytes in {smaller} of {count} fixtures</text>
  <text x="48" y="81" class="dek">Compact UTF-8 JSON = 100% · dCBOR left of 100% uses fewer bytes</text>
  <line x1="48" y1="119" x2="78" y2="119" stroke="{PALETTE["line_strong"]}" stroke-width="3" />
  <circle cx="48" cy="119" r="6" fill="{PALETTE["json"]}" />
  <text x="90" y="124" class="legend">Compact JSON · 100%</text>
  <circle cx="278" cy="119" r="7" fill="{PALETTE["dcbor"]}" />
  <text x="295" y="124" class="legend">dCBOR</text>
  <circle cx="391" cy="119" r="7" fill="{PALETTE["coral"]}" />
  <text x="408" y="124" class="legend">dCBOR increase</text>
  <text x="728" y="148" class="column-head">JSON → dCBOR bytes</text>
  <text x="1052" y="148" text-anchor="end" class="column-head">Change</text>
  {''.join(grid)}
  {''.join(chart_rows)}
  <text x="48" y="{height - 23}" class="caption">Each row shares one percent axis. Positive change marks the scientific-notation size loss; details and hashes are in the report.</text>
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
