"""The key-cache limit applies during conversion, before retaining map caches."""
import subprocess
import sys
import textwrap

import pytest
import dcbor


@pytest.mark.skipif(sys.platform != "linux", reason="requires Linux address-space accounting")
@pytest.mark.parametrize("operation", [
    "dcbor.dumps(value)",
    "dcbor.CBORMap([(0, value)])",
    "dcbor.CBORMap([(value, 0)])",
])
def test_encoder_rejects_shared_graph_before_allocator_abort(operation):
    script = textwrap.dedent('''
        import resource
        from pathlib import Path
        import dcbor
        key = b"x" * (256 * 1024)
        value = 0
        for _ in range(256):
            value = {key: value}
        status = Path("/proc/self/status").read_text()
        baseline = int(next(line for line in status.splitlines()
                            if line.startswith("VmSize:")).split()[1]) * 1024
        _, hard = resource.getrlimit(resource.RLIMIT_AS)
        ceiling = baseline + 64 * 1024 * 1024
        if hard != resource.RLIM_INFINITY:
            ceiling = min(ceiling, hard)
        resource.setrlimit(resource.RLIMIT_AS, (ceiling, hard))
        try:
            OPERATION
        except dcbor.CBORError as exc:
            assert "map key cache" in str(exc), str(exc)
        else:
            raise AssertionError("over-budget graph was accepted")
    ''').replace("OPERATION", operation)
    result = subprocess.run([sys.executable, "-c", script], text=True,
                            capture_output=True, timeout=30)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("use_proxy", [False, True])
def test_shared_subtrees_within_budget_remain_supported(use_proxy):
    key = b"k" * 1024
    value = 0
    for _ in range(32):
        value = {key: value}
    graph = [value] * 8
    obj = dcbor.CBORMap([(0, graph)]) if use_proxy else graph
    encoded = dcbor.dumps(obj)
    assert dcbor.dumps(dcbor.loads(encoded)) == encoded


@pytest.mark.parametrize("operation", [
    lambda snapshot, count: dcbor.dumps([snapshot] * count),
    lambda snapshot, count: dcbor.CBORMap([(0, [snapshot] * count)]),
    lambda snapshot, count: dcbor.CBORMap([([snapshot] * count, 0)]),
])
def test_repeated_snapshots_charge_every_occurrence(operation):
    # Each key's complete encoding is exactly 1 MiB. The 16 MiB boundary
    # permits sixteen occurrences as values, but seventeen always exceed it.
    snapshot = dcbor.CBORMap([(b"x" * ((1 << 20) - 5), 0)])
    operation(snapshot, 7)
    with pytest.raises(dcbor.CBORError, match="map key cache"):
        operation(snapshot, 17)


def test_snapshot_budget_includes_exact_boundary_and_siblings():
    snapshot = dcbor.CBORMap([(b"x" * ((1 << 20) - 5), 0)])
    encoded = dcbor.dumps([snapshot] * 16)
    assert dcbor.validate(encoded) == len(encoded)
    with pytest.raises(dcbor.CBORError, match="map key cache"):
        dcbor.dumps([snapshot] * 16 + [{0: 0}])


def test_snapshot_used_as_key_charges_inner_and_outer_key_caches():
    snapshot = dcbor.CBORMap([(b"x" * ((1 << 20) - 5), 0)])
    # snapshot's key costs 1 MiB, and the snapshot's own encoding as an
    # outer key costs 1 MiB + 2. Eight copies exceed 16 MiB by 16 bytes.
    outer = dcbor.CBORMap([(snapshot, 0)])
    dcbor.dumps([outer] * 7)
    with pytest.raises(dcbor.CBORError, match="map key cache"):
        dcbor.dumps([outer] * 8)


def test_constructor_budget_is_shared_across_pairs():
    snapshot = dcbor.CBORMap([(b"x" * ((1 << 20) - 5), 0)])
    dcbor.CBORMap([(i, snapshot) for i in range(15)])
    with pytest.raises(dcbor.CBORError, match="map key cache"):
        dcbor.CBORMap([(i, snapshot) for i in range(16)])
