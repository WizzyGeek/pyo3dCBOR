"""Independent wire oracles for dCBOR numeric reduction boundaries.

Float reduction follows draft-18 section 2.5's [-2**63, 2**64) interval.
Explicit Python integers retain the library's documented [-2**64, 2**64-1]
range, including values outside that float-reduction interval.
"""
import math

import dcbor
import pytest


LARGE_NEGATIVE_FLOATS = [
    (-float(2**64), "fadf800000"),
    (math.nextafter(-float(2**63), -math.inf), "fbc3e0000000000001"),
    (-18446742974197924000.0, "fadf7fffff"),
]


@pytest.mark.parametrize("number,hex_data", LARGE_NEGATIVE_FLOATS)
def test_large_negative_float_literal_wire(number, hex_data):
    encoded = bytes.fromhex(hex_data)
    assert dcbor.validate(encoded) == len(encoded)
    decoded = dcbor.loads(encoded)
    assert type(decoded) is float
    assert decoded == number
    assert dcbor.dumps(decoded) == encoded
    assert dcbor.dumps(number) == encoded
    # Parsing diagnostics independently catches a numerically corrupted display
    # even if decoding/encoding happen to share a conversion bug.
    assert float(dcbor.diagnostic(encoded)) == number
    assert float(dcbor.diagnostic_flat(encoded)) == number


@pytest.mark.parametrize("number,hex_data", LARGE_NEGATIVE_FLOATS)
@pytest.mark.parametrize("context", ["array", "dict_value", "dict_key", "tag", "map_key", "nested_key", "map_inside_key", "nested_map_tag"])
def test_large_negative_float_preserved_in_containers(number, hex_data, context):
    number_bytes = bytes.fromhex(hex_data)
    if context == "array":
        source, expected = [number], b"\x81" + number_bytes
    elif context == "dict_value":
        source, expected = {0: number}, b"\xa1\x00" + number_bytes
    elif context == "dict_key":
        source, expected = {number: 0}, b"\xa1" + number_bytes + b"\x00"
    elif context == "tag":
        source, expected = dcbor.CBORTag(100, number), b"\xd8\x64" + number_bytes
    elif context == "map_key":
        source = dcbor.CBORMap([(number, 0)])
        expected = b"\xa1" + number_bytes + b"\x00"
    elif context == "map_inside_key":
        source = dcbor.CBORMap([({0: number}, 0)])
        expected = b"\xa1\xa1\x00" + number_bytes + b"\x00"
    elif context == "nested_map_tag":
        source = [{0: dcbor.CBORTag(100, number)}]
        expected = b"\x81\xa1\x00\xd8\x64" + number_bytes
    else:
        source = dcbor.CBORMap([([dcbor.CBORTag(100, number)], 0)])
        expected = b"\xa1\x81\xd8\x64" + number_bytes + b"\x00"
    assert dcbor.dumps(source) == expected
    decoded = dcbor.loads(expected)
    assert dcbor.dumps(decoded) == expected
    if context in {"dict_key", "map_key", "nested_key", "map_inside_key"}:
        for key in decoded:
            assert key in decoded
            assert decoded[key] == 0
        assert dcbor.dumps(dcbor.CBORMap(decoded.items())) == expected
    elif context == "nested_map_tag":
        assert type(decoded[0][0].value) is float
        assert decoded[0][0].value == number
    elif context == "array":
        assert type(decoded[0]) is float
        assert decoded[0] == number
    elif context == "dict_value":
        assert type(decoded[0]) is float
        assert decoded[0] == number
    else:
        assert type(decoded.value) is float
        assert decoded.value == number


def test_float_and_integer_negative_u64_keys_stay_distinct():
    floating = -float(2**64)
    integer = -(2**64)
    assert floating == integer
    mapping = dcbor.CBORMap([(floating, "float"), (integer, "integer")])
    expected = bytes.fromhex("a23bffffffffffffffff67696e7465676572fadf80000065666c6f6174")
    assert dcbor.dumps(mapping) == expected
    for candidate in (mapping, dcbor.loads(expected)):
        assert isinstance(candidate, dcbor.CBORMap)
        assert len(candidate) == 2
        assert candidate[floating] == "float"
        assert candidate[integer] == "integer"
        for key in candidate.keys():
            assert key in candidate
            assert candidate[key] == ("float" if type(key) is float else "integer")
        assert dcbor.dumps(dcbor.CBORMap(candidate.items())) == expected


@pytest.mark.parametrize("number,hex_data,expected_type", [
    (-float(2**63), "3b7fffffffffffffff", int),
    (math.nextafter(-float(2**63), 0.0), "3b7ffffffffffffbff", int),
    (math.nextafter(-float(2**63), -math.inf), "fbc3e0000000000001", float),
    (math.nextafter(float(2**64), 0.0), "1bfffffffffffff800", int),
    (float(2**64), "fa5f800000", float),
    (math.nextafter(float(2**64), math.inf), "fb43f0000000000001", float),
    (math.inf, "f97c00", float),
    (-math.inf, "f9fc00", float),
])
def test_float_reduction_interval_and_nonfinite_boundaries(number, hex_data, expected_type):
    encoded = bytes.fromhex(hex_data)
    assert dcbor.dumps(number) == encoded
    assert dcbor.validate(encoded) == len(encoded)
    decoded = dcbor.loads(encoded)
    assert type(decoded) is expected_type
    assert decoded == number
    assert dcbor.dumps(decoded) == encoded


def test_nan_uses_canonical_half_width():
    encoded = bytes.fromhex("f97e00")
    assert dcbor.dumps(math.nan) == encoded
    assert dcbor.validate(encoded) == len(encoded)
    assert math.isnan(dcbor.loads(encoded))
    assert dcbor.dumps(dcbor.loads(encoded)) == encoded


@pytest.mark.parametrize("number,hex_data", [
    (-(2**64), "3bffffffffffffffff"),
    (-(2**63) - 1, "3b8000000000000000"),
    (-(2**63), "3b7fffffffffffffff"),
    (2**64 - 1, "1bffffffffffffffff"),
])
def test_explicit_python_integer_range_is_unchanged(number, hex_data):
    encoded = bytes.fromhex(hex_data)
    assert dcbor.dumps(number) == encoded
    decoded = dcbor.loads(encoded)
    assert type(decoded) is int
    assert decoded == number
    assert dcbor.validate(encoded) == len(encoded)


@pytest.mark.parametrize("hex_data", [
    "fadf000000",  # -2**63 must reduce to an integer
    "fb43efffffffffffff",  # largest float below 2**64 must reduce
    "fbc3f0000000000000",  # -2**64 is representable in binary32
])
def test_nonpreferred_numeric_width_or_required_integer_is_rejected(hex_data):
    encoded = bytes.fromhex(hex_data)
    for operation in (dcbor.loads, dcbor.validate, dcbor.diagnostic, dcbor.diagnostic_flat):
        with pytest.raises(dcbor.CBORError):
            operation(encoded)
