# dCBOR specification and test review

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
