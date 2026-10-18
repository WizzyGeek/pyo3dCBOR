# FEAT_004 paired performance evidence

**PM sign-off (2026-10-18):** the direct Python-to-bytes encoder is accepted
and complete for development `0.1.1`; see the [encoding architecture and
acceptance record](../../docs/encoding.md). The original mixed-profile decode
observation is preserved in
[BUG_005 history](../../docs/reviews/mixed_profile_decode_history.md) and was
later superseded for the current implementation by the
[paired native-decoder profile](../native_decoder/README.md), without
establishing its cause.

The raw baseline and candidate JSON, per-process samples, SVGs, and build
provenance are in [baseline](baseline/README.md) and `candidate/`. Both reports
used CPython 3.14.7, Linux x86_64, Rust/Cargo 1.98.1, the same benchmark scripts,
fixture hashes, pinned comparator versions, warmups, iteration policy, and
nine-process sampling. The old 0.1.1 extension was loaded from its isolated
wheel install; the candidate was loaded from `python/`. Each run verified that
the imported native extension SHA matched its release artifact. The two
extension hashes are recorded in their report environments.

All eight shared fixtures produced byte-identical dCBOR output before and
after the change. The wire-size report also has matching size/hash values for
every fixture and codec mode. The latency report contains 8 fixtures × 11
implementations × 3 operations × 9 independent process samples. The profile
report contains 24 matched workloads × encode/decode × 9 process samples;
input hashes, wire hashes, wire sizes, and per-case warmup/timed iteration
counts match across versions.

Across the eight common fixtures, the median of the fixture-specific dCBOR
encode median ratios (old/candidate) is 3.04×, ranging from 1.16× to 4.47×.
The corresponding median round-trip ratio is 1.59×. These summarize fixture
medians and are not a pooled speedup or a promised target. Common-fixture
decode ratios are near parity: median old/candidate 1.02×, range 0.99×–1.04×.
For the 24 targeted profile workloads, the median of the encode ratios is
2.61×. The integer-boundary, NFC-collision, nested-tree, and `CBORMap`
snapshot cases all retain identical input/output hashes; their encode ratios
are 2.00×, 2.47×, 2.65×, and 2.24× respectively.

The profile's 10,000-entry map decode case was slower in the mixed
encode/decode profile. With the default 500 timed/100 warmup base counts,
candidate decode medians were 8%–10% higher across sorted, reversed, and
shuffled inputs. A
matched reduced-round recheck (250 timed/50 warmup base counts) measured
candidate medians 25%–29% higher. These are material historical observations.
In a separate fresh-process decode-only control using the same prepared wire
bytes, the 10,000-entry median was 6.483 ms baseline versus
6.434 ms candidate (MAD 0.113 ms versus 0.044 ms); 1,000-entry map and nested
document controls were also within 1% of baseline. The decoder implementation
was not changed. The evidence points to a mixed-profile context effect as a
possibility, but does not establish a cause; do not attribute the slowdown to
the decoder or dismiss the mixed-profile result as noise.

The decode-only control used nine fresh processes per version, 10 warmup and
50 timed `loads()` calls for each prepared input. Its raw samples, exact input
wire hashes, extension fingerprints, and process IDs are in
[`recheck/decode_only.json`](recheck/decode_only.json). The default and
reduced-round profile reports retain their own raw samples and MAD values.
The separate [native-memory probe](memory_report.md) records bounded peak-RSS
comparisons and its measurement limits.

The baseline JSON records `git_worktree_dirty=true` because direct-writer
source edits were already in progress when measurements ran. Its source commit
is still the pre-encoder commit `5e22bbf`; the imported old wheel and clean
build-lock provenance are documented separately in
[`baseline/build_provenance.json`](baseline/build_provenance.json). The
benchmark JSON's run-time lock hash reflects the edited shared checkout. This
distinction is intentional and recorded rather than reporting a clean flag.
