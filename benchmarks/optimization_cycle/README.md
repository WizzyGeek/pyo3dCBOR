# Optimization cycle evidence

## Decision state

- **Single staging-map lookup, v2:** accepted on 2026-11-02. Across the
  measured map cases, paired median changes range from −31.56% to −3.81%;
  64 NFC-colliding keys have a paired median change of −12.63%. Bool and
  integer controls are near parity. The one-character text control `"x"` has
  a +7.44% paired median change (about 7 ns absolute difference) and is slower
  in all nine pairs. The PM accepted that explicit cost for the measured gains.
- **Single staging-map lookup, v1:** superseded by v2. Its isolated controls
  showed 14–20% paired median slowdowns for bool, small-integer, and short-text encoding.
  The v1 source patch is retained in [map_entry_v1.patch](map_entry_v1.patch).
- **Top-level immutable-bytes fast path:** rejected. The large-byte gains came
  with repeatable costs on tiny scalar encodes. Its source delta is retained in
  [rejected_bytes_fastpath.patch](rejected_bytes_fastpath.patch), and its raw
  measurements remain in [bytes_only_20261019.json](bytes_only_20261019.json).
- **Combined capture:** diagnostic only. Its 1 MiB byte timings were bimodal by
  workload position, so do not use them for a speedup claim. No 16x headline is
  supported by these captures.

These decisions apply to the listed workloads and controls. They do not claim
that the library is globally fastest or has no regressions outside the tested
cases.

## Isolated results

The focused captures began on 2026-10-19 in Asia/Kolkata (2026-10-18 UTC) and
used nine alternating baseline/candidate fresh-process pairs per case. Setup,
fixture construction, correctness checks, and warmups were outside the timed
operation loop. Every retained focused pair had matching input, wire, and
decoded-result fingerprints, and the loaded extension hash matched the
selected release artifact.

The map-only candidate used `src/direct_encode.rs` SHA-256
`db615c8188323158ce207568b04334c2c97ae694e2bb55cdf036a09fcba7a9fd` with
baseline `src/lib.rs` SHA-256
`a9b40af8c8f8cf0a6e58407f1d9446b25057de032b42e1ae7fd15d9d22cf5621`. Its
artifact SHA-256 is
`096b3dd665b49dad205f1e2a6d784998f9ef06e29cbc71b79826e965b89f9f29`.

| Map workload | Baseline median | Candidate median | Paired median change (median ratio) | MAD of paired change |
| --- | ---: | ---: | ---: | ---: |
| 10k sorted, 100 encodes | 3.189 ms | 2.225 ms | −30.31% | 0.42% |
| 10k shuffled, 100 encodes | 4.228 ms | 3.098 ms | −25.27% | 3.03% |
| 10k reverse, 100 encodes | 1.710 ms | 1.591 ms | −7.59% | 1.32% |
| 64 NFC-colliding keys, 500 encodes | 46.17 µs | 39.43 µs | −13.60% | 0.99% |

An isolated follow-up on 2026-11-01 rebuilt the baseline from source HEAD
`b3771f6397d757147ad4c47d606bfc5e142e5c32`. Its release artifact matched the
archived baseline SHA-256
`ca06f077c3ca1f2a72270b06d5799bc851a7612dec4728e6407839fe95aa1a94`; Cargo
dep-info named only the temporary source snapshot. The map-only v1 candidate
artifact was copied from the source owner's final build and matched the hash
above. The raw capture has 90 alternating pairs across six map cases
and four controls; all fingerprints and artifact checks passed.

| Map workload | Baseline median | Candidate median | Paired median change (median ratio) | MAD of paired change |
| --- | ---: | ---: | ---: | ---: |
| 100 sorted, 500 encodes | 20.71 µs | 17.00 µs | −18.11% | 0.23% |
| 100 shuffled, 500 encodes | 20.81 µs | 16.47 µs | −21.20% | 0.39% |
| 100 reverse, 500 encodes | 15.35 µs | 14.96 µs | −1.31% | 0.63% |
| 1k sorted, 100 encodes | 276.50 µs | 208.37 µs | −24.82% | 0.18% |
| 1k shuffled, 100 encodes | 301.67 µs | 233.04 µs | −22.78% | 0.36% |
| 1k reverse, 100 encodes | 164.29 µs | 155.80 µs | −5.27% | 1.13% |

| Non-target control | Baseline median | Candidate median | Paired median change (median ratio) | MAD of paired change | Candidate slower pairs |
| --- | ---: | ---: | ---: | ---: | ---: |
| `False` encode | 85.12 ns | 97.43 ns | +14.04% | 2.88% | 8 / 9 |
| integer 23 encode | 91.91 ns | 110.76 ns | +20.03% | 2.04% | 9 / 9 |
| short-text (`"x"`) encode | 111.14 ns | 132.59 ns | +19.21% | 0.62% | 9 / 9 |
| integer-boundary encode | 19.97 µs | 19.81 µs | −1.22% | 0.95% | 2 / 9 |

