"""Reproducible end-to-end workloads for docs/reviews/PERF_REVIEW.md (standard library only).

Run with a freshly built release extension, without replacing the installed one:
  .venv/bin/python benchmarks/perf_review.py --extension /path/lib_dcbor.so \
      --label baseline --output /tmp/perf-baseline.json
Compare wire_sha256 between runs before comparing timings. Timings include
Python call overhead, conversion, encoding/decoding, validation and destruction.
"""

import argparse
import gc
import hashlib
import importlib.util
import json
import os
import platform
import statistics
import sys
import time


def measure(fn, rounds, target_seconds):
    fn()
    number = 1
    while True:
        start = time.perf_counter()
        for _ in range(number):
            fn()
        elapsed = time.perf_counter() - start
        if elapsed >= target_seconds:
            break
        number *= 2
    samples = []
    gc_enabled = gc.isenabled()
    gc.disable()
    try:
        for _ in range(rounds):
            start = time.perf_counter_ns()
            for _ in range(number):
                fn()
            samples.append((time.perf_counter_ns() - start) / number / 1000)
    finally:
        if gc_enabled:
            gc.enable()
    return {"median_us": statistics.median(samples), "min_us": min(samples),
            "max_us": max(samples), "samples_us": samples, "iterations": number}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--extension", required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--rounds", type=int, default=7)
    parser.add_argument("--target-ms", type=float, default=15)
    args = parser.parse_args()
    if args.rounds < 1 or args.target_ms <= 0:
        parser.error("rounds and target-ms must be positive")
    spec = importlib.util.spec_from_file_location("_dcbor", args.extension)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load extension: {args.extension}")
    dcbor = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(dcbor)

    blob = b"x" * (256 * 1024)
    nested = blob
    for _ in range(128):
        nested = [nested]
    fixtures = {
        "integers_4096": list(range(4096)),
        "floats_4096": [i + 0.25 for i in range(4096)],
        "ascii_1024x48": ["a" * 48 for _ in range(1024)],
        "nfc_1024x48": ["é" * 48 for _ in range(1024)],
        "nfd_1024x48": ["e\u0301" * 48 for _ in range(1024)],
        "dict_1024": {f"key{i:04}": i for i in range(1024)},
        "tiny_lists_1024": [[i] for i in range(1024)],
        "bytes_1mib": b"x" * (1024 * 1024),
        "bytes_256kib": blob,
        "nested128_bytes_256kib": nested,
        "fallback_map_1024": dcbor.CBORMap(
            [([i], list(range(16))) for i in range(1024)]),
    }
    output = {"label": args.label, "extension": os.path.abspath(args.extension),
              "extension_sha256": hashlib.sha256(open(args.extension, "rb").read()).hexdigest(),
              "python": sys.version, "platform": platform.platform(),
              "rounds": args.rounds, "target_ms": args.target_ms, "workloads": {}}
    for name, value in fixtures.items():
        wire = dcbor.dumps(value)
        result = {"wire_bytes": len(wire), "wire_sha256": hashlib.sha256(wire).hexdigest()}
        for operation, fn in {
            "dumps": lambda value=value: dcbor.dumps(value),
            "loads": lambda wire=wire: dcbor.loads(wire),
            "validate": lambda wire=wire: dcbor.validate(wire),
        }.items():
            result[operation] = measure(fn, args.rounds, args.target_ms / 1000)
        output["workloads"][name] = result
    pairs = [(f"key{i:04}", i) for i in range(1024)]
    output["cbormap_construct_1024"] = measure(
        lambda: dcbor.CBORMap(pairs), args.rounds, args.target_ms / 1000)
    with open(args.output, "w") as file:
        json.dump(output, file, indent=2)
        file.write("\n")
    print(f"{args.label}: wrote {len(fixtures)} workloads to {args.output}")


if __name__ == "__main__":
    main()
