"""Measure dCBOR profile-specific map, numeric, Unicode, and snapshot workloads.

Run from the repository root with the release extension installed::

    PYTHONPATH=python python benchmarks/profile.py
    PYTHONPATH=python python benchmarks/profile.py --smoke

The full runner launches one fresh Python process per repetition and writes raw
measurements to ``benchmarks/profile/results.json``. It also renders the stable
profile chart through ``benchmarks/comparison_charts.py`` after all samples finish.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import os
import platform
import statistics
import struct
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable

from profile_fixtures import build_workloads


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = Path(__file__).resolve().parent / "profile"
ARTIFACT_DIR = Path(os.environ.get("DCBOR_BENCHMARK_ARTIFACT_DIR", ROOT / ".github" / "assets" / "graphs"))
PACKAGE_ROOT = Path(os.environ.get("DCBOR_PACKAGE_ROOT", ROOT / "python"))
RELEASE_ARTIFACT = Path(os.environ.get("DCBOR_RELEASE_ARTIFACT", ROOT / "target" / "release" / "lib_dcbor.so"))
CHART_PATH = Path(os.environ.get("DCBOR_PROFILE_SVG_PATH", ARTIFACT_DIR / "profile.svg"))
EXPECTED_DCBOR_VERSION = "0.1.1"
sys.path.insert(0, str(PACKAGE_ROOT))
DEFAULT_WARMUP = 100
DEFAULT_ROUNDS = 500
DEFAULT_REPETITIONS = 9
OPERATIONS = ("encode", "decode")
ITERATION_WORK_UNITS = 1_000


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
    generated = {
        b"benchmarks/profile/results.json",
        b"benchmarks/encoded_size/results.json",
        b"benchmarks/wire_size/results.json",
        b"benchmarks/latency/results.json",
        b".github/assets/graphs/profile.svg",
        b".github/assets/graphs/encoded-size.svg",
        b".github/assets/graphs/wire-size.svg",
        b".github/assets/graphs/latency.svg",
    }
    for entry in result.stdout.split(b"\0"):
        if entry and entry[3:] not in generated:
            return True
    return False


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


def release_build_evidence(extension_path: Path) -> dict[str, object]:
    """Verify the loaded extension is byte-identical to Cargo's release artifact."""
    artifact = RELEASE_ARTIFACT.resolve()
    extension_hash = sha256(extension_path.read_bytes())
    artifact_hash = sha256(artifact.read_bytes()) if artifact.is_file() else None
    return {
        "profile": "release" if extension_hash == artifact_hash else "unverified",
        "verified_by": "SHA-256 equality with configured release artifact",
        "release_artifact_path": str(artifact)
        if artifact_hash
        else None,
        "release_artifact_sha256": artifact_hash,
        "extension_path": str(extension_path),
        "extension_sha256": extension_hash,
    }


def environment(dcbor: object) -> dict[str, object]:
    extension_path = Path(dcbor._dcbor.__file__).resolve()  # type: ignore[attr-defined]
    lockfile = ROOT / "Cargo.lock"
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
        "cargo_lock_sha256": sha256(lockfile.read_bytes()) if lockfile.is_file() else None,
        "dcbor_version": dcbor.__version__,  # type: ignore[attr-defined]
        "dcbor_build": release_build_evidence(extension_path),
    }


def input_fingerprint_bytes(value: object) -> bytes:
    """Encode a typed, insertion-order-preserving fingerprint without JSON NaNs."""
    if value is None:
        return b"N"
    if type(value) is bool:
        return b"B1" if value else b"B0"
    if type(value) is int:
        raw = str(value).encode("ascii")
        return b"I" + struct.pack(">Q", len(raw)) + raw
    if type(value) is float:
        return b"F" + struct.pack(">d", value)
    if type(value) is str:
        raw = value.encode("utf-8")
        return b"S" + struct.pack(">Q", len(raw)) + raw
    if isinstance(value, list):
        return b"L" + struct.pack(">Q", len(value)) + b"".join(
            input_fingerprint_bytes(item) for item in value
        )
    if isinstance(value, dict):
        return b"D" + struct.pack(">Q", len(value)) + b"".join(
            input_fingerprint_bytes(key) + input_fingerprint_bytes(item)
            for key, item in value.items()
        )
    if type(value).__name__ == "CBORMap":
        items = value.items()
        return b"M" + struct.pack(">Q", len(items)) + b"".join(
            input_fingerprint_bytes(key) + input_fingerprint_bytes(item)
            for key, item in items
        )
    raise TypeError(f"unsupported profile input type: {type(value).__name__}")


