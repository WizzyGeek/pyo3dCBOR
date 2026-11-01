# `CBORTag`

```{py:currentmodule} dcbor
```

```{py:class} CBORTag(tag, value)
Mutable Python representation of a CBOR tag and its child value.
```

`tag` is an unsigned 64-bit integer from `0` through `2**64 - 1`; `value` may
be any Python object, although `dumps` can encode only supported value types.
Setting either attribute changes the object. Invalid unsigned tag arguments
raise Python's `OverflowError` during construction or assignment. An
unsupported `value` raises `CBORError` when the tag is passed to `dumps`.

```{py:attribute} CBORTag.tag
The mutable unsigned integer tag number.
```

```{py:attribute} CBORTag.value
The mutable Python child value.
```

```{py:method} CBORTag.__eq__(other)
Compare another ``CBORTag`` by tag number and Python equality of child values.
```

```{py:method} CBORTag.__repr__()
Return a tag expression with either the simple child's repr or its type name.
```

For example:

```{doctest}
>>> import dcbor
>>> tagged = dcbor.CBORTag(100, "payload")
>>> tagged.tag, tagged.value
(100, 'payload')
>>> tagged.tag = 101
>>> dcbor.loads(dcbor.dumps(tagged))
CBORTag(101, 'payload')
```

The binding gives numeric CBOR tag 1 special date handling: `loads` converts a
supported numeric timestamp to an aware UTC `datetime`; other values under
tag 1 remain `CBORTag` values. For map keys, the decoder keeps a tag-1 value as
`CBORTag` when converting it to `datetime` would change its canonical
{term}`wire bytes`.

`CBORTag` equality requires the same tag number and uses Python equality for
the child values. The object is unhashable because it is mutable. Its `repr`
shows the child with Python `repr` when the child is a string, integer, or
`None`; otherwise it shows the child's type name in angle brackets.

```{doctest}
>>> import dcbor
>>> dcbor.CBORTag(7, "text") == dcbor.CBORTag(7, "text")
True
>>> repr(dcbor.CBORTag(7, [1, 2]))
'CBORTag(7, <list>)'
>>> try:
...     hash(dcbor.CBORTag(7, None))
... except TypeError:
...     print("unhashable")
unhashable
```

Self-comparison succeeds even for a cyclic tag. Comparing two distinct cyclic
tags can raise `RecursionError` through recursive Python value equality. The
encoder does not preserve object graph references: cyclic input structures
continue recursively until the nesting limit raises `CBORError`.
