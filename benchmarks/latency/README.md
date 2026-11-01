# Codec latency comparison

This harness times encode, decode, and one encode-plus-decode round trip for
eight shared JSON-compatible fixtures. It measures Python's standard-library
`json`, dCBOR, generic `cbor2` and `cborx`, `orjson`, `msgspec` MessagePack,
and strict DAG-CBOR through `cbrrr`. These are selected implementations and
formats, not a ranking of codecs in general.

![Three panels compare every measured codec mode with Python json for encode, decode, and round-trip latency; whiskers show the fixture-to-fixture range.](../../.github/assets/graphs/latency.svg)

Each operation's per-fixture median is divided by the Python `json` median for
that same fixture and operation. The center mark is the median of the eight
ratios; whiskers show the minimum and maximum across fixtures. The `1×`
reference is parity with `json`. Those whiskers describe workload variation,
not timing uncertainty. The [raw report](results.json) retains every
fixture/mode median, MAD, and process sample.

## Calls and scope

| Series | Timed call |
| --- | --- |
| Python JSON | Compact UTF-8 `json.dumps()` and matching `json.loads()`. |
| dCBOR | `dcbor.dumps(value)` and `dcbor.loads(prepared_wire)`. |
| `cbor2` default/canonical | `dumps` and `loads`, with `canonical=True` only in the canonical mode. |
| `cborx` default/canonical | `dumps` and `loads`, with `canonical=True` only in the canonical mode. |
| `orjson` default/sorted | `orjson.dumps` and `orjson.loads`; sorted mode uses `OPT_SORT_KEYS`. |
| `msgspec` MessagePack default/deterministic | Preconstructed `Encoder`/`Decoder` methods; deterministic mode sets `order="deterministic"`. |
| `cbrrr` strict DAG-CBOR | `encode_dag_cbor` and `decode_dag_cbor`. |

The encoder and decoder wrappers for `msgspec` are constructed before timed
calls. Decoding uses ordinary Python values; typed `msgspec.Struct` decoding
is not included. The shared fixtures contain finite JSON-compatible values,
so `orjson`'s handling of non-finite floats is outside this measurement.
Round trip includes one encoding followed by one decoding. The harness checks
type-sensitive round trips before timing. It times each implementation's
normal decoder; there is no separate validation-only operation. DAG-CBOR
decoding applies that codec's strict profile.

Generic CBOR canonical modes, MessagePack deterministic ordering, and strict
DAG-CBOR follow different data and byte rules from dCBOR. In particular,
DAG-CBOR restricts map keys to strings, requires binary64 floats, and permits
only CID tag 42. The shared fixtures fit the common comparison; results do not
imply equivalent accepted domains or conformance to dCBOR.

## Reproduce

Use the same CPython interpreter and host for all modes. Install the pinned
libraries, build the release extension, then run from the repository root:

```sh
python -m pip install -r benchmarks/requirements.txt
CARGO_BUILD_JOBS=2 maturin develop --release --locked
PYTHONPATH=python python benchmarks/latency.py
```

The release-artifact check currently requires Linux's
`target/release/lib_dcbor.so` and verifies the imported extension by SHA-256.
Each repetition launches a fresh Python process with `PYTHONHASHSEED=0`. By
default, each operation gets 500 warmup calls and 1,000 timed calls per
process; each reported mode/fixture has nine process samples. The report
summarizes per-process batch means with their median and MAD, plus minimum and
maximum. Timer, versions, module paths, source fingerprints, extension hash,
fixture/output hashes, and all process samples are recorded in JSON.

The summary describes one host and interpreter. Scheduling, CPU frequency,
thermal state, and background load can change timings; close results should
not be generalized. See the [comparison overview](../../project-notes/benchmarks.md)
for the complete report index.
