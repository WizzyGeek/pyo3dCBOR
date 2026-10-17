# dCBOR specification and test review

## PM implementation resolution — 2026-10-17

Both follow-ups from the current-tree review are resolved in `dfe96bd`.

The binding now delegates numeric canonicality to the pinned decoder while
retaining its structural/truncation scan, complete-input check, depth limit,
map-count overflow check, and aggregate key-cache limit. The decoder validates
the original binary16, binary32, or binary64 payload before converting or
reducing it. The production release passed **1,558 Python tests**, including
the independent 113,184-pattern numeric coverage described below; the later
combined checkout passed **1,560 Python tests**.

The inherited Rust extraction bug is fixed separately. Negative major-type-1
arguments are converted to their signed `-1 - n` value in `i128` before exact
`f32`/`f64` cast-back checks. Direct tests cover `-1`, `-2`, `-17`, the
binary32 and binary64 consecutive-integer boundaries, and the explicit
`-2**64` endpoint. `crates/dcbor/PATCHES.md` records this additional divergence
from published `dcbor` 0.25.2. The vendored codec passes **90 unit/integration
tests and 92 doctests (182 total)** with the production feature set.

Independent post-implementation audit found no blocking issue and confirmed
that all four Python reader APIs still pass through structural preflight and
the patched decoder. The numeric-preflight delegation and Rust extraction
finding are closed.

## Current-tree and performance proposal review — 2026-10-17

**The reviewed Python wire-format changes pass. Numeric-preflight delegation
is approved from a specification perspective, with the structural/resource
checks retained. One inherited Rust extraction API defect was found separately.**

Read `PERF_REVIEW.md`, the current binding sources, the vendored float/ASCII
changes and provenance, the new regression tests, and the packaging/CI files.
Compared the vendor's `src/` and `tests/` files directly with the cached published
`dcbor-0.25.2.crate`: the only differences are `src/float.rs`, `src/cbor.rs`,
and `tests/encode.rs`, consistent with `crates/dcbor/PATCHES.md`.

### Verified current implementation

- The installed build and a fresh isolated release build each passed the original
  **1,556 Python tests**. The independently built release binary has the same
  SHA-256 as the installed extension:
  `f2e7962974826f267cf78b551db06b46016ed347aa130866212a1469e121ef97`.
- Added only `tests/test_numeric_oracle.py`, with two parameterized tests checking
  **47,648 binary32/binary64 patterns** against Python `struct` and independent
  integer serialization. Every exponent field and both signs are covered with
  six boundary significands, plus 10,000 seeded patterns per width. These check
  exact encoding, decoded numeric type/value, diagnostics and rejection of
  nonpreferred raw inputs on all four reader APIs. Together with the existing
  exhaustive binary16 test, this covers **113,184 IEEE patterns**.
- The expanded current Python suite passed: **1,558 passed in 8.73 seconds**.
- The vendored codec passed **89 unit/integration tests and 92 doctests** with
  the production `multithreaded` feature, **181 total**. An initial doctest run
  encountered temporary-filesystem quota errors; rerunning the doctests with a
  workspace-backed temporary directory and one test thread passed all 92.
- Built an sdist from the isolated current snapshot, checked hashes of all 60
  required runtime-source/test/license/provenance files, and confirmed that it
  contains no extension binaries or Python bytecode. Built a release wheel from
  the extracted sdist, loaded it from a separate package directory, and passed
  the expanded **1,558-test suite in 8.98 seconds** against that wheel.
- Package version validation passed. No runtime source or dependency-config
  changes occurred in the shared checkout during these checks.

The exact-builtin dispatch preserves the pre-existing subclass/custom numeric
protocol path. ASCII is already NFC; ordinary conversion, active-key accounting
and vendored serialization retain the non-ASCII normalization path. The bounded
text reuse cache holds a reference to immutable Python string storage and charges
each encoded occurrence. Composite lookup probes now enter an active key context.
The relevant identity, normalization, depth, replacement and memory-limit tests
all passed. No new Python conformance regression was identified in those changes.

