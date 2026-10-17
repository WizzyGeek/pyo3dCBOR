# Rust core and Python binding

This report compares encode and decode timings from the patched Rust dCBOR
core with Python binding calls on the same eight prepared fixture wires. It
measures whole operations; the result is not an isolated FFI-cost estimate.

![Rust core encode and decode compared with Python binding calls; Rust trees are prepared before timing and Python value conversion is included.](../../.github/assets/graphs/rust-core.svg)

Each point is the ratio of Rust-core time to Python-binding time for one
fixture; `1×` is equal time, and a value below `1×` means the Rust path took
less time in this run. The plot shows each fixture separately.

For Rust encoding, each wire is parsed to a CBOR tree before timing, then the
existing tree is encoded. For Python encoding, `dcbor.dumps(value)` converts
the Python fixture during the timed call. Both decoders receive prepared wire
bytes: Rust calls `CBOR::try_from_data`, while Python calls
`dcbor.loads(prepared_wire)`. The Rust tree's map-key sort bytes are prepared
and may be warmed during verification; that work is excluded from its encode
measurement.

The runner checks each Python round trip against the fixture with
type-sensitive equality. Rust parsing must succeed and re-encoding must match
the prepared Python dCBOR bytes exactly. There is no Rust-to-Python decoded
value comparison, so decode parity is established by successful strict parse
and byte-identical re-encoding rather than a type-by-type value oracle.

## Report and method

[`results.json`](results.json) stores results at
`fixtures[name][rust_core|python_dcbor][encode|decode]`. Each operation has
nine fresh-process samples by default, summarized as a median, MAD, minimum,
and maximum. The report also records source and binary fingerprints, Python
and Rust environment details, fixture hashes, and wire hashes. Native worker
startup, fixture construction, and wire preparation happen outside timed
regions; Rust and Python measurements alternate order across repetitions.

The report describes one host and toolchain. Rust's prepared tree and Python's
per-call value conversion differ, and map-cache behavior differs as well. Use
the paired timings to inspect these implementations on this fixture set, not
to infer the cost of an FFI call or predict another application.

## Reproduce

From the repository root, build the optimized example binary and ensure the
Python extension matches the release library:

```sh
cargo build --release --locked --example benchmark-core
PYTHONPATH=python python benchmarks/rust_core.py
```

The driver defaults to 500 warmup calls, 1,000 timed calls per process, and
nine process repetitions. Override with `--binary`, `--warmup`, `--rounds`,
or `--repetitions`. It writes the raw report and the stable figure at
[`rust-core.svg`](../../.github/assets/graphs/rust-core.svg). The report
requires the release extension to match `target/release/lib_dcbor.so` by
SHA-256 and records the binary SHA-256 and build command.
