# Errors

```{py:currentmodule} dcbor
```

```{py:exception} CBORError
Exception raised when an input or value violates the dCBOR API contract.
```

`CBORError` is a direct subclass of Python's `Exception`. The API uses it for
dCBOR-level failures rather than a more specific hierarchy.

| Operation | Failure | Exception |
| --- | --- | --- |
| `dumps` | Unsupported value, out-of-range integer, naive/unsupported datetime, invalid text, excessive depth, or key-cache budget exceeded | `CBORError` |
| `loads`, `validate`, `diagnostic`, `diagnostic_flat` | Malformed, truncated, trailing, or noncanonical wire data; invalid UTF-8; depth or key-cache limit exceeded | `CBORError` |
| `loads`, `validate`, `diagnostic`, `diagnostic_flat` | Argument is not `bytes` or a `bytes` subclass | `TypeError` |
| `load` | Object has no `read` attribute; returned value is not bytes | `AttributeError`; `TypeError` |
| `load` | The reader's `read()` method raises | The original exception propagates unchanged |
| `CBORMap(pairs)` | An iterable entry yields other than two items | `ValueError` |
| `CBORMap(pairs)` | An entry is not iterable | `TypeError` |
| `CBORMap(pairs)` | Keys have duplicate canonical encodings | `CBORError` |
| `CBORMap[key]` | No key has the same canonical encoding | `KeyError` |
| `CBORTag(tag, value)` or assignment to `tag` | Tag is negative or exceeds the unsigned 64-bit range | `OverflowError` |

Argument binding also raises `TypeError` for missing required arguments,
unexpected keywords, duplicate arguments, or invalid receiver/arity. These
Python-level errors are separate from malformed-wire `CBORError` failures.
Exceptions from a `CBORMap` input iterator propagate. `dumps` may call Python
protocols during encoding: `__index__` failures fall through to type dispatch,
datetime hook failures are wrapped as `CBORError`, and out-of-range index
results raise `CBORError`. See [Types and limits](types-and-limits.md).

The table describes exception classes, not a promise that every error message
is stable. Use exception classes to handle failures rather than matching
message text.

```{doctest}
>>> import dcbor
>>> try:
...     dcbor.loads(bytearray(b"\x00"))
... except TypeError:
...     print("bytes required")
bytes required
>>> try:
...     dcbor.loads(b"\x00\x00")
... except dcbor.CBORError:
...     print("one complete item required")
one complete item required
```