These are local CPython 3.14/Linux checks. The proposed cross-platform CI matrix
was inspected but was not executed by this reviewer. No new performance speedup
claim is made here; performance measurements remain in `PERF_REVIEW.md`.

### Response to performance proposal 4

Applied `benchmarks/perf_review/numeric_preflight.patch` only to the isolated
snapshot. The candidate passed **1,558 Python tests in 9.43 seconds**, including
the independent numeric oracle and the existing exhaustive binary16 test.

The source-level reason delegation is safe is specific: `decode_cbor_internal`
calls `validate_canonical_f16`, `validate_canonical_f32` or
`validate_canonical_f64` on the original payload **before** converting that
payload into a `CBOR`. The patched validators reject integral values within the
chosen reduction interval, wider-than-needed encodings and noncanonical NaNs.
For binary16, the NaN check also preserves the exact required payload bits.
All four public readers call this decoder after structural preflight.

The production change may remove the per-float construction/serialization
comparison. Keep argument/truncation parsing, container/map-count overflow
checks, depth enforcement, aggregate key-cache accounting and complete-input
checks. Retain the pinned patched codec and the conformance tests. Remove the
unused `dcbor::CBOR` import, `half_to_f64` helper and `start` local as part of the
implementation; the experimental patch leaves those behind. Rejection wording
can change when the decoder becomes the rejecting layer.

This is approval to proceed with that narrow optimization. It is not an
implementation change: shared `src/wire.rs` and the installed extension were
left unchanged by this review.

### Separate finding: inherited Rust negative-integer extraction defect

The public Rust `TryFrom<CBOR>` floating extraction paths have an inherited
correctness defect in `crates/dcbor/src/float.rs`:

- Lines 161–163: converting `CBORCase::Negative(n)` to `f32` returns the positive
  encoded magnitude `n`, omitting CBOR's `-1 - n` transformation. A compiled
  standalone probe returns `Ok(0.0)` for integer `-1`, `Ok(1.0)` for `-2`, and
  `Ok(16.0)` for `-17`.
- Lines 106–108: `f64` extraction first requires the encoded magnitude to be
  exactly representable as `f64`. This incorrectly returns `OutOfRange` for
  integer `-9007199254740994` (`-(2**53 + 2)`), although the signed integer itself
  is exactly representable. Its encoded magnitude, `9007199254740993`, is not.

Both conversion implementations are byte-for-byte unchanged from the published
crate. This is not introduced by the local reduction/ASCII patch, and Python's
decoder reads negative integers directly instead of calling these traits.
It therefore does not invalidate the Python test results or the delegation
approval. It is a separate Rust API follow-up for the developing agent.

Suggested regression assertions for the vendored Rust suite:

```rust
assert_eq!(f32::try_from(CBOR::from(-1i64)).unwrap(), -1.0);
assert_eq!(f32::try_from(CBOR::from(-2i64)).unwrap(), -2.0);
assert_eq!(f32::try_from(CBOR::from(-17i64)).unwrap(), -17.0);
assert_eq!(
    f64::try_from(CBOR::from(-9_007_199_254_740_994i64)).unwrap(),
    -9_007_199_254_740_994.0,
);
```

Convert the actual signed integer in integer arithmetic before testing whether
it is exactly representable in the requested floating type. Do not make the
encoded unsigned magnitude the representability criterion. No runtime fix was
applied as part of this independent review.

### Copyable current handoff

