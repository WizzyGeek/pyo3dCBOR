# dCBOR for Python

Deterministic CBOR bytes for Python values, validated against the documented
dCBOR application profile.

- **Canonical output:** preferred numeric encodings, bytewise map-key order,
  and NFC text normalization.
- **Checked input:** `loads()` rejects malformed and noncanonical encodings.
- **Python types:** bytes, tags, aware datetimes, and `CBORMap` for distinct
  keys that Python `dict` cannot preserve.

## Install

From a source checkout in an activated Python virtual environment with Rust
and Cargo installed:

```sh
python -m pip install maturin
maturin develop --release --locked
```

To build and install a local wheel instead:

```sh
maturin build --release --locked
python -m pip install target/wheels/dcbor-*.whl
```

PyPI publication is not configured; packaged releases are distributed through
[GitHub Releases](docs/releasing.md).

## Try it

```python
import dcbor
value = {"b": 2, "a": [1, 2, 3]}
wire = dcbor.dumps(value)
assert wire == dcbor.dumps({"a": [1, 2, 3], "b": 2})
restored = dcbor.loads(wire)
assert restored == {"a": [1, 2, 3], "b": 2}
print(dcbor.diagnostic(wire))
# {"a": [1, 2, 3], "b": 2}
```

Reordering map entries produces the same wire bytes. `diagnostic()` prints a
readable representation.

## Benchmark results

![JSON and dCBOR payload sizes across eight fixtures; JSON is 100%, with exact bytes and percentage differences labeled.](.github/assets/graphs/encoded-size.svg)

![Encode, decode, and round-trip latency ratios for dCBOR and fastest generic CBOR versus JSON; 1× is parity.](.github/assets/graphs/latency.svg)

Results vary by workload: JSON can be smaller and generic CBOR is often
faster. Timings are from one host, and generic codecs follow different
canonical rules. See [benchmark scope and raw reports](docs/benchmarks.md),
[encoded-size method](benchmarks/encoded_size/README.md), and
[latency method](benchmarks/latency/README.md).

## Guides

| Guide | Covers |
| --- | --- |
| [Python API](docs/python-api.md) | Supported values, maps, dates, numeric compatibility, errors, and limits |
| [Benchmark reports](docs/benchmarks.md) | Wire-size graph, scope, and comparison caveats |
| [Development and CI](docs/development.md) | Build/test commands and CI matrix |
| [Release guide](docs/releasing.md) | GitHub release process and assets |

Targets [RFC 8949 deterministic encoding](https://www.rfc-editor.org/rfc/rfc8949.html)
with the [dCBOR application profile](https://www.ietf.org/archive/id/draft-mcnally-deterministic-cbor-18.html#section-2.5).
Project tests provide implementation evidence, not external certification.
The numeric compatibility note is in the [Python API guide](docs/python-api.md#numeric-compatibility).

BSD-2-Clause-Patent, matching the upstream `dcbor` Rust crate.
