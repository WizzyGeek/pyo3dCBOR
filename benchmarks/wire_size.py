"""Compare JSON and Python CBOR codecs by serialized bytes for shared fixtures.

Run from the repository root with the pinned comparators installed and dcbor
release-built::

    python -m pip install -r benchmarks/requirements.txt
    CARGO_BUILD_JOBS=2 maturin develop --release --locked
    PYTHONPATH=python python benchmarks/wire_size.py
"""

from __future__ import annotations

import datetime as dt
import hashlib
import importlib.machinery
import importlib.metadata
import json
import platform
import subprocess
import sys
from pathlib import Path
from typing import Callable

from chart_style import COMMON_STYLE, PALETTE, sha256_file, xml_text
from encoded_size import fixtures, equivalent_value


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = Path(__file__).resolve().parent / "wire_size"
SVG_PATH = ROOT / ".github" / "assets" / "graphs" / "wire-size.svg"
PINNED_CBOR2 = "6.1.5"
PINNED_CBORX = "0.2.5"
SERIES = (
    "json",
    "dcbor",
    "cbor2_default",
    "cbor2_canonical",
    "cborx_default",
    "cborx_canonical",
)
SHORT_LABELS = {
    "json": "JSON",
    "dcbor": "dCBOR",
    "cbor2_default": "cbor2 def",
    "cbor2_canonical": "cbor2 canon",
    "cborx_default": "cborx def",
    "cborx_canonical": "cborx canon",
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


def source_worktree_dirty() -> bool | None:
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
    if result.returncode:
        return None
    outputs = {
        b"benchmarks/encoded_size/results.json",
        b"benchmarks/wire_size/results.json",
        b"benchmarks/latency/results.json",
        b".github/assets/graphs/encoded-size.svg",
        b".github/assets/graphs/wire-size.svg",
        b".github/assets/graphs/latency.svg",
    }
    return any(entry and entry[3:] not in outputs for entry in result.stdout.split(b"\0"))


def extension_active(module: object) -> bool:
    suffixes = tuple(importlib.machinery.EXTENSION_SUFFIXES)
    for name, loaded in sys.modules.items():
        if name.startswith(("cbor2", "cborx")):
            module_file = getattr(loaded, "__file__", None)
            if module_file and str(module_file).endswith(suffixes):
                return True
    module_file = getattr(module, "__file__", None)
    return bool(module_file and str(module_file).endswith(suffixes))


def command_version(*args: str) -> str | None:
    try:
        return subprocess.check_output(
            list(args), cwd=ROOT, stderr=subprocess.STDOUT, text=True, timeout=5
        ).strip()
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None


def processor_name() -> str | None:
    name = platform.processor()
    if name:
        return name
    try:
        for line in Path("/proc/cpuinfo").read_text(encoding="utf-8").splitlines():
            key, separator, value = line.partition(":")
            if separator and key.strip().lower() in {"model name", "hardware"}:
                return value.strip()
    except OSError:
        pass
    return None


def release_build(dcbor: object) -> dict[str, object]:
    extension_path = Path(dcbor._dcbor.__file__).resolve()  # type: ignore[attr-defined]
    extension_hash = sha256(extension_path.read_bytes())
    artifact = ROOT / "target" / "release" / "lib_dcbor.so"
    artifact_hash = sha256(artifact.read_bytes()) if artifact.is_file() else None
    return {
        "profile": "release" if extension_hash == artifact_hash else "unverified",
        "extension_path": str(extension_path),
        "extension_sha256": extension_hash,
        "release_artifact_path": artifact.relative_to(ROOT).as_posix() if artifact_hash else None,
        "release_artifact_sha256": artifact_hash,
    }


def environment(dcbor: object, cbor2: object, cborx: object) -> dict[str, object]:
    return {
        "python_version": sys.version,
        "python_implementation": platform.python_implementation(),
        "python_executable": str(Path(sys.executable).resolve()),
        "platform": platform.platform(),
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "processor": processor_name(),
        "rustc_version_verbose": command_version("rustc", "--version", "--verbose"),
        "cargo_version": command_version("cargo", "--version"),
        "cargo_lock_sha256": sha256((ROOT / "Cargo.lock").read_bytes()),
        "dcbor_version": dcbor.__version__,  # type: ignore[attr-defined]
        "dcbor_build": release_build(dcbor),
        "cbor2_version": importlib.metadata.version("cbor2"),
        "cbor2_module_path": getattr(cbor2, "__file__", None),
        "cbor2_native_extension_active": extension_active(cbor2),
        "cborx_version": importlib.metadata.version("cborx"),
        "cborx_module_path": getattr(cborx, "__file__", None),
        "cborx_native_extension_active": extension_active(cborx),
    }


def encode_all(value: object, dcbor: object, cbor2: object, cborx: object) -> dict[str, bytes]:
    return {
        "json": json.dumps(
            value, ensure_ascii=False, separators=(",", ":"), allow_nan=False
        ).encode("utf-8"),
        "dcbor": dcbor.dumps(value),  # type: ignore[attr-defined]
        "cbor2_default": cbor2.dumps(value),  # type: ignore[attr-defined]
        "cbor2_canonical": cbor2.dumps(value, canonical=True),  # type: ignore[attr-defined]
        "cborx_default": cborx.dumps(value),  # type: ignore[attr-defined]
        "cborx_canonical": cborx.dumps(value, canonical=True),  # type: ignore[attr-defined]
    }


def decode(series: str, data: bytes, dcbor: object, cbor2: object, cborx: object) -> object:
    if series == "json":
        return json.loads(data.decode("utf-8"))
    if series == "dcbor":
        return dcbor.loads(data)  # type: ignore[attr-defined]
    if series.startswith("cbor2"):
        return cbor2.loads(data)  # type: ignore[attr-defined]
    return cborx.loads(data)  # type: ignore[attr-defined]


def make_report(dcbor: object, cbor2: object, cborx: object) -> dict[str, object]:
    env = environment(dcbor, cbor2, cborx)
    rows: dict[str, object] = {}
    for name, value in fixtures().items():
        encoded = encode_all(value, dcbor, cbor2, cborx)
        rows[name] = {}
        for series in SERIES:
            if not equivalent_value(decode(series, encoded[series], dcbor, cbor2, cborx), value):
                raise ValueError(f"{series} round-trip changed fixture {name}")
            rows[name][series] = {
                "bytes": len(encoded[series]),
                "sha256": sha256(encoded[series]),
                "percent_vs_json": round(
                    (len(encoded[series]) - len(encoded["json"])) * 100
                    / len(encoded["json"]),
                    2,
                ),
            }  # type: ignore[index]

    source_path = Path(__file__)
    report: dict[str, object] = {
        "status": "complete",
        "measurement": "serialized payload bytes; excludes process memory, database storage, and indexes",
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source": {
            "git_commit": git_value("rev-parse", "HEAD"),
            "git_worktree_dirty": source_worktree_dirty(),
            "generator_path": source_path.resolve().relative_to(ROOT).as_posix(),
            "generator_sha256": sha256(source_path.read_bytes()),
            "chart_style_path": "benchmarks/chart_style.py",
            "chart_style_sha256": sha256_file(Path(__file__).with_name("chart_style.py")),
            "chart_path": SVG_PATH.relative_to(ROOT).as_posix(),
        },
        "methodology": {
            "json": "UTF-8 compact separators, ensure_ascii=False, allow_nan=False",
            "dcbor": "dCBOR profile codec, release extension required",
            "cbor2_default": f"cbor2=={PINNED_CBOR2}, default dumps() options",
            "cbor2_canonical": f"cbor2=={PINNED_CBOR2}, canonical=True; length-first ordering (RFC 8949 section 4.2.3)",
            "cborx_default": f"cborx=={PINNED_CBORX}, default dumps() options",
            "cborx_canonical": f"cborx=={PINNED_CBORX}, canonical=True; bytewise encoded-key ordering per project documentation",
            "scope": "all fixtures are JSON-compatible; each codec is checked with type-sensitive round trips; generic CBOR modes are not dCBOR conformance claims",
            "percent_vs_json": "(series bytes - compact JSON bytes) / compact JSON bytes * 100; negative means fewer bytes than JSON",
        },
        "environment": env,
        "fixtures": rows,
    }
    svg = chart(report)
    report["source"]["chart_sha256"] = sha256(svg.encode("utf-8"))  # type: ignore[index]
    return report


