# FEAT_004: Encode Python values directly to canonical bytes

**Status:** Accepted main-sprint direction; design/measurement under review;
implementation not started. **Development target:** `0.1.1` (development only).

## Problem

`dumps()` builds a vendored `dcbor::CBOR` tree from Python values, serializes it,
then runs preflight. Rust-core timing starts from a prepared tree; Python timing
includes conversion, so it does not isolate FFI cost. It points to extra
conversion/tree construction as work to measure.

Encode supported values into canonical dCBOR bytes in binding Rust, without a
recursive `CBOR` tree for ordinary values. Reduce end-to-end `dumps()` work
while preserving the API, bytes, errors, and limits. No fixed speedup is
promised; agree any target with the owner after the `0.1.1` baseline.

## Expected outcome

- `dumps()` writes scalar and container values into a binding-owned output
  buffer as it visits Python values. Canonical map keys may use bounded,
  temporary encoded-byte buffers for sorting and collision resolution.
- Measure supported `PyBytes.as_bytes()`/`PyString.to_str()` paths; text views
  may cache UTF-8, NFC/numbers transform, and lists/tuples still traverse objects.
  For bytearray, use PyO3 0.29.2's
  `pyo3::sync::critical_section::with_critical_section` around the scoped
  `unsafe { as_bytes() }` borrow and immediate copy into the Rust-owned output
  Vec. Use this same guard on GIL-enabled and free-threaded builds: it is a
  no-op on GIL builds and holds the object's critical section on free-threaded
  builds. Keep the closure to slice acquisition and copying only; make no
  Python/PyO3 calls, callbacks or re-entry, mutation, or detach while the slice
  is borrowed, because interpreter calls can suspend the critical section.
  This requires the current thread to remain attached. Free-threading is a
  build capability available since CPython 3.13, not a 3.15 version boundary;
  this requirement does not claim that free-threaded wheels are currently
  shipped. PyO3's safe `to_vec()` uses the same short-copy guard and returns
  owned bytes, but appending that vector adds an intermediate payload copy.
  With the current `Vec`-to-`PyBytes::new` output, also account for the final
  full-wire copy. Do not read
  headers/reference bytes as payload or add buffer APIs implicitly.
- The normal encoding path avoids constructing a recursive vendored `CBOR`
  value graph. Decoding and the vendored codec remain in place.
- Keep `CBORMap` and `CBORTag` supported. Read snapshots from frozen Rust state;
  do not materialize Python `keys()`/`items()` lists. An isolated adapter may
  serialize an existing snapshot if needed; review and measure any vendor
  encoding as a staged exception. Ordinary `dict`/array graphs must not route
  through a full `CBOR` tree; resolve the exception boundary before prototype
  acceptance.
- Encoded bytes and externally visible acceptance/error behavior remain
  compatible. Speed does not justify a format or correctness tradeoff.

## Scope and constraints

Change only `dumps()` encoding in the Rust binding. Keep vendored decoding,
`loads()`, validation/diagnostic parsing, the immutable `CBORMap` model, and the
vendored dependency. Package/version policy is out of scope.

Preserve all supported values and semantics documented in the
[Python API](../python-api.md), including:

- `None`, booleans, explicit integers `[-2**64, 2**64 - 1]`, floats, text,
  bytes/bytearray, lists/tuples, dictionaries, `CBORMap`, timezone-aware
  datetimes, and arbitrary `CBORTag` values.
- NFC text normalization, rejection of lone surrogates, and reading string
  subclass contents without invoking its `__str__`.
- Preferred float widths, reduction interval, canonical NaN, infinities, and
  signed zero. Preserve the distinction between explicit integers and floats
  outside the reduction interval; do not inherit a narrower integer policy
  from Rust spec-vector assumptions.
- Map order is lexicographic by encoded key bytes. `dict` last-entry-wins when
  distinct keys encode identically, including NFC strings and composite keys.
  `CBORMap` rejects duplicates and preserves `1` versus `True`, composite keys,
  and fresh accessors. Reclaim/compact overwritten staged bytes before
  replacement conversion (or use per-entry buffers); process callbacks once in
  insertion order.
- Explicit tags and datetime tag 1 encoding, including mutable `CBORTag`
  values, timezone checks, finite timestamps, and existing date conversion
  errors.
- Preserve integer-protocol dispatch: call custom `__index__` once per visit,
  keep subclass precedence and fallback/error behavior, and do not invoke user
  hooks again to size, sort, or emit values.
- The 512-level limit for arrays, maps, tags, datetimes, and snapshot reuse.
  Cyclic graphs must raise `CBORError` under existing depth protection.
