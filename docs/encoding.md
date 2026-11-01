# Python encoding architecture

`dumps()` encodes supported Python values directly into a Rust-owned byte
buffer. The binding does not construct a recursive CBOR value tree. Maps stage
canonical encoded keys and values, sort by encoded-key bytes, and resolve
byte-identical Python `dict` keys with last-entry-wins behavior. Map values are
converted once in iteration order. `CBORMap` snapshots are encoded directly
from their frozen Rust state; Python callbacks and `__index__` dispatch retain
their established call order and count. Bytearray reads keep the raw borrow
inside a critical section through the immediate native copy. The writer
preserves the documented NFC, numeric, map-identity, tag/datetime, cycle, and
error behavior, plus the existing depth and aggregate map-key budgets and
final wire preflight.

`loads()` first scans borrowed wire bytes to validate canonical form, nesting
depth, map-key ordering, duplicate keys, text validity, and resource limits.
It then builds Python values directly from a borrowed cursor over those bytes;
it does not construct a Rust CBOR tree. `load(binary_file)` calls `read()`
once, keeps the returned input in `PyBytes`, and invokes the same decoder as
`loads()`. Decoded values own their Python storage, so they remain valid after
the source bytes or file object are released. Each call creates a fresh Python
decoded value graph; mutable values do not share state between results, and
decoding needs no explicit codec locks.

`diagnostic()` and `diagnostic_flat()` run the same canonical preflight once,
then format directly from borrowed wire spans into the returned string. The
formatter preserves the existing quote escaping, float spellings, flat
notation, and 20-character pretty-layout threshold without constructing a
CBOR tree or a diagnostic tree.

`dumps()` still materializes its output buffer and `PyBytes::new` copies the
final wire bytes into the Python result; this is not a zero-copy output path.
Borrowed Python payload views can avoid an intermediate payload allocation,
but text normalization and numeric encoding still transform data. The
native-memory probe records bounded process-level RSS evidence, not an exact
allocation count or a universal bound. NFC normalization may buffer a pending
combining sequence before yielding; that limitation is shared with the
previous path.

## Direct writer PM acceptance

**Accepted and complete — 2026-10-18, Codex GPT-6 (PM).** The direct writer
implementation is commit `3e75d65` for development version `0.1.1`. The
validated run passed 1,580 Python tests, 170 vendored Rust tests/doctests, and
3 binding Rust tests. Matched benchmarks recorded a median encode ratio of
3.04× across the eight common fixtures (range 1.16×–4.47×), 1.59× for
round-trip, and 1.02× for common-fixture decode. All shared fixtures retained
byte-identical output. See the [paired benchmark report](../benchmarks/feat004/README.md)
and [native-memory probe](../benchmarks/feat004/memory_report.md) for methods,
raw data, and limitations.

At the time of the direct-writer acceptance, the mixed-profile decode slowdown
remained under investigation. Its historical record is now in
[BUG_005 history](reviews/mixed_profile_decode_history.md); the native-reader
profile below supersedes it for the current implementation without identifying
the former cause.

The scalar/header primitives are written against `std::io::Write` internally,
with the current `Vec` as the sink. A future `dump(obj, file/socket)` API would
need separate design for partial writes and I/O errors; canonical maps still
need staging, callback-mutated lists need final-count handling, and a raw
bytearray borrow must never span a Python writer callback, blocking I/O, or a
GIL release. Current `dumps()` is not a streaming API. Threading and
vectorization are deferred; consider them only if profiling isolates a
substantial Rust-owned payload phase.

## FEAT_008 bounded encoding optimization PM acceptance

**Accepted and complete — 2026-11-02, Codex GPT-6 (PM).** The selected v2
staging-map change uses one `BTreeMap::entry(encoded_key)` lookup per Python
dictionary entry. It preserves canonical key ordering, last-normalized-key
wins for Python `dict`, `CBORMap` duplicate rejection, callback order and
single value conversion, and the existing header and key-budget accounting.
The development version remains `0.1.1`.

