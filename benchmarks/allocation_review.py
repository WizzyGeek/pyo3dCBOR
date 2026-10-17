"""Bounded allocation/timing probes for the installed dcbor extension.

Run from the repository root with the environment whose extension is under
review, for example:

  .venv/bin/python benchmarks/allocation_review.py --output /tmp/allocation.json

The tracemalloc figures cover Python-managed allocations only. They do not
measure the Rust CBOR tree, encoded-key caches, or allocator-retained native
memory. In particular, peak traced bytes do not count all short-lived Python
objects created and dropped while converting a fallback map.
"""

import argparse
import gc
import hashlib
import importlib
import json
import platform
import statistics
import sys
import time
import tracemalloc


def timed(fn, rounds, target_seconds):
    fn()
    number = 1
    while True:
        start = time.perf_counter()
        for _ in range(number):
            fn()
        if time.perf_counter() - start >= target_seconds:
            break
        number *= 2

    samples = []
    gc_was_enabled = gc.isenabled()
    gc.disable()
    try:
        for _ in range(rounds):
            start = time.perf_counter_ns()
            for _ in range(number):
                fn()
            samples.append((time.perf_counter_ns() - start) / number / 1000)
    finally:
        if gc_was_enabled:
            gc.enable()
    return {
        "median_us": statistics.median(samples),
        "min_us": min(samples),
        "max_us": max(samples),
        "samples_us": samples,
        "iterations_per_sample": number,
    }


def python_peak(fn):
    gc.collect()
    tracemalloc.start()
    result = None
    try:
        result = fn()
        current, peak = tracemalloc.get_traced_memory()
        return {"current_bytes": current, "peak_bytes": peak}
    finally:
        del result
        tracemalloc.stop()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--array-items", type=int, default=16384)
    parser.add_argument("--map-entries", type=int, default=1024)
    parser.add_argument("--rounds", type=int, default=7)
    parser.add_argument("--target-ms", type=float, default=20)
    parser.add_argument("--output")
    args = parser.parse_args()
    if not 1 <= args.array_items <= 32768:
        parser.error("array-items must be between 1 and 32768")
    if not 1 <= args.map_entries <= 2048:
        parser.error("map-entries must be between 1 and 2048")
    if args.rounds < 1 or args.target_ms <= 0:
        parser.error("rounds and target-ms must be positive")

    dcbor = importlib.import_module("dcbor")
    extension_path = dcbor._dcbor.__file__
    with open(extension_path, "rb") as extension_file:
        extension_sha256 = hashlib.sha256(extension_file.read()).hexdigest()

    array_wire = dcbor.dumps(list(range(args.array_items)))
    fallback_source = dcbor.CBORMap(
        [([i], list(range(8))) for i in range(args.map_entries)]
    )
    fallback_wire = dcbor.dumps(fallback_source)
    fallback_map = dcbor.loads(fallback_wire)
    if not isinstance(fallback_map, dcbor.CBORMap):
        raise RuntimeError("array-key map did not decode to CBORMap")

    workloads = {
        "validate_integer_array": (
            lambda: dcbor.validate(array_wire),
            len(array_wire),
        ),
        "loads_integer_array": (
            lambda: dcbor.loads(array_wire),
            len(array_wire),
        ),
        "loads_fallback_map": (
            lambda: dcbor.loads(fallback_wire),
            len(fallback_wire),
        ),
        "cbormap_iter_create": (
            lambda: iter(fallback_map),
            len(fallback_wire),
        ),
        "cbormap_first_key": (
            lambda: next(iter(fallback_map)),
            len(fallback_wire),
        ),
    }

    output = {
        "extension": extension_path,
        "extension_sha256": extension_sha256,
        "python": sys.version,
        "platform": platform.platform(),
        "array_items": args.array_items,
        "fallback_map_entries": args.map_entries,
        "rounds": args.rounds,
        "target_ms": args.target_ms,
        "allocation_metric": (
            "tracemalloc peak/current Python-managed bytes; excludes Rust heap "
            "and does not count cumulative short-lived allocations"
        ),
        "workloads": {},
    }
    for name, (fn, wire_bytes) in workloads.items():
        output["workloads"][name] = {
            "wire_bytes": wire_bytes,
            "timing": timed(fn, args.rounds, args.target_ms / 1000),
            "python_tracemalloc": python_peak(fn),
        }

    rendered = json.dumps(output, indent=2) + "\n"
    if args.output:
        with open(args.output, "w", encoding="utf-8") as result_file:
            result_file.write(rendered)
        print(f"wrote allocation probes to {args.output}")
    else:
        sys.stdout.write(rendered)


if __name__ == "__main__":
    main()
