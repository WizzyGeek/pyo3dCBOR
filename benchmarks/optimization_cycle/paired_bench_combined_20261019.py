"""Paired fresh-process baseline/candidate measurements for approved A/B work.

The parent process launches baseline and candidate workers serially. Worker
setup, fixture creation, correctness checks, and warmups are outside each
operation's ``perf_counter_ns`` loop. No profiler or build is started here.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import os
import platform
import random
import statistics
import struct
import subprocess
import sys
import time
import unicodedata
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
BENCHMARKS = ROOT / "benchmarks"
BYTE_SIZES = (0, 23, 24, 255, 256, 1024, 65_536, 1_048_576)
MAP_SIZES = (10, 100, 1_000, 10_000)
INTEGER_BOUNDARIES = [
    -(2**64), -(2**63) - 1, -(2**63), -(2**32), -25, -1, 0, 23, 24,
    255, 256, 2**32 - 1, 2**32, 2**63 - 1, 2**64 - 1,
] * 32


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def length_prefix(tag: bytes, payload: bytes) -> bytes:
    return tag + len(payload).to_bytes(8, "big") + payload


def typed_bytes(value: object) -> bytes:
    """Insertion-order-preserving type fingerprint for benchmark inputs/results."""
    if value is None:
        return b"n"
    if type(value) is bool:
        return b"b1" if value else b"b0"
    if type(value) is int:
        return length_prefix(b"i", str(value).encode("ascii"))
    if type(value) is float:
        return b"f" + struct.pack(">d", value)
    if type(value) is str:
        return length_prefix(b"s", value.encode("utf-8"))
    if type(value) is bytes:
        return length_prefix(b"y", value)
    if type(value) is list:
        return length_prefix(b"l", b"".join(typed_bytes(item) for item in value))
    if type(value) is dict:
        return length_prefix(
            b"d",
            b"".join(typed_bytes(key) + typed_bytes(item) for key, item in value.items()),
        )
    raise TypeError(f"unsupported fingerprint type: {type(value).__qualname__}")


def same_value(actual: object, expected: object) -> bool:
    """Compare decoded values recursively without bool/int or float/int coercion."""
    if type(actual) is not type(expected):
        return False
    if type(expected) is float:
        if math.isnan(expected):  # type: ignore[arg-type]
            return math.isnan(actual)  # type: ignore[arg-type]
        return actual.hex() == expected.hex()  # type: ignore[union-attr]
    if type(expected) is list:
        return len(actual) == len(expected) and all(  # type: ignore[arg-type]
            same_value(a, e)
            for a, e in zip(actual, expected)  # type: ignore[arg-type]
        )
    if type(expected) is dict:
        return (
            len(actual) == len(expected)  # type: ignore[arg-type]
            and actual.keys() == expected.keys()  # type: ignore[union-attr]
            and all(
                same_value(actual[key], item)  # type: ignore[index]
                for key, item in expected.items()  # type: ignore[union-attr]
            )
        )
    return actual == expected


def make_cases() -> list[dict[str, Any]]:
    """Create the same deterministic inputs for either extension artifact."""
    from fixtures import fixtures

    cases: list[dict[str, Any]] = []

    def add(
        case_id: str,
        value: object,
        expected: object,
        operations: tuple[str, ...],
        rounds: int,
    ) -> None:
        cases.append({
            "case_id": case_id,
            "value": value,
            "expected": expected,
            "operations": operations,
            "rounds": rounds,
            "warmup": max(3, min(20, rounds // 10)),
        })

    for size in MAP_SIZES:
        keys = [f"field-{index:04d}" for index in range(size)]
        values = {key: index for index, key in enumerate(keys)}
        shuffled = list(keys)
        random.Random(0xDCB0 + size).shuffle(shuffled)
        orders = (
            ("sorted", keys),
            ("reverse", list(reversed(keys))),
            ("shuffled", shuffled),
        )
        rounds = 500 if size <= 100 else (100 if size == 1_000 else 10)
        for order, ordered_keys in orders:
            add(
                f"map:{size}:{order}",
                {key: values[key] for key in ordered_keys},
                values,
                ("encode",),
                rounds,
            )

    collision_input: dict[str, int] = {}
    collision_expected: dict[str, int] = {}
    for index in range(64):
        nfc = f"item-{index:03d}-é"
        nfd = unicodedata.normalize("NFD", nfc)
        collision_input[nfd] = index * 2
        collision_input[nfc] = index * 2 + 1
        collision_expected[nfc] = index * 2 + 1
    add(
        "map:nfc_collisions",
        collision_input,
        collision_expected,
        ("encode",),
        100,
    )

    for size in BYTE_SIZES:
        rounds = 500 if size <= 256 else (300 if size == 1024 else (100 if size == 65_536 else 50))
        value = b"\x5a" * size
        add(f"bytes:{size}", value, value, ("encode",), rounds)

    for name, value in fixtures().items():
        if name == "ascii_article":
            rounds = 40
        elif name == "large_collection":
            rounds = 30
        elif name in {"repeated_unicode_strings", "telemetry_batch"}:
            rounds = 100
        else:
            rounds = 200
        add(f"common:{name}", value, value, ("encode", "decode", "roundtrip"), rounds)

    scalar_controls = (
        ("none", None),
        ("bool_false", False),
        ("bool_true", True),
        ("int_23", 23),
        ("int_24", 24),
        ("int_u32", 2**32),
        ("float", 0.25),
        ("short_text", "x"),
    )
    for name, value in scalar_controls:
        add(f"guard:scalar_{name}", value, value, ("encode",), 1_000)

    add(
        "guard:integer_width_boundaries",
        INTEGER_BOUNDARIES,
        list(INTEGER_BOUNDARIES),
        ("encode", "decode", "roundtrip"),
        200,
    )
    return cases


def run_worker(variant: str, package_root: Path, artifact: Path, repetition: int) -> dict[str, Any]:
    package_root = package_root.resolve()
    artifact = artifact.resolve()
    sys.path.insert(0, str(BENCHMARKS))
    sys.path.insert(0, str(package_root))

    import dcbor

    extension_path = Path(dcbor._dcbor.__file__).resolve()  # type: ignore[attr-defined]
    if not extension_path.is_relative_to((package_root / "dcbor").resolve()):
        raise RuntimeError(f"loaded extension outside selected package: {extension_path}")
    extension_hash = sha256_file(extension_path)
    artifact_hash = sha256_file(artifact)
    if extension_hash != artifact_hash:
        raise RuntimeError(
            f"loaded extension and release artifact differ: {extension_hash} != {artifact_hash}"
        )
    if dcbor.__version__ != "0.1.1":  # type: ignore[attr-defined]
        raise RuntimeError(f"expected dcbor 0.1.1, found {dcbor.__version__}")  # type: ignore[attr-defined]

    cases = make_cases()
    case_fingerprints: dict[str, dict[str, Any]] = {}
    prepared: list[dict[str, Any]] = []
    for case in cases:
        value = case["value"]
        wire = dcbor.dumps(value)  # type: ignore[attr-defined]
        decoded = dcbor.loads(wire)  # type: ignore[attr-defined]
        if not same_value(decoded, case["expected"]):
            raise ValueError(f"{variant} failed typed decode check for {case['case_id']}")
        roundtrip = dcbor.loads(dcbor.dumps(value))  # type: ignore[attr-defined]
        if not same_value(roundtrip, case["expected"]):
            raise ValueError(f"{variant} failed roundtrip check for {case['case_id']}")
        case_fingerprints[case["case_id"]] = {
            "input_sha256": sha256(typed_bytes(value)),
            "wire_sha256": sha256(wire),
            "wire_bytes": len(wire),
            "decoded_sha256": sha256(typed_bytes(decoded)),
        }
        prepared.append({**case, "wire": wire})

    # Rotate fixture order and reverse operation order by repetition. Both
    # artifacts get the same order within each pair; baseline-first alternates.
    offset = (repetition * 7) % len(prepared)
    prepared = prepared[offset:] + prepared[:offset]
    measurements: dict[str, dict[str, dict[str, Any]]] = {}
    for case in prepared:
        value, wire = case["value"], case["wire"]
        operations = case["operations"] if repetition % 2 == 0 else tuple(reversed(case["operations"]))
        functions = {
            "encode": lambda value=value: dcbor.dumps(value),  # type: ignore[attr-defined]
            "decode": lambda wire=wire: dcbor.loads(wire),  # type: ignore[attr-defined]
            "roundtrip": lambda value=value: dcbor.loads(dcbor.dumps(value)),  # type: ignore[attr-defined]
        }
        measurements[case["case_id"]] = {}
        for operation in operations:
            function = functions[operation]
            for _ in range(case["warmup"]):
                result = function()
            start = time.perf_counter_ns()
            for _ in range(case["rounds"]):
                result = function()
            elapsed = time.perf_counter_ns() - start
            measurements[case["case_id"]][operation] = {
                "ns_per_operation": elapsed / case["rounds"],
                "rounds": case["rounds"],
                "warmup": case["warmup"],
            }
        # Keep the final result alive through the counter/timing boundary just
        # as the existing profile runner does; the next operation replaces it.
        if "result" in locals():
            del result

    return {
        "variant": variant,
        "repetition": repetition,
        "pid": os.getpid(),
        "started_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "package_root": str(package_root),
        "extension_path": str(extension_path),
        "extension_sha256": extension_hash,
        "release_artifact": str(artifact),
        "release_artifact_sha256": artifact_hash,
        "case_fingerprints": case_fingerprints,
        "measurements": measurements,
    }


def median_mad(values: list[float]) -> tuple[float, float]:
    median = statistics.median(values)
    return median, statistics.median(abs(value - median) for value in values)


def git_head() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def run_parent(args: argparse.Namespace) -> int:
    baseline_package = Path(args.baseline_package).resolve()
    baseline_artifact = Path(args.baseline_artifact).resolve()
    candidate_package = Path(args.candidate_package).resolve()
    candidate_artifact = Path(args.candidate_artifact).resolve()
    output = Path(args.output).resolve()
    if output.exists():
        raise SystemExit(f"refusing to overwrite existing raw results: {output}")
    if args.repetitions < 3:
        raise SystemExit("use at least three paired fresh-process repetitions")

    pairs: list[dict[str, Any]] = []
    for repetition in range(args.repetitions):
        role_order = (
            ("baseline", "candidate")
            if repetition % 2 == 0
            else ("candidate", "baseline")
        )
        pair: dict[str, Any] = {"repetition": repetition, "role_order": list(role_order)}
        for variant in role_order:
            package_root, artifact = (
                (baseline_package, baseline_artifact)
                if variant == "baseline"
                else (candidate_package, candidate_artifact)
            )
            command = [
                sys.executable,
                str(Path(__file__).resolve()),
                "--worker",
                "--variant", variant,
                "--package-root", str(package_root),
                "--artifact", str(artifact),
                "--repetition", str(repetition),
            ]
            env = os.environ.copy()
            env.pop("PYTHONPATH", None)
            env["PYTHONDONTWRITEBYTECODE"] = "1"
            completed = subprocess.run(
                command,
                cwd=ROOT,
                env=env,
                check=False,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            if completed.returncode:
                raise RuntimeError(
                    f"{variant} worker failed (rep {repetition}):\n{completed.stderr}\n{completed.stdout}"
                )
            pair[variant] = json.loads(completed.stdout)
        pairs.append(pair)
        print(f"completed paired process set {repetition + 1}/{args.repetitions}", flush=True)

    errors: list[str] = []
    first = pairs[0]
    expected_fingerprints = first["baseline"]["case_fingerprints"]
    for pair in pairs:
        baseline = pair["baseline"]
        candidate = pair["candidate"]
        if baseline["case_fingerprints"] != expected_fingerprints:
            errors.append(f"baseline fixture/wire hashes changed in repetition {pair['repetition']}")
        if candidate["case_fingerprints"] != expected_fingerprints:
            errors.append(f"candidate fixture/wire/result hashes differ in repetition {pair['repetition']}")

    summaries: dict[str, Any] = {}
    for case_id, case_fingerprint in expected_fingerprints.items():
        operations = first["baseline"]["measurements"][case_id]
        summaries[case_id] = {}
        for operation in operations:
            base_values = [
                pair["baseline"]["measurements"][case_id][operation]["ns_per_operation"]
                for pair in pairs
            ]
            candidate_values = [
                pair["candidate"]["measurements"][case_id][operation]["ns_per_operation"]
                for pair in pairs
            ]
            baseline_median, baseline_mad = median_mad(base_values)
            candidate_median, candidate_mad = median_mad(candidate_values)
            paired_changes = [
                (candidate / baseline - 1.0) * 100.0
                for baseline, candidate in zip(base_values, candidate_values)
            ]
            paired_median, paired_mad = median_mad(paired_changes)
            summaries[case_id][operation] = {
                "baseline_median_ns_per_operation": baseline_median,
                "baseline_mad_ns_per_operation": baseline_mad,
                "candidate_median_ns_per_operation": candidate_median,
                "candidate_mad_ns_per_operation": candidate_mad,
                "paired_change_median_percent": paired_median,
                "paired_change_mad_percent": paired_mad,
                "paired_changes_percent": paired_changes,
                "repetitions": args.repetitions,
            }

    baseline_manifest = baseline_package.parent / "baseline_manifest.json"
    manifest_data = json.loads(baseline_manifest.read_text()) if baseline_manifest.exists() else None
    output.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "method": {
            "driver": str(Path(__file__).resolve().relative_to(ROOT)),
            "source_head_at_run": git_head(),
            "repetitions": args.repetitions,
            "process_policy": "fresh processes, strictly serial; baseline/candidate order alternates each paired repetition",
            "timing_region": "operation loop only; imports, fixture construction, correctness/wire checks, and warmups excluded",
            "candidate_change_percent": "100 * (candidate / baseline - 1); negative is faster",
            "no_profiler": True,
            "baseline_manifest": manifest_data,
        },
        "errors": errors,
        "case_fingerprints": expected_fingerprints,
        "summaries": summaries,
        "raw_pairs": pairs,
    }
    output.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n")
    print(f"wrote {output}")
    if errors:
        print("ERROR: baseline and candidate fixtures/results are not identical", file=sys.stderr)
        return 2
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--variant", choices=("baseline", "candidate"))
    parser.add_argument("--package-root", type=Path)
    parser.add_argument("--artifact", type=Path)
    parser.add_argument("--repetition", type=int)
    parser.add_argument("--baseline-package", type=Path)
    parser.add_argument("--baseline-artifact", type=Path)
    parser.add_argument("--candidate-package", type=Path)
    parser.add_argument("--candidate-artifact", type=Path)
    parser.add_argument("--repetitions", type=int, default=9)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.worker:
        if args.variant is None or args.package_root is None or args.artifact is None or args.repetition is None:
            parser.error("worker mode requires --variant, --package-root, --artifact, and --repetition")
        print(json.dumps(
            run_worker(args.variant, args.package_root, args.artifact, args.repetition),
            sort_keys=True,
            allow_nan=False,
        ))
        return 0
    required = (
        "baseline_package", "baseline_artifact", "candidate_package",
        "candidate_artifact", "output",
    )
    missing = [name.replace("_", "-") for name in required if getattr(args, name) is None]
    if missing:
        parser.error("required for paired mode: " + ", ".join("--" + item for item in missing))
    return run_parent(args)


if __name__ == "__main__":
    raise SystemExit(main())
