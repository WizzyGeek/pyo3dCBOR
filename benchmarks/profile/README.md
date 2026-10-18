# dCBOR profile workloads

This benchmark isolates workload shapes that exercise dCBOR's map ordering,
numeric, and Unicode normalization behavior. It measures the dCBOR Python
extension only; these cases are not the shared cross-codec fixture set.

![Side-by-side map encode and decode scaling use the same logarithmic limits; lower panels show float and Unicode encode/decode medians and wire sizes.](../../.github/assets/graphs/profile.svg)

The top panels plot map encode and decode time against entry count with shared
logarithmic entry-count and time limits. Each shows sorted, reverse, and
seeded-shuffled source insertion order. All three orders produce identical
canonical wire, so decode differences by order are measurement variation, not
evidence of insertion-order-dependent decoding. The encode call includes
Python-map conversion and encoding, so it does not isolate sort-only cost. All
map keys have the same 10-byte ASCII width; this workload cannot distinguish
bytewise order from length-first order. The lower float and Unicode panels
show encode/decode medians in microseconds on a shared logarithmic scale, with
wire bytes shown for each case. Each plotted value comes from the machine-readable
[profile report](results.json), which records case family, operation, medians,
MAD, process samples, hashes, environment, and normalization metadata,
including the four uncharted controls listed below.

## Cases

| Family | Cases | Input |
| --- | --- | --- |
| Maps | `map_{10,100,1000,10000}_{sorted,reverse,shuffled}` | Integer values `0..n-1` under 10-byte ASCII keys `field-{index:04d}`. Orders are dCBOR-encoded-key sorted, reversed, or shuffled with `random.Random(0xDCB0 + n)`. |
| Floats | `float_fractional` | Six values `[0.1, -0.1, 0.25, -1.5, 3.125, 1.1]`, repeated 64 times. |
| Floats | `float_integral` | Python floats `-128.0..127.0`, repeated twice; dCBOR numeric reduction decodes them as integers. |
| Floats | `float_mixed_special` | Finite fractions, signed zero, infinities, and NaN payloads; `-0.0` reduces to integer zero. |
| Floats | `float_boundaries` | `-2**63`, adjacent floats, `2**64`, adjacent floats, `-2**64`, and infinities. |
| Text | `unicode_ascii`, `unicode_nfc`, `unicode_decomposed`, `unicode_expanding_nfc` | 256 strings per case: ASCII; NFC `Málaga café déjà vu Ångström`; its NFD form; and a prefix plus U+0344, which expands to U+0308 U+0301 under NFC. |
| Raw-report controls | `integer_width_boundaries`, `dict_nfc_key_collisions`, `nested_scalar_tree`, `cbor_map_snapshot` | Encode/decode controls recorded in JSON but omitted from the chart; they cover explicit integer widths, normalized-key collisions, nested values, and immutable `CBORMap` snapshots. |

The report records both input and encoded-wire hashes, wire byte counts,
iteration and warmup settings, encode/decode timing samples, median, MAD, and
minimum/maximum. Defaults are 100 warmups, 500 timed calls, and nine process
repetitions. To keep large inputs bounded, each case scales warmups and timed
calls by `max(1, min(base, floor(base * 1000 / work_units)))`, where work units
are map entries, array elements, or total Unicode code points for that case.
Actual counts are recorded per case; a zero warmup stays zero. Profile
correctness checks account for dCBOR normalization: integral floats can become
integers and text is normalized to NFC. Consult the
[Python API guide](../../docs/python-api.md#numeric-compatibility) for the
documented numeric compatibility rules.

## Reproduce

From the repository root, use a release extension whose bytes match
`target/release/lib_dcbor.so`, then run:

```sh
CARGO_BUILD_JOBS=2 maturin develop --release --locked
PYTHONPATH=python python benchmarks/profile.py
```

Pass `--warmup`, `--rounds`, or `--repetitions` to change the defaults;
`--smoke` checks the cases without timing or writing a report.
The runner writes [`results.json`](results.json) and the stable figure at
[`profile.svg`](../../.github/assets/graphs/profile.svg). It records the source
fingerprints, Python/platform details, and release-extension verification so
the result can be tied to the code and environment that produced it. The
current capture uses dCBOR 0.1.1 at source commit `df70782`.