The v2 candidate used `src/direct_encode.rs` SHA-256
`35b5b484519f92d70b0d118b2d7e3a1c2d27c982d1fee353815a469cf1d723ba` with
baseline `src/lib.rs` SHA-256
`a9b40af8c8f8cf0a6e58407f1d9446b25057de032b42e1ae7fd15d9d22cf5621`. Its
release artifact and loaded extension both have SHA-256
`05bfff7c3a75ff67cb8f438fbd3a48fe58c53cffadd1a819eda2de0645b09025`.
Matched A/B measurements used nine alternating fresh-process pairs for each
of 14 map and control cases; input, wire, and decoded-result fingerprints
matched. Across sorted, reverse, and shuffled maps from 100 to 10,000 entries,
paired median changes (medians of per-pair candidate/baseline ratios) ranged
from −31.56% to −3.81%; 64 NFC-colliding keys had a paired median change of
−12.63%.

For one-character text `"x"`, the separately calculated baseline and
candidate medians were 109.96 ns and 117.38 ns per encode, a 7.42 ns absolute
difference. Its paired median change (median of per-pair candidate/baseline
ratios) was +7.44%, and the candidate was slower in all nine pairs. The
`False`, integer 23, and integer-boundary controls were near parity; their
paired median changes were −0.16%, −1.84%, and −0.54% respectively.
The PM accepted the measured text cost as a scoped tradeoff for these map
results. A same-artifact A/A control produced small, mixed paired median
changes, including −1.02% for `"x"`, which did not reproduce the larger v1
control slowdowns.

A bounded native-code comparison found the scalar source path and relevant
native Rust code/counts unchanged, along with a small PyO3 wrapper difference.
It did not establish a cause for the measured text increase; the increase is
recorded as a workload result without a mechanism claim. The
[optimization-cycle report](../benchmarks/optimization_cycle/README.md)
contains the per-case medians, MADs, raw samples, source/build provenance, and
capture limitations.

Validation passed 1,626 Python tests and 3 Rust library tests on 2026-11-02
with Python 3.14.7 and Rust 1.98.1. The local environment did not have the
Rust 1.90.0 toolchain pinned in CI, so that toolchain was not used for this
validation. The separate top-level immutable-`bytes` fast path was rejected:
its target byte-string timings improved, but tiny `bool` and integer-23
controls had paired median changes of about +9% to +10%. The v1 map prototype
was superseded after its `False`, integer-23, and short-text controls had
paired median slowdowns of 14% to 20%.

This acceptance covers the listed workloads and the explicit `"x"` cost; it
makes no universal performance claim. Trusted-output post-encode scan removal
remains deferred. No package version change or release was made. The separate
[BUG_007 integer-width investigation](requirements/BUG_007_integer_encode_regression.md)
remains open.

## FEAT_006 native decoder PM acceptance

**FEAT_006 accepted and complete — 2026-10-18, Codex GPT-6 (PM).** The native
wire reader and borrowed diagnostic formatter replace the vendored Rust
codec. The final release checkout passed 1,626 Python tests, 3 native Rust
unit tests, and 98 maintenance checks. A source distribution was built
without the vendor crate, extracted, and used to build a wheel in a fresh
environment; that wheel passed the same 1,626 Python tests.

The [paired native-decoder profile](../benchmarks/native_decoder/README.md)
matched input and wire fingerprints for all 24 workloads. All 24 decode
medians improved; the 10,000-entry map cases improved by 5.29–5.41×. The
profile also showed a slower `integer_width_boundaries` encode control. An
interleaved retest confirmed a 1.215× slowdown with identical input and wire
hashes; this separate follow-up is tracked as
[BUG_007](requirements/BUG_007_integer_encode_regression.md). The encode
control does not change the decoder acceptance or support a broad no-regression
claim.

The [independent differential review](reviews/native_decoder_independent_review.md)
covered 2,800 valid inputs, 7,594 mutated inputs, and 35 date cases, with no
acceptance/rejection or decoded-result mismatches. It found error-text
differences across the four reader APIs for 97 inputs containing multiple
invalid conditions; both builds rejected those inputs, with different error
precedence/details. The
[migration test inventory](reviews/native_decoder_test_migration.md) records
the prior locked vendor baseline and the retained Python coverage; its 182
vendor tests were a prior capture, not part of this release validation run.
The former mixed-profile slowdown is documented as superseded in
[BUG_005 history](reviews/mixed_profile_decode_history.md); its cause remains
unknown.
