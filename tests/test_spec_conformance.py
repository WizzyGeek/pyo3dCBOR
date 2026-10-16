"""Independent wire expectations for dCBOR draft-18 sections 2.1--2.7.

Reference: https://datatracker.ietf.org/doc/html/draft-mcnally-deterministic-cbor-18
These tests deliberately do not use dumps() to construct decoder inputs.
Round trips alone can miss an encoder and decoder sharing the same defect.
The full negative CBOR integer range is discussed separately in
SPEC_REVIEW.md because draft-18's normative text and Appendix A disagree.
"""

import math
import struct
import unicodedata

import pytest

import dcbor


READERS = (dcbor.loads, dcbor.validate, dcbor.diagnostic, dcbor.diagnostic_flat)

# Non-numeric tags keep datetime conversion out of these wire-format tests.
CONTEXTS = (
    pytest.param(b"", b"", id="root"),
    pytest.param(b"\x81", b"", id="array-element"),
    pytest.param(b"\xa1", b"\x00", id="map-key"),
    pytest.param(b"\xa1\x00", b"", id="map-value"),
    pytest.param(b"\xd8\xc9", b"", id="tag-201-content"),
)


# Literal bytes check shortest float width, subnormals, integer reduction and
# both sides of the reduction range independently of the upstream Rust codec.
NUMBERS = (
    (1.5, "f93e00"),
    (2345678.25, "fa4a0f2b39"),
    (1.2, "fb3ff3333333333333"),
    (2345678.0, "1a0023cace"),
    (-2345678.0, "3a0023cacd"),
    (0.0, "00"),
    (-0.0, "00"),
    (2.0**-24, "f90001"),
    (2.0**-149, "fa00000001"),
    (2.0**-1074, "fb0000000000000001"),
    (2.0**-1022, "fb0010000000000000"),
    (2.0**-14, "f90400"),
    (65504.0, "19ffe0"),
    (33554430.0, "1a01fffffe"),
    (-float(2**63), "3b7fffffffffffffff"),
    (math.nextafter(-float(2**63), math.inf), "3b7ffffffffffffbff"),
    (math.nextafter(float(2**64), 0.0), "1bfffffffffffff800"),
    (float(2**64), "fa5f800000"),
    # Section 2.5 requires these to STAY floats: they are below -2**63.
    (math.nextafter(-float(2**63), -math.inf), "fbc3e0000000000001"),
    (-18446742974197924000.0, "fadf7fffff"),
    (-float(2**64), "fadf800000"),
    (math.nextafter(-float(2**64), -math.inf), "fbc3f0000000000001"),
    (3.4028234663852886e38, "fa7f7fffff"),
    (3.402823466385289e38, "fb47efffffe0000001"),
    (float.fromhex("0x1.fffffffffffffp+1023"), "fb7fefffffffffffff"),
    (math.inf, "f97c00"),
    (-math.inf, "f9fc00"),
    (math.nan, "f97e00"),
)


@pytest.mark.parametrize("number,wire_hex", NUMBERS, ids=[h for _, h in NUMBERS])
def test_numeric_encoding_matches_independent_vectors(number, wire_hex):
    assert dcbor.dumps(number) == bytes.fromhex(wire_hex)


@pytest.mark.parametrize("reader", READERS)
@pytest.mark.parametrize("number,wire_hex", NUMBERS, ids=[h for _, h in NUMBERS])
def test_numeric_decoding_matches_independent_vectors(reader, number, wire_hex):
    encoded = bytes.fromhex(wire_hex)
    decoded = reader(encoded)
    if reader is dcbor.loads:
        if math.isnan(number):
            assert math.isnan(decoded)
        else:
            assert decoded == number
            # Outside DCBOR_INT, even integral values retain floating type.
            reduced = math.isfinite(number) and number.is_integer() and -(2**63) <= number < 2**64
            assert type(decoded) is (int if reduced else float)
    elif reader is dcbor.validate:
        assert decoded == len(encoded)


# A large negative float must also remain valid inside every container kind.
@pytest.mark.parametrize("reader", READERS)
@pytest.mark.parametrize("prefix,suffix", CONTEXTS)
def test_outside_reduction_range_float_is_valid_recursively(reader, prefix, suffix):
    reader(prefix + bytes.fromhex("fadf7fffff") + suffix)


@pytest.mark.parametrize("reader", READERS)
@pytest.mark.parametrize("prefix,suffix", CONTEXTS)
@pytest.mark.parametrize("wire_hex", (
    "5fff", "7fff", "9fff", "bfff",  # all four indefinite-length types
    "5f4161ff", "7f6161ff", "9f00ff", "bf0000ff",  # nonempty too
    "1800", "3800",  # overlong positive and negative integer
    "5800", "7800", "9800", "b800", "d80000",  # overlong lengths/tag
    "190018", "1a00000100", "1b0000000000010000",  # wider integer forms
    "f814", "f815", "f816",  # false/true/null using an extra byte
    "f94a00", "fb3ff8000000000000",  # unreduced 12 / over-wide 1.5
    "63e284ab",  # ANGSTROM SIGN: valid UTF-8, but not NFC
    "6365cc81",  # decomposed e + acute accent: valid UTF-8, but not NFC
    "62c080",  # overlong UTF-8 encoding of NUL
    "63eda080",  # UTF-8 encoded surrogate
    "64f4908080",  # code point above Unicode maximum
    "6180", "62e282",  # stray continuation byte / truncated sequence
    "a22001181800",  # length-first map ordering instead of bytewise ordering
))
def test_reject_nonconforming_items_recursively(reader, prefix, suffix, wire_hex):
    with pytest.raises(dcbor.CBORError):
        reader(prefix + bytes.fromhex(wire_hex) + suffix)


