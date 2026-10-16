"""Key-cache accounting uses NFC wire lengths, including composite keys."""
import subprocess
import sys
import textwrap

import pytest
import dcbor


LIMIT = 16 * 1024 * 1024


@pytest.mark.parametrize("constructor", [False, True])
def test_nfc_expansion_cannot_hide_over_budget_key(constructor):
    # U+0344 expands from two UTF-8 bytes to four after NFC normalization.
    # Canonical key length is 16 MiB + 9, not the raw 8 MiB + 7.
    key = "\u0344" * ((4 << 20) + 1)
    with pytest.raises(dcbor.CBORError, match="map key cache"):
        if constructor:
            dcbor.CBORMap([(key, 0)])
        else:
            dcbor.dumps({key: 0})


@pytest.mark.parametrize("constructor", [False, True])
def test_nfc_contraction_does_not_falsely_reject_key(constructor):
    # Raw UTF-8 is 18 MiB; NFC is 12 MiB, plus the five-byte text header.
    key = "e\u0301" * (6 << 20)
    obj = dcbor.CBORMap([(key, 0)]) if constructor else {key: 0}
    data = dcbor.dumps(obj)
    assert len(data) == (12 << 20) + 7  # map header, text header, integer value
    assert dcbor.validate(data) == len(data)


@pytest.mark.parametrize("composite", [False, True])
def test_nfc_key_exact_wire_budget_and_one_byte_over(composite):
    # Each U+0344 contributes four NFC bytes. ASCII fills out the remaining
    # bytes after accounting for the five-byte text header and optional array.
    padding = 2 if composite else 3
    text = "\u0344" * ((LIMIT - 8) // 4) + "x" * padding
    key = [text] if composite else text
    snapshot = dcbor.CBORMap([(key, 0)])
    data = dcbor.dumps(snapshot)
    assert len(data) == LIMIT + 2
    assert dcbor.validate(data) == len(data)
    larger_key = [text + "x"] if composite else text + "x"
    with pytest.raises(dcbor.CBORError, match="map key cache"):
        dcbor.CBORMap([(larger_key, 0)])


def test_nfc_snapshot_lengths_are_charged_for_each_occurrence():
    # The normalized key encoding is exactly 1 MiB per snapshot.
    text = "\u0344" * (((1 << 20) - 8) // 4) + "xxx"
    snapshot = dcbor.CBORMap([(text, 0)])
    data = dcbor.dumps([snapshot] * 16)
    assert dcbor.validate(data) == len(data)
    with pytest.raises(dcbor.CBORError, match="map key cache"):
        dcbor.dumps([snapshot] * 16 + [{0: 0}])


@pytest.mark.skipif(sys.platform != "linux", reason="requires Linux address-space accounting")
@pytest.mark.parametrize("operation", [
    "dcbor.dumps(graph)",
    "dcbor.CBORMap([(0, graph)])",
    "dcbor.CBORMap([(graph, 0)])",
])
def test_nfc_expanding_shared_siblings_fail_before_allocator_abort(operation):
    script = textwrap.dedent('''
        import resource
        from pathlib import Path
        import dcbor
        key = "\\u0344" * (256 * 1024)
        graph = [{key: 0}] * 40
        status = Path("/proc/self/status").read_text()
        baseline = int(next(line for line in status.splitlines()
                            if line.startswith("VmSize:")).split()[1]) * 1024
        _, hard = resource.getrlimit(resource.RLIMIT_AS)
        ceiling = baseline + 40 * 1024 * 1024
        if hard != resource.RLIM_INFINITY:
            ceiling = min(ceiling, hard)
        resource.setrlimit(resource.RLIMIT_AS, (ceiling, hard))
        try:
            OPERATION
        except dcbor.CBORError as exc:
            assert "map key cache" in str(exc), str(exc)
        else:
            raise AssertionError("over-budget normalized graph was accepted")
    ''').replace("OPERATION", operation)
    result = subprocess.run([sys.executable, "-c", script], capture_output=True,
                            text=True, timeout=60)
    assert result.returncode == 0, result.stderr
