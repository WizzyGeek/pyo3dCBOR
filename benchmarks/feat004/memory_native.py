"""Bounded process-level RSS probe for FEAT004 direct encoder candidates.

This uses Linux ``resource.getrusage().ru_maxrss`` in one fresh child per
sample. It measures process peak RSS, not exact native allocation counts. Use
the same Python build for both revisions and pass isolated import roots.

Example (after the benchmark owner clears the timing window)::

    python benchmarks/feat004/memory_native.py \
      --baseline-import-root /tmp/feat004-baseline/site \
      --candidate-import-root .venv/lib/python3.14/site-packages \
      --output /tmp/feat004-memory-native.json
"""

import argparse
import hashlib
import importlib
import json
import os
import platform
import resource
import statistics
import subprocess
import sys
from pathlib import Path


WORKLOADS = (
    "bytes_2mib",
    "text_2mib",
    "nested_graph",
    "leading_combiners_128k",
)
INPUT_DESCRIPTORS = {
    "bytes_2mib": "bytes: b'abcdefgh' repeated 262144 times (2097152 bytes)",
    "text_2mib": "text: 'abcdefgh' repeated 262144 times (2097152 UTF-8 bytes)",
    "nested_graph": (
        "list of 2048 maps; each has integer id, entry-NNNN name, children "
        "[id, id+1, map(label=node-id, data=64 zero bytes)]"
    ),
    "leading_combiners_128k": (
        "map with one key: U+0344 repeated 131072 times; value is integer zero"
    ),
}


def rss_bytes():
    """Return current resident set size on Linux, when procfs is available."""
    try:
        with open("/proc/self/statm", encoding="ascii") as statm:
            resident_pages = int(statm.read().split()[1])
        return resident_pages * os.sysconf("SC_PAGE_SIZE")
    except (OSError, ValueError, IndexError):
        return None


def maxrss_bytes():
    # Linux reports ru_maxrss in KiB. This script is intentionally Linux-only.
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024


