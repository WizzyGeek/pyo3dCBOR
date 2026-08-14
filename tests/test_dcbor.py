"""Test suite for the dcbor Python bindings.

Many expected hex vectors are lifted directly from the upstream Rust crate's
tests (bc-dcbor-rust/tests/encode.rs) to cross-validate against the
reference implementation.
"""

import datetime
import math

import pytest

import dcbor


# ---------------------------------------------------------------------------
# Integers
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "value, expected_hex",
    [
        (0, "00"),
        (1, "01"),
        (23, "17"),
        (24, "1818"),
        (255, "18ff"),
        (65535, "19ffff"),
        (65536, "1a00010000"),
        (4294967295, "1affffffff"),
        (4294967296, "1b0000000100000000"),
        (18446744073709551615, "1bffffffffffffffff"),  # u64::MAX
        (-1, "20"),
        (-2, "21"),
        (-127, "387e"),
        (-128, "387f"),
        (127, "187f"),
        (-32768, "397fff"),
        (32767, "197fff"),
        (-2147483648, "3a7fffffff"),
        (2147483647, "1a7fffffff"),
        (-9223372036854775808, "3b7fffffffffffffff"),  # i64::MIN
        (9223372036854775807, "1b7fffffffffffffff"),  # i64::MAX
    ],
)
def test_integer_vectors(value, expected_hex):
    assert dcbor.dumps(value).hex() == expected_hex
    assert dcbor.loads(dcbor.dumps(value)) == value


def test_integer_extreme_range():
    max_negative = -(2**64)
    max_positive = 2**64 - 1
    assert dcbor.loads(dcbor.dumps(max_negative)) == max_negative
    assert dcbor.loads(dcbor.dumps(max_positive)) == max_positive


@pytest.mark.parametrize("value", [2**64, -(2**64) - 1, 2**200, -(2**200)])
def test_integer_out_of_range_raises(value):
    with pytest.raises(dcbor.CBORError):
        dcbor.dumps(value)


# ---------------------------------------------------------------------------
# Bytes / strings
# ---------------------------------------------------------------------------

def test_byte_string_vectors():
    assert dcbor.dumps(bytes.fromhex("00112233")).hex() == "4400112233"
    assert dcbor.dumps(bytes([0x11, 0x22, 0x33])).hex() == "43112233"
    assert dcbor.loads(dcbor.dumps(b"")) == b""


def test_bytearray_encodes_same_as_bytes():
    assert dcbor.dumps(bytearray(b"abc")) == dcbor.dumps(b"abc")


def test_string_vector():
    assert dcbor.dumps("Hello").hex() == "6548656c6c6f"
    assert dcbor.loads(dcbor.dumps("Hello")) == "Hello"


def test_string_nfc_normalization():
    composed = "é"  # é (precomposed)
    decomposed = "é"  # e + combining acute accent
    assert composed != decomposed  # different Python strings...
    assert dcbor.dumps(composed) == dcbor.dumps(decomposed)  # ...same dCBOR
    assert dcbor.loads(dcbor.dumps(decomposed)) == composed


# ---------------------------------------------------------------------------
# Booleans / null
# ---------------------------------------------------------------------------

def test_bool_and_none():
    assert dcbor.dumps(True).hex() == "f5"
    assert dcbor.dumps(False).hex() == "f4"
    assert dcbor.dumps(None).hex() == "f6"
    assert dcbor.loads(dcbor.dumps(True)) is True
    assert dcbor.loads(dcbor.dumps(False)) is False
    assert dcbor.loads(dcbor.dumps(None)) is None


# ---------------------------------------------------------------------------
# Floats
# ---------------------------------------------------------------------------

def test_float_numeric_reduction_to_int():
    # dCBOR reduces integral floats to the shortest integer encoding.
    assert dcbor.dumps(42.0) == dcbor.dumps(42)
    decoded = dcbor.loads(dcbor.dumps(42.0))
    assert decoded == 42
    assert isinstance(decoded, int)


def test_float_non_integral_stays_float():
    decoded = dcbor.loads(dcbor.dumps(3.14))
    assert isinstance(decoded, float)
    assert decoded == 3.14


def test_float_nan_canonical():
    assert dcbor.dumps(float("nan")).hex() == "f97e00"
    decoded = dcbor.loads(bytes.fromhex("f97e00"))
    assert isinstance(decoded, float) and math.isnan(decoded)


def test_float_non_canonical_nan_rejected():
    with pytest.raises(dcbor.CBORError):
        dcbor.loads(bytes.fromhex("f97e01"))
    with pytest.raises(dcbor.CBORError):
        dcbor.loads(bytes.fromhex("faffc00001"))


def test_float_infinity_canonical():
    assert dcbor.dumps(float("inf")).hex() == "f97c00"
    assert dcbor.dumps(float("-inf")).hex() == "f9fc00"
    assert dcbor.loads(bytes.fromhex("f97c00")) == float("inf")
    assert dcbor.loads(bytes.fromhex("f9fc00")) == float("-inf")


