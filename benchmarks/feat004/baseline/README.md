# FEAT_004 pre-encoder baseline

This is the matched `0.1.1` baseline captured before the direct-writer encoder
was built. The extension was built from source commit
`5e22bbf1c7bc3c20aa9f42109fc3d49f051a0d21` with the locked release profile,
then preserved outside the worktree and imported from the isolated wheel target
`/tmp/feat004-baseline/site`. The loaded extension and release artifact both
have SHA-256
`44a625d54b2a44f0440aead0783a3a34447231e3d68d1ed4ceeebe01a663115c`.
The wheel SHA-256 is
`4c5e6be88f78142cc9bd687d574a409713eebdb57c6ad1c64835f1d7c249dde5`.

The baseline build used CPython 3.14.7, Linux x86_64, Rust 1.98.1, Cargo
1.98.1, and the clean source commit's `Cargo.lock` SHA-256
`ed5e44be3602ff5137360274e94e80582970ef339296a7eb48d591fd7efa1057`. The
reports record the shared checkout's run-time lock hash
`3df89c5440db5ab14dd758819c4f8aac6b89b3a93be5ca1b5338305e3f5260c3`, which
includes the encoder dependency edits already in progress during measurement;
it is not the old wheel's build lock. The paired candidate must use the same
local Rust toolchain and release settings. The CI-pinned Rust 1.90 toolchain
was not available locally. See [build provenance](build_provenance.json) for
the exact artifact and both lock hashes.

`wire_size/results.json` records all eight shared fixtures and all codec wire
sizes. `latency/results.json` records eight fixtures, 11 implementations,
encode/decode/round-trip timings, nine fresh process samples per operation,
and the complete raw process records. `profile/results.json` records 24
workloads with separate encode/decode timings and nine fresh process samples:
the existing map-order, float, and Unicode cases plus explicit integer-width
boundaries, NFC-equivalent dictionary key collisions, a nested value tree, and
a 64-entry `CBORMap` snapshot. Each profile descriptor retains input and wire
hashes, encoded size, and the per-process timed/warmup iteration counts. The
10,000-entry map cases used 50 timed and 10 warmup calls per process. All
reports retain raw samples, medians, MAD, fingerprints, and source/chart
provenance. The profile SVG retains the existing map/float/Unicode panels; the
new integer, collision, nested, and `CBORMap` cases are present in the JSON
report and raw samples but are not plotted by that existing renderer.

The report source commit is the pre-encoder commit above. The worktree dirty
flag is `true`: encoder source edits were in progress in the shared checkout
while timing ran. The benchmark imported the separately captured old wheel,
not the editable source package, and every report verifies the same extension
and artifact SHA. Historical `0.1.0` benchmark reports were left unchanged.

The wheel and copied release artifact live under `/tmp/feat004-baseline` for
local paired runs; they are not generated repository artifacts. Set
`DCBOR_PACKAGE_ROOT=/tmp/feat004-baseline/site`,
`DCBOR_RELEASE_ARTIFACT=/tmp/feat004-baseline/native/lib_dcbor.so`, and
`DCBOR_BENCHMARK_ARTIFACT_DIR=$PWD/benchmarks/feat004/baseline` to reproduce
the baseline runner inputs. Use the same commands with the candidate wheel and
an output directory under `benchmarks/feat004/candidate` for the paired run.
