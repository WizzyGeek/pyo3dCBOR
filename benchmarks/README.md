# Benchmarks

The [comparison overview](../docs/benchmarks.md) explains what the figures
show and where their limits are. Active reports contain their methodology,
machine-readable measurements, and reproduction command. Historical reports
are labeled and may no longer have a runnable measurement path.

The current active capture uses dCBOR 0.1.1 at source commit `df70782`.

- [Encoded size](encoded_size/README.md): compact JSON and dCBOR bytes.
- [Wire size](wire_size/README.md): JSON, dCBOR, generic CBOR, MessagePack,
  and strict DAG-CBOR bytes.
- [Latency](latency/README.md): encode, decode, and round-trip timings for
  each measured mode.
- [dCBOR profile](profile/README.md): map encode/decode scaling, numeric
  normalization, and Unicode normalization workloads.
- [Native decoder paired profile](native_decoder/README.md): decode and encode
  controls against the preserved pre-migration package.

Shared JSON fixtures are defined in [`fixtures.py`](fixtures.py); profile-only
inputs are in [`profile_fixtures.py`](profile_fixtures.py). Figures are stored
in [`.github/assets/graphs/`](../.github/assets/graphs/). Raw JSON reports keep
per-fixture results, hashes, and run metadata.

The wire-size and latency comparator suites require Python 3.10 or newer; the
`dcbor` source package itself continues to support Python 3.9.

## Reproduce

Run from the repository root. Install the pinned comparison libraries for
wire-size and latency. Build the release extension for those reports and the
profile workload.

```sh
python -m pip install -r benchmarks/requirements.txt
CARGO_BUILD_JOBS=2 maturin develop --release --locked
PYTHONPATH=python python benchmarks/encoded_size.py
PYTHONPATH=python python benchmarks/wire_size.py
PYTHONPATH=python python benchmarks/latency.py
PYTHONPATH=python python benchmarks/profile.py
```

The encoded-size runner needs only `dcbor`; the profile runner adds no
comparison dependencies. The other runners check their required packages,
extension build, fixtures, and output consistency before recording results;
see each report for exact checks and options.
