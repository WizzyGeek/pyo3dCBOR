# Benchmarks

The encoded-size and latency reports keep their methodology and raw JSON beside
their runners. Runs may overwrite stable graph files under
[`.github/assets/graphs/`](../.github/assets/graphs/); review the generated
files before keeping or committing refreshed results.

## Encoded size

The [encoded-size methodology and results](encoded_size/README.md) compare
compact UTF-8 JSON payload bytes with dCBOR wire bytes for equivalent fixtures.
The [raw measurements](encoded_size/results.json) and
[generated chart](../.github/assets/graphs/encoded-size.svg) are committed
alongside the runner at [`encoded_size.py`](encoded_size.py). Reproduce them
from the repository root with:

```sh
PYTHONPATH=python python benchmarks/encoded_size.py
```

## Codec wire size

The [wire-size comparison](wire_size/README.md) compares compact JSON and dCBOR
with pinned `cbor2` and `cborx` default and canonical modes. The current
[machine-readable report](wire_size/results.json) and
[stable graph](../.github/assets/graphs/wire-size.svg) record a blocker if any
comparator or verified release build is unavailable. Reproduce it after
installing [`requirements.txt`](requirements.txt) and building dcbor:

```sh
python -m pip install -r benchmarks/requirements.txt
CARGO_BUILD_JOBS=2 maturin develop --release --locked
PYTHONPATH=python python benchmarks/wire_size.py
```

## Latency

The [latency methodology](latency/README.md) compares encode, decode, and
round-trip operations across six series: Python standard-library `json`,
`dcbor`, `cbor2` default/canonical, and `cborx` default/canonical. The current
[machine-readable report](latency/results.json) contains nine fresh-process
measurements per operation, and the
[stable graph](../.github/assets/graphs/latency.svg) shows the full
fixture-by-fixture results. On the recorded host, dCBOR loses substantially to
the fastest generic-CBOR mode on repeated Unicode strings and the large
collection, while it beats compact JSON on the numeric array and
scientific-notation fixture. See the methodology document for the exact
environment and limitations.

All benchmark outputs describe the listed workloads, fixtures, software
versions, and recorded environments. Payload sizes and operation timings are
specific evidence for those workloads; they do not establish universal claims
about memory use, speed, or format suitability.