def make_value(name):
    if name == "bytes_2mib":
        return b"abcdefgh" * (2 * 1024 * 1024 // 8)
    if name == "text_2mib":
        return "abcdefgh" * (2 * 1024 * 1024 // 8)
    if name == "nested_graph":
        return [
            {
                "id": index,
                "name": f"entry-{index:04d}",
                "children": [
                    index,
                    index + 1,
                    {"label": f"node-{index}", "data": bytes(64)},
                ],
            }
            for index in range(2048)
        ]
    if name == "leading_combiners_128k":
        return {"\u0344" * (128 * 1024): 0}
    raise ValueError(f"unknown workload: {name}")


def worker(name):
    dcbor = importlib.import_module("dcbor")
    extension_path = Path(dcbor._dcbor.__file__).resolve()
    extension_hash = hashlib.sha256(extension_path.read_bytes()).hexdigest()
    value = make_value(name)

    # Load encoder paths before sampling, so interpreter/import startup does
    # not masquerade as workload growth. Keep the complete source graph alive.
    warmup = dcbor.dumps(None)
    del warmup
    import gc

    gc.collect()
    baseline = {
        "current_rss_bytes": rss_bytes(),
        "peak_rss_bytes": maxrss_bytes(),
    }
    encoded = dcbor.dumps(value)
    after = {
        "current_rss_bytes": rss_bytes(),
        "peak_rss_bytes": maxrss_bytes(),
    }
    output_sha256 = hashlib.sha256(encoded).hexdigest()
    output_length = len(encoded)
    del encoded
    gc.collect()
    after_release = {"current_rss_bytes": rss_bytes(), "peak_rss_bytes": maxrss_bytes()}

    return {
        "workload": name,
        "extension_path": str(extension_path),
        "extension_sha256": extension_hash,
        "python": sys.version,
        "platform": platform.platform(),
        "input_descriptor": INPUT_DESCRIPTORS[name],
        "input_descriptor_sha256": hashlib.sha256(
            INPUT_DESCRIPTORS[name].encode("utf-8")
        ).hexdigest(),
        "baseline": baseline,
        "after_encode": after,
        "after_release": after_release,
        "peak_rss_growth_over_pre_encode_high_water_bytes": max(
            0, after["peak_rss_bytes"] - baseline["peak_rss_bytes"]
        ),
        "output_length": output_length,
        "output_sha256": output_sha256,
    }


def run_sample(python, import_root, workload):
    env = os.environ.copy()
    # Isolate import resolution; do not let a user PYTHONPATH shadow a revision.
    env["PYTHONPATH"] = str(Path(import_root).resolve())
    script = str(Path(__file__).resolve())
    proc = subprocess.run(
        [python, script, "--_worker", workload],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    return json.loads(proc.stdout)


def summarize(samples):
    growth = [
        sample["peak_rss_growth_over_pre_encode_high_water_bytes"]
        for sample in samples
    ]
    peak = [sample["after_encode"]["peak_rss_bytes"] for sample in samples]
    return {
        "peak_rss_growth_over_pre_encode_high_water_bytes_median": statistics.median(growth),
        "peak_rss_growth_over_pre_encode_high_water_bytes_min_max": [min(growth), max(growth)],
        "absolute_process_peak_rss_bytes_median": statistics.median(peak),
        "absolute_process_peak_rss_bytes_min_max": [min(peak), max(peak)],
    }


def parent(args):
    if not sys.platform.startswith("linux"):
        raise SystemExit("this probe requires Linux ru_maxrss units and procfs")
    if args.samples < 3:
        raise SystemExit("use at least three child samples per workload")
    revisions = {
        "baseline": (args.baseline_python, args.baseline_import_root),
        "candidate": (args.candidate_python, args.candidate_import_root),
    }
    result = {
        "measurement": "isolated child process peak RSS via resource.getrusage(RUSAGE_SELF).ru_maxrss",
        "scope_limit": (
            "Process-level peak RSS includes interpreter, extension, source graph, output, "
            "allocator retention, and other process memory. The reported growth is only "
            "the increase over pre-encode high-water mark; it is not native allocation "
            "count or exact encoder-attributed memory."
        ),
        "samples_per_workload_per_revision": args.samples,
        "python_executable_parent": sys.executable,
        "platform": platform.platform(),
        "workloads": {},
    }
    for workload in WORKLOADS:
        result["workloads"][workload] = {}
        for revision, (python, import_root) in revisions.items():
            samples = [
                run_sample(python, import_root, workload)
                for _ in range(args.samples)
            ]
            hashes = {sample["output_sha256"] for sample in samples}
            lengths = {sample["output_length"] for sample in samples}
            if len(hashes) != 1 or len(lengths) != 1:
                raise RuntimeError(f"unstable output for {revision}/{workload}")
            result["workloads"][workload][revision] = {
                "python_executable": str(Path(python).resolve()),
                "import_root": str(Path(import_root).resolve()),
                "summary": summarize(samples),
                "samples": samples,
            }
        baseline = result["workloads"][workload]["baseline"]["samples"][0]
        candidate = result["workloads"][workload]["candidate"]["samples"][0]
        if (baseline["output_length"], baseline["output_sha256"]) != (
            candidate["output_length"], candidate["output_sha256"]
        ):
            raise RuntimeError(f"baseline/candidate output differs for {workload}")

    rendered = json.dumps(result, indent=2) + "\n"
    if args.output:
        Path(args.output).write_text(rendered, encoding="utf-8")
        print(f"wrote raw native-memory samples to {args.output}")
    else:
        sys.stdout.write(rendered)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-python", default=sys.executable)
    parser.add_argument("--baseline-import-root")
    parser.add_argument("--candidate-python", default=sys.executable)
    parser.add_argument("--candidate-import-root")
    parser.add_argument("--samples", type=int, default=5)
    parser.add_argument("--output")
    parser.add_argument("--_worker", choices=WORKLOADS, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args._worker:
        print(json.dumps(worker(args._worker), separators=(",", ":")))
        return
    if not args.baseline_import_root or not args.candidate_import_root:
        parser.error("both baseline and candidate import roots are required")
    parent(args)


if __name__ == "__main__":
    main()
