# dcbor

Python bindings for [Blockchain Commons' `dcbor`](https://github.com/BlockchainCommons/bc-dcbor-rust)
Rust crate — a deterministic CBOR ("dCBOR") encoder/decoder implementing the
constraints of the dCBOR specification (RFC 8949 §4.2.1 plus the dCBOR
application profile): canonical shortest-form integers, floating-point
numeric reduction, NFC-normalized strings, lexicographically ordered map
keys, and rejection of non-canonical encodings on decode.

All encoding/decoding logic runs in the real Rust crate via
[PyO3](https://pyo3.rs/); this package only converts between Python objects
and `dcbor::CBOR` values.

## Install (from source)

```sh
pip install maturin
maturin develop --release   # or: maturin build --release && pip install target/wheels/*.whl
```

## Usage

```python
import dcbor

data = dcbor.dumps({"b": 2, "a": [1, 2, 3], "c": None})
assert dcbor.loads(data) == {"a": [1, 2, 3], "b": 2, "c": None}

print(dcbor.diagnostic(data))
# {"a": [1, 2, 3], "b": 2, "c": null}
```

### Supported types

| Python                 | dCBOR                          |
|------------------------|---------------------------------|
| `None`                 | simple value `null`             |
| `bool`                 | simple value `true`/`false`     |
| `int`                  | major type 0/1 (unsigned/negative, must fit `[-2**64, 2**64-1]`) |
| `float`                | major type 7 float (numerically reduced to an integer when exact, per dCBOR) |
| `str`                  | major type 3 text string (NFC-normalized) |
| `bytes` / `bytearray`  | major type 2 byte string        |
| `list` / `tuple`       | major type 4 array              |
| `dict`                 | major type 5 map (keys sorted into canonical order automatically) |
| `datetime.datetime`    | tag 1 (epoch date/time)         |
| `dcbor.CBORTag`        | arbitrary tag (major type 6)    |

`loads()` is the exact inverse mapping, except tag 1 always decodes to an
aware UTC `datetime.datetime`, and any other tag decodes to a `CBORTag`.
`datetime.datetime` values passed to `dumps()` must be timezone-aware —
naive datetimes are rejected with `CBORError` rather than silently encoded
using the host machine's local timezone, which would make the encoding
depend on where it runs (unacceptable for a *deterministic* format).

### Errors

Malformed or non-canonical dCBOR raises `dcbor.CBORError` (a subclass of
`Exception`) on `loads()`/`diagnostic()`/`validate()`. Values that can't be
represented in dCBOR (unsupported Python types, out-of-range integers) raise
`dcbor.CBORError` from `dumps()`.

### Known limitations

- **Map keys that aren't Python-hashable.** dCBOR permits arrays and maps
  as map keys; Python dicts don't. `loads()` raises `CBORError` if a
  decoded map contains such a key. `dumps()` can't produce one either,
  since Python `dict` can't hold it in the first place.
- **NFC string collisions.** dCBOR text strings are normalized to Unicode
  NFC before encoding. Two distinct Python strings that normalize to the
  same NFC form (e.g. `"é"` composed vs. `"e"` + combining acute) encode
  identically, so as dict keys the later one silently overwrites the
  earlier one — the same behavior the underlying Rust crate has.
- **Nesting depth is capped at 512 levels** (arrays/maps/tags, on both
  `dumps()` and `loads()`) to prevent stack-exhaustion crashes on
  adversarial input; deeper structures raise `CBORError` rather than
  crashing the process.
- **Verified interpreter.** This has been built and tested against
  CPython 3.14 in this environment. PyO3 0.29 supports building against
  CPython 3.9–3.14, but only 3.14 has actually been exercised here.

## Development

```sh
python3 -m venv .venv && source .venv/bin/activate
pip install maturin pytest
maturin develop
pytest
```

## License

BSD-2-Clause-Patent, matching the upstream `dcbor` Rust crate.
