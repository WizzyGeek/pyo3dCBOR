"""Every exposed map key retains its canonical CBOR lookup identity."""
import datetime

import dcbor
import pytest


def assert_key_identity(mapping, encoded):
    assert dcbor.dumps(mapping) == encoded
    for key in mapping:
        assert key in mapping
        assert mapping[key] == "payload"
    for key in mapping.keys():
        assert key in mapping
        assert mapping[key] == "payload"
    for key, value in mapping.items():
        assert key in mapping
        assert mapping[key] == value
    assert dcbor.dumps(dcbor.CBORMap(mapping.items())) == encoded


@pytest.mark.parametrize("timestamp", [
    1e-7,
    -1e-7,
    -0.5000001,
    253402300799.12344,  # year 9999: float spacing exceeds microseconds
    -62135596799.12345,  # year 1, negative fractional timestamp
])
@pytest.mark.parametrize("shape", ["direct", "array", "tag", "map", "nested"])
def test_map_keys_preserve_identity_recursively(timestamp, shape):
    date = dcbor.CBORTag(1, timestamp)
    keys = {
        "direct": date,
        "array": [date],
        "tag": dcbor.CBORTag(100, date),
        "map": {"date": date},
        "nested": dcbor.CBORTag(101, [[{"date": [date]}]]),
    }
    mapping = dcbor.CBORMap([(keys[shape], "payload")])
    encoded = dcbor.dumps(mapping)
    assert_key_identity(mapping, encoded)
    assert_key_identity(dcbor.loads(encoded), encoded)


@pytest.mark.parametrize("timestamp", [1e-7, -1e-7, -0.5000001])
def test_lossy_date_key_keeps_tag_even_without_other_fallback_keys(timestamp):
    encoded = dcbor.dumps(dcbor.CBORMap([(dcbor.CBORTag(1, timestamp), "payload")]))
    decoded = dcbor.loads(encoded)
    assert isinstance(decoded, dcbor.CBORMap)
    key = decoded.keys()[0]
    assert isinstance(key, dcbor.CBORTag)
    assert key.tag == 1
    assert key.value == timestamp
    assert_key_identity(decoded, encoded)


def test_exact_date_key_retains_datetime_convenience():
    encoded = dcbor.dumps(dcbor.CBORMap([(dcbor.CBORTag(1, -0.5), "payload")]))
    decoded = dcbor.loads(encoded)
    assert type(decoded) is dict
    assert isinstance(next(iter(decoded)), datetime.datetime)
    assert_key_identity(decoded, encoded)


def test_original_mixed_key_report():
    mapping = dcbor.CBORMap([
        (dcbor.CBORTag(1, 1e-7), "payload"),
        ([], "payload"),
    ])
    encoded = dcbor.dumps(mapping)
    assert_key_identity(mapping, encoded)
    assert_key_identity(dcbor.loads(encoded), encoded)


def test_map_used_as_key_preserves_dates_in_both_keys_and_values():
    inner = dcbor.CBORMap([
        (dcbor.CBORTag(1, 1e-7), dcbor.CBORTag(1, -1e-7)),
    ])
    mapping = dcbor.CBORMap([(inner, "payload")])
    encoded = dcbor.dumps(mapping)
    assert_key_identity(mapping, encoded)
    assert_key_identity(dcbor.loads(encoded), encoded)


@pytest.mark.parametrize("shape", [
    lambda date: date,
    lambda date: [date],
    lambda date: dcbor.CBORTag(100, date),
    lambda date: {"date": date},
])
def test_invalid_date_in_composite_key_still_raises(shape):
    key = shape(dcbor.CBORTag(1, 2**64 - 1))
    encoded = dcbor.dumps(dcbor.CBORMap([(key, "payload")]))
    with pytest.raises(dcbor.CBORError):
        dcbor.loads(encoded)
