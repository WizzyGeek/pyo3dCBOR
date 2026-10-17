"""Compare encode, decode, and round-trip latency for JSON-compatible values.

From the repository root, install the pinned comparator and run against a
release-built extension::

    python -m pip install -r benchmarks/requirements.txt
    CARGO_BUILD_JOBS=2 maturin develop --release --locked
    PYTHONPATH=python python benchmarks/latency.py

The runner launches one fresh Python process per repetition. It writes raw
measurements to ``benchmarks/latency/results.json`` and replaces the stable
chart at ``.github/assets/graphs/latency.svg``.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.machinery
import importlib.metadata
import json
import os
import platform
import statistics
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable

from chart_style import COMMON_STYLE, PALETTE, ratio_fill, sha256_file, xml_text


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = Path(__file__).resolve().parent / "latency"
SVG_PATH = ROOT / ".github" / "assets" / "graphs" / "latency.svg"
PINNED_CBOR2 = "6.1.5"
PINNED_CBORX = "0.2.5"
DEFAULT_WARMUP = 500
DEFAULT_ROUNDS = 1_000
DEFAULT_REPETITIONS = 9
IMPLEMENTATIONS = (
    "json", "dcbor", "cbor2_default", "cbor2_canonical",
    "cborx_default", "cborx_canonical",
)


def fixtures() -> dict[str, object]:
    """Keep these values and names aligned with benchmarks/encoded_size.py."""
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


def type_sensitive_equal(left: object, right: object) -> bool:
    """Compare JSON-compatible values without Python's bool/int equality trap."""
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        if len(left) != len(right):  # type: ignore[arg-type]
            return False
        unmatched = list(right.items())  # type: ignore[union-attr]
        for left_key, left_value in left.items():
            for index, (right_key, right_value) in enumerate(unmatched):
                if type_sensitive_equal(left_key, right_key):
                    if not type_sensitive_equal(left_value, right_value):
                        return False
                    unmatched.pop(index)
                    break
            else:
                return False
        return not unmatched
    if isinstance(left, (list, tuple)):
        return len(left) == len(right) and all(  # type: ignore[arg-type]
            type_sensitive_equal(a, b) for a, b in zip(left, right)  # type: ignore[arg-type]
        )
    return left == right


