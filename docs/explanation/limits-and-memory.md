# Limits and memory behavior

(limits-and-memory)=

`dcbor` has explicit limits for nesting and for encoded map-key storage. These
are library limits, not limits in the {term}`CBOR` format. The {term}`depth limit` and
{term}`key-cache budget` bound particular recursive and key-cache work; they
are not a maximum message size or a cap on total process memory.

(depth-limit)=

## Nesting depth

Arrays, maps, and tags may be nested up to 512 levels when encoding or
decoding. Tag wrappers count as levels, including the tag used for datetimes.
Deeper input or Python structures raise {py:exc}`dcbor.CBORError`. Cyclic Python containers
are not represented as references in CBOR; they eventually fail at the same
depth guard rather than being serialized as a graph.

(key-cache-budget)=

## Aggregate encoded-key budget

Canonical map-key encodings share a 16 MiB aggregate budget. Nested keys are
counted at every level where their bytes contribute to a retained key
encoding; repeated occurrences are charged again. The accounting uses the
normalized text bytes and CBOR headers that contribute to the canonical key
bytes. Exceeding the budget raises `CBORError`.

This budget bounds encoded-key cache amplification. It does not cap the total
wire message, all map values, the full encoding produced by `dumps()`, or all
temporary and Python object memory. Applications processing untrusted data
should apply their own message-size and overall resource policies as well.

(whole-buffer-memory)=

## Whole-buffer operations and copies

{py:func}`dcbor.dumps` constructs the full encoded result before returning
Python `bytes`.
The current implementation first holds a native output buffer, then copies
the final bytes into the Python result. It is not a streaming writer.

{py:func}`dcbor.loads` accepts one complete immutable byte string. The
decoder validates the complete input before it constructs Python values;
Python text, byte strings, and containers then own their decoded storage. A decoded
{py:class}`dcbor.CBORMap` snapshot retains an owner reference to the input
bytes and the encoded map span it represents. Its key/value accessors decode
fresh Python values when called, which can allocate again.

{py:func}`dcbor.load` calls the file object's no-argument `read()` once and
decodes the returned bytes. The file stays caller-owned, but the data is read
into memory as a whole; this method is also not streaming. For exact input types, return
values, and error contracts, see
[Serialization and decoding](../reference/serialization.md).

(support-scope)=

## Support and guarantees

The project CI matrix targets regular GIL-enabled CPython 3.9–3.14. It does
not currently include free-threaded CPython or alternative interpreters.
These documented behaviors do not promise constant-time processing,
application-level thread-safety guarantees, or a hard bound on total memory.
The 512-level and 16 MiB limits should not be treated as a general security
boundary.
