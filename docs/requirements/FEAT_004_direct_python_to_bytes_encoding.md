# FEAT_004: Encode Python values directly to canonical bytes

**Status:** Direct writer locally implemented; 1,580 Python tests passed,
along with 170 vendored Rust tests/doctests and 3 binding Rust tests. Matched
encoding and bounded-memory evidence are recorded. Open issue: mixed-profile
10k-map decode was 8–10% slower in the default run and 25–29% in the
reduced-round recheck; decode-only control was within 1%.
Cause and feature owner sign-off remain pending. **Target:** `0.1.1` development.

## Problem

Before this change, `dumps()` built a vendored `dcbor::CBOR` tree from Python
values, serialized it, then ran preflight. Rust-core timing starts from a
prepared tree; Python timing includes conversion, so it does not isolate FFI
cost. It points to extra
conversion/tree construction as work to measure.

Encode supported values into canonical dCBOR bytes in binding Rust, without a
recursive `CBOR` tree for ordinary values. Reduce end-to-end `dumps()` work
while preserving the API, bytes, errors, and limits. No fixed speedup is
promised; agree any target with the owner after the `0.1.1` baseline.

## Expected outcome

- `dumps()` writes scalar and container values into a binding-owned output
  buffer as it visits Python values. Canonical map keys may use bounded,
  temporary encoded-byte buffers for sorting and collision resolution.
- Prefer supported borrowed `PyBytes.as_bytes()`/`PyString.to_str()` views;
  NFC/numeric encoding still transforms data, and lists/tuples require object
  traversal. For bytearray, use PyO3 0.29.2
  `with_critical_section` around length/budget checks and the immediate
  `unsafe { as_bytes() }` copy into the Rust `Vec`. While the raw slice is live,
  make no Python/PyO3 calls, callbacks, mutation, or detach; keep the thread
  attached. The guard is a no-op under the GIL and protects free-threaded builds
  (a CPython 3.13+ capability; no claim that such wheels ship). Safe `to_vec()`
  adds a payload copy; `PyBytes::new` copies the final wire too. Do not read
  object headers as payload or add buffer APIs. See the [memory research](../reviews/FEAT_004_MEMORY_ACCESS.md).
- Avoid a recursive vendored `CBOR` graph for ordinary `dumps()` encoding;
  retain vendored decoding. Support `CBORMap` and `CBORTag`; encode snapshots
  directly from frozen Rust state, without Python `keys()`/`items()` lists or a
  snapshot adapter. Leave `CBORMap` construction on the existing tree converter.
- Encoded bytes and externally visible acceptance/error behavior remain
  compatible. Speed does not justify a format or correctness tradeoff.

## Scope and constraints

Change only Rust binding `dumps()` encoding. Keep `CBORMap` construction on its
existing converter and retain vendored decoding, `loads()`, validation/diagnostic
parsing, the immutable `CBORMap` model, and the vendored dependency. Package and
version policy is out of scope.

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
   full Python suite (1,580 passed locally), writer regressions, and Rust tests:
   170 vendored tests/doctests plus 3 binding tests passed. Use independent
   wire/numeric oracles; round trips alone are insufficient.
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

Review key-buffer release, callback/reference lifetime during sorting, snapshot
and mutable-tag boundaries, and native-memory evidence. Do not weaken API or
resource guarantees.

Threading and vectorization stay on the back burner. Python traversal and
callbacks are order-sensitive, and heterogeneous sequences offer no obvious
bulk SIMD path; revisit only if profiling finds a substantial Rust-owned
payload phase where synchronization and copy costs can be measured separately.

## Research references

- [Rust-core benchmark method and limits](../../benchmarks/rust_core/README.md)
- [FEAT_004 paired benchmark evidence and open decode investigation](../../benchmarks/feat004/README.md)
- [FEAT_004 native-memory probe and its limits](../../benchmarks/feat004/memory_report.md)
- [Benchmarking overview](../benchmarks.md)
- [Prior architecture review: direct Python-to-output writer](../reviews/PERF_REVIEW.md#architecture-follow-up--2026-10-17)
- [FEAT_004 encoder research notes](../reviews/FEAT_004_ENCODER_RESEARCH.md)
- [FEAT_004 Python memory-access research](../reviews/FEAT_004_MEMORY_ACCESS.md)
- [Python API mappings, collisions, and limits](../python-api.md)
- [Allocation measurement limits and native-memory caveat](../allocation-plan.md)
- [Numeric compatibility and independent conformance checks](../reviews/SPEC_REVIEW.md)
- Source paths: `src/lib.rs`, `src/direct_encode.rs`, `src/direct_wire.rs`,
  `src/encode.rs`, `src/python_types.rs`, `src/scalars.rs`, `src/wire.rs`;
  regressions: `tests/test_direct_encoder.py`, `tests/test_numeric_oracle.py`,
  `tests/test_spec_conformance.py`, `tests/test_encoder_budget.py`,
  `tests/test_dispatch_fastpath.py`, `tests/test_key_identity.py`.