def test_float_non_canonical_infinity_rejected():
    with pytest.raises(dcbor.CBORError):
        dcbor.loads(bytes.fromhex("fa7f800000"))
    with pytest.raises(dcbor.CBORError):
        dcbor.loads(bytes.fromhex("fbfff0000000000000"))


# ---------------------------------------------------------------------------
# Arrays / maps
# ---------------------------------------------------------------------------

def test_array_vector():
    assert dcbor.dumps([1, 2, 3]).hex() == "83010203"
    assert dcbor.loads(dcbor.dumps([1, 2, 3])) == [1, 2, 3]


def test_tuple_encodes_as_array():
    assert dcbor.dumps((1, 2, 3)) == dcbor.dumps([1, 2, 3])


def test_heterogeneous_array():
    mixed = [1, "Hello", [1, 2, 3]]
    encoded = dcbor.dumps(mixed)
    assert encoded.hex() == "83016548656c6c6f83010203"
    assert dcbor.loads(encoded) == mixed


def test_map_vector():
    assert dcbor.dumps({"key": 123}).hex() == "a1636b6579187b"


def test_map_keys_sorted_canonically_regardless_of_insertion_order():
    m1 = {"b": 2, "a": 1, "c": 3}
    m2 = {"c": 3, "a": 1, "b": 2}
    assert dcbor.dumps(m1) == dcbor.dumps(m2)


def test_map_round_trip():
    m = {"b": 2, "a": [1, 2, 3], "c": None}
    assert dcbor.loads(dcbor.dumps(m)) == m


def test_map_int_keys_sort_by_encoding_not_value():
    # dCBOR/CBOR canonical map key order is by the *encoded* bytes of the
    # key, so e.g. 1, 50, 25 sort as 1, 25, 50 (all single-byte-header
    # unsigned ints, compared lexicographically on their encoding).
    m = {1: "A", 50: "B", 25: "C"}
    assert dcbor.diagnostic(dcbor.dumps(m)) == '{1: "A", 25: "C", 50: "B"}'


# ---------------------------------------------------------------------------
# Decode-time canonical-encoding enforcement
# ---------------------------------------------------------------------------

def test_decode_rejects_misordered_map_keys():
    # map(2){ 25:"C", 1:"A" } -- wrong order (25 before 1)
    bad = bytes.fromhex("a2") + bytes.fromhex("1819") + dcbor.dumps("C") + bytes.fromhex("01") + dcbor.dumps("A")
    with pytest.raises(dcbor.CBORError):
        dcbor.loads(bad)


def test_decode_rejects_duplicate_map_keys():
    dup = bytes.fromhex("a2") + bytes.fromhex("01") + dcbor.dumps("A") + bytes.fromhex("01") + dcbor.dumps("B")
    with pytest.raises(dcbor.CBORError):
        dcbor.loads(dup)


def test_decode_rejects_non_canonical_integer():
    # 0 encoded in 2-byte form (0x1800) instead of the required 1-byte form.
    with pytest.raises(dcbor.CBORError):
        dcbor.loads(bytes.fromhex("1800"))


def test_decode_rejects_trailing_data():
    with pytest.raises(dcbor.CBORError):
        dcbor.loads(dcbor.dumps(1) + b"\x00")


def test_decode_rejects_garbage():
    with pytest.raises(dcbor.CBORError):
        dcbor.loads(b"\xff")


# ---------------------------------------------------------------------------
# Tags / datetime
# ---------------------------------------------------------------------------

def test_datetime_round_trip_utc():
    dt = datetime.datetime(2023, 2, 8, tzinfo=datetime.timezone.utc)
    encoded = dcbor.dumps(dt)
    assert dcbor.loads(encoded) == dt


def test_datetime_with_fraction_round_trip():
    dt = datetime.datetime(
        2023, 2, 8, 12, 30, 45, 500000, tzinfo=datetime.timezone.utc
    )
    encoded = dcbor.dumps(dt)
    decoded = dcbor.loads(encoded)
    assert abs((decoded - dt).total_seconds()) < 1e-6


def test_datetime_before_epoch():
    dt = datetime.datetime(1960, 1, 1, tzinfo=datetime.timezone.utc)
    assert dcbor.loads(dcbor.dumps(dt)) == dt


def test_custom_tag_round_trip():
    tag = dcbor.CBORTag(9999, "hello")
    decoded = dcbor.loads(dcbor.dumps(tag))
    assert isinstance(decoded, dcbor.CBORTag)
    assert decoded.tag == 9999
    assert decoded.value == "hello"


