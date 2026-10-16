"""Implicit datetime tags count toward the same depth limit as explicit tags."""
import datetime

import pytest

import dcbor


@pytest.fixture(params=["datetime", "explicit_tag"])
def date_leaf(request):
    if request.param == "datetime":
        return datetime.datetime(1970, 1, 1, tzinfo=datetime.timezone.utc)
    return dcbor.CBORTag(1, 0)


def wrap(value, count, mixed=False):
    for index in range(count):
        kind = index % 3 if mixed else 0
        if kind == 0:
            value = [value]
        elif kind == 1:
            value = (value,)
        else:
            value = {0: value}
    return value


def assert_valid_encoding(value):
    encoded = dcbor.dumps(value)
    assert dcbor.validate(encoded) == len(encoded)


@pytest.mark.parametrize("mixed", [False, True])
def test_direct_date_tag_depth_boundary(date_leaf, mixed):
    # 511 surrounding containers + the implicit/explicit date tag = 512.
    assert_valid_encoding(wrap(date_leaf, 511, mixed))
    with pytest.raises(dcbor.CBORError, match="depth"):
        dcbor.dumps(wrap(date_leaf, 512, mixed))


@pytest.mark.parametrize("side", ["key", "value"])
@pytest.mark.parametrize("mixed", [False, True])
def test_constructor_counts_date_tag_before_accepting_snapshot(date_leaf, side, mixed):
    # The constructor contributes one map container in either key/value context.
    accepted = wrap(date_leaf, 510, mixed)
    pairs = [(accepted, 0)] if side == "key" else [(0, accepted)]
    assert_valid_encoding(dcbor.CBORMap(pairs))

    rejected = wrap(date_leaf, 511, mixed)
    pairs = [(rejected, 0)] if side == "key" else [(0, rejected)]
    with pytest.raises(dcbor.CBORError, match="depth"):
        dcbor.CBORMap(pairs)


@pytest.mark.parametrize("side", ["key", "value"])
def test_date_snapshot_reuse_counts_existing_tag_depth(date_leaf, side):
    nested_date = wrap(date_leaf, 100)
    pairs = [(nested_date, 0)] if side == "key" else [(0, nested_date)]
    snapshot = dcbor.CBORMap(pairs)
    # Snapshot = map + 100 arrays + date tag = 102 containers.
    assert_valid_encoding(wrap(snapshot, 410, mixed=True))
    with pytest.raises(dcbor.CBORError, match="depth"):
        dcbor.dumps(wrap(snapshot, 411, mixed=True))
