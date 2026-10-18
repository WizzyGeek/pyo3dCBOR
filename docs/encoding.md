# Python encoding architecture

`dumps()` encodes supported Python values directly into a Rust-owned byte
buffer. The binding no longer constructs a recursive vendored `dcbor::CBOR`
tree for ordinary encoding. Maps stage canonical encoded keys and values,
sort by encoded-key bytes, and resolve byte-identical Python `dict` keys with
last-entry-wins behavior. Map values are converted once in iteration order.
`CBORMap` snapshots are encoded directly from their frozen Rust state; Python
callbacks and `__index__` dispatch retain their established call order and
count. Bytearray reads keep the raw borrow inside a critical section through
the immediate native copy. The writer preserves the documented NFC, numeric,
map-identity, tag/datetime, cycle, and error behavior, plus the existing depth
and aggregate map-key budgets and final wire preflight.

The public `CBORMap` constructors still use the existing converter, and
vendored decoding remains in place. `dumps()` still materializes its output
buffer and `PyBytes::new` copies the final wire bytes into the Python result;
this is not a zero-copy output path. Borrowed Python payload views can avoid an
intermediate payload allocation, but text normalization and numeric encoding
still transform data. The native-memory probe records bounded process-level
RSS evidence, not an exact allocation count or a universal bound. NFC
normalization may buffer a pending combining sequence before yielding; that
limitation is shared with the previous path.

## PM acceptance

**Accepted and complete — 2026-10-18, Codex GPT-6 (PM).** The direct writer
implementation is commit `3e75d65` for development version `0.1.1`. The
validated run passed 1,580 Python tests, 170 vendored Rust tests/doctests, and
3 binding Rust tests. Matched benchmarks recorded a median encode ratio of
3.04× across the eight common fixtures (range 1.16×–4.47×), 1.59× for
round-trip, and 1.02× for common-fixture decode. All shared fixtures retained
byte-identical output. See the [paired benchmark report](../benchmarks/feat004/README.md)
and [native-memory probe](../benchmarks/feat004/memory_report.md) for methods,
raw data, and limitations.

The mixed-profile 10,000-entry map decode slowdown remains an explicit open
investigation tracked as [BUG_005](requirements/BUG_005_mixed_profile_decode_slowdown.md).
It does not block acceptance of the direct-encoding feature; it remains visible
and is not attributed to a cause or treated as noise.

The scalar/header primitives are written against `std::io::Write` internally,
with the current `Vec` as the sink. A future `dump(obj, file/socket)` API would
need separate design for partial writes and I/O errors; canonical maps still
need staging, callback-mutated lists need final-count handling, and a raw
bytearray borrow must never span a Python writer callback, blocking I/O, or a
GIL release. Current `dumps()` is not a streaming API. Threading and
vectorization are deferred; consider them only if profiling isolates a
substantial Rust-owned payload phase.