The v1 map gains were robust for sorted and shuffled inputs, but the scalar
and short-text costs failed the non-target regression screen. These results
are historical evidence for the superseded v1 artifact; the source diff alone
does not establish a mechanism for those costs.

Before timing the v2 refactor, a same-artifact A/A control ran from
2026-11-01 18:35:08 UTC through 18:35:14 UTC (2026-11-02 in Asia/Kolkata).
Both role packages loaded the original baseline extension and
artifact SHA-256
`ca06f077c3ca1f2a72270b06d5799bc851a7612dec4728e6407839fe95aa1a94`; the
capture makes no candidate source-variant claim. It completed 36 pairs across
the same four controls with matching fingerprints and alternating role order.

| A/A control | Baseline-labeled median | Candidate-labeled median | Paired median change (median ratio) | MAD of paired change | Candidate-labeled role slower pairs |
| --- | ---: | ---: | ---: | ---: | ---: |
| `False` encode | 86.23 ns | 86.18 ns | +1.63% | 1.62% | 5 / 9 |
| integer 23 encode | 93.39 ns | 91.62 ns | −3.44% | 1.10% | 3 / 9 |
| one-character text (`"x"`) encode | 113.14 ns | 110.13 ns | −1.02% | 1.10% | 1 / 9 |
| integer-boundary encode | 19.95 µs | 19.77 µs | −0.46% | 0.37% | 1 / 9 |

The A/A differences are small and mixed; the same-artifact role/path setup
does not account for the 14–20% v1 paired median scalar and short-text
slowdowns. The v2
implementation passed 1,626 Python tests and 3 Rust library tests on
2026-11-02. Validation used Rust 1.98.1; the Rust 1.90.0 toolchain pinned in
CI was unavailable locally. Its A/B timing is recorded below. The A/A capture
and manifest are
[aa_controls_20261102.json](aa_controls_20261102.json) and
[aa_controls_manifest_20261102.json](aa_controls_manifest_20261102.json).

The v2 capture ran from 2026-11-01 18:37:37 UTC through 18:38:15 UTC
(2026-11-02 in Asia/Kolkata). It used fixed source mappings supplied by the
build owner.
Baseline `direct_encode.rs` SHA-256 is
`0a2b5aed802b510553dc8308be641b2fe03c73fbad3debfd4998a6abb82aba5b`; baseline
and candidate `lib.rs` SHA-256 is
`a9b40af8c8f8cf0a6e58407f1d9446b25057de032b42e1ae7fd15d9d22cf5621`.
Candidate `direct_encode.rs` SHA-256 is
`35b5b484519f92d70b0d118b2d7e3a1c2d27c982d1fee353815a469cf1d723ba`.
Baseline and candidate artifact SHA-256 are
`ca06f077c3ca1f2a72270b06d5799bc851a7612dec4728e6407839fe95aa1a94` and
`05bfff7c3a75ff67cb8f438fbd3a48fe58c53cffadd1a819eda2de0645b09025`. The
driver asserted both hashes before launching workers and did not derive source
identity from the live checkout. It completed 126 alternating pairs; all
fingerprints and artifact checks matched.

| Map workload | Paired median change (median ratio) | MAD of paired change |
| --- | ---: | ---: |
| 100 sorted, 500 encodes | −20.29% | 0.27% |
| 100 shuffled, 500 encodes | −18.36% | 0.59% |
| 100 reverse, 500 encodes | −3.81% | 0.95% |
| 1k sorted, 100 encodes | −28.91% | 0.57% |
| 1k shuffled, 100 encodes | −24.29% | 0.50% |
| 1k reverse, 100 encodes | −5.94% | 0.87% |
| 10k sorted, 100 encodes | −31.56% | 0.14% |
| 10k shuffled, 100 encodes | −26.02% | 0.59% |
| 10k reverse, 100 encodes | −7.22% | 0.48% |
| 64 NFC-colliding keys, 500 encodes | −12.63% | 0.44% |

| Non-target control | Paired median change (median ratio) | MAD of paired change | Candidate slower pairs |
| --- | ---: | ---: | ---: |
| `False` encode | −0.16% | 0.73% | 4 / 9 |
| integer 23 encode | −1.84% | 2.06% | 3 / 9 |
| one-character text (`"x"`) encode | +7.44% | 0.64% | 9 / 9 |
| integer-boundary encode | −0.54% | 1.63% | 2 / 9 |

The v2 map gains appear in every map workload shown. Bool and integer controls
are near parity. For short-text encode of `"x"`, the separately calculated
baseline and candidate medians were 109.96 ns and 117.38 ns, a 7.42 ns
absolute difference. Its paired median change (median of per-pair
candidate/baseline ratios) was +7.44%, and the candidate was slower in all
nine pairs. PM accepted v2 with that tradeoff. A bounded native-code
comparison found the scalar source path and relevant native Rust code/counts
unchanged, along with a small PyO3 wrapper difference. It did not establish a
cause for the measured text increase. Full per-case timing samples are in
[map_v2_20261102.json](map_v2_20261102.json); its source, package, and run
manifest is [map_v2_manifest_20261102.json](map_v2_manifest_20261102.json), and
the exact driver is [paired_bench_map_v2_20261102.py](paired_bench_map_v2_20261102.py).

