# Make stable digests from dCBOR bytes

If an application needs a content identifier for a supported Python value,
hash its dCBOR bytes with a cryptographic digest such as SHA-256. dCBOR
canonical encoding sorts map keys and normalizes text to {term}`NFC`, so
equivalent input dictionaries in this example have the same encoded bytes and
digest.

```{doctest}
>>> import hashlib
>>> import dcbor
>>> first = {"label": "Café", "count": 2}
>>> same_value = {"count": 2, "label": "Cafe\u0301"}
>>> wire = dcbor.dumps(first)
>>> wire == dcbor.dumps(same_value)
True
>>> digest = hashlib.sha256(wire).digest()
>>> digest == hashlib.sha256(dcbor.dumps(same_value)).digest()
True
```

The digest is computed from {term}`wire bytes`. The comparison above checks
that two representations of the same application value produce identical
bytes; it does not rely on a hard-coded digest produced by the same call.

## Keep the value contract stable

- Use only the documented Python values and agree with other producers on the
  dCBOR profile and value mapping. Start with the
  [type and limits reference](../reference/types-and-limits.md).
- dCBOR normalizes strings to NFC. If your application distinguishes two
  strings that normalize to the same text, encode that distinction explicitly
  in your data model before hashing.
- Build maps from data that preserves every intended key. A Python `dict`
  cannot contain `1` and `True` as separate keys; use
  {py:class}`dcbor.CBORMap` when those CBOR key identities matter. See
  [preserve distinct map keys](preserve-distinct-map-keys.md).
- Use `hashlib` rather than Python's built-in `hash()`, which is intended for
  in-process table lookup and is not a persistent identifier format.

Canonical bytes make the digest reproducible for values under this profile.
The digest does not define application semantics or replace a protocol's
agreement about which values are equivalent. For the encoding rules, see the
[serialization API](../reference/serialization.md) and the glossary entry for
{term}`canonical encoding`.
