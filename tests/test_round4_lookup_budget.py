"""CBORMap lookup probes obey the same canonical-key resource limits."""

import subprocess
import sys
import textwrap

import dcbor
import pytest


LIMIT = 16 * 1024 * 1024


@pytest.mark.skipif(sys.platform != "linux", reason="requires Linux address-space accounting")
@pytest.mark.parametrize("shape", ["tuple", "list"])
@pytest.mark.parametrize("operation", ["contains", "getitem", "get"])
def test_oversized_composite_lookup_rejects_before_allocator_abort(shape, operation):
    script = textwrap.dedent(
        r'''
        import resource
        from pathlib import Path

        import dcbor

        mapping = dcbor.CBORMap([(0, "present")])
        chunk = b"x" * (256 * 1024)
        key = (chunk,) * 512 if SHAPE == "tuple" else [chunk] * 512

        baseline = int(next(
            line for line in Path("/proc/self/status").read_text().splitlines()
            if line.startswith("VmSize:")
        ).split()[1]) * 1024
        _, hard = resource.getrlimit(resource.RLIMIT_AS)
        ceiling = baseline + 64 * 1024 * 1024
        if hard != resource.RLIM_INFINITY:
            ceiling = min(ceiling, hard)
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        resource.setrlimit(resource.RLIMIT_AS, (ceiling, hard))

        try:
            if OPERATION == "contains":
                _ = key in mapping
            elif OPERATION == "getitem":
                mapping[key]
            else:
                mapping.get(key)
        except dcbor.CBORError as exc:
            assert "map key cache" in str(exc), str(exc)
        else:
            raise AssertionError("oversized lookup probe was accepted")
        '''
    ).replace("SHAPE", repr(shape)).replace("OPERATION", repr(operation))
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, timeout=30
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