def same_profile_value(actual: object, expected: object) -> bool:
    """Compare decoded data by type and exact finite float bits; accept any NaN."""
    if type(actual) is not type(expected):
        return False
    if isinstance(expected, float):
        return math.isnan(actual) if math.isnan(expected) else actual.hex() == expected.hex()
    if isinstance(expected, list):
        return len(actual) == len(expected) and all(
            same_profile_value(left, right) for left, right in zip(actual, expected)
        )
    if isinstance(expected, dict):
        if list(actual) != list(expected):
            return False
        return all(
            same_profile_value(actual[key], value) for key, value in expected.items()
        )
    return actual == expected


def validate_profile_vectors(dcbor: object, case_id: str, case: dict[str, object]) -> None:
    vectors = case.get("_profile_vectors", [])
    assert isinstance(vectors, list)
    for vector in vectors:
        assert isinstance(vector, dict)
        value = vector["value"]
        wire = dcbor.dumps(value)  # type: ignore[attr-defined]
        expected_wire = bytes.fromhex(vector["wire_hex"])  # type: ignore[arg-type]
        if wire != expected_wire:
            raise ValueError(
                f"{case_id}/{vector['name']}: expected independent wire oracle "
                f"{expected_wire.hex()}, got {wire.hex()}"
            )
        decoded = dcbor.loads(wire)  # type: ignore[attr-defined]
        expected_type = vector["decoded_type"]
        if expected_type == "int":
            if type(decoded) is not int or decoded != int(value):  # type: ignore[arg-type]
                raise ValueError(f"{case_id}/{vector['name']}: expected integer reduction")
        elif type(decoded) is not float:
            raise ValueError(f"{case_id}/{vector['name']}: expected decoded float")
        elif vector["expected"] == "isnan":
            if not math.isnan(decoded):
                raise ValueError(f"{case_id}/{vector['name']}: expected NaN")
        elif decoded.hex() != value.hex():  # type: ignore[union-attr]
            raise ValueError(f"{case_id}/{vector['name']}: float bits changed")


def case_iteration_count(base_count: int, work_units: int) -> int:
    """Scale operation counts inversely with workload size, with a one-call floor."""
    if base_count == 0:
        return 0
    scaled = base_count * ITERATION_WORK_UNITS // max(1, work_units)
    return max(1, min(base_count, scaled))


def prepare_cases(
    dcbor: object, warmup: int, rounds: int
) -> tuple[dict[str, dict[str, object]], dict[str, dict[str, object]]]:
    workloads = build_workloads(
        lambda key: dcbor.dumps(key), cbor_map_factory=dcbor.CBORMap  # type: ignore[attr-defined]
    )
    prepared: dict[str, dict[str, object]] = {}
    descriptors: dict[str, dict[str, object]] = {}
    maps_by_size: dict[int, bytes] = {}

    for case_id, case in workloads.items():
        value = case["input"]
        expected = case["expected"]
        wire = dcbor.dumps(value)  # type: ignore[attr-defined]
        decoded = dcbor.loads(wire)  # type: ignore[attr-defined]
        if not same_profile_value(decoded, expected):
            raise ValueError(f"dCBOR profile normalization mismatch for {case_id}")
        if case["family"] == "map_order":
            if list(decoded) != list(expected):  # type: ignore[arg-type]
                raise ValueError(f"canonical decoded key order changed for {case_id}")
            size = int(case["size"])
            previous = maps_by_size.setdefault(size, wire)
            if previous != wire:
                raise ValueError(f"input ordering changed canonical bytes for map size {size}")
        validate_profile_vectors(dcbor, case_id, case)

        work_units = int(case["work_units"])
        iterations = case_iteration_count(rounds, work_units)
        warmup_iterations = case_iteration_count(warmup, work_units)
        prepared[case_id] = {
            "input": value,
            "wire": wire,
            "iterations": iterations,
            "warmup": warmup_iterations,
        }
        descriptor = {
            key: item
            for key, item in case.items()
            if key not in {"input", "expected", "_profile_vectors"}
        }
        descriptor["input_sha256"] = sha256(input_fingerprint_bytes(value))
        descriptor["wire_sha256"] = sha256(wire)
        descriptor["wire_bytes"] = len(wire)
        descriptor["iterations_per_process"] = iterations
        descriptor["warmup_per_process"] = warmup_iterations
        if case.get("_profile_vectors"):
            descriptor["profile_vectors"] = [
                {key: item for key, item in vector.items() if key != "value"}
                for vector in case["_profile_vectors"]  # type: ignore[union-attr]
            ]
        descriptors[case_id] = descriptor

    return prepared, descriptors