def chart(report: dict[str, object]) -> str:
    if report.get("status") != "complete":
        reason = xml_text(report.get("blocker", "benchmark unavailable"))
        return f'''<svg xmlns="http://www.w3.org/2000/svg" width="900" height="220" viewBox="0 0 900 220" role="img" aria-labelledby="title desc">
  <title id="title">CBOR wire-size comparison unavailable</title>
  <desc id="desc">No complete codec comparison is plotted. The report records: {reason}</desc>
  <style>{COMMON_STYLE}</style>
  <rect width="900" height="220" fill="{PALETTE["canvas"]}" />
  <rect x="1" y="1" width="898" height="218" rx="12" fill="{PALETTE["paper"]}" stroke="{PALETTE["line"]}" />
  <text x="28" y="48" class="title">Wire-size comparison unavailable</text>
  <text x="28" y="82" class="subtitle">No complete codec comparison is plotted: {reason}</text>
  <text x="28" y="126" class="caption">Install the benchmark requirements, build the release extension, and rerun benchmarks/wire_size.py.</text>
  <text x="28" y="157" class="caption">No values are inferred for unavailable libraries.</text>
</svg>
'''

    fixtures_result = report["fixtures"]
    fixture_labels = {
        "small_record": "Small record",
        "nested_document": "Nested document",
        "repeated_unicode_strings": "Repeated Unicode strings",
        "numeric_array": "Numeric array",
        "compact_scientific_notation": "Compact scientific notation",
        "large_collection": "Large collection",
    }
    width, height = 1000, 835
    card_width, card_height = 460, 204
    x_positions = (32, 508)
    y_positions = (134, 354, 574)
    cards = []
    for fixture_index, (fixture_name, details) in enumerate(fixtures_result.items()):
        x = x_positions[fixture_index % 2]
        y = y_positions[fixture_index // 2]
        maximum = max(details[series]["bytes"] for series in SERIES)
        bar_x, plot_width = x + 109, 104
        rows = []
        for series_index, series in enumerate(SERIES):
            row = details[series]
            baseline = y + 57 + series_index * 21
            bar_width = max(2.0, plot_width * row["bytes"] / maximum)
            rows.append(
                f'<text x="{x + 14}" y="{baseline + 4}" class="small" fill="{PALETTE[series]}">{SHORT_LABELS[series]}</text>'
                f'<rect x="{bar_x}" y="{baseline - 6}" width="{plot_width}" height="8" rx="4" fill="{PALETTE["track"]}" />'
                f'<rect x="{bar_x}" y="{baseline - 6}" width="{bar_width:.2f}" height="8" rx="4" fill="{PALETTE[series]}" />'
                f'<text x="{x + 225}" y="{baseline + 4}" class="value">{row["bytes"]:,} B · {row["percent_vs_json"]:+.2f}%</text>'
            )
        fixture_label = xml_text(fixture_labels.get(fixture_name, fixture_name.replace("_", " ")))
        cards.append(
            f'<g aria-label="{fixture_label}">'
            f'<rect x="{x}" y="{y}" width="{card_width}" height="{card_height}" rx="12" class="card" />'
            f'<text x="{x + 14}" y="{y + 29}" class="fixture">{fixture_label}</text>'
            f'<text x="{x + card_width - 14}" y="{y + 29}" text-anchor="end" class="caption">bytes · % vs JSON</text>'
            f'{"".join(rows)}'
            f'</g>'
        )
    colors = PALETTE
    legend = []
    legend_x = (32, 153, 265, 399, 554, 682)
    legend_labels = ("JSON", "dCBOR", "cbor2 default", "cbor2 canonical", "cborx default", "cborx canonical")
    for x, series, label in zip(legend_x, SERIES, legend_labels):
        legend.append(
            f'<rect x="{x}" y="84" width="10" height="10" rx="3" fill="{colors[series]}" />'
            f'<text x="{x + 16}" y="93" class="caption">{label}</text>'
        )
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">
  <title id="title">Wire size by Python codec and fixture</title>
  <desc id="desc">Six fixture cards show exact payload byte counts and percentage differences from compact JSON for JSON, dCBOR, cbor2 default and canonical, and cborx default and canonical. Each card has its own zero-based scale. The chart measures serialized payload bytes only.</desc>
  <style>{COMMON_STYLE}</style>
  <rect width="1000" height="{height}" fill="{PALETTE["canvas"]}" />
  <text x="32" y="39" class="title">Wire size across six codec modes</text>
  <text x="32" y="62" class="subtitle">Exact payload bytes and difference from compact JSON · lower is smaller</text>
  {''.join(legend)}
  <text x="32" y="117" class="caption">Each fixture card uses its own zero-based scale. Values show bytes · percent versus JSON.</text>
  {''.join(cards)}
  <text x="32" y="811" class="caption">cbor2 {PINNED_CBOR2} and cborx {PINNED_CBORX}; canonical modes follow their respective ordering rules. See report for methodology and hashes.</text>
</svg>
'''


def write_report(report: dict[str, object]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "results.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    SVG_PATH.parent.mkdir(parents=True, exist_ok=True)
    SVG_PATH.write_text(chart(report), encoding="utf-8")


def main() -> int:
    try:
        import cbor2
        import cborx
        import dcbor
    except ImportError as exc:
        reason = f"required benchmark package is unavailable: {exc.name}"
        report = {
            "status": "blocked",
            "blocker": reason,
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
            "expected_versions": {
                "dcbor": "0.1.0",
                "cbor2": PINNED_CBOR2,
                "cborx": PINNED_CBORX,
            },
            "environment": {
                "python_version": sys.version,
                "platform": platform.platform(),
                "machine": platform.machine(),
                "rustc_version_verbose": command_version("rustc", "--version", "--verbose"),
                "cargo_version": command_version("cargo", "--version"),
            },
            "fixtures": None,
        }
        report["source"]["chart_sha256"] = sha256(chart(report).encode("utf-8"))
        write_report(report)
        print(f"Blocked: {reason}; install benchmarks/requirements.txt")
        return 2

    env = environment(dcbor, cbor2, cborx)
    blockers = []
    for package, expected, observed in (
        ("dcbor", "0.1.0", dcbor.__version__),
        ("cbor2", PINNED_CBOR2, env["cbor2_version"]),
        ("cborx", PINNED_CBORX, env["cborx_version"]),
    ):
        if observed != expected:
            blockers.append(f"expected {package}=={expected}, found {observed}")
    if env["dcbor_build"]["profile"] != "release":
        blockers.append("loaded dcbor extension does not match target/release/lib_dcbor.so")
    if blockers:
        report = {
            "status": "blocked",
            "blocker": "; ".join(blockers),
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
            "environment": env,
            "fixtures": None,
        }
        report["source"]["chart_sha256"] = sha256(chart(report).encode("utf-8"))
        write_report(report)
        print(f"Blocked: {report['blocker']}")
        return 2

    try:
        report = make_report(dcbor, cbor2, cborx)
    except Exception as exc:
        report = {
            "status": "failed",
            "blocker": f"fixture validation failed: {type(exc).__name__}: {exc}",
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
            "environment": env,
            "fixtures": None,
        }
        report["source"]["chart_sha256"] = sha256(chart(report).encode("utf-8"))
        write_report(report)
        print(f"Failed: {report['blocker']}")
        return 1
    write_report(report)
    print(f"Wrote {OUTPUT_DIR / 'results.json'} and {SVG_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
