# dCBOR for Python

Deterministic CBOR bytes for Python values, validated against the documented
dCBOR application profile.

- **Canonical output:** preferred numeric encodings, bytewise map-key order,
  and NFC text normalization.
- **Checked input:** `loads()` rejects malformed and noncanonical encodings;
  `load(file)` reads a binary file object once and uses the same decoder.
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

`load(file)` accepts a binary file object and reads it once. Reordering map
entries produces the same wire bytes. `diagnostic()` prints a readable
representation.

## Benchmark results

![Eight fixtures compare compact JSON at 100% with dCBOR bytes and signed size changes.](.github/assets/graphs/encoded-size.svg)

![All measured codec modes compared with Python json; ratios summarize eight fixtures and whiskers show fixture variation.](.github/assets/graphs/latency.svg)

The byte chart includes a scientific-notation case where compact JSON is
smaller than dCBOR. Timing results cover one host; codec ordering and numeric
rules differ. See the [benchmark scope and reports](docs/benchmarks.md),
[wire-size method](benchmarks/wire_size/README.md), and
[latency method](benchmarks/latency/README.md).

## Guides

| Guide | Covers |
| --- | --- |
| [Python API](docs/python-api.md) | `dumps()`, `loads()`, `load()`, supported values, maps, dates, errors, and limits |
| [Benchmark reports](docs/benchmarks.md) | Size, latency, profile, and a historical Rust-core graph |
| [Development and CI](docs/development.md) | Build/test commands and CI matrix |
| [Release guide](docs/releasing.md) | GitHub release process and assets |

Targets [RFC 8949 deterministic encoding](https://www.rfc-editor.org/rfc/rfc8949.html)
with the [dCBOR application profile](https://www.ietf.org/archive/id/draft-mcnally-deterministic-cbor-18.html#section-2.5).
Project tests provide implementation evidence, not external certification.
The numeric compatibility note is in the [Python API guide](docs/python-api.md#numeric-compatibility).

BSD-2-Clause-Patent, matching the upstream `dcbor` Rust crate.
