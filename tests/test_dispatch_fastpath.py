"""Regression coverage for Python numeric-protocol dispatch."""

import pytest

import dcbor


class IndexValue:
    def __init__(self, value):
        self.value = value
        self.calls = 0

    def __index__(self):
        self.calls += 1
        return self.value


@pytest.mark.parametrize(
    "value",
    [
        7,
        -7,
        2**63,
        -(2**63) - 1,
        -(2**64),
        2**64 - 1,
    ],
)
def test_custom_index_is_called_once_for_in_range_integers(value):
    candidate = IndexValue(value)

    assert dcbor.dumps(candidate) == dcbor.dumps(value)
    assert candidate.calls == 1


@pytest.mark.parametrize("value", [2**64, -(2**64) - 1, 2**100, 2**200])
def test_custom_index_out_of_range_is_still_an_integer_error(value):
    candidate = IndexValue(value)

    with pytest.raises(dcbor.CBORError, match="integer out of range"):
        dcbor.dumps(candidate)
    assert candidate.calls == 1


@pytest.mark.parametrize("error", [ValueError("bad index"), RuntimeError("boom")])
def test_custom_index_errors_preserve_existing_fallback(error):
    class FailingIndex:
        calls = 0

        def __index__(self):
            self.calls += 1
            raise error

    candidate = FailingIndex()

    with pytest.raises(dcbor.CBORError, match="not dCBOR serializable"):
        dcbor.dumps(candidate)
    assert candidate.calls == 1


def test_custom_index_must_return_an_integer():
    class InvalidIndex:
        calls = 0

        def __index__(self):
            type(self).calls += 1
            return "7"

    candidate = InvalidIndex()

    with pytest.raises(dcbor.CBORError, match="not dCBOR serializable"):
        dcbor.dumps(candidate)
    assert InvalidIndex.calls == 1


def test_stateful_index_result_is_observed_once():
    class ChangingIndex:
        calls = 0

        def __index__(self):
            type(self).calls += 1
            return 2**63 if type(self).calls == 1 else 8

    candidate = ChangingIndex()
    expected = bytes.fromhex("1b8000000000000000")

    assert dcbor.dumps(candidate) == expected
    assert dcbor.dumps(2**63) == expected
    assert ChangingIndex.calls == 1


def test_int_subclass_uses_its_stored_integer_without_calling_override():
    class IntSubclass(int):
        calls = 0

        def __index__(self):
            type(self).calls += 1
            return 9

    candidate = IntSubclass(17)

    assert dcbor.dumps(candidate) == dcbor.dumps(17)
    assert IntSubclass.calls == 0


@pytest.mark.parametrize(
    ("base", "value"),
    [
        (float, 1.5),
        (str, "text"),
        (list, [1, 2]),
        (tuple, (1, 2)),
        (dict, {"value": 1}),
    ],
)
def test_builtin_subclass_index_protocol_keeps_precedence(base, value):
    class Subclass(base):
        calls = 0

        def __index__(self):
            type(self).calls += 1
            return 9

    candidate = Subclass(value)

    assert dcbor.dumps(candidate) == dcbor.dumps(9)
    assert Subclass.calls == 1


@pytest.mark.parametrize(
    ("base", "value"),
    [
        (float, 1.5),
        (str, "text"),
        (bytes, b"bytes"),
        (bytearray, bytearray(b"bytes")),
    ],
)
def test_builtin_subclass_failing_index_falls_back_to_native_encoding(base, value):
    class Subclass(base):
        calls = 0

        def __index__(self):
            type(self).calls += 1
            raise ValueError("bad index")

    candidate = Subclass(value)

    assert dcbor.loads(dcbor.dumps(candidate)) == dcbor.loads(dcbor.dumps(value))
    assert Subclass.calls == 1


@pytest.mark.parametrize(
    ("base", "value", "decoded"),
    [
        (int, 17, 17),
        (float, 1.5, 1.5),
        (str, "text", "text"),
        (list, [1, 2], [1, 2]),
        (tuple, (1, 2), [1, 2]),
        (dict, {"value": 1}, {"value": 1}),
    ],
)
def test_builtin_subclasses_without_index_keep_native_encoding(base, value, decoded):
    class Subclass(base):
        pass

    assert dcbor.loads(dcbor.dumps(Subclass(value))) == decoded


@pytest.mark.parametrize(
    ("value", "decoded"),
    [
        (1.5, 1.5),
        ("text", "text"),
        (b"bytes", b"bytes"),
        (bytearray(b"bytes"), b"bytes"),
        ([1, 2], [1, 2]),
        ((1, 2), [1, 2]),
        ({"value": 1}, {"value": 1}),
    ],
)
def test_exact_builtin_nonintegers_keep_their_native_encoding(value, decoded):
    assert dcbor.loads(dcbor.dumps(value)) == decoded


def test_bool_dispatch_precedes_integer_dispatch():
    assert dcbor.dumps(True) == bytes.fromhex("f5")
    assert dcbor.dumps(False) == bytes.fromhex("f4")
    assert dcbor.dumps(True) != dcbor.dumps(1)
