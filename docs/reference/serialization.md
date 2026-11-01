# Serialization and decoding

```{py:currentmodule} dcbor
```

## `dumps`

```{py:function} dumps(obj)
Encode one supported Python value as canonical dCBOR and return its complete
wire representation as `bytes`.
```

`dumps` accepts the value types listed in [Types and limits](types-and-limits.md).
Maps are sorted by the bytewise order of their canonical encoded keys. String
values and map keys are normalized to {term}`NFC`; floats use the {term}`preferred encoding`
rules described there.

The call builds the full result before returning. It has no file or streaming
variant in this API. Unsupported values, explicit integers outside the dCBOR
integer range, excessive nesting, and map-key cache exhaustion raise
`CBORError`. Errors from Python protocols can be caught or converted during
value dispatch; see [Errors](errors.md) and [Types and limits](types-and-limits.md).

```{doctest}
>>> import dcbor
>>> dcbor.dumps([1, "é", b"x"]).hex()
'830162c3a94178'
>>> dcbor.loads(dcbor.dumps((1, 2)))
[1, 2]
```

Tuples encode as arrays and decode as lists. `dumps` does not promise to leave
the input object unchanged when Python callbacks run during conversion; its
observed `__index__` and list-traversal behavior is described in
[Types and limits](types-and-limits.md).

## `loads`

```{py:function} loads(data)
Validate and decode one complete dCBOR item from a `bytes` object.
```

`data` must be `bytes` or a subclass of `bytes`. A `bytearray`, `memoryview`,
text string, or integer sequence is rejected with `TypeError`; convert it to
`bytes` explicitly if that is the intended input. The complete buffer must
contain exactly one well-formed canonical dCBOR item. Truncation, trailing
bytes, invalid UTF-8, non-NFC text, duplicate or out-of-order map keys,
noncanonical numeric encodings, or a resource-limit violation raises
`CBORError`.

The binding scans the complete input before creating decoded Python values.
Text and byte-string payloads become owned Python objects. A lossless
{term}`CBORMap snapshot` can retain the original immutable `bytes` object and a
span into it; its public accessors decode fresh values when called.

```{doctest}
>>> import dcbor
>>> dcbor.loads(bytes.fromhex("a2616101617a81f5"))
{'a': 1, 'z': [True]}
>>> type(dcbor.loads(dcbor.dumps({"a": 1}))) is dict
True
```

Maps whose keys Python `dict` cannot represent without losing key identity
decode as `CBORMap`. For example, distinct encoded keys `1` and `true` compare
equal as Python keys, so the lossless representation preserves both. See
[`CBORMap`](cbor-map.md) and [encoded-key identity](types-and-limits.md).

## `load`

```{py:function} load(file)
Call ``file.read()`` once, then validate and decode the returned bytes.
```

`file` is a file-like object with a no-argument `read` method. The method must
return `bytes` (or a `bytes` subclass); `load` does not repeatedly read chunks,
accept a path in place of an open reader, or close the object. The caller owns
its lifetime. A missing `read` method raises `AttributeError`; an exception
raised by `read` propagates unchanged; a non-bytes result raises `TypeError`.
After a bytes result is returned, decoding follows the same validation and
error rules as `loads`.

```{doctest}
>>> import dcbor
>>> class Reader:
...     def __init__(self):
...         self.calls = 0
...     def read(self):
...         self.calls += 1
...         return b"\x00"
>>> reader = Reader()
>>> dcbor.load(reader), reader.calls
(0, 1)
```

`load` reads the entire value into a single returned `bytes` object. The API
does not provide incremental decoding or a `dump` function.
