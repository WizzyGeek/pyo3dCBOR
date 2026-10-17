"""CBORMap lookup probes obey the same canonical-key resource limits."""

import dcbor
import pytest
from _subprocess_utils import (
    linux_address_space_limit_available,
    run_address_space_limited,
)


LIMIT = 16 * 1024 * 1024


@pytest.mark.skipif(
    not linux_address_space_limit_available(),
    reason="requires /proc VmSize and resource.RLIMIT_AS to cap allocations",
)
@pytest.mark.parametrize("shape", ["tuple", "list"])
@pytest.mark.parametrize("operation", ["contains", "getitem", "get"])
def test_oversized_composite_lookup_rejects_before_allocator_abort(shape, operation):
    prepare = f'''
import dcbor
mapping = dcbor.CBORMap([(0, "present")])
chunk = b"x" * (256 * 1024)
key = (chunk,) * 512 if {shape!r} == "tuple" else [chunk] * 512
'''
    script = f'''
try:
    if {operation!r} == "contains":
        _ = key in mapping
    elif {operation!r} == "getitem":
        mapping[key]
    else:
        mapping.get(key)
except dcbor.CBORError as exc:
    assert "map key cache" in str(exc), str(exc)
else:
    raise AssertionError("oversized lookup probe was accepted")
'''
    result = run_address_space_limited(
        script,
        prepare=prepare,
        memory_headroom=64 * 1024 * 1024,
        timeout=30,
        disable_core=True,
    )
    assert result.returncode == 0, (result.returncode, result.stderr)


@pytest.mark.parametrize("container", [tuple, list])
def test_lookup_probe_exact_key_budget_boundary(container):
    mapping = dcbor.CBORMap([(0, "present")])
    marker = object()

    # One-byte array header + five-byte byte-string header + payload.
    exact = container([b"x" * (LIMIT - 6)])
    assert exact not in mapping
    assert mapping.get(exact, marker) is marker
    with pytest.raises(KeyError):
        mapping[exact]

    over = container([b"x" * (LIMIT - 5)])
    with pytest.raises(dcbor.CBORError, match="map key cache"):
        _ = over in mapping
    with pytest.raises(dcbor.CBORError, match="map key cache"):
        _ = mapping.get(over, marker)
    with pytest.raises(dcbor.CBORError, match="map key cache"):
        mapping[over]


def test_lookup_preserves_canonical_array_and_nfc_identity():
    mapping = dcbor.CBORMap([
        ([1, 2], "array"),
        ("\u00e9", "acute"),
        ("\u00c5", "ring"),
    ])

    for probe, expected in (
        ((1, 2), "array"),
        ([1, 2], "array"),
        ("e\u0301", "acute"),
        ("\u212b", "ring"),
    ):
        assert probe in mapping
        assert mapping[probe] == expected
        assert mapping.get(probe) == expected


def test_lookup_preserves_missing_key_and_default_behavior():
    mapping = dcbor.CBORMap([(0, "present")])
    marker = object()

    assert "missing" not in mapping
    assert mapping.get("missing") is None
    assert mapping.get("missing", marker) is marker
    with pytest.raises(KeyError):
        mapping["missing"]


def test_lookup_probe_depth_limit_matches_map_key_conversion():
    mapping = dcbor.CBORMap([(0, "present")])
    accepted = 1
    for _ in range(511):
        accepted = [accepted]
    assert accepted not in mapping

    rejected = [accepted]
    with pytest.raises(dcbor.CBORError, match="depth"):
        _ = rejected in mapping
    with pytest.raises(dcbor.CBORError, match="depth"):
        mapping.get(rejected)
    with pytest.raises(dcbor.CBORError, match="depth"):
        mapping[rejected]
