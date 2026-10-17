"""Regression oracles for early composite-key budget and replacement accounting."""
import dcbor
import pytest
from _subprocess_utils import (
    linux_address_space_limit_available,
    run_address_space_limited,
)


@pytest.mark.parametrize("operation", ["dumps", "constructor_tuple", "constructor_list"])
@pytest.mark.skipif(
    not linux_address_space_limit_available(),
    reason="requires /proc VmSize and resource.RLIMIT_AS to cap allocations",
)
def test_composite_key_budget_rejects_before_large_materialization(operation):
    prepare = r'''
import dcbor
chunk = b'x' * (256 * 1024)
key = (chunk,) * 512
source = {key: 0}
'''
    code = r'''
try:
    OPERATION
except dcbor.CBORError as exc:
    assert 'map key cache' in str(exc), str(exc)
else:
    raise AssertionError('oversized composite map key accepted')
'''.replace("OPERATION", {
        "dumps": "dcbor.dumps(source)",
        "constructor_tuple": "dcbor.CBORMap([(key, 0)])",
        "constructor_list": "dcbor.CBORMap([(list(key), 0)])",
    }[operation])
    result = run_address_space_limited(
        code,
        prepare=prepare,
        memory_headroom=64 * 1024 * 1024,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("snapshot", [False, True])
def test_replaced_canonical_keys_release_discarded_value_budget(snapshot):
    keys = ["\u00c5", "A\u030a", "\u212b"]
    chunk = b"x" * (6 * 1024 * 1024)
    value = dcbor.CBORMap([(chunk, 0)]) if snapshot else {chunk: 0}
    source = {key: value for key in keys}
    expected = dcbor.dumps({keys[-1]: value})
    assert len(expected) == 6291467
    assert dcbor.dumps(source) == expected
    assert dcbor.validate(expected) == len(expected)


def test_replacement_uses_last_value_not_first():
    keys = ["\u00c5", "A\u030a", "\u212b"]
    chunk = b"x" * (6 * 1024 * 1024)
    source = {key: {chunk: position} for position, key in enumerate(keys)}
    expected = dcbor.dumps({keys[-1]: {chunk: 2}})
    assert dcbor.dumps(source) == expected


@pytest.mark.parametrize("snapshot", [False, True])
def test_distinct_retained_values_still_enforce_total_key_budget(snapshot):
    chunk = b"x" * (6 * 1024 * 1024)
    value = dcbor.CBORMap([(chunk, 0)]) if snapshot else {chunk: 0}
    with pytest.raises(dcbor.CBORError, match="map key cache"):
        dcbor.dumps({"a": value, "b": value, "c": value})


@pytest.mark.parametrize("snapshot", [False, True])
def test_replacement_accounting_within_composite_key(snapshot):
    keys = ["\u00c5", "A\u030a", "\u212b"]
    # Outer key retains both the nested key cache and the complete subtree's
    # wire bytes. Two 3-MiB retained copies fit; obsolete copies must disappear.
    chunk = b"x" * (3 * 1024 * 1024)
    value = dcbor.CBORMap([(chunk, 0)]) if snapshot else {chunk: 0}
    source_key = {key: value for key in keys}
    expected_key = {keys[-1]: value}
    expected = dcbor.dumps(dcbor.CBORMap([(expected_key, 0)]))
    assert dcbor.dumps(dcbor.CBORMap([(source_key, 0)])) == expected


def test_replacement_subprocess_with_shared_large_value():
    if not linux_address_space_limit_available():
        pytest.skip("requires /proc VmSize and resource.RLIMIT_AS to cap allocations")
    prepare = r'''
import dcbor
keys = ['\u00c5', 'A\u030a', '\u212b']
chunk = b'x' * (6 * 1024 * 1024)
value = {chunk: 0}
source = {key: value for key in keys}
'''
    code = r'''
expected = dcbor.dumps({keys[-1]: value})
assert len(expected) == 6291467
assert dcbor.dumps(source) == expected
'''
    result = run_address_space_limited(
        code,
        prepare=prepare,
        memory_headroom=128 * 1024 * 1024,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