def worker(warmup: int, rounds: int, order_offset: int) -> dict[str, object]:
    import dcbor

    if dcbor.__version__ != EXPECTED_DCBOR_VERSION:  # type: ignore[attr-defined]
        raise RuntimeError(f"expected dcbor=={EXPECTED_DCBOR_VERSION}, found {dcbor.__version__}")  # type: ignore[attr-defined]
    env = environment(dcbor)
    if env["dcbor_build"]["profile"] != "release":  # type: ignore[index]
        raise RuntimeError("loaded dcbor extension does not match configured release artifact")

    prepared, descriptors = prepare_cases(dcbor, warmup, rounds)
    case_order = list(prepared)
    if case_order:
        offset = order_offset % len(case_order)
        case_order = case_order[offset:] + case_order[:offset]

    measurements: dict[str, dict[str, float]] = {}
    operation_order = OPERATIONS
    if order_offset % 2:
        operation_order = tuple(reversed(operation_order))
    for case_id in case_order:
        case = prepared[case_id]
        value = case["input"]
        wire = case["wire"]
        functions: dict[str, Callable[[], object]] = {
            "encode": lambda value=value: dcbor.dumps(value),  # type: ignore[attr-defined]
            "decode": lambda wire=wire: dcbor.loads(wire),  # type: ignore[attr-defined]
        }
        measurements[case_id] = {}
        for operation in operation_order:
            function = functions[operation]
            for _ in range(int(case["warmup"])):
                function()
            count = int(case["iterations"])
            start = time.perf_counter_ns()
            for _ in range(count):
                function()
            elapsed = time.perf_counter_ns() - start
            measurements[case_id][operation] = elapsed / count

    return {
        "pid": os.getpid(),
        "started_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "order_offset": order_offset,
        "operation_order": list(operation_order),
        "measurements_ns_per_operation": measurements,
        "case_fingerprints": {
            case_id: {
                "input_sha256": descriptor["input_sha256"],
                "wire_sha256": descriptor["wire_sha256"],
                "wire_bytes": descriptor["wire_bytes"],
            }
            for case_id, descriptor in descriptors.items()
        },
    }


def summarize(samples: list[float]) -> dict[str, object]:
    median = statistics.median(samples)
    return {
        "samples_ns_per_operation": samples,
        "median_ns_per_operation": median,
        "mad_ns_per_operation": statistics.median(
            abs(value - median) for value in samples
        ),
        "minimum_ns_per_operation": min(samples),
        "maximum_ns_per_operation": max(samples),
    }


def source_metadata() -> dict[str, object]:
    source_path = Path(__file__)
    fixture_path = source_path.with_name("profile_fixtures.py")
    return {
        "git_commit": git_value("rev-parse", "HEAD"),
        "git_worktree_dirty": source_worktree_dirty(),
        "generator_path": source_path.resolve().relative_to(ROOT).as_posix(),
        "generator_sha256": sha256(source_path.read_bytes()),
        "fixtures_path": fixture_path.resolve().relative_to(ROOT).as_posix(),
        "fixtures_sha256": sha256(fixture_path.read_bytes()),
    }


