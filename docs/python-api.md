# Python API and compatibility

This page records the Python value mappings, validation behavior, compatibility
choices, and resource limits of `dcbor`.

## Supported values

| Python value | dCBOR representation |
| --- | --- |
| `None` | simple value `null` |
| `bool` | simple value `true` or `false` |
| `int` | major type 0/1; range `[-2**64, 2**64 - 1]` |
| `float` | preferred-width float; integral values in `[-2**63, 2**64)` reduce to integers |
| `str` | major type 3 text, normalized to Unicode NFC; lone surrogates are rejected |
| `bytes` / `bytearray` | major type 2 byte string |
| `list` / `tuple` | major type 4 array |
| `dict` / `dcbor.CBORMap` | major type 5 map; keys are sorted into canonical order |
| `datetime.datetime` | tag 1 (epoch date/time) |
| `dcbor.CBORTag` | arbitrary tag (major type 6) |

`loads()` converts numeric tag 1 values to aware UTC `datetime.datetime`
values. Nonnumeric tag 1 values and other tags decode to `CBORTag`. Nonfinite
timestamps and dates outside Python's supported range raise `CBORError`.
Values passed to `dumps()` as `datetime.datetime` must be timezone-aware;
naive datetimes raise `CBORError` instead of depending on the host's local
timezone.

Maps normally decode to `dict`. If a key is unhashable or distinct CBOR keys
compare equal in Python, such as `1` and `True`, maps decode to `CBORMap`, a
read-only snapshot whose lookups use canonical key encodings:

```python
import dcbor

mapping = dcbor.CBORMap([(1, "integer"), (True, "boolean")])
assert mapping[1] == "integer"
assert mapping[True] == "boolean"
assert dcbor.dumps(dcbor.loads(dcbor.dumps(mapping))) == dcbor.dumps(mapping)
```

`CBORMap` supports indexing, membership, iteration, `len()`, `get()`, `keys()`,
`values()`, and `items()`. Its constructor accepts key/value pairs and rejects
duplicate canonical keys. Returned containers are fresh decoded values;
mutating them does not change the snapshot. Converting a `CBORMap` to `dict`
can lose distinctions such as `1` versus `True`.
Arrays, maps, and mutable tags can be `CBORMap` keys; their encoded identity is
preserved without relying on Python hashing.

Python `dict` encoding preserves its established last-entry-wins behavior when
distinct string keys normalize to the same NFC encoding. This differs from
`CBORMap`, which rejects duplicate canonical pairs. Map-key conversion
preserves canonical encoding throughout composite keys. A numeric date key
converts to `datetime` only when that conversion round-trips exactly;
otherwise it keeps its original `CBORTag` representation. Thus keys returned
by iteration, `keys()`, and `items()` remain usable for membership and lookup,
including sub-microsecond date keys.

`CBORTag` is mutable and unhashable; tagged map keys use `CBORMap`. Strings are
read from their Unicode contents without calling a subclass's `__str__`. Lone
surrogates raise `CBORError` because they cannot be encoded as valid CBOR UTF-8
text; they are never silently replaced.

## Numeric compatibility

Floating-point reduction follows
[draft-mcnally-deterministic-cbor-18 §2.5](https://www.ietf.org/archive/id/draft-mcnally-deterministic-cbor-18.html#section-2.5).
For example, `-float(2**64)` remains a float (`fadf800000`), while the explicit
integer `-(2**64)` retains its integer encoding (`3bffffffffffffffff`). Floats
below `-2**63` are preserved by decoding, diagnostics, and map-key
serialization as well as encoding.

Explicit integers retain the documented full CBOR range `[-2**64, 2**64-1]`.
The draft's Appendix A rejects some large negative integer encodings without
an equally explicit prohibition in its normative integer rules. This binding
preserves its existing integer API while that ambiguity remains; it does not
claim strict agreement with those Appendix A rejection vectors. `CBORMap` can
preserve a large negative integer and the numerically equal, separately
encoded float as distinct keys.

## Errors and limits

Malformed or noncanonical input raises `dcbor.CBORError` (a subclass of
`Exception`) from `loads()`, `diagnostic()`, and `validate()`. Unsupported
Python types and out-of-range integers raise `CBORError` from `dumps()`.

- **NFC collisions:** dCBOR text is normalized to NFC before encoding. Two
  distinct strings with the same NFC form encode identically. In a `dict`,
  the later value wins for compatibility; `CBORMap` rejects the duplicate.
- **Nesting depth:** arrays, maps, and tags are limited to 512 levels in
  `dumps()` and `loads()`. Deeper structures raise `CBORError` rather than
  risking stack exhaustion.
- **Encoded map-key storage:** keys share a 16 MiB aggregate budget, counting
  nested keys at every level to match the decoder's cached copies. Encoding
  reserves the same budget during conversion before caching keys or descending
  into values, including nested maps and repeated shared objects. Text is
  normalized before its UTF-8 bytes and length headers are counted. This bounds
  key-cache amplification, not total input size or all process memory.
- **Datetime precision:** fractional epoch timestamps use floating-point
  seconds. Microseconds far from the Unix epoch may lose precision, and
  decoded timestamps are limited to Python's resolution and range.
- **Interpreters:** CI targets regular CPython 3.9–3.14. Free-threaded CPython
  and alternative interpreters are not currently in the build matrix.
