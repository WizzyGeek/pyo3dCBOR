"""Baseline fixtures for the native decoder and diagnostic writer."""

import datetime as dt
import gc
import io

import pytest

import dcbor


READERS = (dcbor.loads, dcbor.validate, dcbor.diagnostic, dcbor.diagnostic_flat)


@pytest.mark.parametrize(
    ("wire_hex", "pretty", "flat"),
    [
        (
            "a261618201f94100617ad8644178",
            '{\n    "a":\n    [1, 2.5],\n    "z":\n    100(h\'78\')\n}',
            '{"a": [1, 2.5], "z": 100(h\'78\')}',
        ),
        (
            "d864a10102",
            "100(\n    {1: 2}\n)",
            "100({1: 2})",
        ),
        (
            "4178",
            "h'78'",
            "h'78'",
        ),
        (
            "62c3a9",
            '"é"',
            '"é"',
        ),
        (
            "c100",
            "1(0)",
            "1(0)",
        ),
    ],
)
def test_reader_lengths_and_diagnostic_text_match_release_fixture(
    wire_hex, pretty, flat
):
    wire = bytes.fromhex(wire_hex)
    assert dcbor.validate(wire) == len(wire)
    assert dcbor.diagnostic(wire) == pretty
    assert dcbor.diagnostic_flat(wire) == flat
    dcbor.loads(wire)


def test_nested_diagnostic_fixture_preserves_decoded_types():
    value = dcbor.loads(bytes.fromhex("a261618201f94100617ad8644178"))

    assert value["a"] == [1, 2.5]
    assert type(value["a"][0]) is int
    assert type(value["a"][1]) is float
    assert isinstance(value["z"], dcbor.CBORTag)
    assert value["z"].tag == 100
    assert value["z"].value == b"x"


@pytest.mark.parametrize(
    ("wire_hex", "expected"),
    [
        ("00", 0),
        ("1818", 24),
        ("1bffffffffffffffff", 2**64 - 1),
        ("20", -1),
        ("3bffffffffffffffff", -(2**64)),
    ],
)
def test_integer_wire_boundaries_decode_to_builtin_int(wire_hex, expected):
    value = dcbor.loads(bytes.fromhex(wire_hex))

    assert type(value) is int
    assert value == expected


def test_lossless_map_keeps_integer_and_boolean_keys_and_diagnostic():
    wire = bytes.fromhex("a2016161f56162")
    value = dcbor.loads(wire)

    assert isinstance(value, dcbor.CBORMap)
    assert len(value) == 2
    assert value[1] == "a"
    assert value[True] == "b"
    assert dcbor.diagnostic(wire) == '{1: "a", true: "b"}'
    assert dcbor.diagnostic_flat(wire) == '{1: "a", true: "b"}'


def test_datetime_tag_fixture_has_datetime_value_and_generic_diagnostic():
    wire = bytes.fromhex("c100")
    value = dcbor.loads(wire)

    assert value == dt.datetime(1970, 1, 1, tzinfo=dt.timezone.utc)
    assert dcbor.diagnostic(wire) == "1(0)"
    assert dcbor.diagnostic_flat(wire) == "1(0)"


@pytest.mark.parametrize(
    ("wire_hex", "message"),
    [
        ("1800", "a CBOR numeric value was encoded in non-canonical form"),
        ("a201000101", "the decoded CBOR map has a duplicate key"),
        ("6180", "invalid UTF‑8 string: invalid utf-8 sequence of 1 bytes from index 0"),
        ("5f", "invalid or truncated CBOR data"),
        ("f97e01", "a CBOR numeric value was encoded in non-canonical form"),
    ],
)
@pytest.mark.parametrize("reader", READERS)
def test_malformed_reader_error_matches_release_fixture(wire_hex, message, reader):
    with pytest.raises(dcbor.CBORError) as caught:
        reader(bytes.fromhex(wire_hex))
    assert str(caught.value) == message


@pytest.mark.parametrize("major", [2, 3])
def test_large_scalar_result_remains_owned_after_input_is_dropped(major):
    payload_length = 1 << 20
    marker = b"x" if major == 2 else b"a"
    head = bytes([0x5a if major == 2 else 0x7a]) + payload_length.to_bytes(4, "big")
    encoded = head + marker * payload_length

    decoded = dcbor.loads(encoded)
    del encoded
    gc.collect()

    expected = marker if major == 2 else marker.decode("ascii")
    assert len(decoded) == payload_length
    assert decoded[:8] == expected * 8
    assert decoded[-8:] == expected * 8
    assert type(decoded) is (bytes if major == 2 else str)


def test_load_reads_binary_file_and_bytes_io_once(tmp_path):
    wire = bytes.fromhex("a2616101617a81f5")
    path = tmp_path / "value.cbor"
    path.write_bytes(wire)

    with path.open("rb") as stream:
        assert dcbor.load(stream) == {"a": 1, "z": [True]}

    class ReadOnce:
        def __init__(self, data):
            self.data = data
            self.calls = 0

        def read(self):
            self.calls += 1
            return self.data

    stream = ReadOnce(wire)
    assert dcbor.load(stream) == {"a": 1, "z": [True]}
    assert stream.calls == 1
    assert dcbor.load(io.BytesIO(wire)) == {"a": 1, "z": [True]}


@pytest.mark.parametrize(
    "wire",
    [
        bytes.fromhex("1800"),
        bytes.fromhex("a201000101"),
        bytes.fromhex("6180"),
        bytes.fromhex("5f"),
        bytes.fromhex("f97e01"),
        b"\x81" * 513 + b"\x00",
        bytes.fromhex("0000"),
    ],
    ids=["overlong", "duplicate-map-key", "invalid-utf8", "truncated", "nan", "depth", "trailing"],
)
def test_load_file_reader_errors_match_loads(wire):
    with pytest.raises(dcbor.CBORError) as from_bytes:
        dcbor.loads(wire)
    with pytest.raises(dcbor.CBORError) as from_file:
        dcbor.load(io.BytesIO(wire))

    assert type(from_file.value) is type(from_bytes.value)
    assert str(from_file.value) == str(from_bytes.value)


def test_load_propagates_file_read_exception_unchanged():
    failure = OSError("source read failed")

    class BrokenReader:
        def read(self):
            raise failure

    with pytest.raises(OSError) as caught:
        dcbor.load(BrokenReader())
    assert caught.value is failure


def test_load_rejects_text_reader():
    with pytest.raises(TypeError):
        dcbor.load(io.StringIO("0"))


def test_large_loaded_bytes_remain_owned_after_file_close(tmp_path):
    payload_length = 1 << 20
    payload = b"z" * payload_length
    path = tmp_path / "large.cbor"
    path.write_bytes(b"\x5a" + payload_length.to_bytes(4, "big") + payload)
    del payload

    with path.open("rb") as stream:
        decoded = dcbor.load(stream)

    assert stream.closed
    assert len(decoded) == payload_length
    assert decoded[:8] == b"z" * 8
    assert decoded[-8:] == b"z" * 8
