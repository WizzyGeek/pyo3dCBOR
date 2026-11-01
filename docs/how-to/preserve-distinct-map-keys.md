# Preserve distinct CBOR map keys

Python dictionaries treat `1` and `True` as the same key. If a CBOR map needs
to preserve those as distinct keys, use {py:class}`dcbor.CBORMap`. It identifies
keys by their canonical encoded form, the glossary's
{term}`encoded-key identity`.

```{doctest}
>>> import dcbor
>>> mapping = dcbor.CBORMap([(1, "integer"), (True, "boolean")])
>>> wire = dcbor.dumps(mapping)
>>> restored = dcbor.loads(wire)
>>> type(restored).__name__
'CBORMap'
>>> restored[1], restored[True]
('integer', 'boolean')
>>> len(restored)
2
>>> len(dict(restored.items()))
1
```

The final line shows why converting the map back to `dict` loses the
distinction. Keep the `CBORMap` when both entries matter. Decoding ordinary
maps still returns a dictionary unless a key cannot be represented safely as
a Python dictionary key or distinct CBOR keys compare equal in Python.

`CBORMap` can also use compound keys, including arrays:

```{doctest}
>>> import dcbor
>>> coordinates = dcbor.CBORMap([([40, 12], "site")])
>>> coordinates[[40, 12]]
'site'
```

The map is an immutable {term}`CBORMap snapshot`: keys and values returned
from it are fresh decoded snapshots. Construct it from an iterable of
key-value pairs when the source data contains keys that a `dict` would merge.
Duplicate canonical keys are rejected, including text keys that become the
same after NFC normalization.

See the [CBORMap API](../reference/cbor-map.md) for lookup and snapshot
behavior, and the [type reference](../reference/types-and-limits.md) for
Python map conversions.