def blocked_report(reason: str, warmup: int, rounds: int, repetitions: int) -> dict[str, object]:
    try:
        import dcbor

        env: dict[str, object] = environment(dcbor)
    except ImportError:
        env = {
            "python_version": sys.version,
            "python_implementation": platform.python_implementation(),
            "platform": platform.platform(),
            "machine": platform.machine(),
            "rustc_version_verbose": command_version("rustc", "--version", "--verbose"),
            "cargo_version": command_version("cargo", "--version"),
        }
    return {
        "status": "blocked",
        "blocker": reason,
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source": source_metadata(),
        "build": env.get("dcbor_build"),
        "environment": env,
        "methodology": {
            "operations": list(OPERATIONS),
            "warmup_base_calls": warmup,
            "rounds_base_calls": rounds,
            "independent_process_repetitions": repetitions,
        },
        "unsupported": [],
        "cases": {},
        "raw_process_runs": [],
    }


def build_report(
    env: dict[str, object],
    cases: dict[str, dict[str, object]],
    runs: list[dict[str, object]],
    warmup: int,
    rounds: int,
    repetitions: int,
) -> dict[str, object]:
    for run in runs:
        if set(run["case_fingerprints"]) != set(cases):  # type: ignore[arg-type]
            raise ValueError("worker case set changed across processes")
        for case_id, descriptor in cases.items():
            observed = run["case_fingerprints"][case_id]  # type: ignore[index]
            for key in ("input_sha256", "wire_sha256", "wire_bytes"):
                if observed[key] != descriptor[key]:
                    raise ValueError(f"worker fingerprint changed for {case_id}/{key}")

    result_cases: dict[str, dict[str, object]] = {}
    for case_id, descriptor in cases.items():
        operations: dict[str, object] = {}
        for operation in OPERATIONS:
            samples = [
                run["measurements_ns_per_operation"][case_id][operation]
                for run in runs
            ]
            operations[operation] = summarize(samples)  # type: ignore[arg-type]
        result_cases[case_id] = {**descriptor, "operations": operations}

    return {
        "status": "complete",
        "measurement": "dCBOR encode/decode latency for profile-specific maps, explicit integer widths, NFC key collisions, nested values, floats, Unicode, and CBORMap snapshots",
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source": source_metadata(),
        "build": env["dcbor_build"],
        "environment": env,
        "methodology": {
            "operations": list(OPERATIONS),
            "clock": "time.perf_counter_ns",
            "timing_unit": "nanoseconds per operation; each sample is a process-local batch mean",
            "warmup_base_calls": warmup,
            "rounds_base_calls": rounds,
            "independent_process_repetitions": repetitions,
            "iteration_policy": f"per case and operation count = max(1, min(base_count, floor(base_count * {ITERATION_WORK_UNITS} / work_units))); warmup zero remains zero",
            "work_units": "case-specific bounded estimate recorded with each input; map entry count, scalar element count, and Unicode code points are explicit",
            "input_fingerprint": "recursive typed tags with insertion-order dicts, CBORMap item snapshots, UTF-8 string bytes, decimal integer bytes, and exact IEEE-754 binary64 bytes",
            "map_key_order": "fixed-width ASCII string keys are ranked by their dCBOR encoded bytes; canonical output is checked byte-identical for sorted, reversed, and seeded-shuffled insertion orders. Equal-length keys isolate insertion-order sorting cost and do not distinguish bytewise ordering from length-first ordering",
            "float_profile": "dCBOR float reduction and canonicalization are checked using type-sensitive values, exact finite float.hex() values, isnan() for NaNs, and independent known CBOR hex vectors at signed-zero and integer-reduction boundaries",
            "unicode_profile": "decoded strings are checked against Python unicodedata.normalize('NFC', text)",
            "excluded": "generic CBOR comparator modes and round-trip timing; encode and decode are measured separately",
        },
        "unsupported": [],
        "cases": result_cases,
        "raw_process_runs": [
            {
                "pid": run["pid"],
                "started_at_utc": run["started_at_utc"],
                "order_offset": run["order_offset"],
                "operation_order": run["operation_order"],
                "measurements_ns_per_operation": run["measurements_ns_per_operation"],
                "case_fingerprints": run["case_fingerprints"],
            }
            for run in runs
        ],
    }


