# Native decoder test migration

The default locked vendor baseline was captured before deleting the vendored
Rust crate:

```text
cargo test --manifest-path crates/dcbor/Cargo.toml --locked
```

The run passed all **182** tests. The baseline package and CPython 3.14
extension are preserved at
`/tmp/native-decoder-baseline/site/dcbor`; the extension SHA-256 is
`36502b893f69ae0c7bf8b159d53099b17c7ec02446c14b5d6a3555a6a278d581`.
The complete command output was not retained in the current workspace.

| Vendor target | Passed | Coverage disposition |
| --- | ---: | --- |
| Library unit tests | 24 | Numeric and byte-string wire behavior is covered by the independent Python vector suites below. `walk` unit tests exercise a vendor-only visitor API. |
| `tests/encode.rs` | 37 | Python-facing wire behavior is covered by retained tests. Rust `CBOR` constructors and conversion traits are not extension APIs. |
| `tests/format.rs` | 15 | The extension exposes diagnostic rendering, covered by baseline fixtures. Description, debug, annotated-hex, and summary methods are not exposed. |
| `tests/num_bigint.rs` | 0 | The target is feature-gated and disabled in the locked default run. The Python extension does not expose the vendor's `BigInt` conversion traits. |
| `tests/version-numbers.rs` | 2 | Checks vendor README/version metadata, not Python reader behavior. |
| `tests/walk.rs` | 12 | Exercises the vendor's public `CBOR::walk` API, which the Python extension does not expose. |
| Rust doctests | 92 | Examples for vendor constructors, conversions, and auxiliary APIs have no Python-facing counterpart. Public codec and diagnostic behavior is covered by the retained API tests. |

The prior 170-case count omitted the 12 active `tests/walk.rs` cases. The
locked default command runs that target, so 182 is the complete count. The
feature-gated `num_bigint` target contributes zero tests in this configuration.

Applicable codec behavior remains covered by retained tests with independent
expected wires or a baseline observation:

- Integer widths, signed values, maps, tags, arrays, bytes, and basic decoding:
  `tests/test_dcbor.py`.
- Canonical numeric reduction, Unicode NFC, map ordering, and malformed
  encodings: `tests/test_spec_conformance.py` and `tests/test_wire_safety.py`.
- Independent float-width and numeric-boundary oracle:
  `tests/test_numeric_oracle.py`.
- Scalar, date, and Unicode behavior: `tests/test_scalars.py` and
  `tests/test_ascii_fastpath.py`.
- Frozen-map identity, tag/date keys, and canonical diagnostics:
  `tests/test_maps_tags.py` and `tests/test_key_identity.py`.
- Direct writer nested wires and mutation/callback compatibility:
  `tests/test_direct_encoder.py`.
- Baseline reader and formatter fixtures:
  `tests/test_direct_decoder.py`. It records exact pretty and flat diagnostic
  strings for nested maps, tags, byte strings, NFC text, and datetime tags;
  verifies distinct integer/boolean map keys and exact built-in integer types
  at the preferred-width boundaries; captures error type and message for
  overlong integers, duplicate keys, malformed UTF-8, truncation, and
  noncanonical NaN; and checks that 1 MiB byte-string and text results remain
  valid after deleting the input object. Its `load()` cases cover binary files
  and `BytesIO`, a single read, unchanged read exceptions, text-stream
  rejection, error parity with `loads()`, and owned bytes after the file closes.

Vendor-only traversal visitors, Rust `CBOR` conversion traits, annotated hex,
debug descriptions, summaries, and optional `num_bigint` conversion behavior
are intentionally not represented as Python API tests. They are removed
Rust-library surface, rather than behavior provided by this extension.
