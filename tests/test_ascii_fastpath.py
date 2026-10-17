"""ASCII serialization fast paths preserve text and canonical-key semantics."""

import unicodedata

import pytest

import dcbor


def _short_text_wire(text):
    payload = text.encode("utf-8")
    if len(payload) < 24:
        header = bytes([0x60 + len(payload)])
    else:
        assert len(payload) < 256
        header = bytes([0x78, len(payload)])
    return header + payload


@pytest.mark.parametrize(
    "text",
    [
        "",
        "plain ASCII",
        "\x00",
        "\x01\x1f",
        "\x7f",
        "a" * 23,
        "a" * 24,
    ],
)
def test_ascii_text_has_exact_wire_bytes(text):
    encoded = dcbor.dumps(text)
    assert encoded == _short_text_wire(text)
    assert dcbor.loads(encoded) == text


def test_string_subclass_uses_actual_storage_without_calling_str():
    class MisleadingString(str):
        def __str__(self):
            raise AssertionError("must read the string's actual contents")

    value = MisleadingString("stored\x00ASCII")
    assert dcbor.dumps(value) == _short_text_wire("stored\x00ASCII")
    assert dcbor.loads(dcbor.dumps(value)) == "stored\x00ASCII"


@pytest.mark.parametrize(
    "text",
    [
        "ASCII + café + 東京",
        "e\u0301",  # contracts under NFC
        "\u0344",  # expands under NFC
        "A\u0315\u0300",  # reorders and composes under NFC
    ],
)
def test_non_ascii_text_still_uses_nfc(text):
    normalized = unicodedata.normalize("NFC", text)
    assert dcbor.dumps(text) == _short_text_wire(normalized)
    assert dcbor.loads(dcbor.dumps(text)) == normalized


def test_nfc_collisions_keep_dictionary_last_entry_wins_behavior():
    keys = ["\u00c5", "A\u030a", "\u212b"]
    source = {key: index for index, key in enumerate(keys)}

    encoded = dcbor.dumps(source)
    assert encoded == dcbor.dumps({"\u00c5": 2})
    assert dcbor.loads(encoded) == {"\u00c5": 2}


def test_nfc_collisions_remain_duplicate_keys_for_cbor_map():
    with pytest.raises(dcbor.CBORError, match="duplicate"):
        dcbor.CBORMap([("ASCII", 0), ("e\u0301", 1), ("é", 2)])
