"""Regression tests for canonical CBOR key identity and mutable tags."""
import gc
import subprocess
import sys

import pytest
import dcbor


def test_boolean_integer_key_collision_is_lossless():
    encoded = bytes.fromhex("a2016161f56162")
    value = dcbor.loads(encoded)
    assert isinstance(value, dcbor.CBORMap)
    assert len(value) == 2
    assert value[1] == "a"
    assert value[True] == "b"
    assert dcbor.dumps(value) == encoded
    assert list(value) == [1, True]
    assert value.items() == [(1, "a"), (True, "b")]
    assert value.get("missing", 42) == 42
    with pytest.raises(KeyError):
        value["missing"]


def test_ordinary_maps_still_decode_as_dicts():
    assert type(dcbor.loads(dcbor.dumps({"a": 1}))) is dict


def test_zero_false_and_one_true_remain_four_distinct_keys():
    mapping = dcbor.CBORMap([(0, "zero"), (False, "false"),
                             (1, "one"), (True, "true")])
    decoded = dcbor.loads(dcbor.dumps(mapping))
    assert len(decoded) == 4
    assert decoded[0] == "zero" and decoded[False] == "false"
    assert decoded[1] == "one" and decoded[True] == "true"


@pytest.mark.parametrize("leaf", [[], {}, ()])
def test_empty_containers_respect_encoder_depth_boundary(leaf):
    value = leaf
    for _ in range(511):
        value = [value]
    encoded = dcbor.dumps(value)
    dcbor.loads(encoded)
    with pytest.raises(dcbor.CBORError, match="depth"):
        dcbor.dumps([value])


def test_unhashable_keys_roundtrip():
    value = dcbor.CBORMap([([1, 2], "array"), (dcbor.CBORTag(100, 1), "tag")])
    decoded = dcbor.loads(dcbor.dumps(value))
    assert decoded[[1, 2]] == "array"
    assert decoded[dcbor.CBORTag(100, 1)] == "tag"
    assert dcbor.dumps(decoded) == dcbor.dumps(value)


def test_constructor_rejects_duplicate_canonical_keys():
    with pytest.raises(dcbor.CBORError, match="duplicate"):
        dcbor.CBORMap([(1, "first"), (1.0, "second")])
    with pytest.raises(dcbor.CBORError, match="duplicate"):
        dcbor.CBORMap([("e\u0301", 1), ("é", 2)])


def test_snapshot_does_not_change_when_source_or_decoded_keys_change():
    key, value = [1], [2]
    mapping = dcbor.CBORMap([(key, value)])
    key.append(3)
    value.append(4)
    assert mapping[[1]] == [2]
    mapping.keys()[0].append(5)
    mapping[[1]].append(6)
    assert mapping[[1]] == [2]


def test_tag_is_mutable_and_unhashable():
    tag = dcbor.CBORTag(100, None)
    tag.tag = 101
    tag.value = tag
    assert tag.tag == 101
    with pytest.raises(TypeError):
        hash(tag)
    assert tag == tag
    assert repr(tag).startswith("CBORTag(101")
    assert gc.is_tracked(tag)


def test_cyclic_tag_comparisons_and_hash_do_not_crash():
    code = """
import dcbor
x = dcbor.CBORTag(100, None)
y = dcbor.CBORTag(100, None)
x.value = x
y.value = y
try:
    hash(x)
except TypeError:
    pass
else:
    raise AssertionError('mutable tag is hashable')
try:
    x == y
except RecursionError:
    pass
"""
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_snapshot_cannot_bypass_encoder_depth_limit():
    key = 0
    for _ in range(200):
        key = [key]
    snapshot = dcbor.CBORMap([(key, "nested")])
    value = snapshot
    for _ in range(400):
        value = [value]
    with pytest.raises(dcbor.CBORError, match="depth"):
        dcbor.dumps(value)


def test_snapshot_cross_thread_access():
    from concurrent.futures import ThreadPoolExecutor
    mapping = dcbor.CBORMap([([1], "array")])
    with ThreadPoolExecutor(max_workers=1) as executor:
        assert executor.submit(lambda: mapping[[1]]).result() == "array"


def test_tag_reference_cycle_is_collected():
    import weakref

    class Sentinel:
        tag: dcbor.CBORTag

    sentinel = Sentinel()
    observed = weakref.ref(sentinel)
    tag = dcbor.CBORTag(100, [sentinel])
    sentinel.tag = tag
    del sentinel, tag
    gc.collect()
    assert observed() is None
