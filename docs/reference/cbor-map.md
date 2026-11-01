# `CBORMap`

```{py:currentmodule} dcbor
```

```{py:class} CBORMap(pairs)
Immutable map snapshot whose keys are identified by their canonical encoded
wire bytes.
```

Use `CBORMap` when a Python `dict` would reject a key as unhashable or merge
distinct encoded keys that compare equal in Python. A snapshot can preserve
keys such as `1` and `True`, list keys, nested maps, and tagged keys. Converting
it to `dict` may fail for unhashable keys or lose distinctions such as `1`
versus `True`.

The constructor accepts an iterable of two-item iterables. It encodes each key
and value into an immutable snapshot; later changes to the source pair
objects do not change the snapshot. A pair with other than two items raises
`ValueError`. A non-iterable entry raises `TypeError`. Each pair iterator is
read at most three times to distinguish two items from an overlong pair. If
two keys have the same canonical encoding, construction raises `CBORError`
instead of choosing one value.

```{doctest}
>>> import dcbor
>>> mapping = dcbor.CBORMap([(1, "integer"), (True, "boolean")])
>>> len(mapping), mapping[1], mapping[True]
(2, 'integer', 'boolean')
>>> list(mapping)
[1, True]
>>> dcbor.dumps(mapping).hex()
'a20167696e7465676572f567626f6f6c65616e'
```

`CBORMap` is frozen and unhashable. Its methods return decoded Python objects
from the stored wire data. `keys()`, `values()`, and `items()` return new lists;
the keys and values inside those lists are fresh decoded values. Mutating a
returned list or decoded container does not modify the snapshot. Iteration
iterates a newly decoded key list. Accessor order follows the snapshot's
canonical encoded-key order.

```{py:method} CBORMap.__len__()
Return the number of entries.
```

```{py:method} CBORMap.__getitem__(key)
Return the value whose canonical encoded key matches ``key``.
```

Missing keys raise `KeyError` with the lookup key. Keys need not be hashable:
lookup encodes the candidate key and compares its bytes. A value that cannot
be encoded as a dCBOR key raises `CBORError` during lookup.

```{py:method} CBORMap.__contains__(key)
Return whether an entry has the same canonical encoded key.
```

An encodable but missing key returns `False`. An unencodable lookup key raises
`CBORError`, as it does for `__getitem__`.

```{py:method} CBORMap.__iter__()
Iterate over freshly decoded keys in canonical encoded-key order.
```

```{py:method} CBORMap.keys()
Return a new list of freshly decoded keys.
```

```{py:method} CBORMap.values()
Return a new list of freshly decoded values.
```

```{py:method} CBORMap.items()
Return a new list of ``(key, value)`` tuples with freshly decoded contents.
```

```{py:method} CBORMap.get(key, default=None)
Return the value for ``key``, or ``default`` when no encoded key matches.
```

`get` defaults to `None`. It only uses the default for a missing key;
conversion errors for an unencodable key still propagate.

```{py:method} CBORMap.__eq__(other)
Compare another ``CBORMap`` by its complete canonical encoded bytes.
```

Equality compares the stored encoded map bytes. It does not compare a
`CBORMap` structurally against an ordinary `dict`. `CBORMap` is unhashable.
Its `repr` is `CBORMap(...)` containing single-line diagnostic notation.

```{py:method} CBORMap.__repr__()
Return ``CBORMap(...)`` containing single-line diagnostic notation.
```

```{doctest}
>>> import dcbor
>>> source_key, source_value = [1], [2]
>>> snapshot = dcbor.CBORMap([(source_key, source_value)])
>>> source_key.append(3)
>>> source_value.append(4)
>>> snapshot[[1]]
[2]
>>> snapshot[[1]].append(5)
>>> snapshot[[1]]
[2]
>>> snapshot.items()
[([1], [2])]
>>> repr(dcbor.CBORMap([(1, "one")]))
'CBORMap({1: "one"})'
```

When `loads` encounters a map that cannot be represented faithfully by a Python
`dict`, it returns a `CBORMap` backed by the original immutable input bytes and
a span for that map. Its accessors still decode fresh values. See
[Serialization and decoding](serialization.md) and
[Types and limits](types-and-limits.md).