def write_report(report: dict[str, object], output_dir: Path) -> None:
    from comparison_charts import profile_chart, stamp_chart_provenance

    svg = profile_chart(report)
    stamp_chart_provenance(report, svg, CHART_PATH.relative_to(ROOT).as_posix())
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "results.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    CHART_PATH.parent.mkdir(parents=True, exist_ok=True)
    CHART_PATH.write_text(svg, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Measure dCBOR profile workloads for map ordering, float reduction, and Unicode normalization."
    )
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--warmup", type=int, default=DEFAULT_WARMUP)
    parser.add_argument("--rounds", type=int, default=DEFAULT_ROUNDS)
    parser.add_argument("--repetitions", type=int, default=DEFAULT_REPETITIONS)
    parser.add_argument("--smoke", action="store_true", help="validate all fixtures once without timing or writing reports")
    parser.add_argument("--order-offset", type=int, default=0, help=argparse.SUPPRESS)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.warmup < 0 or min(args.rounds, args.repetitions) < 1:
        parser.error("warmup must be non-negative; rounds and repetitions must be positive")
    if args.worker:
        print(json.dumps(worker(args.warmup, args.rounds, args.order_offset), allow_nan=False))
        return 0

    try:
        import dcbor
    except ImportError as exc:
        report = blocked_report(
            f"dcbor is unavailable: {exc.name}; build the release extension first",
            args.warmup,
            args.rounds,
            args.repetitions,
        )
        write_report(report, args.output_dir)
        print(f"Blocked: {report['blocker']}")
        return 2

    env = environment(dcbor)
    if dcbor.__version__ != EXPECTED_DCBOR_VERSION:  # type: ignore[attr-defined]
        reason = f"expected dcbor=={EXPECTED_DCBOR_VERSION}, found {dcbor.__version__}"  # type: ignore[attr-defined]
        report = blocked_report(reason, args.warmup, args.rounds, args.repetitions)
        report["environment"] = env
        report["build"] = env["dcbor_build"]
        write_report(report, args.output_dir)
        print(f"Blocked: {reason}")
        return 2
    if env["dcbor_build"]["profile"] != "release":  # type: ignore[index]
        reason = "loaded dcbor extension does not match configured release artifact"
        report = blocked_report(reason, args.warmup, args.rounds, args.repetitions)
        report["environment"] = env
        report["build"] = env["dcbor_build"]
        write_report(report, args.output_dir)
        print(f"Blocked: {reason}")
        return 2

    if args.smoke:
        _, cases = prepare_cases(dcbor, warmup=0, rounds=1)
        print(f"Smoke validation passed for {len(cases)} profile workloads")
        return 0

    _, cases = prepare_cases(dcbor, args.warmup, args.rounds)
    worker_command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--worker",
        "--warmup",
        str(args.warmup),
        "--rounds",
        str(args.rounds),
    ]
    worker_env = os.environ.copy()
    worker_env["PYTHONHASHSEED"] = "0"
    worker_env["PYTHONPATH"] = (
        str(PACKAGE_ROOT)
        + os.pathsep
        + str(ROOT / "benchmarks")
        + os.pathsep
        + worker_env.get("PYTHONPATH", "")
    )
    runs: list[dict[str, object]] = []
    for repetition in range(args.repetitions):
        command = worker_command + ["--order-offset", str(repetition)]
        try:
            completed = subprocess.run(
                command,
                cwd=ROOT,
                env=worker_env,
                check=True,
                capture_output=True,
                text=True,
            )
            run = json.loads(completed.stdout)
        except subprocess.CalledProcessError as exc:
            report = blocked_report(
                f"worker process {repetition + 1} failed with exit code {exc.returncode}",
                args.warmup,
                args.rounds,
                args.repetitions,
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
            report = blocked_report(
                f"worker process {repetition + 1} output could not be read: {type(exc).__name__}: {exc}",
                args.warmup,
                args.rounds,
                args.repetitions,
            )
            report.update({"status": "failed", "raw_process_runs": runs})
            write_report(report, args.output_dir)
            print(f"Failed: {report['blocker']}")
            return 1
        runs.append(run)

    report = build_report(env, cases, runs, args.warmup, args.rounds, args.repetitions)
    write_report(report, args.output_dir)
    print(f"Wrote {args.output_dir / 'results.json'} and {CHART_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
