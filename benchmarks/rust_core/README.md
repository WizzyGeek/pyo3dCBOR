# Historical Rust-core benchmark

**Retired 2026-10-18.** This report measured the vendored `dcbor` Rust core
against the Python binding before the project moved to its native decoder.
Its raw measurements and chart remain available for historical reference, but
the benchmark runner and standalone example have been removed with that old
architecture. These results do not measure the native decoder and should not
be used to infer its performance.

The comparison used the same eight prepared fixture wires on both sides. Rust
encoding started with vendored `CBOR` trees prepared before timing, while
Python `dcbor.dumps()` included conversion from Python values. Decoding used
prepared wires: the Rust path parsed them into vendored `CBOR` values and the
Python path called `dcbor.loads()`. The timing therefore compared whole
operations with different preparation boundaries; it was not an isolated FFI
measurement.

The historical report's method, environment, raw samples, medians, MAD, and
fingerprints remain in [`results.json`](results.json). Its original figure is
preserved at [`rust-core.svg`](../../.github/assets/graphs/rust-core.svg).
The historical raw JSON and SVG were left unchanged when the active runner was
retired; this README now records the retirement. There is no current
reproduction command.
