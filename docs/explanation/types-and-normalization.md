# Python types and normalization

(types-and-normalization)=

Python types and {term}`CBOR` data-model values do not have a one-to-one mapping.
Python dictionaries require hashable keys and treat equal keys as the same
entry. CBOR maps can use arbitrary CBOR values as keys and distinguish keys
whose encodings differ. `dcbor` therefore maps values into Python forms that
preserve the distinctions its API promises.

The [Python API reference](../reference/index.md) contains the complete
type mapping. This page explains two places where normalization and Python
container semantics affect identity.

(text-normalization)=

## Text is normalized to NFC

When encoding a Python `str`, `dcbor` applies {term}`NFC` before writing UTF-8
text. Two distinct Python strings that normalize to the same NFC text produce
the same encoded text. This is canonical equivalence; compatibility
normalization such as NFKC is not applied. Lone surrogate code points cannot
be represented as valid CBOR UTF-8 text and are rejected.

The decoder does not silently normalize bytes it receives. It validates that
text is already NFC and rejects non-NFC input as noncanonical. This keeps the
wire rule symmetric: encoders produce normalized text, and decoders accept
only the normalized representation.

(map-key-identity)=

## Maps and key identity

For a Python `dict`, two distinct keys can normalize to identical encoded
keys. The established behavior is last-entry-wins: when canonical key bytes
collide, the later dictionary value is retained. That can discard an earlier
value, so applications that need to detect or preserve collisions should use
{py:class}`dcbor.CBORMap` and handle duplicate-key errors explicitly.

`CBORMap` is a read-only {term}`CBORMap snapshot`. Its keys are identified by
their canonical encoded bytes rather than Python equality or hashing. For
example, Python considers `1 == True`, but CBOR has distinct integer and
boolean encodings. `CBORMap` can preserve both keys. It can also preserve
composite keys such as arrays, nested maps, and tagged values that a Python
`dict` cannot use directly.

On decoding, ordinary maps become `dict` when their keys can be represented
there without collapsing distinct CBOR keys. A map that contains an unhashable
key or keys that Python considers equal despite distinct encodings becomes a
`CBORMap` snapshot instead. This fallback preserves canonical map identity
instead of silently merging entries.

The snapshot retains immutable encoded data. Its accessors decode keys and
values afresh, so returned mutable Python containers are independent values;
changing one does not change the snapshot. Lists returned by `keys()`,
`values()`, and `items()` are also new results on each call.

(datetime-key-identity-types)=

## Datetime keys keep exact identity

Numeric CBOR tag 1 values normally become aware UTC `datetime` objects. A
datetime has microsecond precision, while the tag value can contain a finer
fraction. If a date key cannot be converted to a Python datetime and re-encoded
with exactly the same bytes, it remains a {py:class}`dcbor.CBORTag` carrying its numeric value.
This lets the key's original encoded identity remain available for lookup,
including sub-microsecond timestamps.

This conversion rule applies recursively to keys inside composite map keys.
For value mappings and supported Python types, see the
[Python API reference](../reference/index.md).
