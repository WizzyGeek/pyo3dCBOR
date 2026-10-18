# BUG_005: Mixed-profile decode slowdown history

**Status:** Superseded by the native decoder replacement (2026-10-18 paired
profile). The former implementation's slowdown remains historically observed;
its cause was not established.

The completed native decoder migration changes the architecture measured by
the original reports. The paired profile is now captured against the preserved
pre-migration package and the native candidate in
[`benchmarks/native_decoder`](../../benchmarks/native_decoder/README.md). The
native candidate is faster on every decode workload, including all three
10,000-entry map profiles. This supersedes the investigation for the current
implementation; it does not explain or causally resolve the former slowdown.

## Observed behavior

### Historical observation and disposition

The original mixed-profile observations below remain evidence about the
former vendored decoder. In the matched native-decoder profile, all 24 decode
case medians improved, and the 10,000-entry map medians improved by 5.29–5.41x.
Input and wire fingerprints match across the paired runs. The new native
decoder replaces the implementation under investigation, so this issue is
superseded for the current code. No claim is made that the prior observation
was caused by the decoder or that its cause has been identified. Raw samples,
per-case medians and MADs, and build provenance are preserved in the linked
profile report.

The 10,000-entry map `loads()` case regressed when measured inside the mixed
profile that also measures encoding. With the default 500/100 base timed and
warmup counts, candidate decode medians were 8%–10% slower across sorted,
reversed, and shuffled insertion orders. The matched reduced-round recheck
(250/50 base counts) measured 25%–29% slower. These remain material historical
observations; they were not attributed to decoder code or dismissed as noise.

A separate decode-only fresh-process control, using prepared wire bytes and no
`dumps()` in its timed or warmup path, measured 6.483 ms baseline versus
6.434 ms candidate for the 10,000-entry sorted map (MAD 0.113 ms versus
0.044 ms). The 1,000-entry map and nested-document controls were also within
1% of baseline. This contrast does not establish why the mixed-profile result
differs.

## Reproduction and provenance

Run from the repository root with the same CPython 3.14.7/Rust 1.98.1 release
environment and captured artifacts. The benchmark runner and profile fixtures
are [`benchmarks/profile.py`](../../benchmarks/profile.py) and
[`benchmarks/profile_fixtures.py`](../../benchmarks/profile_fixtures.py). The
pre-encoder wheel and build locks are described in
[`baseline/README.md`](../../benchmarks/feat004/baseline/README.md) and
[`build_provenance.json`](../../benchmarks/feat004/baseline/build_provenance.json).
The default profile raw reports are
[`baseline/profile/results.json`](../../benchmarks/feat004/baseline/profile/results.json)
and
[`candidate/profile/results.json`](../../benchmarks/feat004/candidate/profile/results.json);
the reduced-round reports are under
[`recheck/baseline/profile/results.json`](../../benchmarks/feat004/recheck/baseline/profile/results.json)
and
[`recheck/candidate/profile/results.json`](../../benchmarks/feat004/recheck/candidate/profile/results.json).

Run these four matched profile captures from the repository root. The baseline
artifact is the captured old `0.1.1` wheel; the candidate is the release
extension whose SHA is recorded in its report.

```sh
# Default profile, pre-encoder baseline.
DCBOR_PACKAGE_ROOT=/tmp/feat004-baseline/site \
DCBOR_RELEASE_ARTIFACT=/tmp/feat004-baseline/native/lib_dcbor.so \
DCBOR_PROFILE_SVG_PATH="$PWD/benchmarks/feat004/baseline/profile.svg" \
python benchmarks/profile.py --warmup 100 --rounds 500 --repetitions 9 \
  --output-dir benchmarks/feat004/baseline/profile

# Default profile, direct-encoder candidate.
DCBOR_PACKAGE_ROOT="$PWD/python" \
DCBOR_RELEASE_ARTIFACT="$PWD/target/release/lib_dcbor.so" \
DCBOR_PROFILE_SVG_PATH="$PWD/benchmarks/feat004/candidate/profile.svg" \
python benchmarks/profile.py --warmup 100 --rounds 500 --repetitions 9 \
  --output-dir benchmarks/feat004/candidate/profile

# Reduced-round recheck, pre-encoder baseline.
DCBOR_PACKAGE_ROOT=/tmp/feat004-baseline/site \
DCBOR_RELEASE_ARTIFACT=/tmp/feat004-baseline/native/lib_dcbor.so \
DCBOR_PROFILE_SVG_PATH="$PWD/benchmarks/feat004/recheck/baseline/profile.svg" \
python benchmarks/profile.py --warmup 50 --rounds 250 --repetitions 9 \
  --output-dir benchmarks/feat004/recheck/baseline/profile

# Reduced-round recheck, direct-encoder candidate.
DCBOR_PACKAGE_ROOT="$PWD/python" \
DCBOR_RELEASE_ARTIFACT="$PWD/target/release/lib_dcbor.so" \
DCBOR_PROFILE_SVG_PATH="$PWD/benchmarks/feat004/recheck/candidate/profile.svg" \
python benchmarks/profile.py --warmup 50 --rounds 250 --repetitions 9 \
  --output-dir benchmarks/feat004/recheck/candidate/profile
```

The standalone control's complete wire hashes, nine-process samples, and
extension fingerprints are preserved in
[`recheck/decode_only.json`](../../benchmarks/feat004/recheck/decode_only.json).
It records the protocol (10 warmup and 50 timed `loads()` calls per input in
each of nine fresh processes), but no standalone control runner is checked in;
do not infer a command beyond that recorded protocol.

The 10,000-entry sorted map wire is 139,723 bytes with SHA-256
`b00d8be6ee21e01910ae4c5df0d45fa4d32b0391ac231f3baa2711715bedb535`; the
1,000-entry and nested control wires are also identified by hash in the raw
report. The old extension SHA-256 is
`44a625d54b2a44f0440aead0783a3a34447231e3d68d1ed4ceeebe01a663115c`; the
candidate extension SHA-256 is
`36502b893f69ae0c7bf8b159d53099b17c7ec02446c14b5d6a3555a6a278d581`.
The historical `0.1.0` benchmark reports are not this paired baseline.

## Original resolution criteria

The original cause-focused criteria below were not met. BUG_005 is closed only
as superseded by the native decoder replacement; the historical slowdown's
cause remains unknown.

- Reproduce the mixed-profile observation with matched artifacts, fixtures,
  runtime, release settings, and raw samples, or identify a concrete defect in
  that measurement.
- Determine the cause through controlled profiling or comparison. If the
  source change contributes, fix it and rerun the matched profile; if the
  measurement context contributes, document evidence that distinguishes it.
- Preserve byte hashes and decoder correctness while investigating. Close only
  with an evidence-based explanation and follow-up comparison; do not silently
  relabel the measured slowdown as noise.
