# BUG_007: Investigate integer-width encode regression

**Status:** Open performance investigation. First reproduced in the
interleaved native-decoder profile on 2026-10-18; the cause is unknown.

## Observed behavior

For the `integer_width_boundaries` encode control, nine adjacent fresh-process
baseline/candidate pairs alternated which build ran first. Each process used
100 warmup calls and 500 timed `dumps()` calls. The baseline median was
23.389 μs (MAD 0.258 μs); the native candidate median was 28.414 μs (MAD
0.216 μs), a 1.215× slowdown.

The input contains 480 integers and produces 2,435 wire bytes. Input SHA-256
`149c605090eae16a67e5354524d0abfb43c24ef2cb052e2f7f61d2e849395d08` and wire
SHA-256 `6471484050db5344b0710f65f4abfa2b5d5779ce201b69edfe9fbd2f6d99af8b`
match across both builds. This isolates a measured timing difference for one
control; it does not identify a cause or establish a broad regression.

## Expected behavior and impact

Encoding this integer workload should preserve its byte-identical output and
avoid a repeatable latency regression against the matched prior release. The
measured difference is limited to this control; the native decoder profile
reports improved decode medians across all 24 decode workloads.

## Reproduction and provenance

Run from the repository root with the preserved baseline package and matching
release artifacts available at the paths configured by the script:

```sh
python benchmarks/native_decoder/interleaved_integer.py
```

The [paired report](../../benchmarks/native_decoder/README.md) records the
method and summary. The runner is
[`interleaved_integer.py`](../../benchmarks/native_decoder/interleaved_integer.py);
the raw process samples, pair order, hashes, and extension fingerprints are in
[`interleaved_integer.json`](../../benchmarks/native_decoder/interleaved_integer.json).

## Acceptance criteria

- Reproduce or explain the paired timing difference with the recorded input,
  wire hashes, artifacts, and interleaved fresh-process protocol.
- Identify the cause before proposing a source change. If the native source
  contributes, fix it and rerun the matched control; otherwise document the
  evidence that distinguishes the measurement context.
- Preserve byte-identical output and verify the surrounding integer boundary
  and numeric compatibility cases.
