"""Compare the patched Rust dCBOR core with its Python binding on shared wires.

This runner does not build the native benchmark executable. From the repository
root, build it explicitly and then run the driver with a release extension
available in ``python``::

    cargo build --release --locked --example benchmark-core
    PYTHONPATH=python python benchmarks/rust_core.py

The driver launches nine fresh Python worker processes by default. Each worker
also launches the native executable once. Both implementations receive the
same eight wire fixtures produced by the installed Python ``dcbor`` package.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.machinery
import json
import os
import platform
import statistics
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable


ROOT = Path(__file__).resolve().parents[1]
FIXTURES_PATH = ROOT / "benchmarks" / "fixtures.py"
RUST_SOURCE_PATH = ROOT / "benchmarks" / "rust_core.rs"
CARGO_TOML_PATH = ROOT / "Cargo.toml"
CARGO_LOCK_PATH = ROOT / "Cargo.lock"
OUTPUT_PATH = ROOT / "benchmarks" / "rust_core" / "results.json"
SVG_PATH = ROOT / ".github" / "assets" / "graphs" / "rust-core.svg"
CHART_RENDERER_PATH = ROOT / "benchmarks" / "comparison_charts.py"
DEFAULT_BINARY = ROOT / "target" / "release" / "examples" / "benchmark-core"
DEFAULT_WARMUP = 500
DEFAULT_ROUNDS = 1_000
DEFAULT_REPETITIONS = 9

# Keep the repository's Python package importable when invoked from its root;
# the loaded extension is still checked against Cargo's release artifact.
sys.path.insert(0, str(ROOT / "python"))
sys.path.insert(0, str(ROOT / "benchmarks"))

from fixtures import fixtures  # noqa: E402


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def type_sensitive_equal(left: object, right: object) -> bool:
    """Compare JSON values while keeping bool and int distinct."""
    if type(left) is not type(right):
        return False
    if isinstance(left, float):
        return left.hex() == right.hex()  # type: ignore[union-attr]
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
    reports = {
        b"benchmarks/encoded_size/results.json",
        b"benchmarks/wire_size/results.json",
        b"benchmarks/latency/results.json",
        b"benchmarks/perf_review/results.json",
        b"benchmarks/perf_review/p1_results.json",
        b"benchmarks/profile/results.json",
        b"benchmarks/rust_core/results.json",
        b".github/assets/graphs/encoded-size.svg",
        b".github/assets/graphs/wire-size.svg",
        b".github/assets/graphs/latency.svg",
        b".github/assets/graphs/perf-review.svg",
        b".github/assets/graphs/profile.svg",
        b".github/assets/graphs/rust-core.svg",
    }
    entries = result.stdout.split(b"\0")
    return any(entry and entry[3:] not in reports for entry in entries)


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


def release_extension_evidence(dcbor: object) -> dict[str, object]:
    extension_path = Path(dcbor._dcbor.__file__).resolve()  # type: ignore[attr-defined]
    extension_hash = sha256(extension_path.read_bytes())
    extension_suffixes = tuple(importlib.machinery.EXTENSION_SUFFIXES)
    if not str(extension_path).endswith(extension_suffixes):
        raise RuntimeError(f"dcbor is not loaded from a native extension: {extension_path}")

    artifact_path = ROOT / "target" / "release" / "lib_dcbor.so"
    artifact_hash = sha256(artifact_path.read_bytes()) if artifact_path.is_file() else None
    if artifact_hash != extension_hash:
        raise RuntimeError(
            "loaded dcbor extension does not match target/release/lib_dcbor.so; "
            "build the release extension before collecting measurements"
        )
    return {
        "profile": "release",
        "verified_by": "SHA-256 equality with target/release/lib_dcbor.so",
        "extension_path": str(extension_path),
        "extension_sha256": extension_hash,
        "release_artifact_path": artifact_path.relative_to(ROOT).as_posix(),
        "release_artifact_sha256": artifact_hash,
    }


def environment(dcbor: object, binary: Path) -> dict[str, object]:
    binary_profile = "release" if binary == DEFAULT_BINARY.resolve() else "unverified custom executable"
    return {
        "python_version": sys.version,
        "python_implementation": platform.python_implementation(),
        "python_executable": str(Path(sys.executable).resolve()),
        "platform": platform.platform(),
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "processor": processor_name(),
        "dcbor_version": getattr(dcbor, "__version__", "unknown"),
        "dcbor_build": release_extension_evidence(dcbor),
        "rustc_version_verbose": command_version("rustc", "--version", "--verbose"),
        "cargo_version": command_version("cargo", "--version"),
        "cargo_lock_sha256": sha256(CARGO_LOCK_PATH.read_bytes())
        if CARGO_LOCK_PATH.is_file()
        else None,
        "native_binary_path": str(binary),
        "native_binary_sha256": sha256(binary.read_bytes()),
        "native_binary_profile": binary_profile,
        "native_build_command": "cargo build --release --locked --example benchmark-core",
        "native_build_configuration": {
            "profile": "release",
            "lto": True,
            "dcbor_features": ["multithreaded"],
        },
    }


def logical_fixture_hashes(values: dict[str, object]) -> dict[str, str]:
    return {
        name: sha256(
            json.dumps(
                value, ensure_ascii=False, separators=(",", ":"), allow_nan=False
            ).encode("utf-8")
        )
        for name, value in values.items()
    }


def prepared_wires(dcbor: object, values: dict[str, object]) -> dict[str, bytes]:
    wires: dict[str, bytes] = {}
    for name, value in values.items():
        wire = dcbor.dumps(value)  # type: ignore[attr-defined]
        if not isinstance(wire, bytes):
            raise TypeError(f"dcbor.dumps returned {type(wire).__name__} for {name}")
        if not type_sensitive_equal(dcbor.loads(wire), value):  # type: ignore[attr-defined]
            raise ValueError(f"Python dCBOR round trip changed fixture {name}")
        wires[name] = wire
    return wires


def measure(operation: Callable[[], object], warmup: int, rounds: int) -> float:
    for _ in range(warmup):
        operation()
    start = time.perf_counter_ns()
    for _ in range(rounds):
        operation()
    return (time.perf_counter_ns() - start) / rounds


def run_rust(
    binary: Path,
    wires: dict[str, bytes],
    warmup: int,
    rounds: int,
    order_offset: int,
) -> dict[str, dict[str, object]]:
    command = [
        str(binary),
        "--warmup",
        str(warmup),
        "--rounds",
        str(rounds),
        "--order-offset",
        str(order_offset),
    ]
    command.extend(f"{name}={wire.hex()}" for name, wire in wires.items())
    result = subprocess.run(
        command,
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(
            f"Rust benchmark process failed ({result.returncode}): {result.stderr.strip()}"
        )
    payload = json.loads(result.stdout)
    rust_fixtures = payload["fixtures"]
    if set(rust_fixtures) != set(wires):
        raise ValueError("Rust benchmark returned a different fixture set")
    for name, wire in wires.items():
        if rust_fixtures[name]["wire_hex"] != wire.hex():
            raise ValueError(f"Rust re-encoded wire bytes differ for fixture {name}")
    return rust_fixtures


def worker(binary: Path, warmup: int, rounds: int, order_offset: int) -> dict[str, object]:
    import dcbor

    values = fixtures()
    wires = prepared_wires(dcbor, values)
    # Validate the extension for every independent worker used in the report.
    env = environment(dcbor, binary)
    if env["dcbor_version"] != "0.1.0":
        raise RuntimeError(f"expected dcbor==0.1.0, found {env['dcbor_version']}")

    order = list(values)
    if order:
        offset = order_offset % len(order)
        order = order[offset:] + order[:offset]
    rust_order = list(values)
    if rust_order:
        offset = order_offset % len(rust_order)
        rust_order = rust_order[offset:] + rust_order[:offset]

    python_times: dict[str, dict[str, float]] = {}
    python_operation_order: dict[str, list[str]] = {}
    rust_operation_order = {
        name: ["encode", "decode"] if (order_offset + index) % 2 == 0 else ["decode", "encode"]
        for index, name in enumerate(rust_order)
    }

    def measure_python() -> None:
        for index, name in enumerate(order):
            value = values[name]
            wire = wires[name]
            operations: list[tuple[str, Callable[[], object]]] = [
                ("encode", lambda value=value: dcbor.dumps(value)),
                ("decode", lambda wire=wire: dcbor.loads(wire)),
            ]
            if (order_offset + index) % 2:
                operations.reverse()
            python_operation_order[name] = [operation_name for operation_name, _ in operations]
            python_times[name] = {
                operation_name: measure(operation, warmup, rounds)
                for operation_name, operation in operations
            }

    if order_offset % 2:
        rust_fixtures = run_rust(binary, wires, warmup, rounds, order_offset)
        measure_python()
    else:
        measure_python()
        rust_fixtures = run_rust(binary, wires, warmup, rounds, order_offset)

    paired: dict[str, object] = {}
    for name in values:
        rust = rust_fixtures[name]
        paired[name] = {
            "rust_core": {
                "encode": rust["encode_ns_per_operation"],
                "decode": rust["decode_ns_per_operation"],
            },
            "python_dcbor": python_times[name],
        }
    implementation_group_order = (
        ["rust_core", "python_dcbor"]
        if order_offset % 2
        else ["python_dcbor", "rust_core"]
    )
    return {
        "process": {
            "pid": os.getpid(),
            "order_offset": order_offset,
            "fixture_order": order,
            "rust_fixture_order": rust_order,
            "implementation_group_order": implementation_group_order,
            "python_operation_order": python_operation_order,
            "rust_operation_order": rust_operation_order,
        },
        "environment": env,
        "fixtures": paired,
    }


def summarize(samples: list[float]) -> dict[str, object]:
    median = statistics.median(samples)
    return {
        "samples_ns_per_operation": samples,
        "median_ns_per_operation": median,
        "mad_ns_per_operation": statistics.median(abs(sample - median) for sample in samples),
        "minimum_ns_per_operation": min(samples),
        "maximum_ns_per_operation": max(samples),
    }


def source_metadata(binary: Path) -> dict[str, object]:
    source_paths = {
        "generator_sha256": Path(__file__).resolve(),
        "rust_source_sha256": RUST_SOURCE_PATH,
        "cargo_toml_sha256": CARGO_TOML_PATH,
        "cargo_lock_sha256": CARGO_LOCK_PATH,
        "fixtures_sha256": FIXTURES_PATH,
        "chart_renderer_sha256": CHART_RENDERER_PATH,
    }
    return {
        "git_commit": git_value("rev-parse", "HEAD"),
        "git_worktree_dirty": source_worktree_dirty(),
        "generator_path": Path(__file__).resolve().relative_to(ROOT).as_posix(),
        **{
            key: sha256(path.read_bytes()) if path.is_file() else None
            for key, path in source_paths.items()
        },
        "native_binary_path": binary.relative_to(ROOT).as_posix()
        if binary.is_relative_to(ROOT)
        else str(binary),
        "native_binary_sha256": sha256(binary.read_bytes()),
    }


def collect(args: argparse.Namespace) -> dict[str, object]:
    binary = args.binary.resolve()
    if not binary.is_file():
        raise FileNotFoundError(
            f"native benchmark executable not found: {binary}; build it with "
            "cargo build --release --locked --example benchmark-core"
        )
    if not os.access(binary, os.X_OK):
        raise PermissionError(f"native benchmark executable is not executable: {binary}")
    if args.warmup < 0 or args.rounds <= 0 or args.repetitions <= 0:
        raise ValueError("warmup must be non-negative; rounds and repetitions must be positive")

    repetitions: list[dict[str, object]] = []
    for repetition in range(args.repetitions):
        command = [
            sys.executable,
            str(Path(__file__).resolve()),
            "--worker",
            "--binary",
            str(binary),
            "--warmup",
            str(args.warmup),
            "--rounds",
            str(args.rounds),
            "--order-offset",
            str(repetition),
        ]
        result = subprocess.run(
            command,
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env={**os.environ, "PYTHONHASHSEED": "0"},
            check=False,
        )
        if result.returncode:
            raise RuntimeError(
                f"worker {repetition + 1}/{args.repetitions} failed "
                f"({result.returncode}): {result.stderr.strip()}"
            )
        repetitions.append(json.loads(result.stdout))

    values = fixtures()
    wires = prepared_wires(_load_dcbor(), values)
    results: dict[str, object] = {}
    for name in values:
        results[name] = {}
        for implementation in ("rust_core", "python_dcbor"):
            results[name][implementation] = {}  # type: ignore[index]
            for operation in ("encode", "decode"):
                samples = [
                    repetition["fixtures"][name][implementation][operation]  # type: ignore[index]
                    for repetition in repetitions
                ]
                results[name][implementation][operation] = summarize(samples)  # type: ignore[index]

    environment_record = repetitions[0]["environment"]
    return {
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source": source_metadata(binary),
        "methodology": {
            "timed_operations": [
                "rust_core.encode",
                "rust_core.decode",
                "python_dcbor.encode",
                "python_dcbor.decode",
            ],
            "warmup_calls_per_operation_per_process": args.warmup,
            "timed_calls_per_operation_per_process": args.rounds,
            "independent_process_repetitions": args.repetitions,
            "summary": "median of per-process batch means; dispersion is median absolute deviation (MAD)",
            "clock": "std::time::Instant for Rust; time.perf_counter_ns for Python",
            "Rust core": "CBOR::to_cbor_data() on a CBOR tree parsed before timing; CBOR::try_from_data() on prepared wire bytes",
            "Python binding": "dcbor.dumps(value) includes Python-to-CBOR value conversion; dcbor.loads(prepared_wire) decodes the Python dcbor wire bytes",
            "shared_inputs": "Eight fixtures from benchmarks/fixtures.py; each wire is produced once per worker by the installed Python dcbor package and passed as hex to the Rust process",
            "correctness_gates": "Python loads each prepared wire to the original type-sensitive fixture; Rust parses each wire and requires byte-identical re-encoding; the driver checks the Rust-reported re-encoded wire against the Python wire",
            "process_boundary": "Python worker and native executable startup, CLI parsing, fixture construction, and wire preparation are outside timed regions",
            "map_key_behavior": "Rust CBOR trees are parsed before encoding measurements and hold encoded map-key sort bytes; Python dcbor.dumps converts Python maps during each timed operation, so map tree/cache work differs",
            "comparison_limit": "Paired timings are whole-operation comparisons, not isolated FFI cost; Rust tree construction is excluded while Python value conversion is included",
            "implementation_order": "Fixture and encode/decode order rotate across fresh processes; Python and Rust measurement groups alternate order across repetitions",
            "python_hash_seed": 0,
        },
        "fixture_hashes": logical_fixture_hashes(values),
        "fixture_wire_sha256": {name: sha256(wire) for name, wire in wires.items()},
        "status": "complete",
        "environment": environment_record,
        "fixtures": results,
        "raw_process_runs": repetitions,
    }


def _load_dcbor() -> object:
    import dcbor

    return dcbor


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, default=DEFAULT_BINARY)
    parser.add_argument("--warmup", type=int, default=DEFAULT_WARMUP)
    parser.add_argument("--rounds", type=int, default=DEFAULT_ROUNDS)
    parser.add_argument("--repetitions", type=int, default=DEFAULT_REPETITIONS)
    parser.add_argument("--order-offset", type=int, default=0)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()

    try:
        if args.worker:
            import dcbor

            if not args.binary.is_file():
                raise FileNotFoundError(args.binary)
            if args.rounds <= 0 or args.warmup < 0:
                raise ValueError("warmup must be non-negative and rounds must be positive")
            result = worker(
                args.binary.resolve(), args.warmup, args.rounds, args.order_offset
            )
            print(json.dumps(result, separators=(",", ":"), allow_nan=False))
            return 0

        from comparison_charts import rust_core_chart, stamp_chart_provenance

        report = collect(args)
        svg = rust_core_chart(report)
        stamp_chart_provenance(report, svg, SVG_PATH)
        SVG_PATH.parent.mkdir(parents=True, exist_ok=True)
        SVG_PATH.write_text(svg, encoding="utf-8")
        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT_PATH.write_text(
            json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8"
        )
        print(f"wrote {OUTPUT_PATH.relative_to(ROOT)}")
        return 0
    except (OSError, ImportError, RuntimeError, TypeError, ValueError, KeyError) as error:
        print(f"rust_core benchmark: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
