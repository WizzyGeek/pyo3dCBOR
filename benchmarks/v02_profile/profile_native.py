"""Run one existing dCBOR fixture repeatedly for external native profilers.

Examples from the repository root::

    PYTHONPATH=python:benchmarks .venv/bin/python benchmarks/v02_profile/profile_native.py \
        --fixture profile:map_10000_shuffled --operation encode --rounds 100
    PYTHONPATH=python:benchmarks .venv/bin/python benchmarks/v02_profile/profile_native.py \
        --fixture bytes:1048576 --operation decode --rounds 100

This helper keeps fixture construction, imports, and one correctness check
outside the measured call loop. External tools such as ``perf`` can wrap it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import subprocess
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "python"), str(ROOT / "benchmarks")]


def fixture_value(
    dcbor: object, spec: str
) -> tuple[object, object | None, str, bool]:
    namespace, separator, name = spec.partition(":")
    if not separator:
        raise ValueError("fixture must be shared:NAME, profile:NAME, or bytes:SIZE")
    if namespace == "shared":
        from fixtures import fixtures

        value = fixtures()[name]
        return value, value, name, False
    if namespace == "profile":
        from profile_fixtures import build_workloads

        workloads = build_workloads(
            lambda key: dcbor.dumps(key),  # type: ignore[attr-defined]
            cbor_map_factory=dcbor.CBORMap,  # type: ignore[attr-defined]
        )
        case = workloads[name]
        return case["input"], case["expected"], name, True
    if namespace == "bytes":
        size = int(name)
        if size < 0:
            raise ValueError("byte fixture size must be non-negative")
        return b"\x5a" * size, None, f"bytes_{size}", False
    raise ValueError(f"unknown fixture namespace {namespace!r}")


def equivalent(actual: object, expected: object, ordered_maps: bool) -> bool:
    if type(actual) is not type(expected):
        return False
    if isinstance(expected, float):
        return actual.hex() == expected.hex()  # type: ignore[union-attr]
    if isinstance(expected, list):
        return len(actual) == len(expected) and all(  # type: ignore[arg-type]
            equivalent(a, e, ordered_maps)
            for a, e in zip(actual, expected)  # type: ignore[arg-type]
        )
    if isinstance(expected, dict):
        if len(actual) != len(expected):  # type: ignore[arg-type]
            return False
        if ordered_maps and list(actual) != list(expected):  # type: ignore[arg-type]
            return False
        if not ordered_maps and actual.keys() != expected.keys():  # type: ignore[union-attr]
            return False
        return all(
            equivalent(actual[key], value, ordered_maps)  # type: ignore[index]
            for key, value in expected.items()
        )
    return actual == expected


def callgrind_control(enabled: bool) -> None:
    """Toggle Callgrind collection from the guest process after setup."""
    action = "on" if enabled else "off"
    subprocess.run(
        ["callgrind_control", "--instr=" + action, str(os.getpid())],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )


class PerfControl:
    """Control perf stat's named FIFO from inside the child process."""

    def __init__(self, prefix: str | None) -> None:
        self.ctl = None
        self.ack = None
        if prefix is not None:
            # Open in the same order used by perf's documented FIFO protocol.
            self.ctl = open(prefix + ".ctl", "w", encoding="ascii", buffering=1)
            self.ack = open(prefix + ".ack", "r", encoding="ascii")

    def set_enabled(self, enabled: bool) -> None:
        if self.ctl is None or self.ack is None:
            return
        self.ctl.write("enable\n" if enabled else "disable\n")
        ack = self.ack.readline().replace("\x00", "").strip()
        if ack != "ack":
            raise RuntimeError(f"perf stat did not acknowledge the ROI control: {ack!r}")

    def close(self) -> None:
        if self.ctl is not None:
            self.ctl.close()
        if self.ack is not None:
            self.ack.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", required=True)
    parser.add_argument("--operation", choices=("encode", "decode"), required=True)
    parser.add_argument("--rounds", type=int, default=100)
    parser.add_argument("--warmup", type=int, default=20)
    parser.add_argument(
        "--perf-control-prefix",
        help="control FIFO prefix; perf stat then counts only the measured loop",
    )
    parser.add_argument(
        "--pause-for-profiler",
        action="store_true",
        help="wait for an external native profiler to start/stop around the call loop",
    )
    parser.add_argument(
        "--callgrind-control",
        action="store_true",
        help="toggle Callgrind instrumentation only around the measured call loop",
    )
    args = parser.parse_args()
    if args.rounds < 1 or args.warmup < 0:
        parser.error("rounds must be positive and warmup non-negative")

    import dcbor

    value, expected, name, ordered_maps = fixture_value(dcbor, args.fixture)
    wire = dcbor.dumps(value)
    decoded = dcbor.loads(wire)
    if expected is not None and not equivalent(decoded, expected, ordered_maps):
        raise ValueError(f"fixture normalization check failed for {name}")
    if args.operation == "decode" and isinstance(value, bytes) and decoded != value:
        raise ValueError(f"bytes fixture round trip failed for {name}")

    operation = (
        (lambda: dcbor.dumps(value))
        if args.operation == "encode"
        else (lambda: dcbor.loads(wire))
    )
    for _ in range(args.warmup):
        operation()
    perf_control = PerfControl(args.perf_control_prefix)
    if args.pause_for_profiler:
        print(f"READY {os.getpid()}", flush=True)
        if sys.stdin.readline().strip() != "go":
            raise RuntimeError("expected 'go' from the external profiler controller")
    if args.callgrind_control:
        callgrind_control(True)
    perf_control.set_enabled(True)
    start = time.perf_counter_ns()
    for _ in range(args.rounds):
        result = operation()
    elapsed = time.perf_counter_ns() - start
    perf_control.set_enabled(False)
    if args.callgrind_control:
        callgrind_control(False)
    perf_control.close()

    print(json.dumps({
        "fixture": name,
        "fixture_spec": args.fixture,
        "operation": args.operation,
        "rounds": args.rounds,
        "warmup": args.warmup,
        "input_bytes": len(value) if isinstance(value, (bytes, bytearray)) else None,
        "wire_bytes": len(wire),
        "wire_sha256": hashlib.sha256(wire).hexdigest(),
        "ns_per_operation": elapsed / args.rounds,
        "counter_region": "measured call loop only" if args.perf_control_prefix else None,
        "callgrind_controlled": args.callgrind_control,
        "extension_path": dcbor._dcbor.__file__,  # type: ignore[attr-defined]
    }, sort_keys=True), flush=True)
    if args.pause_for_profiler:
        if sys.stdin.readline().strip() != "exit":
            raise RuntimeError("expected 'exit' after the external profiler stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