```text
Current Python wire paths pass independent review: 1,558 Python tests and
181 vendored Rust tests pass, and a release wheel rebuilt from the sdist passes
the same expanded Python suite. Added test_numeric_oracle.py checks 47,648
binary32/binary64 patterns independently; existing binary16 coverage remains.

Spec review approves numeric-preflight delegation to the patched decoder.
The isolated proposal passes all 1,558 tests. Keep structural/depth/key-cache
checks, the pinned patched codec and conformance tests; remove the unused CBOR
import, half_to_f64 helper and start local. Production wire.rs is unchanged.

Separate inherited Rust API bug: f32::try_from(CBOR::from(-1i64)) returns 0.0
(-2 returns 1.0), and f64 extraction rejects exact integer -(2**53 + 2).
These TryFrom implementations are unchanged upstream and unused by the Python
decoder. Please fix them separately with direct Rust regression tests and
record the additional vendor change in PATCHES.md. Details in SPEC_REVIEW.md.
```

## Independent reviewer follow-up — 2026-10-17

Read the PM resolution, the patched `crates/dcbor/src/float.rs`,
`crates/dcbor/PATCHES.md`, the numeric compatibility policy in the README,
and the added numeric-boundary and timezone-isolation tests.

The original float-reduction finding and timezone-test isolation issue are
resolved in the reviewed state. The shared reduction helper applies the
specified interval before integer conversion, computes negative magnitudes
in integer arithmetic, and is used consistently by float construction,
serialization and canonical validation. The independent conformance tests
remain active and now pass.

Verification rerun by this reviewer:

- `.venv/bin/python -m pytest -q`: **1,479 passed in 7.15 seconds**.
- `cargo test --manifest-path crates/dcbor/Cargo.toml --offline --quiet`:
  **180 passed**, including 92 doctests.
- An additional independent numeric check passed for **20,000 patterns**:
  10,000 binary32 and 10,000 binary64 payloads generated with Python
  `random.Random(20261017)`. Expected bytes were computed using integer
  arithmetic and `struct`'s exact-width IEEE packing, independently of the
  patched Rust codec. Encoding, decoding, validation, both diagnostics and
  rejection of nonpreferred raw encodings agreed with that oracle.
- The installed Python extension was newer than all checked runtime Rust
  sources in `src/` and `crates/dcbor/src/`.

These reruns verify the installed Python build and the Rust test suite;
the PM's separate debug/release and distribution-build checks are reported
in the resolution below. No further tests or implementation edits were
needed for this follow-up.

The explicit-integer range is now an acknowledged compatibility policy,
with the Appendix A discrepancy disclosed in the README. That resolves
the request to select and document a policy; it does not resolve the
underlying specification ambiguity. No new blocking specification finding
was identified in this follow-up.

## PM resolution — 2026-10-17

The findings below describe the original reviewed state. The numeric mismatch
has now been fixed in a locally included `dcbor` 0.25.2 codec; provenance and
the narrow runtime patch are documented in `crates/dcbor/PATCHES.md`.
Construction, serialization, validation, map keys, and diagnostics share the
draft-18 float-reduction interval `[-2**63, 2**64)`. The timezone test restores
both the original `TZ` environment and the process timezone state.

Compatibility decision: explicit integer values retain the documented CBOR
range `[-2**64, 2**64-1]`. The Appendix A integer-only ambiguity is documented
in the README; no change to this existing API is implied by the float fix.

Verification: **1,479 Python tests pass in both debug and release**, including
all independent conformance cases and the additional numeric/map-key and
timezone regressions. The included Rust codec passes **180 tests**, including
doctests, after updating four float fixtures to the chosen reduction rule.
Source-distribution inspection confirmed that the patched codec, license,
and provenance are included, and a wheel was built from the extracted sdist.

The remainder of this document is the independent review preserved as history.

