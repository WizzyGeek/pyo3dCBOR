# Encoded-size comparison

This evidence bundle compares **serialized payload bytes** from Python's
standard-library JSON encoder with canonical dCBOR wire bytes for the same
eight JSON-compatible workloads. It measures neither Python object size nor
process memory. The companion [`results.json`](results.json) records every byte count and hash,
the source commit, Python/platform details, dcbor package version, and the
loaded extension's SHA-256. The generated
[encoded-size.svg](../../.github/assets/graphs/encoded-size.svg) uses a shared
horizontal scale normalized to compact JSON at 100%. Each row labels both
exact byte counts and dCBOR's percentage difference; values below 100% mean
fewer dCBOR payload bytes and values above 100% mean more.

![Eight fixture rows compare compact JSON and dCBOR payload bytes on a shared scale with JSON at 100%; exact byte counts and percentage differences are labeled.](../../.github/assets/graphs/encoded-size.svg)

The compact scientific-notation fixture is one counterexample: JSON is 15
bytes and dCBOR is 19 bytes (+26.67%). The figure keeps each workload visible.

## Reproduce

From the repository root, build the optimized extension for the active
interpreter and run the benchmark:

```sh
CARGO_BUILD_JOBS=2 maturin develop --release --locked
PYTHONPATH=python python benchmarks/encoded_size.py
```

The benchmark runner uses only the Python standard library plus the `dcbor`
package under measurement. The report records `rustc`, Cargo, the root
`Cargo.lock` hash, and the exact imported extension hash. It labels the build
profile `release` only when that extension matches
`target/release/lib_dcbor.so` byte for byte; otherwise the profile is
`unverified`. The recorded build command is the reproducible build command, not
a claim that the generator performed a build. The script writes `results.json`
here and overwrites the stable chart at
`.github/assets/graphs/encoded-size.svg`. For an installed package, omit
`PYTHONPATH=python`. The output includes the
current git commit, a dirty-worktree indicator, interpreter and platform
metadata, package version, extension path and hash, and a UTC generation time.
Compare those fields before comparing or refreshing results. The script checks
that both JSON and dCBOR decode back to each fixture using a recursive,
type-sensitive comparison. Numerically equal substitutions such as `True` for
`1`, or a float for an integer, fail the check.
The cleanliness indicator excludes the three generated benchmark JSON reports
and three stable SVG charts; other source or worktree changes still mark the
report dirty. It is `null` if Git status cannot be read. The generator path and
SHA-256 identify the exact script used to produce the report, and the chart
path is recorded in the raw results.

JSON uses UTF-8, `ensure_ascii=False`, compact separators `(',', ':')`, and
`allow_nan=False`. This removes optional whitespace, emits Unicode directly as
UTF-8 rather than `\\u` escapes, and rejects non-finite numbers. The dCBOR side
measures the bytes returned by `dcbor.dumps()`.

## Fixtures and scope

| Fixture | What it represents |
| --- | --- |
| `small_record` | A compact object with a string, integer, boolean, and null. |
| `nested_document` | Nested objects, arrays, strings, integers, and a boolean. |
| `repeated_unicode_strings` | Repeated city and label strings, including non-ASCII UTF-8. |
| `numeric_array` | Signed and unsigned integers plus finite, non-integral floats. |
| `compact_scientific_notation` | Two large-magnitude finite floats whose compact JSON scientific notation may use fewer bytes than CBOR's float64 representation. |
| `large_collection` | 128 object records with repeated group labels and small arrays. |
| `telemetry_batch` | 64 sensor samples with integer timestamps, fractional readings, status flags, and device IDs. |
| `ascii_article` | An object with article-length plain ASCII text. |

All fixtures use only JSON-compatible values. This makes each comparison use
the same Python logical value and allows round-trip checks on both encoders.
The scientific-notation fixture is included as an intentional counterexample:
compact JSON can encode some values more briefly than a binary float. The
measurements and graph report that result alongside every other fixture.
Ordinary JSON cannot preserve CBOR byte strings, arbitrary key types, semantic
tags, NaN or infinity, or distinctions between integer and floating-point wire
representations. Such values are deliberately excluded. These results describe
only the listed fixtures and do not establish that either format is generally
smaller, faster, or better for other workloads. No cross-library latency
comparison is made here.

## Reading the output

`json_utf8_bytes` and `dcbor_wire_bytes` are absolute encoded byte lengths.
`dcbor_vs_json_percent` is `(dCBOR bytes - JSON bytes) / JSON bytes * 100`; a
negative value means fewer dCBOR payload bytes for that fixture. JSON and dCBOR
SHA-256 values bind each reported length to the exact encoded bytes. The raw
report also records `chart_sha256`; verify it against the SVG file to confirm the
graph matches that report. Results are specific to the recorded source commit,
dcbor version/build, and fixture definitions. Refresh the measurements and SVG
after changing those inputs.
