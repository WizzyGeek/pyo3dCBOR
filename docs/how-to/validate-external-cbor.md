# Validate external dCBOR data

Use {py:func}`dcbor.loads` when you need a Python value: it validates the
complete input before decoding it. Use {py:func}`dcbor.validate` when you need
to check the bytes without materializing Python objects. Both reject malformed
or noncanonical input with {py:class}`dcbor.CBORError`.

```{doctest}
>>> import dcbor
>>> valid = bytes.fromhex("a1616101")
>>> dcbor.validate(valid)
4
>>> dcbor.loads(valid)
{'a': 1}
```

`validate` returns the number of bytes consumed, which is the input length for
a valid complete item. It rejects trailing bytes and noncanonical encodings:

```{doctest}
>>> import dcbor
>>> def rejected(data):
...     try:
...         dcbor.validate(data)
...     except dcbor.CBORError:
...         return True
...     return False
>>> rejected(bytes.fromhex("1800"))  # zero encoded with a non-preferred width
True
>>> rejected(bytes.fromhex("a1616101") + b"\x00")  # a second trailing item
True
```

If decoding is needed, call `loads` directly; calling `validate` first would
repeat its wire scan. Catch `CBORError` at the boundary where your application
handles invalid payloads:

```{doctest}
>>> import dcbor
>>> payload = bytes.fromhex("ff")
>>> try:
...     value = dcbor.loads(payload)
... except dcbor.CBORError:
...     print("invalid dCBOR")
invalid dCBOR
```

## Set an application size limit

The decoder checks nesting depth and aggregate encoded map-key storage, but it
does not impose a total input-size limit. Set a limit that fits your
application before decoding. For network input, also cap the amount read by
the transport layer; checking `len(payload)` after an unbounded read cannot
undo that allocation.

```{doctest}
>>> import dcbor
>>> MAX_PAYLOAD = 1_000_000
>>> def decode_payload(payload):
...     if len(payload) > MAX_PAYLOAD:
...         raise ValueError("payload is too large")
...     return dcbor.loads(payload)
>>> decode_payload(bytes.fromhex("a1616101"))
{'a': 1}
```

The built-in limits include a {term}`depth limit` of 512 and a
{term}`key-cache budget` of 16 MiB for aggregate encoded map keys. See the
[types and limits reference](../reference/types-and-limits.md) and the
[errors API](../reference/errors.md) for the full behavior.