- The 16 MiB aggregate encoded map-key budget, including nested keys at every
  containing-key level, repeated objects, normalized text, snapshots, and map
  headers. This bounds key-cache amplification, not total output/scratch memory.
  Reject before unbounded key materialization or value descent, and preserve
  discarded-key replacement accounting for all canonical `dict` collisions.
- Existing `CBORError` behavior for unsupported objects, out-of-range
  integers, invalid text, naive/invalid datetimes, depth overflow, and budget
  overflow. Callback exceptions and stateful values must retain established
  behavior.

## Acceptance criteria

1. **Canonical parity:** match current `0.1.1` output byte-for-byte across the
   full Python suite (1,569 tests at planning baseline), new writer regressions,
   and applicable vendored Rust conformance tests. Use independent wire and
   numeric oracles; round trips alone are insufficient.
2. **Compatibility:** retain API, map identity/collisions, callback count and
   fallback, datetime/error behavior, depth and key-budget boundaries. Add
   focused regressions before switching any uncovered behavior, including
   overwrite-heavy colliding maps.
3. **Early rejection:** prove the same key-budget policy: exact-boundary input
   is accepted and the first over-limit input rejected, including nested and
   repeated snapshots. A bounded-memory subprocess or equivalent must show
   rejection before retaining the offending key or converting its value;
   document whether earlier output bytes remain buffered.
   `tracemalloc` alone does not measure total Rust-side memory.
4. **Measured effect:** capture a fresh `0.1.1` baseline before implementation,
   then compare using the same fixtures, CPython, Rust toolchain, release flags,
   host, warmups, repetitions, and correctness gates. Include the shared eight
   fixtures plus numeric, NFC, map order/collision, nested, and `CBORMap` cases.
   Measure copy/temporary-allocation effects on bounded bytes/text/nested cases;
   preserve raw samples, medians/MAD, wire hashes, and fingerprints. Report
   tooling limits, regressions, and variability without an unapproved target;
   cache misses remain a hypothesis unless profiling supports them.
5. **Honest comparison:** report `dumps()` end-to-end. Keep prepared-tree Rust
   serialization separate, label tree preparation as excluded, and do not
   call the ratio isolated bridge overhead. Measure phases directly if
   attributing conversion and writing costs.
6. **Migration gate:** switch the default after parity, boundary checks, and
   matched evidence pass review. Document any `CBORMap` adapter and its cost;
   retain the old path while constructor/snapshot uses remain.

## Phases and research deliverables

1. **Baseline (before encoder work):** update benchmark guards/metadata for
   development `0.1.1`, preserve `0.1.0` reports as historical (not a paired
   baseline), and capture a clean optimized baseline with existing gates.
2. **Design review:** specify scalar/array/tag writing and map sorting,
   replacement, collision accounting, callback order, bounded key staging, and
   direct snapshot handling. Decide whether/where a `CBORMap` adapter stops and
   how budgets are checked before key retention or value descent.
3. **Incremental implementation:** add independent regressions behind the API;
   cover scalars/text, containers/tags/datetimes, then maps/snapshots. Keep a
   rollback path until each phase passes its checks.
4. **Rollout review:** collect matched release and bounded-memory evidence;
   inspect hashes, controls, regressions, and spread. Document remaining vendor
   encoder use, then switch the default after the migration gate passes.

Review questions: how key buffers are bounded/released during replacement;
whether sorting retains Python references or value bytes while callbacks run;
how snapshots and mutable tag values cross the writer boundary; and what
native-memory measurement supports any allocation claim. Do not weaken API or
resource guarantees.

## Research references

- [Rust-core benchmark method and limits](../../benchmarks/rust_core/README.md)
- [Benchmarking overview](../benchmarks.md)
- [Prior architecture review: direct Python-to-output writer](../reviews/PERF_REVIEW.md#architecture-follow-up--2026-10-17)
- [FEAT_004 encoder research notes](../reviews/FEAT_004_ENCODER_RESEARCH.md)
- [FEAT_004 Python memory-access research](../reviews/FEAT_004_MEMORY_ACCESS.md)
- [Python API mappings, collisions, and limits](../python-api.md)
- [Allocation measurement limits and native-memory caveat](../allocation-plan.md)
- [Numeric compatibility and independent conformance checks](../reviews/SPEC_REVIEW.md)
- Source paths reviewed: `src/lib.rs`, `src/encode.rs`, `src/python_types.rs`,
  `src/scalars.rs`, `src/wire.rs`; regression areas include
  `tests/test_numeric_oracle.py`, `tests/test_spec_conformance.py`,
  `tests/test_encoder_budget.py`, `tests/test_dispatch_fastpath.py`, and
  `tests/test_key_identity.py`.
