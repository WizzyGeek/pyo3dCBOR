# Performance proposals for PM

Reviewed 2026-10-17. **Recommendation: prioritize Python dispatch and the ASCII
normalization fast path.** Independent prototypes delivered roughly 6–7× faster
float/list encoding and 3–3.5× faster ASCII-array encoding on the workloads below.
Both pass the existing 1,479 Python tests. These are useful first investments:
they remove routine work without changing the supported data model.

Queue shared-buffer serialization next. Ask the **spec reviewer** to review
delegating numeric canonicality to the patched decoder before implementing that
proposal. The **reviewer** should review the resulting implementation last.

This review adds this report and benchmark evidence. Runtime sources and the
installed extension were preserved; all experimental builds live in an isolated
temporary directory. The patches linked below are experiments for the PM to
evaluate, not applied implementation changes.

## Measured opportunities

Times are end-to-end microseconds per call from the second benchmark pass.
Speedup ranges cover the initial and second passes, each against its corresponding
baseline. Every candidate was built independently from the same baseline;
**these gains cannot be multiplied together**.

| Priority / proposal | Workload and API | Baseline µs | Prototype µs | Observed speedup |
| --- | --- | ---: | ---: | ---: |
| P1: cheaper Python dispatch | 4,096 fractional floats, `dumps` | 2,173 | 322 | 6.1–6.7× |
| P1: cheaper Python dispatch | 1,024 singleton lists, `dumps` | 967 | 137 | 6.6–7.1× |
| P1: cheaper Python dispatch | 1,024 ASCII-key dictionary entries, `dumps` | 1,005 | 513 | 2.0–2.1× |
| P1: ASCII fast path | 1,024 strings of 48 ASCII characters, `dumps` | 1,846 | 523 | 3.1–3.5× |
| P2: shared output buffer | 256 KiB byte string inside 128 arrays, `dumps` | 976 | 416 | 2.30–2.35× |
| P2: delegate numeric canonicality | 4,096 fractional floats, `validate` | 277 | 145 | 1.91× |
| P2: delegate numeric canonicality | Same float array, `loads` | 354 | 214 | 1.65× |

### 1. P1 — Avoid failed numeric probes and unnecessary datetime checks

Where: `src/lib.rs::py_to_cbor_with_budget` and
`src/scalars.rs::encode_datetime`.

After `None` and booleans, encoding tries `i64`, `u64`, and `i128` extraction
before testing floats, strings, bytes, or containers. Ordinary noninteger values
therefore take three failing extraction paths. Containers also reach a
`datetime` import, attribute lookup and instance check before their own branches.

[Prototype](benchmarks/perf_review/dispatch.patch): bypass integer extraction
for exact builtin noninteger types; bypass datetime detection for exact builtin
lists, tuples and dictionaries. Keep the existing path for subclasses and custom
objects, including their numeric protocols. Do not replace this with a blanket
`PyInt`-only acceptance rule: that could change existing `__index__` behavior.

PM case: a small binding change improves common numeric and nested-container
workloads. The 4,096-integer control stayed essentially unchanged: 160 → 157 µs
in the repeat pass. Existing tests pass, but add focused custom `__index__` and
subclass regressions before shipping; those behaviors are not established by
the benchmark fixtures.

### 2. P1 — Recognize ASCII without running Unicode normalization

Where: `src/scalars.rs::encode_text` and
`crates/dcbor/src/cbor.rs::CBOR::to_cbor_data`.

The binding normalizes Python text before key-budget accounting. Serialization
then normalizes text again, including ASCII. Text used as a key is also
serialized for the map's key cache. ASCII is already NFC, so these paths can
copy its bytes directly.

[Prototype](benchmarks/perf_review/ascii.patch): use `is_ascii()` at both
normalization points, keeping the existing normalization path for all other
text. This also improves the ASCII-key dictionary workload by 1.29–1.38×.

PM case: a narrow fast path with a clear invariant. Preserve normalization
before budget accounting, surrogate rejection, subclass string contents and
canonical collision behavior. Do not bypass normalization for arbitrary
non-ASCII text based only on it having passed through a particular constructor:
the Rust codec can construct unnormalized text through other entry points.

### 3. P2 — Serialize descendants into one output buffer

Where: `crates/dcbor/src/cbor.rs::CBOR::to_cbor_data` and
`crates/dcbor/src/map.rs::Map::cbor_data`.

Arrays and tags serialize each child into a new vector and then copy it into
the parent's vector. Deeply nested large payloads are consequently copied at
each ancestor. Map serialization additionally clones cached encoded keys and
collects all encoded key/value pairs before joining them.

[Prototype](benchmarks/perf_review/append.patch): introduce an internal append
operation, recurse into a shared vector, and append cached map-key bytes directly.
The nested-payload workload improves by about 2.3×. Encoding a 1,024-entry
`CBORMap` with array keys improves by about 1.2×. Small integer/list controls
show slight regressions in some samples, so assess the workload mix before
prioritizing this over P1.

PM case: valuable for nested documents and large payloads, with broader codec
maintenance cost. The prototype still allocates small headers and scalar
encodings; it is not an allocation-free encoder. It leaves key caches and their
budget checks intact. Update `crates/dcbor/PATCHES.md` if adopted.

