# Benchmarks

Each report keeps its methodology and raw JSON beside its runner. The stable
SVGs under [`.github/assets/graphs/`](../.github/assets/graphs/) are compact
views of those measurements; the JSON retains exact values, hashes, and run
metadata. Each graph links to its methodology and reproduction steps below.

## Encoded size

The [encoded-size report](encoded_size/README.md) compares compact UTF-8 JSON
payload bytes with dCBOR wire bytes for the same six fixtures. Each fixture has
its own chart scale. One counterexample is explicit: compact scientific
notation is 15 bytes in JSON and 19 bytes in dCBOR. The
[raw measurements](encoded_size/results.json) retain every byte count and hash.
Reproduce the report from the repository root with:

```sh
PYTHONPATH=python python benchmarks/encoded_size.py
```

## Codec wire size

The [wire-size comparison](wire_size/README.md) adds pinned `cbor2` and `cborx`
default and canonical modes. Each fixture panel shows all six codec modes;
canonical options are library-specific and do not establish dCBOR profile
conformance. The [machine-readable report](wire_size/results.json) records
complete, blocked, or failed status. Reproduce it after installing
[`requirements.txt`](requirements.txt) and building dcbor:

```sh
python -m pip install -r benchmarks/requirements.txt
CARGO_BUILD_JOBS=2 maturin develop --release --locked
PYTHONPATH=python python benchmarks/wire_size.py
```

## Latency

The [latency report](latency/README.md) compares encode, decode, and round-trip
medians across six codec modes. Its graph expresses each median as a ratio to
Python `json` for that same fixture and operation, so 1× is parity and values
below 1× are faster. The [machine-readable report](latency/results.json)
retains the exact medians, median absolute deviations (MAD), and nine
fresh-process samples per operation.

All benchmark outputs describe the listed workloads, fixtures, software
versions, and recorded environments. Payload sizes and operation timings are
specific evidence for those workloads; they do not establish universal claims
about memory use, speed, or format suitability.
