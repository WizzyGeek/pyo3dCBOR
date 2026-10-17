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
            "fixtures_sha256": sha256(Path(__file__).with_name("fixtures.py").read_bytes()),
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
  <rect width="900" height="220" fill="{PALETTE["paper"]}" />
  <text x="32" y="54" class="title">Wire-size comparison unavailable</text>
  <text x="32" y="88" class="subtitle">No values are inferred for unavailable libraries: {reason}</text>
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
        "telemetry_batch": "Telemetry batch",
        "ascii_article": "ASCII article",
    }
    generic_modes = ("cbor2_default", "cbor2_canonical", "cborx_default", "cborx_canonical")
    count = len(fixtures_result)
    ratios = []
    for details in fixtures_result.values():
        baseline = details["json"]["bytes"]
        ratios.extend(details[series]["bytes"] * 100 / baseline for series in ("dcbor", *generic_modes))
    low = min(50, int(min(ratios) // 25) * 25)
    high = max(150, ((int(max(ratios)) + 24) // 25) * 25)
    if high <= low:
        high = low + 100
    width = 1100
    plot_x, plot_width = 300, 410
    top, row_pitch = 222, 36
    row_end = top + count * row_pitch
    axis_y = row_end + 14
    height = max(606, axis_y + 82)

    def x_for_percent(percent: float) -> float:
        return plot_x + (percent - low) / (high - low) * plot_width

    def mode_size(values: list[int]) -> str:
        if len(set(values)) == 1:
            return f"{values[0]:,} B"
        return f"{min(values):,}–{max(values):,} B"

    numeric = fixtures_result.get("numeric_array")
    if numeric:
        default_values = [numeric["cbor2_default"]["bytes"], numeric["cborx_default"]["bytes"]]
        canonical_values = [numeric["dcbor"]["bytes"], numeric["cbor2_canonical"]["bytes"], numeric["cborx_canonical"]["bytes"]]
        if len(set(default_values)) == 1:
            defaults_note = f"cbor2/cborx defaults {default_values[0]:,} B"
        else:
            defaults_note = f"cbor2 {default_values[0]:,} B · cborx {default_values[1]:,} B"
        if len(set(canonical_values)) == 1:
            canonical_note = f"dCBOR/canonical {canonical_values[0]:,} B"
        else:
            canonical_note = f"dCBOR {canonical_values[0]:,} · canonical {canonical_values[1]:,}/{canonical_values[2]:,} B"
        numeric_note = f"{defaults_note} · {canonical_note}"
    else:
        numeric_note = "Default and canonical modes can produce different byte counts."

    scientific = fixtures_result.get("compact_scientific_notation")
    if scientific:
        json_bytes = scientific["json"]["bytes"]
        dcbor_bytes = scientific["dcbor"]["bytes"]
        generic_values = [scientific[series]["bytes"] for series in generic_modes]
        delta = (dcbor_bytes / json_bytes - 1) * 100
        sign = "+" if delta >= 0 else "−"
        scientific_note = (
            f"dCBOR {dcbor_bytes:,} B vs JSON {json_bytes:,} B ({sign}{abs(delta):.2f}%) · "
            f"generic {mode_size(generic_values)}"
        )
    else:
        scientific_note = "The report includes the compact scientific-notation fixture."

    grid = []
    ticks = list(range(low, high + 1, 25))
    for tick in ticks:
        x = x_for_percent(tick)
        baseline = tick == 100
        grid.append(
            f'<line x1="{x:.2f}" y1="{top - 11}" x2="{x:.2f}" y2="{row_end - 4}" '
            f'stroke="{PALETTE["ink"] if baseline else PALETTE["line"]}" '
            f'stroke-width="{2 if baseline else 1}" stroke-dasharray="{"0" if baseline else "2 5"}" />'
            f'<text x="{x:.2f}" y="{axis_y + 22}" text-anchor="middle" class="axis">{tick}%</text>'
        )
    rows = []
    for index, (name, details) in enumerate(fixtures_result.items()):
        label = xml_text(fixture_labels.get(name, name.replace("_", " ")))
        center_y = top + index * row_pitch + row_pitch / 2
        baseline = details["json"]["bytes"]
        dcbor_bytes = details["dcbor"]["bytes"]
        dcbor_percent = dcbor_bytes * 100 / baseline
        generic_bytes = [details[series]["bytes"] for series in generic_modes]
        generic_low, generic_high = min(generic_bytes), max(generic_bytes)
        generic_low_percent = generic_low * 100 / baseline
        generic_high_percent = generic_high * 100 / baseline
        dcbor_x = x_for_percent(dcbor_percent)
        generic_low_x = x_for_percent(generic_low_percent)
        generic_high_x = x_for_percent(generic_high_percent)
        if generic_low == generic_high:
            generic_mark = f'<circle cx="{generic_low_x:.2f}" cy="{center_y + 4}" r="6" fill="{PALETTE["generic_range"]}" />'
        else:
            generic_mark = (
                f'<line x1="{generic_low_x:.2f}" y1="{center_y + 4}" x2="{generic_high_x:.2f}" y2="{center_y + 4}" '
                f'stroke="{PALETTE["generic_range"]}" stroke-width="8" stroke-linecap="round" />'
                f'<line x1="{generic_low_x:.2f}" y1="{center_y - 3}" x2="{generic_low_x:.2f}" y2="{center_y + 11}" stroke="{PALETTE["generic_range"]}" stroke-width="2" />'
                f'<line x1="{generic_high_x:.2f}" y1="{center_y - 3}" x2="{generic_high_x:.2f}" y2="{center_y + 11}" stroke="{PALETTE["generic_range"]}" stroke-width="2" />'
            )
        byte_summary = f"{baseline:,} · {dcbor_bytes:,} · {mode_size(generic_bytes)}"
        generic_tooltip = ", ".join(
            "{} {:,} B".format(series, details[series]["bytes"])
            for series in generic_modes
        )
        tooltip = xml_text(
            f"{fixture_labels.get(name, name.replace('_', ' '))}: JSON {baseline:,} B; dCBOR {dcbor_bytes:,} B; "
            f"generic modes {generic_tooltip}"
        )
        rows.append(
            f'<line x1="48" y1="{center_y + 18}" x2="1052" y2="{center_y + 18}" class="rule" />'
            f'<text x="48" y="{center_y + 6}" class="row-label">{label}</text>'
            f'{generic_mark}'
            f'<circle cx="{dcbor_x:.2f}" cy="{center_y - 4}" r="7" fill="{PALETTE["dcbor"]}" stroke="#FFFFFF" stroke-width="2"><title>{tooltip}</title></circle>'
            f'<text x="756" y="{center_y + 6}" class="bytes">{byte_summary}</text>'
        )
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">
  <title id="title">Wire size by fixture, dCBOR and generic CBOR modes</title>
  <desc id="desc">For each of {count} fixtures, the normalized chart shows compact JSON at 100 percent, a teal dCBOR point, and the min-to-max range across cbor2/cborx default and canonical modes. When all four generic byte counts are equal, the range collapses to one point. Each row prints exact JSON and dCBOR bytes and the generic range; the full six-mode measurements remain in the raw JSON report.</desc>
  <style>{COMMON_STYLE}
    .hero {{ font-size: 29px; font-weight: 750; letter-spacing: -0.5px; }}
    .dek {{ font-size: 15px; fill: {PALETTE["muted"]}; }}
    .row-label {{ font-size: 15px; font-weight: 620; }}
    .bytes {{ font-size: 14px; font-variant-numeric: tabular-nums; }}
  </style>
  <rect width="{width}" height="{height}" fill="{PALETTE["paper"]}" />
  <text x="48" y="43" class="hero">Wire size: where the modes split</text>
  <text x="48" y="70" class="dek">JSON = 100% · generic band spans four cbor2/cborx modes</text>
  <circle cx="56" cy="98" r="6" fill="{PALETTE["dcbor"]}" />
  <text x="72" y="103" class="legend">dCBOR</text>
  <line x1="153" y1="98" x2="187" y2="98" stroke="{PALETTE["generic_range"]}" stroke-width="7" stroke-linecap="round" />
  <text x="198" y="103" class="legend">Generic CBOR min–max; equal byte counts collapse to a point</text>
  <line x1="740" y1="89" x2="740" y2="107" stroke="{PALETTE["ink"]}" stroke-width="2" />
  <text x="752" y="103" class="legend">JSON baseline: 100%</text>
  <rect x="48" y="117" width="488" height="70" rx="8" fill="#F6F9FA" />
  <rect x="562" y="117" width="490" height="70" rx="8" fill="#F6F9FA" />
  <text x="64" y="142" class="callout-label">NUMERIC ARRAY · DEFAULT WIDTH</text>
  <text x="64" y="167" class="callout-value">{xml_text(numeric_note)}</text>
  <text x="580" y="142" class="callout-label">COMPACT SCIENTIFIC NOTATION</text>
  <text x="580" y="167" class="callout-value" fill="{PALETTE["coral"]}">{xml_text(scientific_note)}</text>
  <text x="48" y="210" class="column-head">Fixture</text>
  <text x="756" y="210" class="column-head">Exact bytes · JSON / dCBOR / generic range</text>
  {''.join(grid)}
  {''.join(rows)}
  <text x="48" y="{height - 20}" class="caption">Generic range covers cbor2 and cborx, default and canonical. Raw JSON retains every mode, sample value, and hash.</text>
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
                "fixtures_sha256": sha256(Path(__file__).with_name("fixtures.py").read_bytes()),
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
                "fixtures_sha256": sha256(Path(__file__).with_name("fixtures.py").read_bytes()),
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
                "fixtures_sha256": sha256(Path(__file__).with_name("fixtures.py").read_bytes()),
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