### 4. P2 — Stop reserializing every float during preflight

Where: `src/wire.rs::preflight_key_cache_bytes`, major type 7;
`crates/dcbor/src/decode.rs` and `crates/dcbor/src/float.rs`.

Preflight converts each float payload to `f64`, creates a `CBOR`, serializes it,
and compares the resulting bytes. Reader APIs then run the decoder's own
preferred-width/reduction/NaN checks. The local numeric patch now uses the
chosen reduction interval consistently, unlike the original dependency behavior
described in `SPEC_REVIEW.md`.

[Prototype](benchmarks/perf_review/numeric_preflight.patch): delegate numeric
canonicality to the patched decoder. Keep the structural preflight, depth bound,
aggregate key-cache bound, and truncation checks. `dumps` still emits canonical
numbers through the serializer. The full Python suite, including exhaustive
binary16 conformance and the negative-boundary regressions, passes.

PM case: approximately 1.9× faster validation and 1.65× faster decoding for the
float-array workload, with little implementation volume. **Spec review focus:**
verify rejection before reduction for all three float
widths and all reader APIs. Do not delete preflight wholesale. Error wording
can change when the decoder becomes the rejecting layer. A production patch
should also remove the now-unused half-float conversion helper/import.

## Experiments to defer

- [Combined ownership cleanup](benchmarks/perf_review/ownership.patch): remove
  redundant byte-input copying and clones in owned map/string conversion.
  **Not acceptable as tested: 1,476 passed, three failed.** All three
  `test_nfc_expanding_shared_siblings_fail_before_allocator_abort` cases abort
  with a failed 4 MiB allocation under their address-space ceiling, instead of
  returning `CBORError`. A focused rerun reproduces the failures; the baseline
  passes all three. The exact allocator/lifetime cause is unresolved. Split
  this experiment and investigate before reconsidering it.
- [Isolated byte-input cleanup](benchmarks/perf_review/bytes_only.patch): the
  baseline copies the Python slice into a vector, copies it in `ByteString::new`,
  then copies it again through `From<ByteString>` / `to_byte_string`. Directly
  constructing the byte-string case removes those two extra input copies and
  passes all 1,479 tests, but the exploratory 1 MiB `dumps` measurement worsens
  from 1,235 to 2,587 µs. The 256 KiB case is essentially unchanged. Fewer copies
  did not establish an end-to-end speedup; no allocator explanation is proven.

## Evidence and limits

- Fresh offline release builds with the existing `lto = true`, CPython 3.14.7
  with the GIL enabled, Rust 1.98.1, Linux x86-64, AMD Ryzen 7 7435HS.
- Baseline and all four recommended prototypes independently pass **1,479
  Python tests**. The ASCII and shared-buffer prototypes also run the vendored
  Rust suite with the production `multithreaded` feature: **180 tests pass for
  each**, including 92 doctests. Results are recorded alongside the benchmark data.
- [Runner](benchmarks/perf_review.py): standard library only; warmed calls,
  adaptive batch lengths targeting 15 ms, seven timed batches, GC disabled
  during timed batches. Destruction of returned values is included. Fixture
  construction is excluded; `CBORMap` construction is measured separately.
- [Raw measurements and source fingerprints](benchmarks/perf_review/results.json)
  include every workload, samples, controls, extension hashes, test outcomes,
  and rejected experiments. All **132 fixture/run wire hashes** agree.
- Two benchmark passes support the recommended gains. These are single-process
  synthetic workloads on one machine, without CPU affinity, allocation/RSS
  profiling or a customer workload distribution. Repeated fixture strings
  share Python objects. No combined-candidate or concurrency result is claimed.
  Initial baseline decomposed-Unicode encoding varied from 4,721 to 3,048 µs
  on repeat; do not count that difference as an optimization win.

## Reproduce and acceptance criteria

Copy the current source snapshot to a temporary directory. Build the baseline
there, then apply **one** experimental patch to a fresh copy of that snapshot
and rebuild. Do not stack these patches for the individual comparisons above.
Example, run from the repository root:

```sh
review_root="$PWD"
perf_lab=$(mktemp -d /tmp/dcbor-perf.XXXXXX)
cp -a Cargo.toml Cargo.lock src crates "$perf_lab/"
# For a candidate, apply its patch here before building:
# (cd "$perf_lab" && patch -p1 < "$review_root/benchmarks/perf_review/ascii.patch")
PYO3_PYTHON="$review_root/.venv/bin/python" cargo build --release --offline \
  --manifest-path "$perf_lab/Cargo.toml" --target-dir "$perf_lab/target"
.venv/bin/python benchmarks/perf_review.py \
  --extension "$perf_lab/target/release/lib_dcbor.so" \
  --label baseline --output "$perf_lab/results.json"
```

Before shipping, compare repeated release benchmarks against the same source
baseline and verify the intended workloads and controls. Rebuild and run the
entire Python suite, including subprocess memory/depth tests, plus the vendored
Rust suite for codec changes. Keep canonical bytes, key identity, eager invalid
date rejection and snapshot isolation unchanged. Add the focused dispatch
regressions, document adopted vendor changes, and benchmark the combined result
after implementation. Route proposal 4 through the spec reviewer, then send the
final implementation and evidence to the reviewer.
