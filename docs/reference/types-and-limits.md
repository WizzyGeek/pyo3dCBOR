# Types, identity, and limits

```{py:currentmodule} dcbor
```

## Python values

`dumps` accepts these Python values. The inverse mapping is not always a
one-to-one Python type round trip: floats can reduce to integers, tuples become
lists, and maps that Python dictionaries cannot represent faithfully become
`CBORMap` objects.

| Python input | Encoding and decoded form |
| --- | --- |
| `None`, `bool` | CBOR `null`, `false`, or `true`; decodes to the same built-in value |
| `int` | CBOR integer in `[-2**64, 2**64 - 1]`; outside this range, `dumps` raises `CBORError` |
| `float` | Preferred-width float, except integral values in `[-2**63, 2**64)` reduce to an integer encoding |
| `str` | UTF-8 text normalized to {term}`NFC`; decodes as normalized `str` |
| `bytes`, `bytearray` | CBOR byte string; decodes as owned `bytes` |
| `list`, `tuple` | CBOR array; decodes as a fresh `list` |
| `dict`, `CBORMap` | CBOR map with keys in canonical encoded-byte order; decodes as `dict` or lossless `CBORMap` |
| timezone-aware `datetime.datetime` | Tag 1 with epoch seconds; decodes as UTC `datetime` when representable |
| `CBORTag` | Its tag and recursively encoded child value; numeric tag 1 follows the date rules below |

These built-ins and classes are accepted as described; `dumps` does not accept
arbitrary buffer exporters such as `memoryview` as byte strings. For runtime
argument types, see [Serialization and decoding](serialization.md) and
[Errors](errors.md).

## Floats and integers

Canonical floats use the shortest supported floating-point width that
preserves the value. An integral float reduces to a CBOR integer only when its
value is at least `-2**63` and less than `2**64`; the upper bound is exclusive.
Thus `-0.0` reduces to integer zero, while `-float(2**64)` remains a float.
An explicit Python integer `-(2**64)` is valid even though a float with the
same numerical value is outside the float-reduction interval.

NaNs are encoded using the canonical half-precision NaN. Infinities use
half-precision encodings. On decoding, an integral float within
`[-2**63, 2**64)` that is encoded as a float instead of an integer, a
wider-than-needed float, or a noncanonical NaN/infinity representation is
rejected with `CBORError`. Integral floats outside that reduction interval
remain floats and can use their preferred floating-point encoding.

```{doctest}
>>> import dcbor
>>> dcbor.dumps(42.0) == dcbor.dumps(42)
True
>>> dcbor.dumps(-0.0).hex()
'00'
>>> dcbor.loads(dcbor.dumps(42.0)), type(dcbor.loads(dcbor.dumps(42.0))) is int
(42, True)
>>> dcbor.dumps(-(2**64)).hex()
'3bffffffffffffffff'
>>> dcbor.dumps(-float(2**64)).hex()
'fadf800000'
```

