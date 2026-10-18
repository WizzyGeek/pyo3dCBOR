"""Interleaved fresh-process follow-up for integer-width encode latency."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WARMUP = 100
ROUNDS = 500
REPETITIONS = 9


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def worker(package_root: Path, artifact: Path) -> dict[str, object]:
    sys.path.insert(0, str(package_root))
    import dcbor
    from profile_fixtures import build_workloads

    artifact_hash = sha256(artifact.read_bytes())
    extension_path = Path(dcbor._dcbor.__file__).resolve()
    extension_hash = sha256(extension_path.read_bytes())
    if artifact_hash != extension_hash:
        raise RuntimeError("loaded extension does not match the configured artifact")

    cases = build_workloads(
        lambda key: dcbor.dumps(key), cbor_map_factory=dcbor.CBORMap
    )
    case = cases["integer_width_boundaries"]
    value = case["input"]
    wire = dcbor.dumps(value)
    iterations = min(ROUNDS, ROUNDS * 1000 // int(case["work_units"]))
    warmup = min(WARMUP, WARMUP * 1000 // int(case["work_units"]))
    for _ in range(warmup):
        dcbor.dumps(value)
    start = time.perf_counter_ns()
    for _ in range(iterations):
        dcbor.dumps(value)
    elapsed = time.perf_counter_ns() - start
    return {
        "pid": os.getpid(),
        "started_at_utc": __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        ).isoformat(),
        "median_sample_ns_per_operation": elapsed / iterations,
        "iterations": iterations,
        "warmup": warmup,
        "input_sha256": sha256(__import__("profile").input_fingerprint_bytes(value)),
        "wire_sha256": sha256(wire),
        "wire_bytes": len(wire),
        "extension_path": str(extension_path),
        "extension_sha256": extension_hash,
        "artifact_sha256": artifact_hash,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "benchmarks/native_decoder/interleaved_integer.json")
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--package-root", type=Path)
    parser.add_argument("--artifact", type=Path)
    args = parser.parse_args()
    if args.worker:
        assert args.package_root is not None and args.artifact is not None
        print(json.dumps(worker(args.package_root, args.artifact), allow_nan=False))
        return 0

    configurations = {
        "baseline": (
            Path("/tmp/native-decoder-baseline/site"),
            Path("/tmp/native-decoder-baseline/site/dcbor/_dcbor.cpython-314-x86_64-linux-gnu.so"),
        ),
        "candidate": (ROOT / "python", ROOT / "target/release/lib_dcbor.so"),
    }
    samples: dict[str, list[dict[str, object]]] = {role: [] for role in configurations}
    pairs = []
    for index in range(REPETITIONS):
        order = ["baseline", "candidate"]
        if index % 2:
            order.reverse()
        pair: dict[str, object] = {"pair": index + 1, "order": order}
        for role in order:
            package_root, artifact = configurations[role]
            output = subprocess.check_output(
                [
                    sys.executable,
                    str(Path(__file__).resolve()),
                    "--worker",
                    "--package-root",
                    str(package_root),
                    "--artifact",
                    str(artifact),
                ],
                cwd=ROOT,
                env={**os.environ, "PYTHONHASHSEED": "0", "PYTHONPATH": str(ROOT / "benchmarks")},
                text=True,
            )
            sample = json.loads(output)
            samples[role].append(sample)
            pair[role + "_pid"] = sample["pid"]
            pair[role + "_ns_per_operation"] = sample["median_sample_ns_per_operation"]
        pairs.append(pair)

    summaries = {}
    for role, role_samples in samples.items():
        values = [float(sample["median_sample_ns_per_operation"]) for sample in role_samples]
        median = statistics.median(values)
        summaries[role] = {
            "samples_ns_per_operation": values,
            "median_ns_per_operation": median,
            "mad_ns_per_operation": statistics.median(abs(value - median) for value in values),
        }
    report = {
        "status": "complete",
        "case_id": "integer_width_boundaries",
        "operation": "encode",
        "methodology": {
            "runner": str(Path(__file__).resolve().relative_to(ROOT)),
            "fresh_processes": True,
            "interleaving": "nine adjacent baseline/candidate pairs; starting role alternates",
            "warmup_calls_per_process": WARMUP,
            "timed_calls_per_process": ROUNDS,
            "clock": "time.perf_counter_ns",
            "measurement": "batch mean nanoseconds per dumps operation",
        },
        "process_samples": samples,
        "pairs": pairs,
        "summaries": summaries,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
