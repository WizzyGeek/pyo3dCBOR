# Wire-size comparison

This report measures encoded payload bytes for eight shared JSON-compatible
fixtures. It compares compact UTF-8 JSON, dCBOR 0.1.0, four generic CBOR
modes, two `orjson` JSON modes, two `msgspec` MessagePack modes, and strict
DAG-CBOR through `cbrrr`. It does not measure object memory, database storage,
transport, or query cost.

![Eight fixtures compare compact JSON at 100%, dCBOR and DAG-CBOR points, and family ranges for generic CBOR, orjson, and msgspec MessagePack.](../../.github/assets/graphs/wire-size.svg)

The figure normalizes each fixture to compact JSON at 100%. It shows dCBOR and
DAG-CBOR as individual points and ranges across each library's measured
modes. Where modes have the same size, their range collapses to one point.
Direct labels show exact JSON, dCBOR, and range bytes. The scientific-notation
fixture is included because JSON decimal text can be shorter than dCBOR's
binary64 representation. All per-mode bytes and SHA-256 values are in the
[raw report](results.json).

## Measured modes

| Report series | API or option |
| --- | --- |
| Compact JSON | `json.dumps(..., ensure_ascii=False, separators=(",", ":"), allow_nan=False)`, UTF-8 encoded. |
| dCBOR | `dcbor.dumps()` from the verified release extension. |
| `cbor2_default` | `cbor2.dumps()` defaults. |
| `cbor2_canonical` | `cbor2.dumps(..., canonical=True)`. |
| `cborx_default` | `cborx.dumps()` defaults. |
| `cborx_canonical` | `cborx.dumps(..., canonical=True)`. |
| `orjson_default` | `orjson.dumps()` defaults. |
| `orjson_sorted` | `orjson.dumps(..., option=orjson.OPT_SORT_KEYS)`. |
| `msgspec_msgpack` | Preconstructed `msgspec.msgpack.Encoder()` and `Decoder()`. |
| `msgspec_msgpack_deterministic` | Preconstructed encoder with `order="deterministic"` and a `Decoder()`. |
| `cbrrr_strictdagcbor` | `cbrrr.encode_dag_cbor()` and `decode_dag_cbor()`. |

The comparators are pinned to `cbor2==6.1.5`, `cborx==0.2.5`,
`orjson==3.13.0`, `msgspec==0.22.0`, and `cbrrr==1.1.0` in
[`requirements.txt`](../requirements.txt). Encoder/decoder wrappers are
constructed before timed calls in the latency harness. The MessagePack
comparison decodes to ordinary Python values; it does not use typed
`msgspec.Struct` decoding. The expanded comparator environment requires
Python 3.10 or newer because of `orjson` and `msgspec`; the `dcbor` source
package itself continues to declare Python 3.9 support.

The common fixtures contain finite values, so they do not exercise
`orjson`'s non-finite-number behavior. Its JSON API serializes NaN and
infinities as `null`; the wire result therefore must be interpreted as the
listed fixture comparison, not a broader equivalence claim. [DAG-CBOR](https://ipld.io/specs/codecs/dag-cbor/spec/)
is a different profile: its map keys must be strings, floats are binary64,
and only tag 42 is allowed; its specification excludes non-finite floats and
negative zero. The measured `cbrrr==1.1.0` API rejects NaN and infinities but
accepts and emits `-0.0` as binary64, so it is measured as provided. The shared
fixtures contain none of these values. Generic CBOR `canonical=True` and
MessagePack deterministic ordering likewise do not establish dCBOR
conformance.

## Reproduce

From the repository root, install the pinned libraries, build the optimized
Python extension, and run:

```sh
python -m pip install -r benchmarks/requirements.txt
CARGO_BUILD_JOBS=2 maturin develop --release --locked
PYTHONPATH=python python benchmarks/wire_size.py
```

The runner records a complete comparison only when the pinned packages are
available, the `dcbor` extension matches `target/release/lib_dcbor.so`, and
each encoder's output passes the type-sensitive round-trip check. If a
required package, version, or check is missing, the report status is
`blocked` or `failed` and the fixture values are not presented as a complete
comparison.

The JSON includes versions, module paths and native-extension status,
environment, source fingerprints, fixture and output hashes, exact byte
counts, and run status. The release-artifact comparison currently checks the
Linux path `target/release/lib_dcbor.so` by SHA-256. The JSON retains all ten
codec modes plus the compact JSON baseline, even when the graph groups modes
into a point or range.

See [benchmark scope](../../docs/benchmarks.md) for the other reports and
comparison limits.
