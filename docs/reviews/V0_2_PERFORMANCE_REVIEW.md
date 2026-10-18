# v0.2 native performance review

This review covers the direct Python-to-Rust encoder and Rust-to-Python decoder at runtime source `df70782` (dCBOR 0.1.1). The loaded CPython 3.14.7 release extension and `target/release/lib_dcbor.so` both match SHA-256 `ca06f077c3ca1f2a72270b06d5799bc851a7612dec4728e6407839fe95aa1a94`. No runtime code was changed. The measured opportunities below are candidates for isolated A/B work; none has a measured speedup yet.

## Confirmed opportunities

1. **Avoid reparsing bytes just emitted by `dumps`.** `dumps` encodes into a Rust `Vec`, runs `preflight_trusted_output`, then creates the Python result ([`src/lib.rs:74-84`](../../src/lib.rs#L74)). That preflight checks structure and resource bounds ([`src/wire.rs:324-345`](../../src/wire.rs#L324)); it skips canonicality checks for trusted output, but still reads every item header.

   Callgrind around 1,000 `profile:float_fractional` encodes (384 float elements, 2,307 wire bytes, SHA-256 `4aa650eb…ba172`) attributed 89,733,892 inclusive Ir to direct encoding and 43,091,000 inclusive Ir to the subsequent preflight, including 384,000 calls to `Cursor::read_header`. These are simulated instruction references, not elapsed time or hardware retired instructions. The stable uninstrumented profile median for this encode is 13,838.534 ns/op (MAD 52.016 ns/op) in [`benchmarks/profile/results.json`](../../benchmarks/profile/results.json).

   **Candidate:** carry structural and resource-limit state out of the trusted writer so it need not scan its own output again. Keep all depth, encoded-size, key-cache, canonical-output, NFC, and numeric guarantees. An isolated A/B must pass the existing malformed-input and encoder/decoder conformance tests plus depth, payload/key-budget, composite-map-key, NFC collision, numeric-boundary, and tag cases. The scanner for untrusted `loads` input and snapshot validation must remain intact unless independently proven redundant.

2. **Reduce per-entry staging costs for large Python dictionaries.** [`src/direct_encode.rs:289-340`](../../src/direct_encode.rs#L289) creates an encoded-key `Vec` and encoded-value `Vec` for each entry, stores them in a `BTreeMap`, then copies their contents into the final output buffer. This supports canonical encoded-key order and replacement of normalized-key collisions, but it has measurable native work on a large map.

   The 10,000-entry shuffled-map profile has a stable uninstrumented encode median of 6,379,178 ns/op (MAD 196,138 ns/op) for 139,723 wire bytes. A single loop-only Callgrind sample attributed 36,624,886 inclusive Ir to `write_dict`. Its two separate `__memcmp_avx2_movbe` child edges each record 181,954 calls and 4,040,691 Ir; together these non-overlapping edges account for 8,081,382 Ir, about 22.1% of the inclusive `write_dict` Ir. The raw profile ID-to-symbol legend verifies ID 2892 as `__memcmp_avx2_movbe`. This supports repeated encoded-key comparison work in the current `BTreeMap` path; it is instruction evidence, not a wall-time estimate. The source performs `entries.remove(&encoded_key)` at line 313 and `entries.insert(encoded_key, ...)` at line 330 for each item, matching two searches through the map.

   The same trace's `RawVec::finish_grow` edge contains 30,016 calls, with 20,002 `malloc` and 10,015 `realloc` calls beneath it during the measured `dumps` path. These are allocator call counts, not allocated-byte counts, and include vector growth elsewhere in that encode path; they do not predict a wall-time gain. Perf hardware counters for 100 encode calls recorded 3,884,587,706 user instructions and 1,907,436,056 user cycles (38,845,877 instructions and 19,074,361 cycles per call). The controlled ROI includes Python loop/lambda dispatch, result reference replacement and release, PyO3 and extension work, plus small enable/disable boundary overhead; it is not Rust-only attribution.

   **First, lower-risk experiment:** prototype one `BTreeMap::entry(encoded_key)` lookup per entry so an occupied key does not need the current remove search followed by another insert search. Preserve the existing order: convert the key, release/drop the replaced staging data and its budget charge, reserve the candidate key budget, then convert the value once in Python iteration order. If the Entry design cannot release old storage and budget before value conversion while retaining last-NFC-collision-wins behavior, do not use that design. Keep `CBORMap` duplicate rejection, header accounting, early aggregate-key budget checks, and exception/callback order unchanged. Compare the two named `memcmp` edges and uninstrumented timings on collisions and sorted, reverse, and shuffled maps before accepting any gain.

   **Then, if still useful:** compare the current staging with a compact, bounded staging representation and sorted key indexes to reduce separate buffers and final flattening copies. Retaining overwritten payloads in an arena would change peak-memory behavior. Require byte-identical canonical output, identical exceptions and callback order, and lower measured encode latency and peak allocation on maps from 10 to 10,000 entries, including collision and composite-key controls. No representation change is recommended without that A/B evidence.

3. **Remove one full payload copy for top-level immutable `bytes`.** For `bytes`, [`src/direct_encode.rs:77-82`](../../src/direct_encode.rs#L77) borrows the Python payload, charges its byte budget, writes a CBOR header, and copies the payload into the Rust output `Vec`. [`src/lib.rs:83-84`](../../src/lib.rs#L83) then copies the complete vector into the returned Python `bytes`. Thus a 1 MiB payload has a source-visible 1 MiB payload copy into the vector and a second copy of the 1,048,581-byte encoded result into Python-owned storage. This is a source-level copy audit, not a measured byte-traffic or allocator trace.

   A synthetic 1 MiB probe measured 143,528 ns/op encode (MAD 1,601 ns/op) and 71,081 ns/op decode (MAD 1,530 ns/op), from nine fresh uninstrumented processes with 200 calls each. The corresponding bytes were 1,048,581 on the wire. Encode and decode perform different work, so their timing difference does not isolate the cost of the extra copy. Perf counters recorded 199,363 instructions and 171,183 cycles per encode call in the controlled ROI; these do not measure copied bytes.

   **Candidate:** test a top-level bytes fast path that writes the header and payload into the final Python bytes allocation once, after the same size-budget check. Compare against the current encoder using the synthetic payload across small and large sizes, and confirm exact wire output, budget failures, and standard bytes round trips. Do not change bytearray locking or borrow mutable storage outside its current guard.

## Decode coverage and deferred ideas

The controlled decode-counter samples cover the 10,000-entry map, synthetic 1 MiB bytes, `float_fractional`, `unicode_decomposed`, and shared `large_collection` fixtures; raw counts are in [`benchmarks/v02_profile/perf_roi.json`](../../benchmarks/v02_profile/perf_roi.json). The stable uninstrumented 10,000-entry map decode median is 1,723,579 ns/op (MAD 27,046 ns/op), and the synthetic 1 MiB bytes decode median is 71,081 ns/op (MAD 1,530 ns/op). The map decode ROI recorded 17,558,620 hardware instructions and 5,306,885 cycles per call, including Python/PyO3 and helper-loop work. No Callgrind decode attribution was collected, so these measurements do not identify an avoidable native decode hotspot. The decoder's preflight pass validates untrusted bytes before Python objects are created; this pass did not establish that merging validation and materialization would preserve that behavior more cheaply. No decode change is prioritized.

The source has a known-length `PyList` decode path that appends elements ([`src/direct_decode.rs:95-117`](../../src/direct_decode.rs#L95)), and `decode_map` can discard a tentative `PyDict` when Python key semantics require `CBORMap` ([`src/direct_decode.rs:120-168`](../../src/direct_decode.rs#L120)). This pass did not collect native allocation or timing attribution for those cases, so list preallocation and map-fallback work remain unproven. Branch and cache event counts are retained as raw measurements, but no branch-predictor, cache-miss, or pipeline cause is inferred from them. There is no equivalent measured competing dCBOR implementation here, so this review makes no global “fastest” claim.

## Reproduction and evidence

`perf stat` worked with `perf_event_paranoid=2`; no counter permission error occurred. FIFO acknowledgements enabled counters immediately before and disabled them immediately after the helper call loop, excluding imports, fixture creation, correctness checks, and warmups. The ROI still includes the Python loop/lambda, result reference lifecycle, and small counter-control boundary overhead. The CPU governor was `powersave`, so absolute cycle and latency values are machine/session specific. Hardware counters were not gathered in the same runs as the committed normal timing medians. Callgrind `Ir` is its instrumented instruction-reference metric; raw inclusive parent and child values overlap and must not be summed. The release extension has named Rust function symbols but no DWARF source-line data.

The compact evidence is in [`benchmarks/v02_profile/perf_roi.json`](../../benchmarks/v02_profile/perf_roi.json), [`benchmarks/v02_profile/perf_stat_raw.txt`](../../benchmarks/v02_profile/perf_stat_raw.txt), [`benchmarks/v02_profile/callgrind_excerpts.txt`](../../benchmarks/v02_profile/callgrind_excerpts.txt), and [`benchmarks/v02_profile/bytes_wall_samples.json`](../../benchmarks/v02_profile/bytes_wall_samples.json). The current fixture helper is [`benchmarks/v02_profile/profile_native.py`](../../benchmarks/v02_profile/profile_native.py), SHA-256 `23cb2f7f89c89bbdf247373aa762066d394e581fdddd3b7b736f3725540772f6`. The perf and uninstrumented bytes samples record the earlier helper hash `535b9f552d596ba8aa9e6d283aa51bdbe2492b26b55d996fe58985c873cf0718`; the only helper change since those samples makes Callgrind control target its own PID, and that code path was inactive in those samples. The raw perf output text is retained with trailing column-padding spaces trimmed; counts, event modifiers, timestamps, and printed fields are unchanged. FIFO acknowledgement lines were consumed and validated by the helper but were not logged; they are unavailable and have not been reconstructed.

This perf command creates fresh FIFOs in a unique temporary directory and removes them on exit. It runs one sample; use a new temporary directory for each run.

```sh
set -euo pipefail
task_tmpdir="$(mktemp -d "${TMPDIR:-/tmp}/aidcbor-perf.XXXXXX")"
trap 'rm -rf -- "$task_tmpdir"' EXIT
perf_prefix="$task_tmpdir/counters"
mkfifo "${perf_prefix}.ctl" "${perf_prefix}.ack"

PYTHONPATH=python:benchmarks perf stat -D -1 \
  --control="fifo:${perf_prefix}.ctl,${perf_prefix}.ack" \
  -e cycles:u,instructions:u,branches:u,branch-misses:u,cache-references:u,cache-misses:u \
  -- .venv/bin/python benchmarks/v02_profile/profile_native.py \
  --perf-control-prefix "$perf_prefix" \
  --fixture profile:map_10000_shuffled --operation encode --rounds 100 --warmup 10

PYTHONPATH=python:benchmarks valgrind --tool=callgrind --instr-atstart=no \
  --callgrind-out-file=/tmp/dcbor_floatenc_pid.out.%p --quiet -- \
  .venv/bin/python -u benchmarks/v02_profile/profile_native.py \
  --callgrind-control --fixture profile:float_fractional \
  --operation encode --rounds 1000 --warmup 100
```

The Callgrind excerpts preserve the measured commands, fixture wire hashes, helper/extension fingerprints, loop boundaries, raw inclusive edges, and the function-ID-to-symbol legend copied from the original text profiles. Full Callgrind text profiles remain in `/tmp` only.
