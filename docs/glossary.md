# Glossary

(glossary)=

```{glossary}
CBOR
    Concise Binary Object Representation, the binary data format specified by
    RFC 8949.

dCBOR
    The deterministic CBOR profile used by this project.

canonical encoding
    The one wire representation selected for a value by a particular profile.

preferred encoding
    The shortest allowed width for an integer or length header, or the
    smallest exact width for a float. Integral floats may reduce to integers
    within the documented interval.

NFC
    Unicode Normalization Form C. It orders canonically equivalent combining
    marks and composes when possible; it does not apply compatibility
    substitutions.

encoded-key identity
    The canonical encoded bytes that identify a map key, even when Python
    equality or hashing would merge or reject that key.

CBORMap snapshot
    An immutable, read-only `CBORMap` retaining an encoded map snapshot. Its
    accessors decode fresh Python keys and values.

tag
    A CBOR value pairing a tag number with a child value. The number supplies
    application meaning; this library interprets numeric tag 1 as a datetime
    when the timestamp is supported.

wire bytes
    The serialized CBOR byte sequence stored or exchanged by an application.

round trip
    Encoding a value and decoding the resulting bytes. The Python type or text
    may be normalized while the documented dCBOR value and key identity are
    retained.

depth limit
    The library's maximum of 512 nested arrays, maps, and tags during encoding
    or decoding.

key-cache budget
    The 16 MiB aggregate limit on canonical encoded map-key storage, including
    nested key encodings. It does not limit total input size or process memory.

framing
    A higher-level convention identifying where one serialized message ends
    and another begins. This API decodes a complete byte string;
    `load(file)` reads one complete `read()` result instead of consuming
    successive items from a stream.
```
