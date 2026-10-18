"""Independent compatibility checks for the direct Python-to-bytes writer."""

import pytest

import dcbor


def test_nested_values_and_frozen_map_have_independent_wire_bytes():
    snapshot = dcbor.CBORMap([(True, "t"), (1, "i")])
    value = {
        "z": [snapshot],
        "a": dcbor.CBORTag(100, bytearray(b"x")),
    }

    # Outer text keys sort by encoded bytes; the snapshot retains the distinct
    # integer and boolean keys that a Python dict would merge.
    expected = bytes.fromhex("a26161d8644178617a81a2016169f56174")
    assert dcbor.dumps(value) == expected


def test_composite_nfc_colliding_keys_keep_last_value():
    source = {("e\u0301",): 1, ("é",): 2}

    # Both tuple keys normalize to the same one-element CBOR array key.
    expected = bytes.fromhex("a18162c3a902")
    assert dcbor.dumps(source) == expected


def test_composite_numeric_colliding_keys_keep_last_value_and_call_once():
    calls = []

    class Index:
        def __init__(self, label):
            self.label = label

        def __index__(self):
            calls.append(self.label)
            return 7

    source = {
        (Index("first"),): "discarded",
        (Index("last"),): "kept",
    }

    expected = bytes.fromhex("a18107646b657074")
    assert dcbor.dumps(source) == expected
    assert calls == ["first", "last"]


def test_overwritten_canonical_map_entries_keep_callback_order():
    calls = []

    class Index:
        def __init__(self, label, result):
            self.label = label
            self.result = result

        def __index__(self):
            calls.append(self.label)
            return self.result

    source = {
        Index("key-1", 1): Index("value-1", 10),
        Index("key-2", 1): Index("value-2", 2),
    }

    # The canonical-key collision keeps the second pair, after conversion has
    # visited both pairs in insertion order.
    assert dcbor.dumps(source) == bytes.fromhex("a10102")
    assert calls == ["key-1", "value-1", "key-2", "value-2"]


@pytest.mark.parametrize(
    ("mutation", "expected", "decoded"),
    [
        ("append", bytes.fromhex("83070102"), [7, 1, 2]),
        ("remove_last", bytes.fromhex("820701"), [7, 1]),
    ],
)
def test_list_mutation_during_index_callback_preserves_traversal_result(
    mutation, expected, decoded
):
    values = []

    class Index:
        def __index__(self):
            if mutation == "append":
                values.append(3)
            else:
                values.pop()
            return 7

    values.extend([Index(), 1, 2])

    # These outputs record the established recursive encoder's live traversal
    # behavior, including the array length actually visited after the callback.
    assert dcbor.dumps(values) == expected
    assert dcbor.loads(expected) == decoded


@pytest.mark.parametrize("initial_len", [24, 256])
def test_list_head_compacts_across_length_width_after_callback_removes_last(
    initial_len,
):
    calls = []
    values = []

    class Index:
        def __index__(self):
            calls.append("index")
            values.pop()
            return 7

    values.extend([Index(), *([1] * (initial_len - 1))])
    visited_len = initial_len - 1
    if visited_len < 24:
        head = bytes([0x80 + visited_len])
    elif visited_len <= 255:
        head = bytes([0x98, visited_len])
    else:
        head = bytes([0x99]) + visited_len.to_bytes(2, "big")
    expected = head + b"\x07" + b"\x01" * (visited_len - 1)

    assert dcbor.dumps(values) == expected
    assert calls == ["index"]


def test_bytearray_subclass_callback_can_mutate_later_payload_before_copy():
    payload = bytearray(b"old")

    class MutatingBytearray(bytearray):
        def __init__(self):
            super().__init__(b"trigger")

        def __index__(self):
            payload[:] = b"new"
            raise ValueError("fall back to bytearray contents")

    source = {"trigger": MutatingBytearray(), "payload": payload}
    expected = bytes.fromhex(
        "a2677061796c6f6164436e657767747269676765724774726967676572"
    )

    assert dcbor.dumps(source) == expected
    assert payload == b"new"


@pytest.mark.parametrize("field", ["tag", "value"])
def test_child_index_cannot_mutate_its_enclosing_tag_during_conversion(field):
    tag = dcbor.CBORTag(100, None)
    calls = []

    class MutatingIndex:
        def __index__(self):
            calls.append("index")
            setattr(tag, field, 101 if field == "tag" else 7)
            return 5

    child = MutatingIndex()
    tag.value = child

    # The recursive converter holds a borrow of the enclosing tag while it
    # visits the child, so the setter failure keeps the established error.
    with pytest.raises(dcbor.CBORError):
        dcbor.dumps(tag)
    assert calls == ["index"]
    assert tag.tag == 100
    assert tag.value is child
