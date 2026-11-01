# Determinism and wire identity

(determinism)=

## Why deterministic bytes matter

{term}`CBOR` can represent the same value with different byte sequences. An integer
can use a wider-than-needed argument; a float can use more bits than its value
needs; maps can list entries in different orders; and Unicode can express
visually equivalent text in more than one way. A {term}`canonical encoding`
chooses one wire representation for each value under a specified profile.

`dcbor` encodes values according to its {term}`dCBOR` profile. The encoded bytes are
the stable representation to compare, store, or transmit. Decoding still
returns Python values, and some Python details are intentionally normalized
along the way. See the [Python API reference](../reference/index.md) for
the exact accepted values and function contracts.

(profile-choices)=

## What the profile chooses

The writer uses the {term}`preferred encoding`: shortest valid integer and
length headers, and the smallest exact binary width when a value remains a
float. It sorts map entries by the complete encoded key bytes. Text is normalized to
{term}`NFC` before it is encoded. The reader checks these choices when it
validates incoming {term}`wire bytes`; it rejects a representation that is
valid CBOR but is not canonical dCBOR.

Map ordering depends on encoded keys, not Python insertion order or
`repr(key)`. Therefore maps with the same canonical key/value pairs produce
the same wire ordering regardless of how their entries were inserted.

(numeric-profile)=

## Numeric reduction and floating-point edge cases

An explicitly supplied Python integer is encoded as an integer throughout the
range `[-2**64, 2**64 - 1]`. An integral Python float reduces to an integer
only in `[-2**63, 2**64)`. Outside that float-reduction interval it remains a
floating-point value and uses the smallest exact float width. The negative
boundary is intentionally asymmetric: the explicit integer `-(2**64)` is
accepted as an integer, while the equal-valued float `-float(2**64)` remains a
float. These are separate input-type rules, not a comparison of numeric
equality.

Negative zero is integral, so `-0.0` reduces to integer zero and its sign is
not preserved in the wire representation. NaNs with different signs or
payloads encode as the single canonical half-precision NaN. On decoding,
nonpreferred float widths and noncanonical NaN encodings are rejected.

These rules mean that a {term}`round trip` preserves the profile's value and
identity guarantees, not every detail of the original Python object. For
example, decoding a float that reduced to an integer returns a Python `int`.
See [Types, identity, and limits](../reference/types-and-limits.md#floats-and-integers)
for the full numeric mapping.

(datetime-key-identity)=

## Datetimes and map keys

An aware `datetime.datetime` is represented by CBOR tag 1 with an epoch
timestamp. Timestamps use floating-point seconds, so Python's microsecond
resolution and range matter. Ordinary numeric tag-1 values decode to aware
UTC datetimes, subject to those Python limits.

A map key must retain its encoded identity so that lookup can find the same
key after decoding. A numeric tag-1 key becomes a `datetime` only when
converting it to a datetime and encoding that datetime again reproduces the
original bytes exactly. If conversion would change the timestamp bytes, the
key stays a {py:class}`dcbor.CBORTag`. This preserves keys whose fractional
seconds cannot survive Python datetime precision. See also
{term}`encoded-key identity` and the
[map identity explanation](types-and-normalization.md#maps-and-key-identity).