The explicit integer API keeps the full CBOR range `[-2**64, 2**64 - 1]`.
Although [draft-18 §2.5](https://www.ietf.org/archive/id/draft-mcnally-deterministic-cbor-18.html#section-2.5)
specifies numeric reduction for floats, its [Appendix A numeric test vectors](https://www.ietf.org/archive/id/draft-mcnally-deterministic-cbor-18.html)
reject some large negative integer encodings. This binding preserves its
existing integer API and does not claim strict agreement with those Appendix A
rejection vectors.

## Text normalization

Text is normalized to NFC before its UTF-8 bytes are encoded. Two distinct
Python strings that normalize to the same text have the same {term}`canonical encoding`.
Lone surrogate code points cannot be represented as valid UTF-8 and raise
`CBORError`; they are not replaced. `loads`, `validate`, and both
diagnostic functions reject encoded text that is not already NFC.

```{doctest}
>>> import dcbor
>>> dcbor.dumps("e\u0301") == dcbor.dumps("é")
True
>>> dcbor.loads(dcbor.dumps("e\u0301"))
'é'
```

## Map keys and encoded identity

Python `dict` can contain only keys allowed by Python's hashing and equality
rules. During encoding, `dumps` serializes each surviving dictionary key and
sorts entries by the complete canonical encoded key bytes. If distinct keys
that remain in the Python dictionary encode to identical key bytes, the later
entry in dictionary iteration order supplies the encoded value. Python may
already have merged equal keys before `dumps` receives the dictionary.

`CBORMap` instead uses {term}`encoded-key identity`: it permits unhashable or
Python-equal-but-wire-distinct keys, and rejects two keys with the same
canonical encoding. For example, Python regards `1 == True`, while their CBOR
encodings differ. `CBORMap` preserves both; converting it to `dict` can lose
one entry.

```{doctest}
>>> import dcbor
>>> mapping = dcbor.CBORMap([(1, "integer"), (True, "boolean")])
>>> mapping[1], mapping[True]
('integer', 'boolean')
>>> dcbor.dumps({"e\u0301": 1, "é": 2}).hex()
'a162c3a902'
>>> try:
...     dcbor.CBORMap([("e\u0301", 1), ("é", 2)])
... except dcbor.CBORError:
...     print("duplicate canonical key")
duplicate canonical key
```

When a decoded map cannot fit a Python `dict` without a key collision or
unhashable key, `loads` returns `CBORMap`. Maps nested inside a map key also
retain lossless encoded representation so that their key identity is not
changed by Python dictionary semantics. Every decoded key exposed by a
`CBORMap` accessor can be used again for membership and lookup by its canonical
encoding.

Numeric tag 1 is normally decoded as a UTC `datetime` when its timestamp is
within Python's supported range. For map keys, a date conversion is used only
when re-encoding that datetime yields exactly the original key bytes. A
sub-microsecond or otherwise lossy timestamp remains a `CBORTag(1, value)` so
the map key remains usable with the same {term}`wire bytes`. Conversion to
`datetime` uses Python's microsecond resolution, and float timestamps can lose
precision far from the epoch.

## Dates and tags

When encoding a `datetime.datetime`, the binding calls `utcoffset()` to ensure
the value is timezone-aware, then calls `timestamp()` and encodes the result
as tag 1. A missing offset (`None`) raises `CBORError`; exceptions raised by
timezone hooks are wrapped as `CBORError`. The timestamp must be finite. The
encoded instant does not retain the input timezone name or offset; decoding
returns an aware UTC datetime.

Tag 1 with a numeric child decodes as a datetime if the timestamp is finite
and within the supported datetime range. A nonnumeric child remains a
`CBORTag`; unsupported numeric timestamps raise `CBORError`. Other tag numbers
decode as `CBORTag`.

## Depth and map-key cache

Nested arrays, maps, and tags have a maximum {term}`depth limit` of 512 levels
in encoding, decoding, validation, and diagnostic formatting. A scalar may appear at the
end of 512 nested levels. The implicit tag 1 used for a datetime counts toward
the encoding depth. Cyclic Python containers are not represented as references
in CBOR; they recurse until the depth guard raises `CBORError`.

The binding limits aggregate encoded map-key cache/storage to 16 MiB under its
{term}`key-cache budget`. The accounting includes keys nested inside other map
keys and repeated encoded
copies of a `CBORMap` snapshot when it is reused in a key context. Reader
validation also counts encoded map-key bytes across nested maps. Exceeding the
limit raises `CBORError`. This limit bounds map-key storage; it is not a maximum
input size, output size, or process-memory limit.

The 512-level guard and 16 MiB map-key budget apply to `dumps`, `loads`,
`validate`, `diagnostic`, and `diagnostic_flat`. `CBORMap` construction and
encoded-key lookup also enforce the depth and key-cache constraints relevant
to the key/value data they encode.

## Observable Python callbacks

`dumps` follows Python's integer-index protocol during type dispatch. For a
custom object, it attempts `__index__()` once; a valid in-range integer result
is encoded before datetime and other supported-type checks. If that attempt
fails or returns an invalid value, dispatch continues and an otherwise
unsupported object raises `CBORError`. An out-of-range integer result raises
`CBORError`. An `int` subclass uses its stored integer value without calling
an overridden `__index__`. Exact built-in noninteger values skip this probe;
subclasses of supported built-ins can have `__index__` called before their
built-in contents are encoded.

The callback runs while encoding is in progress and can have side effects. In
tested behavior, when two dictionary keys encode to the same canonical bytes,
encoding still visits the later key and value in dictionary iteration order
before retaining the later value. A list callback that appends an element
during traversal does not add that element to the current encoded array; a
callback that removes a later element results in an array containing the items
actually visited. A `bytearray` subclass's `__index__` callback can mutate a
separate bytearray that is encoded later in the same traversal, and that later
payload reflects the mutation. A `str` subclass's contents are encoded without
calling its overridden `__str__`. These observations describe current
behavior, not a general transaction or mutation guarantee.

## Input scans, copies, and threading scope

`loads`, `validate`, and diagnostic formatting scan the entire input before
returning. `loads` then creates Python objects from the bytes: decoded text and
byte strings are copied into owned objects. A lossless `CBORMap` retains an
immutable `bytes` owner and the map's wire span; its accessors decode new
Python values from that span. `validate` scans without materializing a decoded
value tree. Diagnostic calls scan and build a returned Python string.

`dumps` builds a complete native output buffer and then returns Python-owned
`bytes`; it is not a streaming writer. `load` reads the whole result of one
`read()` call before decoding. The API does not claim constant-time behavior,
cryptographic security, authentication, or encryption.

The project build matrix targets regular CPython 3.9 through 3.14. The native
methods do not explicitly detach from Python or release the GIL; callbacks and
`file.read()` still run according to their Python runtime behavior. The project
does not currently target free-threaded CPython or alternative interpreters.
A test checks access to an immutable `CBORMap` snapshot from another thread
under regular GIL-enabled CPython; that does not establish a broader
parallelism or free-threaded guarantee.