def test_custom_tag_nested_structure():
    tag = dcbor.CBORTag(100, {"a": [1, 2, dcbor.CBORTag(200, b"\x01\x02")]})
    decoded = dcbor.loads(dcbor.dumps(tag))
    assert decoded.tag == 100
    assert decoded.value["a"][0] == 1
    assert isinstance(decoded.value["a"][2], dcbor.CBORTag)
    assert decoded.value["a"][2].tag == 200
    assert decoded.value["a"][2].value == b"\x01\x02"


def test_cbor_tag_repr_and_eq():
    a = dcbor.CBORTag(1, "x")
    b = dcbor.CBORTag(1, "x")
    c = dcbor.CBORTag(2, "x")
    assert a == b
    assert a != c
    assert "CBORTag(1" in repr(a)


# ---------------------------------------------------------------------------
# Diagnostic notation
# ---------------------------------------------------------------------------

def test_diagnostic_notation():
    data = dcbor.dumps([1, "Hello", [1, 2, 3]])
    assert dcbor.diagnostic_flat(data) == '[1, "Hello", [1, 2, 3]]'


def test_diagnostic_matches_rust_doctest_example():
    m = {"key": 123}
    assert dcbor.diagnostic_flat(dcbor.dumps(m)) == '{"key": 123}'


# ---------------------------------------------------------------------------
# validate()
# ---------------------------------------------------------------------------

def test_validate_returns_length_for_well_formed_data():
    data = dcbor.dumps({"a": 1})
    assert dcbor.validate(data) == len(data)


def test_validate_raises_for_malformed_data():
    with pytest.raises(dcbor.CBORError):
        dcbor.validate(b"\xff")


# ---------------------------------------------------------------------------
# Errors on unsupported input types
# ---------------------------------------------------------------------------

def test_dumps_unsupported_type_raises():
    class Foo:
        pass

    with pytest.raises(dcbor.CBORError):
        dcbor.dumps(Foo())


def test_cbor_error_is_exception_subclass():
    assert issubclass(dcbor.CBORError, Exception)


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------

def test_same_value_always_encodes_identically():
    value = {"z": [1, 2, {"nested": True}], "a": None, "m": 3.0}
    assert dcbor.dumps(value) == dcbor.dumps(value)


def test_naive_datetime_rejected():
    naive = datetime.datetime(2023, 2, 8)
    with pytest.raises(dcbor.CBORError):
        dcbor.dumps(naive)


def test_datetime_encoding_is_timezone_independent(monkeypatch):
    import time as time_mod

    dt = datetime.datetime(2023, 2, 8, 12, 0, 0, tzinfo=datetime.timezone.utc)
    encoded_a = dcbor.dumps(dt)
    monkeypatch.setenv("TZ", "Asia/Tokyo")
    if hasattr(time_mod, "tzset"):
        time_mod.tzset()
    try:
        encoded_b = dcbor.dumps(dt)
    finally:
        monkeypatch.delenv("TZ", raising=False)
        if hasattr(time_mod, "tzset"):
            time_mod.tzset()
    assert encoded_a == encoded_b


def test_decode_map_with_array_key_raises_cbor_error_not_type_error():
    # map(1){ [-1]: 1 } -- a valid dCBOR map with an array key, which has
    # no hashable Python equivalent and so cannot become a dict key.
    bad = bytes.fromhex("a1") + bytes.fromhex("8120") + bytes.fromhex("01")
    with pytest.raises(dcbor.CBORError):
        dcbor.loads(bad)


def test_huge_int_reports_range_error_not_type_error():
    with pytest.raises(dcbor.CBORError, match="out of range"):
        dcbor.dumps(2**200)
    with pytest.raises(dcbor.CBORError, match="out of range"):
        dcbor.dumps(-(2**200))


def test_cbor_tag_hash_consistent_with_eq():
    a = dcbor.CBORTag(1, "x")
    b = dcbor.CBORTag(1, "x")
    assert a == b
    assert hash(a) == hash(b)


def test_decode_deeply_nested_array_raises_instead_of_crashing():
    # 100,000 levels of array nesting would blow the native stack if
    # handed directly to the recursive decoder; the depth pre-scan must
    # reject it as a normal Python exception instead.
    data = b"\x81" * 100_000 + b"\x00"
    with pytest.raises(dcbor.CBORError, match="depth"):
        dcbor.loads(data)


def test_encode_deeply_nested_list_raises_instead_of_crashing():
    value = None
    for _ in range(100_000):
        value = [value]
    with pytest.raises(dcbor.CBORError, match="depth"):
        dcbor.dumps(value)


def test_moderately_nested_structure_still_round_trips():
    value = None
    for _ in range(400):
        value = [value]
    encoded = dcbor.dumps(value)
    assert dcbor.loads(encoded) == value


def test_round_trip_is_lossless_for_deeply_nested_structures():
    value = {
        "list": [1, 2, [3, 4, {"x": "y"}]],
        "bytes": b"\x00\x01\x02",
        "flag": True,
        "none": None,
        "float": 1.5,
    }
    assert dcbor.loads(dcbor.dumps(value)) == value
