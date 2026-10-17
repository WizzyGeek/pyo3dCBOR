# Benchmarks

The [comparison overview](../docs/benchmarks.md) explains the graphs, fixture
scope, and limits. Each report includes methodology, machine-readable data, and
reproduction commands:

- [Encoded size](encoded_size/README.md): compact JSON versus dCBOR payload bytes.
- [Wire size](wire_size/README.md): JSON and dCBOR versus `cbor2`/`cborx` modes.
- [Latency](latency/README.md): encode, decode, and round-trip timing.

The shared fixture definitions are in [`fixtures.py`](fixtures.py). Stable SVGs
are stored in [`.github/assets/graphs/`](../.github/assets/graphs/); raw JSON
reports retain exact measurements and run metadata.

## Reproduce

Run from the repository root. Build the release extension first for the
wire-size and latency reports:

```sh
python -m pip install -r benchmarks/requirements.txt
CARGO_BUILD_JOBS=2 maturin develop --release --locked
PYTHONPATH=python python benchmarks/encoded_size.py
PYTHONPATH=python python benchmarks/wire_size.py
PYTHONPATH=python python benchmarks/latency.py
```

The encoded-size runner needs only the active `dcbor` package. The other
runners need the pinned comparators and a release extension matching the Cargo
artifact; see each method for its checks and recorded metadata.