def git_value(*args: str) -> str | None:
    try:
        return subprocess.check_output(
            ["git", *args], cwd=ROOT, stderr=subprocess.DEVNULL, text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def dirty_from_porcelain(status: bytes) -> bool:
    """Ignore generated benchmark reports/charts, but flag source changes."""
    report_outputs = {
        b"benchmarks/encoded_size/results.json",
        b"benchmarks/wire_size/results.json",
        b"benchmarks/latency/results.json",
        b".github/assets/graphs/encoded-size.svg",
        b".github/assets/graphs/wire-size.svg",
        b".github/assets/graphs/latency.svg",
    }
    for entry in status.split(b"\0"):
        if entry and entry[3:] not in report_outputs:
            return True
    return False


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
    if result.returncode != 0:
        return None
    return dirty_from_porcelain(result.stdout)


def command_version(*args: str) -> str | None:
    try:
        return subprocess.check_output(
            list(args), cwd=ROOT, stderr=subprocess.STDOUT, text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def build_provenance() -> dict[str, str | None]:
    lockfile = ROOT / "Cargo.lock"
    return {
        "rustc_version_verbose": command_version("rustc", "--version", "--verbose"),
        "cargo_version": command_version("cargo", "--version"),
        "cargo_lock_sha256": sha256(lockfile.read_bytes()) if lockfile.is_file() else None,
    }


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


def release_build_evidence(extension_path: Path) -> dict[str, object]:
    """Verify the loaded extension is byte-identical to Cargo's release artifact."""
    release_artifact = ROOT / "target" / "release" / "lib_dcbor.so"
    extension_hash = sha256(extension_path.read_bytes())
    artifact_hash = sha256(release_artifact.read_bytes()) if release_artifact.is_file() else None
    return {
        "profile": "release" if artifact_hash == extension_hash else "unverified",
        "verified_by": "SHA-256 equality with target/release/lib_dcbor.so",
        "release_artifact": str(release_artifact),
        "release_artifact_sha256": artifact_hash,
        "extension_sha256": extension_hash,
    }


def extension_active(module: object) -> bool:
    """Report whether an imported comparator module uses a native extension."""
    suffixes = tuple(importlib.machinery.EXTENSION_SUFFIXES)
    for name, loaded in sys.modules.items():
        if name.startswith(("cbor2", "cborx")):
            module_file = getattr(loaded, "__file__", None)
            if module_file and str(module_file).endswith(suffixes):
                return True
    module_file = getattr(module, "__file__", None)
    return bool(module_file and str(module_file).endswith(suffixes))


def cbor2_version(module: object) -> str:
    try:
        return importlib.metadata.version("cbor2")
    except importlib.metadata.PackageNotFoundError:
        return str(getattr(module, "__version__", "unknown"))


def environment(dcbor: object, cbor2: object, cborx: object) -> dict[str, object]:
    extension_path = Path(dcbor._dcbor.__file__).resolve()  # type: ignore[attr-defined]
    return {
        "python_version": sys.version,
        "python_implementation": platform.python_implementation(),
        "python_executable": str(Path(sys.executable).resolve()),
        "stdlib_json_version": getattr(json, "__version__", "bundled with Python"),
        "platform": platform.platform(),
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "processor": processor_name(),
        **build_provenance(),
        "dcbor_version": dcbor.__version__,  # type: ignore[attr-defined]
        "dcbor_extension_path": str(extension_path),
        "dcbor_extension_sha256": sha256(extension_path.read_bytes()),
        "dcbor_build": release_build_evidence(extension_path),
        "cbor2_version": cbor2_version(cbor2),
        "cbor2_module_path": getattr(cbor2, "__file__", None),
        "cbor2_native_extension_active": extension_active(cbor2),
        "cborx_version": importlib.metadata.version("cborx"),
        "cborx_module_path": getattr(cborx, "__file__", None),
        "cborx_native_extension_active": extension_active(cborx),
    }


def logical_fixture_hashes() -> dict[str, str]:
    return {
        name: sha256(
            json.dumps(
                value, ensure_ascii=False, separators=(",", ":"), allow_nan=False
            ).encode("utf-8")
        )
        for name, value in fixtures().items()
    }


def worker(warmup: int, rounds: int, order_offset: int) -> dict[str, object]:
    import cbor2
    import cborx
    import dcbor

    if cbor2_version(cbor2) != PINNED_CBOR2:
        raise RuntimeError(
            f"expected cbor2=={PINNED_CBOR2}, found {cbor2_version(cbor2)}"
        )
    cborx_version = importlib.metadata.version("cborx")
    if cborx_version != PINNED_CBORX:
        raise RuntimeError(f"expected cborx=={PINNED_CBORX}, found {cborx_version}")
    env = environment(dcbor, cbor2, cborx)
    if dcbor.__version__ != "0.1.0":  # type: ignore[attr-defined]
        raise RuntimeError(f"expected dcbor==0.1.0, found {dcbor.__version__}")  # type: ignore[attr-defined]
    if env["dcbor_build"]["profile"] != "release":  # type: ignore[index]
        raise RuntimeError("loaded dcbor extension does not match target/release/lib_dcbor.so")

    rows: dict[str, object] = {}
    for name, value in fixtures().items():
        json_bytes = json.dumps(
            value, ensure_ascii=False, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
        dcbor_bytes = dcbor.dumps(value)  # type: ignore[attr-defined]
        cbor2_default_bytes = cbor2.dumps(value)
        cbor2_canonical_bytes = cbor2.dumps(value, canonical=True)
        cborx_default_bytes = cborx.dumps(value)
        cborx_canonical_bytes = cborx.dumps(value, canonical=True)
        if not type_sensitive_equal(json.loads(json_bytes.decode("utf-8")), value):
            raise ValueError(f"JSON changed fixture {name}")
        if not type_sensitive_equal(dcbor.loads(dcbor_bytes), value):  # type: ignore[attr-defined]
            raise ValueError(f"dCBOR changed fixture {name}")
        if not type_sensitive_equal(cbor2.loads(cbor2_default_bytes), value):
            raise ValueError(f"cbor2 default mode changed fixture {name}")
        if not type_sensitive_equal(cbor2.loads(cbor2_canonical_bytes), value):
            raise ValueError(f"cbor2 canonical mode changed fixture {name}")
        if not type_sensitive_equal(cborx.loads(cborx_default_bytes), value):
            raise ValueError(f"cborx default mode changed fixture {name}")
        if not type_sensitive_equal(cborx.loads(cborx_canonical_bytes), value):
            raise ValueError(f"cborx canonical mode changed fixture {name}")

        implementations: dict[str, dict[str, Callable[[], object]]] = {
            "json": {
                "encode": lambda value=value: json.dumps(
                    value, ensure_ascii=False, separators=(",", ":"), allow_nan=False
                ).encode("utf-8"),
                "decode": lambda data=json_bytes: json.loads(data.decode("utf-8")),
                "round_trip": lambda value=value: json.loads(
                    json.dumps(
                        value, ensure_ascii=False, separators=(",", ":"), allow_nan=False
                    ).encode("utf-8").decode("utf-8")
                ),
            },
            "dcbor": {
                "encode": lambda value=value: dcbor.dumps(value),  # type: ignore[attr-defined]
                "decode": lambda data=dcbor_bytes: dcbor.loads(data),  # type: ignore[attr-defined]
                "round_trip": lambda value=value: dcbor.loads(dcbor.dumps(value)),  # type: ignore[attr-defined]
            },
            "cbor2_default": {
                "encode": lambda value=value: cbor2.dumps(value),
                "decode": lambda data=cbor2_default_bytes: cbor2.loads(data),
                "round_trip": lambda value=value: cbor2.loads(cbor2.dumps(value)),
            },
            "cbor2_canonical": {
                "encode": lambda value=value: cbor2.dumps(value, canonical=True),
                "decode": lambda data=cbor2_canonical_bytes: cbor2.loads(data),
                "round_trip": lambda value=value: cbor2.loads(
                    cbor2.dumps(value, canonical=True)
                ),
            },
            "cborx_default": {
                "encode": lambda value=value: cborx.dumps(value),
                "decode": lambda data=cborx_default_bytes: cborx.loads(data),
                "round_trip": lambda value=value: cborx.loads(cborx.dumps(value)),
            },
            "cborx_canonical": {
                "encode": lambda value=value: cborx.dumps(value, canonical=True),
                "decode": lambda data=cborx_canonical_bytes: cborx.loads(data),
                "round_trip": lambda value=value: cborx.loads(
                    cborx.dumps(value, canonical=True)
                ),
            },
        }
        measured: dict[str, object] = {}
        implementation_order = IMPLEMENTATIONS
        offset = order_offset % len(implementation_order)
        implementation_order = implementation_order[offset:] + implementation_order[:offset]
        for implementation in implementation_order:
            operations = implementations[implementation]
            measured[implementation] = {}
            for operation, function in operations.items():
                for _ in range(warmup):
                    function()
                start = time.perf_counter_ns()
                for _ in range(rounds):
                    function()
                elapsed_ns = time.perf_counter_ns() - start
                measured[implementation][operation] = elapsed_ns / rounds  # type: ignore[index]
        rows[name] = measured

    return {
        "pid": os.getpid(),
        "started_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "implementation_order": implementation_order,
        "measurements_ns_per_operation": rows,
        "encoded_hashes": {
            name: {
                "json_utf8_sha256": sha256(json.dumps(
                    value, ensure_ascii=False, separators=(",", ":"), allow_nan=False
                ).encode("utf-8")),
                "dcbor_sha256": sha256(dcbor.dumps(value)),  # type: ignore[attr-defined]
                "cbor2_default_sha256": sha256(cbor2.dumps(value)),
                "cbor2_canonical_sha256": sha256(cbor2.dumps(value, canonical=True)),
                "cborx_default_sha256": sha256(cborx.dumps(value)),
                "cborx_canonical_sha256": sha256(cborx.dumps(value, canonical=True)),
            }
            for name, value in fixtures().items()
        },
        "environment": env,
    }


def summarize(samples: list[float]) -> dict[str, object]:
    median = statistics.median(samples)
    return {
        "samples_ns_per_operation": samples,
        "median_ns_per_operation": median,
        "mad_ns_per_operation": statistics.median(abs(value - median) for value in samples),
        "minimum_ns_per_operation": min(samples),
        "maximum_ns_per_operation": max(samples),
    }


def aggregate(worker_runs: list[dict[str, object]]) -> dict[str, object]:
    fixture_rows: dict[str, object] = {}
    for name in fixtures():
        fixture_rows[name] = {}
        for implementation in IMPLEMENTATIONS:
            fixture_rows[name][implementation] = {}  # type: ignore[index]
            for operation in ("encode", "decode", "round_trip"):
                samples = [
                    run["measurements_ns_per_operation"][name][implementation][operation]
                    for run in worker_runs
                ]
                fixture_rows[name][implementation][operation] = summarize(samples)  # type: ignore[index]
    return fixture_rows


def metadata(warmup: int, rounds: int, repetitions: int) -> dict[str, object]:
    source_path = Path(__file__)
    return {
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
            "timed_operations": ["encode", "decode", "round_trip"],
            "warmup_calls_per_operation_per_process": warmup,
            "timed_calls_per_operation_per_process": rounds,
            "independent_process_repetitions": repetitions,
            "implementation_order": "rotates json/dcbor/cbor2_default/cbor2_canonical/cborx_default/cborx_canonical start order across fresh processes",
            "summary": "median of per-process batch means; dispersion is median absolute deviation (MAD)",
            "clock": "time.perf_counter_ns",
            "decode_input": "precomputed encoded bytes for that implementation and fixture",
            "round_trip": "one encode followed by one decode within each timed call",
            "json": "UTF-8, ensure_ascii=False, compact separators, allow_nan=False",
            "cbor_comparators": {
                "dcbor": "dcbor source extension version 0.1.0, required release artifact",
                "cbor2_default": f"generic CBOR library cbor2=={PINNED_CBOR2}, dumps() default canonical=False",
                "cbor2_canonical": f"generic CBOR library cbor2=={PINNED_CBOR2}, dumps(canonical=True), length-first key order (legacy RFC 8949 section 4.2.3)",
                "cborx_default": f"generic CBOR library cborx=={PINNED_CBORX}, dumps() default canonical=False; backend recorded",
                "cborx_canonical": f"generic CBOR library cborx=={PINNED_CBORX}, dumps(canonical=True), bytewise encoded-key order per project documentation",
            },
            "map_key_order": "dcbor and cborx canonical=True use bytewise ordering; cbor2 canonical=True uses length-first ordering (legacy RFC 8949 section 4.2.3)",
            "cbor_scope": "cbor2 and cborx are generic CBOR comparators, not dCBOR implementations; defaults and canonical modes are reported separately",
            "excluded": "strict validation is excluded because comparator validation semantics differ",
        },
        "fixture_hashes": logical_fixture_hashes(),
    }


def blocked_results(reason: str, warmup: int, rounds: int, repetitions: int) -> dict[str, object]:
    report = metadata(warmup, rounds, repetitions)
    try:
        import dcbor

        blocked_environment: dict[str, object] = {
            "python_version": sys.version,
            "python_implementation": platform.python_implementation(),
            "python_executable": str(Path(sys.executable).resolve()),
            "stdlib_json_version": getattr(json, "__version__", "bundled with Python"),
            "platform": platform.platform(),
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "processor": processor_name(),
            **build_provenance(),
            "dcbor_version": dcbor.__version__,
            "dcbor_extension_path": str(Path(dcbor._dcbor.__file__).resolve()),  # type: ignore[attr-defined]
            "dcbor_extension_sha256": sha256(Path(dcbor._dcbor.__file__).read_bytes()),  # type: ignore[attr-defined]
            "dcbor_build": release_build_evidence(Path(dcbor._dcbor.__file__).resolve()),  # type: ignore[attr-defined]
            "cbor2_expected_version": PINNED_CBOR2,
            "cbor2_version": None,
            "cbor2_native_extension_active": None,
            "cborx_expected_version": PINNED_CBORX,
            "cborx_version": None,
            "cborx_native_extension_active": None,
        }
    except ImportError:
        blocked_environment = {
            "python_version": sys.version,
            "python_implementation": platform.python_implementation(),
            "python_executable": str(Path(sys.executable).resolve()),
            "stdlib_json_version": getattr(json, "__version__", "bundled with Python"),
            "platform": platform.platform(),
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "processor": processor_name(),
            **build_provenance(),
            "cbor2_expected_version": PINNED_CBOR2,
            "cbor2_version": None,
            "cbor2_native_extension_active": None,
            "cborx_expected_version": PINNED_CBORX,
            "cborx_version": None,
            "cborx_native_extension_active": None,
        }
    report.update(
        {
            "status": "blocked",
            "blocker": reason,
            "environment": blocked_environment,
            "fixtures": None,
            "raw_process_runs": [],
        }
    )
    return report


def chart(results: dict[str, object]) -> str:
    if results["status"] != "complete":
        reason = xml_text(results.get("blocker", "benchmark unavailable"))
        return f'''<svg xmlns="http://www.w3.org/2000/svg" width="900" height="220" viewBox="0 0 900 220" role="img" aria-labelledby="title desc">
  <title id="title">Latency comparison unavailable</title>
  <desc id="desc">No complete comparison is shown. The machine-readable report records the reason: {reason}</desc>
  <style>{COMMON_STYLE}</style>
  <rect width="900" height="220" fill="{PALETTE["canvas"]}" />
  <rect x="1" y="1" width="898" height="218" rx="12" fill="{PALETTE["paper"]}" stroke="{PALETTE["line"]}" />
  <text x="28" y="48" class="title">Latency comparison unavailable</text>
  <text x="28" y="82" class="subtitle">No measurements are plotted: {reason}</text>
  <text x="28" y="126" class="caption">Install the benchmark requirements, build the release extension, and rerun benchmarks/latency.py.</text>
  <text x="28" y="157" class="caption">Raw reports preserve status and completed process samples; unavailable values are not inferred.</text>
</svg>
'''

    fixtures_result = results["fixtures"]
    fixture_labels = {
        "small_record": "Small record",
        "nested_document": "Nested document",
        "repeated_unicode_strings": "Repeated Unicode strings",
        "numeric_array": "Numeric array",
        "compact_scientific_notation": "Compact scientific notation",
        "large_collection": "Large collection",
    }
    codec_labels = {
        "json": "Python JSON",
        "dcbor": "dCBOR",
        "cbor2_default": "cbor2 default",
        "cbor2_canonical": "cbor2 canonical",
        "cborx_default": "cborx default",
        "cborx_canonical": "cborx canonical",
    }
    width, height = 1080, 822
    operations = ("encode", "decode", "round_trip")
    operation_titles = {"encode": "Encode", "decode": "Decode", "round_trip": "Round trip"}
    panel_y = (125, 347, 569)
    panel_height = 208
    label_x, cell_x, cell_width, cell_gap = 48, 229, 126, 8
    matrix_panels = []
    for operation_index, operation in enumerate(operations):
        y = panel_y[operation_index]
        elements = [
            f'<rect x="32" y="{y}" width="1016" height="{panel_height}" rx="12" class="card" />',
            f'<text x="{label_x}" y="{y + 27}" class="fixture">{operation_titles[operation]}</text>',
            f'<text x="{label_x + 104}" y="{y + 27}" class="caption">median ratio to Python JSON</text>',
        ]
        for codec_index, implementation in enumerate(IMPLEMENTATIONS):
            x = cell_x + codec_index * (cell_width + cell_gap)
            if implementation == "dcbor":
                elements.extend([
                    f'<rect x="{x + 2}" y="{y + 39}" width="{cell_width - 4}" height="19" rx="5" fill="{PALETTE["dcbor"]}" />',
                    f'<text x="{x + cell_width / 2}" y="{y + 52}" text-anchor="middle" font-size="11" font-weight="650" style="fill:#FFFFFF">{codec_labels[implementation]}</text>',
                ])
            else:
                elements.append(
                    f'<text x="{x + cell_width / 2}" y="{y + 52}" text-anchor="middle" class="small">{codec_labels[implementation]}</text>'
                )
        for fixture_index, (fixture_name, details) in enumerate(fixtures_result.items()):
            row_y = y + 77 + fixture_index * 20
            fixture_label = xml_text(fixture_labels.get(fixture_name, fixture_name.replace("_", " ")))
            elements.append(
                f'<text x="{label_x}" y="{row_y + 14}" class="small">{fixture_label}</text>'
            )
            json_median = details["json"][operation]["median_ns_per_operation"]
            for codec_index, implementation in enumerate(IMPLEMENTATIONS):
                x = cell_x + codec_index * (cell_width + cell_gap)
                value = details[implementation][operation]["median_ns_per_operation"]
                ratio = value / json_median
                emphasized = implementation == "dcbor"
                elements.extend([
                    f'<rect x="{x + 2}" y="{row_y}" width="{cell_width - 4}" height="18" rx="5" fill="{ratio_fill(ratio)}" stroke="{PALETTE["dcbor"] if emphasized else PALETTE["line"]}" stroke-width="{2 if emphasized else 0.8}" />',
                    f'<text x="{x + cell_width / 2}" y="{row_y + 13}" text-anchor="middle" class="value">{ratio:.2f}×</text>',
                ])
        matrix_panels.append("".join(elements))
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">
  <title id="title">Serialization latency relative to Python JSON</title>
  <desc id="desc">Three matrix panels show median latency ratios for six fixtures, six codec modes, and encode, decode, and round-trip operations. Each ratio compares a codec median with Python JSON for the same fixture and operation; 1.00 times is parity, values below one are faster. Teal/coral color strength follows log2 ratio and caps at 0.125× and 8×. The dCBOR column is outlined in teal. Raw medians, median absolute deviations, and process samples remain in the JSON report.</desc>
  <style>{COMMON_STYLE}</style>
  <rect width="1080" height="{height}" fill="{PALETTE["canvas"]}" />
  <text x="32" y="39" class="title">Latency relative to Python JSON</text>
  <text x="32" y="63" class="subtitle">Median per-call time ÷ same-fixture JSON median · 1.00× is parity · lower is faster</text>
  <rect x="32" y="82" width="13" height="13" rx="4" fill="{PALETTE["fast_pale"]}" stroke="{PALETTE["line"]}" />
  <text x="52" y="93" class="caption">Faster than JSON</text>
  <rect x="164" y="82" width="13" height="13" rx="4" fill="{PALETTE["parity"]}" stroke="{PALETTE["line"]}" />
  <text x="184" y="93" class="caption">Near parity</text>
  <rect x="278" y="82" width="13" height="13" rx="4" fill="{PALETTE["slow_pale"]}" stroke="{PALETTE["line"]}" />
  <text x="298" y="93" class="caption">Slower than JSON</text>
  <text x="1048" y="93" text-anchor="end" class="caption">dCBOR column highlighted</text>
  {''.join(matrix_panels)}
  <text x="32" y="801" class="caption">Medians of process batch means · one host. Decode: precomputed bytes; round trip: encode + decode. Raw values/MAD: benchmarks/latency/results.json.</text>
</svg>
'''

def write_report(report: dict[str, object], output_dir: Path) -> None:
    svg = chart(report)
    report["source"]["chart_sha256"] = sha256(svg.encode("utf-8"))  # type: ignore[index]
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "results.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8"
    )
    SVG_PATH.parent.mkdir(parents=True, exist_ok=True)
    SVG_PATH.write_text(svg, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--warmup", type=int, default=DEFAULT_WARMUP)
    parser.add_argument("--rounds", type=int, default=DEFAULT_ROUNDS)
    parser.add_argument("--repetitions", type=int, default=DEFAULT_REPETITIONS)
    parser.add_argument("--order-offset", type=int, default=0, help=argparse.SUPPRESS)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if min(args.warmup, args.rounds, args.repetitions) < 1:
        parser.error("warmup, rounds, and repetitions must be positive")
    if args.worker:
        print(json.dumps(worker(args.warmup, args.rounds, args.order_offset), allow_nan=False))
        return 0

    try:
        import cbor2
        import cborx
        import dcbor
    except ImportError as exc:
        report = blocked_results(
            f"required benchmark package is unavailable: {exc.name}; install benchmarks/requirements.txt and build dcbor",
            args.warmup, args.rounds, args.repetitions,
        )
        write_report(report, args.output_dir)
        print(f"Blocked: {report['blocker']}")
        return 2

    env = environment(dcbor, cbor2, cborx)
    blocker = None
    if cbor2_version(cbor2) != PINNED_CBOR2:
        blocker = f"expected cbor2=={PINNED_CBOR2}, found {cbor2_version(cbor2)}"
    elif importlib.metadata.version("cborx") != PINNED_CBORX:
        blocker = f"expected cborx=={PINNED_CBORX}, found {importlib.metadata.version('cborx')}"
    elif dcbor.__version__ != "0.1.0":  # type: ignore[attr-defined]
        blocker = f"expected dcbor==0.1.0, found {dcbor.__version__}"  # type: ignore[attr-defined]
    elif env["dcbor_build"]["profile"] != "release":  # type: ignore[index]
        blocker = "loaded dcbor extension does not match target/release/lib_dcbor.so"
    if blocker:
        report = blocked_results(blocker, args.warmup, args.rounds, args.repetitions)
        report["environment"] = env
        write_report(report, args.output_dir)
        print(f"Blocked: {blocker}")
        return 2

    runs: list[dict[str, object]] = []
    worker_command = [
        sys.executable, str(Path(__file__).resolve()), "--worker",
        "--warmup", str(args.warmup), "--rounds", str(args.rounds),
    ]
    worker_env = os.environ.copy()
    worker_env["PYTHONHASHSEED"] = "0"
    worker_env["PYTHONPATH"] = str(ROOT / "python") + os.pathsep + str(ROOT / "benchmarks") + os.pathsep + worker_env.get("PYTHONPATH", "")
    for repetition in range(args.repetitions):
        process_command = worker_command + ["--order-offset", str(repetition)]
        try:
            completed = subprocess.run(
                process_command, cwd=ROOT, env=worker_env, check=True,
                capture_output=True, text=True,
            )
            run = json.loads(completed.stdout)
        except subprocess.CalledProcessError as exc:
            report = blocked_results(
                f"worker process {repetition + 1} failed with exit code {exc.returncode}",
                args.warmup, args.rounds, args.repetitions,
            )
            report.update({
                "status": "failed",
                "failure": {
                    "repetition": repetition + 1,
                    "returncode": exc.returncode,
                    "stdout": exc.stdout,
                    "stderr": exc.stderr,
                },
                "raw_process_runs": runs,
            })
            write_report(report, args.output_dir)
            print(f"Failed: {report['blocker']}")
            return 1
        except (json.JSONDecodeError, OSError) as exc:
            report = blocked_results(
                f"worker process {repetition + 1} output could not be read: {type(exc).__name__}: {exc}",
                args.warmup, args.rounds, args.repetitions,
            )
            report.update({"status": "failed", "raw_process_runs": runs})
            write_report(report, args.output_dir)
            print(f"Failed: {report['blocker']}")
            return 1
        run["repetition"] = repetition + 1
        runs.append(run)

    report = metadata(args.warmup, args.rounds, args.repetitions)
    report.update({
        "status": "complete",
        "environment": env,
        "fixture_encoded_hashes": runs[0]["encoded_hashes"],
        "fixtures": aggregate(runs),
        "raw_process_runs": runs,
    })
    write_report(report, args.output_dir)
    print(f"Wrote {args.output_dir / 'results.json'} and {SVG_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
