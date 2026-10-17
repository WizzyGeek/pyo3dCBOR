# Benchmark comparisons

The reports use eight shared, JSON-compatible workloads: records, nested
values, repeated Unicode, numeric arrays, scientific-notation floats, a larger
collection, a telemetry batch, and an ASCII article. They measure serialized
payload bytes and Python operation latency, not memory use or database storage.

## Wire size

The wire-size report compares compact UTF-8 JSON and dCBOR with `cbor2` and
`cborx` in default and canonical modes. Each row uses JSON as a 100% baseline,
shows dCBOR as a point, and shows the generic CBOR min–max range as a band.
Rows print exact byte counts; the band collapses when all four generic codecs
produce the same size. The raw report keeps all 48 fixture-and-codec values,
hashes, and run metadata.

![Eight fixture rows compare JSON at 100%, dCBOR, and the generic CBOR size range. Exact byte counts and the range endpoints are labeled.](../.github/assets/graphs/wire-size.svg)

For the compact scientific-notation fixture, JSON used 15 bytes and each CBOR
mode used 19 bytes in the recorded report. The figure also calls out the small
numeric-array increase in the generic default modes. These cases remain visible
alongside the other fixtures.

`cbor2` and `cborx` are generic CBOR codecs, not dCBOR implementations. Their
canonical options follow library-specific ordering rules and are not
interchangeable with each other or with the dCBOR profile. JSON also cannot
represent all CBOR values. The comparison therefore describes only these
codecs on the listed fixtures.

## Latency

The latency figure compares dCBOR and the fastest generic-CBOR median with
Python `json` for each fixture and operation on a shared log-ratio axis. The
1× reference means equal medians; lower ratios are faster. The generic mode is selected independently
for each fixture and operation. Full medians for every codec, median absolute
deviations, and process samples remain in the
[machine-readable report](../benchmarks/latency/results.json).

The timing report is one host and interpreter, with fresh-process samples. It
does not establish a general speed ranking or predict another workload. Use
the [latency methodology](../benchmarks/latency/README.md) for the environment,
sampling method, and reproduction commands.

## Detailed reports

- [Encoded-size method and raw data](../benchmarks/encoded_size/README.md)
- [Wire-size method and raw data](../benchmarks/wire_size/README.md)
- [Latency method and raw data](../benchmarks/latency/README.md)
- [Benchmark index and reproduction commands](../benchmarks/README.md)
- [Competitive landscape, including PostgreSQL JSONB](competitive-landscape.md)