@pytest.mark.parametrize("reader", READERS)
def test_all_disallowed_simple_values_are_rejected(reader):
    for value in (*range(20), 23, *range(32, 256)):
        encoded = bytes([0xE0 | value]) if value < 24 else bytes([0xF8, value])
        with pytest.raises(dcbor.CBORError):
            reader(encoded)


@pytest.mark.parametrize("reader", READERS)
@pytest.mark.parametrize("major", range(8))
@pytest.mark.parametrize("info", (28, 29, 30))
def test_reserved_additional_information_is_rejected(reader, major, info):
    with pytest.raises(dcbor.CBORError):
        reader(bytes([(major << 5) | info]))


@pytest.mark.parametrize("reader", READERS)
def test_bytewise_map_order_differs_from_length_first_order(reader):
    # 24 = 1818 sorts BEFORE -1 = 20, despite requiring more encoded bytes.
    encoded = bytes.fromhex("a21818002001")
    decoded = reader(encoded)
    if reader is dcbor.loads:
        assert list(decoded.items()) == [(24, 0), (-1, 1)]
    assert dcbor.dumps({-1: 1, 24: 0}) == encoded


@pytest.mark.parametrize("reader", READERS)
@pytest.mark.parametrize("prefix,suffix", CONTEXTS)
@pytest.mark.parametrize("wire_hex", (
    "a200000001",  # integer keys
    "a260006001",  # text keys
    "a280008001",  # array keys
    "a2d8640000d8640001",  # tagged keys
    "a2f97e0000f97e0001",  # canonical NaN keys, despite Python NaN != NaN
))
def test_duplicate_keys_are_rejected_recursively(reader, prefix, suffix, wire_hex):
    with pytest.raises(dcbor.CBORError):
        reader(prefix + bytes.fromhex(wire_hex) + suffix)


def test_tagged_keys_remain_distinct_from_untagged_numbers():
    # Section 2.5: neither the tag number nor the tag wrapper can be discarded.
    encoded = bytes.fromhex("a30000d8640001d8650002")
    value = dcbor.loads(encoded)
    assert len(value) == 3
    assert value[0] == 0
    assert value[dcbor.CBORTag(100, 0)] == 1
    assert value[dcbor.CBORTag(101, 0)] == 2
    assert dcbor.dumps(value) == encoded


@pytest.mark.parametrize("first,second", (
    (0, -0.0),
    (math.nan, struct.unpack(">d", bytes.fromhex("fff8000000000001"))[0]),
    (["e\u0301"], ["é"]),
    ([1], (1.0,)),
    (b"a", bytearray(b"a")),
    (dcbor.CBORTag(100, 1), dcbor.CBORTag(100, 1.0)),
    ({"a": 1, "b": 2}, {"b": 2, "a": 1}),
))
def test_map_constructor_detects_canonical_key_collisions(first, second):
    with pytest.raises(dcbor.CBORError, match="duplicate"):
        dcbor.CBORMap([(first, "first"), (second, "second")])


@pytest.mark.parametrize("text", ("e\u0301", "\u212b", "\u1100\u1161", "a\u0315\u0300"))
def test_encoder_normalizes_unicode_beyond_one_composed_character(text):
    expected = unicodedata.normalize("NFC", text).encode("utf-8")
    assert len(expected) < 24
    encoded = bytes([0x60 + len(expected)]) + expected
    assert dcbor.dumps(text) == encoded
    assert dcbor.loads(encoded) == unicodedata.normalize("NFC", text)


def test_nfc_is_not_compatibility_normalization():
    # These change under NFKC, but MUST retain their distinct NFC forms.
    assert dcbor.dumps("①") == bytes.fromhex("63e291a0")
    assert dcbor.dumps("①") != dcbor.dumps("1")


def _small_integer_wire(number):
    """Independent preferred integer writer, only needed for binary16 values."""
    major = 0 if number >= 0 else 0x20
    argument = number if number >= 0 else -1 - number
    if argument < 24:
        return bytes([major | argument])
    if argument < 256:
        return bytes([major | 24, argument])
    return bytes([major | 25]) + argument.to_bytes(2, "big")


def test_every_binary16_encoding_has_the_specified_canonical_form():
    # Covers every sign, exponent, significand, subnormal, NaN payload, and
    # signed zero. Python's struct module supplies an independent IEEE oracle.
    for bits in range(1 << 16):
        encoded = b"\xf9" + bits.to_bytes(2, "big")
        number = struct.unpack(">e", encoded[1:])[0]
        if math.isnan(number):
            expected = bytes.fromhex("f97e00")
        elif math.isfinite(number) and number.is_integer():
            expected = _small_integer_wire(int(number))
        else:
            expected = encoded
        assert dcbor.dumps(number) == expected, f"binary16 {bits:04x}"
        for reader in READERS:
            if encoded == expected:
                reader(encoded)
            else:
                with pytest.raises(dcbor.CBORError):
                    reader(encoded)
