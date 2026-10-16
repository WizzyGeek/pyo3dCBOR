"""CBORMap entry validation reads at most three items per pair iterator."""
import subprocess
import sys

import dcbor
import pytest


@pytest.mark.parametrize("length", [0, 1, 3, 4, 100])
def test_wrong_length_pair_rejected_with_bounded_consumption(length):
    seen = []

    def entry():
        for value in range(length):
            seen.append(value)
            yield value

    with pytest.raises(ValueError, match="CBORMap entries must be key/value pairs"):
        dcbor.CBORMap([entry()])
    assert seen == list(range(min(length, 3)))


def test_two_item_generator_accepted():
    mapping = dcbor.CBORMap([(item for item in ["key", "value"])])
    assert mapping["key"] == "value"


@pytest.mark.parametrize("position", [0, 1, 2])
def test_iterator_errors_within_first_three_items_propagate(position):
    class IteratorFailure(Exception):
        pass

    def entry():
        for value in range(position):
            yield value
        raise IteratorFailure("entry iterator failed")

    with pytest.raises(IteratorFailure, match="entry iterator failed"):
        dcbor.CBORMap([entry()])


def test_fourth_item_is_never_requested():
    seen = []

    def entry():
        for value in range(3):
            seen.append(value)
            yield value
        raise AssertionError("fourth item must not be requested")

    with pytest.raises(ValueError, match="key/value pairs"):
        dcbor.CBORMap([entry()])
    assert seen == [0, 1, 2]


def test_infinite_pair_iterator_is_rejected_in_subprocess():
    # A timeout bounds the test even against the unfixed implementation. The
    # fourth-read assertion also prevents an old build from exhausting memory.
    code = """
import dcbor
class InfiniteEntry:
    def __init__(self):
        self.reads = 0
    def __iter__(self):
        return self
    def __next__(self):
        self.reads += 1
        if self.reads > 3:
            raise AssertionError('read past the third item')
        return self.reads
entry = InfiniteEntry()
try:
    dcbor.CBORMap([entry])
except ValueError as exc:
    assert 'key/value pairs' in str(exc)
else:
    raise AssertionError('malformed entry was accepted')
assert entry.reads == 3
"""
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=10
    )
    assert result.returncode == 0, result.stderr


def test_true_infinite_generator_is_rejected_in_subprocess():
    # itertools.repeat has no side effects and no finite length to inspect.
    # Limit virtual memory so a regressed implementation cannot exhaust host RAM.
    code = """
import dcbor
import itertools
try:
    import resource
    from pathlib import Path
    size = int(next(line for line in Path('/proc/self/status').read_text().splitlines()
                    if line.startswith('VmSize:')).split()[1]) * 1024
    _, hard = resource.getrlimit(resource.RLIMIT_AS)
    cap = size + 64 * 1024 * 1024
    if hard != resource.RLIM_INFINITY:
        cap = min(cap, hard)
    resource.setrlimit(resource.RLIMIT_AS, (cap, hard))
except (ImportError, FileNotFoundError):
    pass
try:
    dcbor.CBORMap([itertools.repeat(None)])
except ValueError as exc:
    assert 'key/value pairs' in str(exc)
else:
    raise AssertionError('infinite malformed entry was accepted')
"""
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=10
    )
    assert result.returncode == 0, result.stderr