The bytes-only capture used the isolated bytes candidate recorded in
`variant_manifest_20261019.json`. It measured 1 KiB, 64 KiB, and 1 MiB top-level
bytes with paired median changes of −37.48%, −49.09%, and −51.32%, respectively.
The same capture found paired median changes of about +10% for `False` and
`True` encodes and about +9% for integer 23.
Those controls motivated rejection of the exact-bytes path. Other unexplained
telemetry changes in that capture are not treated as causal evidence.

## Provenance and retained files

The focused JSONs originally recorded `candidate_source_sha256` from the
shared checkout after both experiments, rather than from the isolated source
variant used by each artifact. The corrected field now names the actual
variant, and the original shared-checkout values remain under
`candidate_source_sha256_at_capture_root_checkout`. The raw timing samples and
worker artifact hashes were not changed. The correction basis is recorded in
`variant_manifest_20261019.json`.

The old `/tmp/dcbor-opt-cycle-3w27af12` and
`/tmp/dcbor-opt-variants-fnb_gqq0` directories are historical paths and are no
longer present. The 2026-11-01 baseline reconstruction and copied candidate
paths are also temporary. Their source, build, dep-info, and artifact hashes
are recorded in [map_medium_manifest_20261101.json](map_medium_manifest_20261101.json).
The medium raw samples and full per-case summaries are in
[map_medium_20261101.json](map_medium_20261101.json); the exact helper and hash
are in [paired_bench_medium_map_20261101.py](paired_bench_medium_map_20261101.py).
The original focused helper remains unchanged at SHA-256
`5abf29b98bc530ae61a2233c61f368df34880af16adc893c83c0281b45926873`.

## Repeating a focused capture

Use clean temporary source and target directories, build baseline and
candidate serially, and give each capture a new output file. The variables
below avoid dependence on the historical machine paths; `CANDIDATE_HEAD` must
identify a revision whose source files match the candidate hashes being
measured.

```sh
source .venv/bin/activate
BASELINE_HEAD=b3771f6397d757147ad4c47d606bfc5e142e5c32
CANDIDATE_HEAD=PUT_CANDIDATE_COMMIT_HERE
RUN_ROOT="$(mktemp -d /tmp/dcbor-opt-cycle-XXXXXX)"
mkdir -p "$RUN_ROOT/baseline/source" "$RUN_ROOT/candidate/source"
mkdir -p "$RUN_ROOT/baseline/wheels" "$RUN_ROOT/candidate/wheels"
mkdir -p "$RUN_ROOT/baseline/package" "$RUN_ROOT/candidate/package"
git archive "$BASELINE_HEAD" | tar -x -C "$RUN_ROOT/baseline/source"
git archive "$CANDIDATE_HEAD" | tar -x -C "$RUN_ROOT/candidate/source"

(
  cd "$RUN_ROOT/baseline/source"
  CARGO_BUILD_JOBS=2 CARGO_TARGET_DIR="$RUN_ROOT/baseline/target" \
    maturin build --release --locked --interpreter "$(command -v python)" \
    --out "$RUN_ROOT/baseline/wheels"
)
(
  cd "$RUN_ROOT/candidate/source"
  CARGO_BUILD_JOBS=2 CARGO_TARGET_DIR="$RUN_ROOT/candidate/target" \
    maturin build --release --locked --interpreter "$(command -v python)" \
    --out "$RUN_ROOT/candidate/wheels"
)
python -m zipfile -e "$RUN_ROOT/baseline/wheels/"*.whl "$RUN_ROOT/baseline/package"
python -m zipfile -e "$RUN_ROOT/candidate/wheels/"*.whl "$RUN_ROOT/candidate/package"
```

Extract each wheel to its own package root, verify that the loaded extension
matches `target/release/lib_dcbor.so`, and verify the source hashes before
timing. Run from the repository root, keep the machine otherwise idle, and
never overwrite an existing raw capture:

```sh
PYTHONDONTWRITEBYTECODE=1 python benchmarks/optimization_cycle/paired_bench_map_v2_20261102.py \
  --baseline-package "$RUN_ROOT/baseline/package" \
  --baseline-artifact "$RUN_ROOT/baseline/target/release/lib_dcbor.so" \
  --candidate-package "$RUN_ROOT/candidate/package" \
  --candidate-artifact "$RUN_ROOT/candidate/target/release/lib_dcbor.so" \
  --focus-confirm --focus-profile map_v2 --repetitions 9 \
  --output benchmarks/optimization_cycle/map_v2_rerun_20261102.json
```

The focused v2 profile contains 100, 1k, and 10k maps in sorted, reverse, and
shuffled orders, NFC-colliding keys, plus `False`, integer 23, short-text, and
integer-boundary encode controls. It records each operation's rounds and
warmups in the raw JSON. The original 10k map and bytes profiles remain
available in `paired_bench.py`; use a new output name for each run.
