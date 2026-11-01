# Validation and diagnostics

```{py:currentmodule} dcbor
```

All three functions below accept one `bytes` object (or subclass) containing
exactly one complete item. They reject `bytearray`, `memoryview`, text, and
other non-bytes arguments with `TypeError`. Each validates the complete input
before returning a result; malformed or noncanonical input, trailing bytes,
and resource-limit violations raise `CBORError`.

## `validate`

```{py:function} validate(data)
Validate one complete dCBOR item without decoding it and return its byte length.
```

The return value is the length of the complete input buffer. `validate` does
not return a partial-consumption offset: an extra byte after the item makes the
whole call fail. It scans wire bytes without materializing the decoded Python
value tree.

```{doctest}
>>> import dcbor
>>> encoded = dcbor.dumps({"a": [1, 2]})
>>> dcbor.validate(encoded) == len(encoded)
True
>>> try:
...     dcbor.validate(b"\x00\x00")
... except dcbor.CBORError:
...     print("trailing byte rejected")
trailing byte rejected
```

## `diagnostic`

```{py:function} diagnostic(data)
Return CBOR diagnostic notation, using line breaks and indentation for groups
when the formatter's layout threshold calls for them.
```

This formats the encoded wire representation. In particular, a numeric tag 1
is printed as a tag expression even though `loads` converts that value to a
Python `datetime` when the timestamp is supported. Diagnostic formatting does
not decode the item into a Python object graph.

## `diagnostic_flat`

```{py:function} diagnostic_flat(data)
Return single-line CBOR diagnostic notation for the item.
```

The flat formatter emits one line, including for nested groups. Both
diagnostic functions use the same canonical wire validation as `validate` and
the initial scan in `loads`. They do not perform Python-specific materializing
conversions such as turning numeric tag 1 into a `datetime`. Consequently, a
canonical wire item can pass `validate` and diagnostic formatting but still
raise `CBORError` in `loads` if its timestamp cannot become a supported Python
datetime.

```{doctest}
>>> import dcbor
>>> data = dcbor.dumps({"a": [1, 2], "z": dcbor.CBORTag(100, b"x")})
>>> dcbor.diagnostic_flat(data)
'{"a": [1, 2], "z": 100(h\'78\')}'
>>> dcbor.diagnostic(data)
'{\n    "a":\n    [1, 2],\n    "z":\n    100(h\'78\')\n}'
>>> date_wire = bytes.fromhex("c1f97c00")
>>> dcbor.validate(date_wire)
4
>>> dcbor.diagnostic_flat(date_wire)
'1(Infinity)'
>>> try:
...     dcbor.loads(date_wire)
... except dcbor.CBORError:
...     print("timestamp cannot become datetime")
timestamp cannot become datetime
```

Byte strings use diagnostic hexadecimal notation. Diagnostic strings are not
an alternate framing format and do not preserve the original input bytes as a
text serialization.