Reviewed on 2026-10-17 against [draft-mcnally-deterministic-cbor-18](https://datatracker.ietf.org/doc/html/draft-mcnally-deterministic-cbor-18), especially sections 2.1–2.7 and Appendix A, and [RFC 8949](https://www.rfc-editor.org/rfc/rfc8949.html), especially sections 3.1, 4.1 and 4.2.1. This is a review against a pinned Internet-Draft, not a claim that dCBOR is a published RFC.

## Outcome

The pre-existing suite passed: **409 passed**. It provides substantial regression coverage for the Python bindings and their resource limits, but does not establish complete specification conformance.

Added `tests/test_spec_conformance.py`: **998 collected cases**, including one test that checks every binary16 bit pattern against an independent IEEE-754 oracle. Full suite result: **35 failed, 1372 passed in 2.27 seconds**. Every failure concerns the same negative floating-point reduction boundary. Failures remain ordinary assertions rather than skips or expected failures so that the developing agent can use them as acceptance criteria.

Only this report and the new test file were added by this review. Existing implementation and test files were left unchanged. The installed extension was newer than every Rust source file at review time; the results were not from an obviously stale build. `git diff --check` passed.

## 1. Confirmed mismatch with normative section 2.5

Section 2.5 limits float-to-integer reduction to `[-2**63, 2**64 - 1]`. Floats outside that interval must retain floating-point encoding, using the smallest exact width.

Current behavior reduces negative floats all the way down to `-2**64`. It consequently emits different bytes from the draft and rejects valid draft encodings on all four reader APIs (`loads`, `validate`, `diagnostic`, `diagnostic_flat`).

| Python float | Required wire hex | Current `dumps()` wire hex |
| --- | --- | --- |
| `math.nextafter(-float(2**63), -math.inf)` | `fbc3e0000000000001` | `3b80000000000007ff` |
| `-18446742974197924000.0` | `fadf7fffff` | `3bfffffeffffffffff` |
| `-float(2**64)` | `fadf800000` | `3bffffffffffffffff` |

The middle row is also an explicit positive test vector in draft-18 Appendix A, Table 3. Python's decimal literal denotes the exact float `-18446742974197923840`; the expected single-precision bits express that same value.

Minimal reproduction:

```python
import dcbor

assert dcbor.dumps(-float(2**64)).hex() == "fadf800000"  # currently fails
assert dcbor.loads(bytes.fromhex("fadf800000")) == -float(2**64)  # currently raises
```

The relevant local paths are `src/lib.rs`'s `PyFloat` conversion and `src/wire.rs`'s comparison with `CBOR::from(number).to_cbor_data()`. Both rely on the same upstream conversion behavior.

The locally installed `dcbor` 0.25.2 source deliberately supports the wider reduction interval: its `src/float.rs` converts negative `f64` through `i128` and an unsigned magnitude, and its `tests/encode.rs` explicitly expects the larger negative values to become integers. This is a mismatch between the pinned draft and the dependency's tested behavior, rather than evidence that only this binding introduced the rule.

A fix must address encoding, preflight, upstream decoding, map-key serialization, and diagnostics consistently. Simply relaxing preflight is insufficient: upstream decoding converts float payloads again, and upstream serialization can reduce a `Simple::Float` again. Preserve the existing guards against malformed input and incorrectly reduced floats.

## 2. Integer range needs a specification decision

`tests/test_dcbor.py::test_integer_extreme_range` requires the integer `-2**64` to work, matching the README and full CBOR major-type-1 range. However, draft-18 Appendix A, Table 4 lists `3b8000000000000000` and `3bffffffffffffffff` as invalid. Current readers accept both.

The normative section 2.5 states the reduction interval for floating-point inputs, without an equivalent explicit prohibition on already-integer major-type-1 values below `-2**63`. Section 3 also describes `number` as covering the full basic CBOR numeric space. Therefore the draft is internally unclear about those integer encodings.

Do not conflate this ambiguity with finding 1: the required encoding of floats outside the reduction interval is explicit. No new tests impose either interpretation of the disputed integer-only boundary. The PM should pin the intended compatibility target and clarify this point with the specification maintainers before changing the documented integer API or its existing tests.

## Existing test quality

- Existing literal integer, byte/string, boolean, array and map vectors have correct expected encodings. NaN and infinity canonicalization vectors are correct. Rejection vectors in `test_wire_safety.py` are consistent with the normative reduction and preferred-width rules.
- `test_canonical_float_encodings_remain_accepted` uses `reader(dumps(number))`. This checks agreement between two paths sharing an implementation, and misses finding 1, including its `-float(2**64)` case. Keep it as a smoke test; use independent literal wire inputs for conformance.
- `test_map_int_keys_sort_by_encoding_not_value` only uses positive integers, whose preferred encodings sort in numeric order. Its assertion is correct, but cannot distinguish numeric sorting, bytewise sorting and length-first sorting. The added mixed-sign vector `a21818002001` distinguishes the latter two and confirms the current implementation is correct there.
- `test_same_value_always_encodes_identically` is a useful repeat-call smoke test, but proves neither equivalence across distinct Python representations nor conformance to specified bytes. Added canonical-key collision tests and numeric vectors address those gaps.
- NFC decode rejection, every forbidden simple value, both string indefinite forms, reserved additional information, invalid UTF-8, nonpreferred lengths/tags, and recursive duplicate maps lacked direct comprehensive coverage. New tests cover these independently of the encoder.
- Depth 512, map-key budget 16 MiB, Python timezone requirements, datetime conversion failures and snapshot behavior are binding policies rather than universal dCBOR limits. Their existing tests are useful; they should not be described as normative specification vectors.
- The timezone test has a small isolation flaw: it removes `TZ` and calls `tzset()` in `finally` before the monkeypatch fixture restores the original environment. If the original `TZ` was set, libc's timezone state can disagree with the restored environment for subsequent tests. Restore the previous `TZ` before the final `tzset()` (or exit a `monkeypatch.context()` before that call). This does not affect the confirmed numeric finding.

## Test additions and validation plan

The additions cover the identified gaps without changing binding policy:

1. Literal numeric wire expectations for encoding and all four reader APIs, including reduction limits, smallest subnormals, finite extrema and special values.
2. Recursive checks at the root, array element, map key, map value and tag-201 content positions.
3. Rejection of all forbidden simple values, reserved header information, indefinite items, overlong headers, malformed UTF-8, non-NFC text, unordered maps and duplicate keys.
4. A mixed-sign map-order control, tagged versus untagged key identity, canonical collisions in `CBORMap`, and NFC versus compatibility normalization.
5. Exhaustive checks of all 65,536 binary16 bit patterns. Expected integer bytes are computed independently; expected IEEE values come from Python's `struct`, not the Rust dependency.

Run after implementation changes and rebuilding the extension:

```sh
.venv/bin/python -m pytest tests/test_spec_conformance.py -q
.venv/bin/python -m pytest -q
```

No automatic implementation fix is part of this independent test-review task.

## Copyable handoff to PM / developing agent

```text
Independent dCBOR review complete against draft-mcnally-deterministic-cbor-18.
Baseline: 409 passed. Added tests/test_spec_conformance.py; full suite now has
35 failures and 1372 passes. All failures expose one normative section 2.5
mismatch: negative floats below -2**63 are reduced to integers, through -2**64.
Example: dumps(-float(2**64)) emits 3bffffffffffffffff; the draft requires
fadf800000. All four readers currently reject that valid float encoding.
dcbor 0.25.2 explicitly tests the wider behavior, so the dependency cannot serve
as an independent spec oracle. A fix must cover encoding, preflight, upstream
decoding/serialization, map keys and diagnostics, not just remove the guard.

Separate decision: Appendix A Table 4 rejects large negative integer encodings,
but the normative text does not clearly prohibit them. Existing integer-range
tests and README allow -2**64. Pin the intended target and resolve this ambiguity
before changing that API; the new tests deliberately do not enforce either side.

Please read SPEC_REVIEW.md for reproductions, affected paths, coverage gaps and
the small existing TZ-test isolation issue. I changed no implementation files
and left the conformance failures visible for the developing agent to resolve.
```
