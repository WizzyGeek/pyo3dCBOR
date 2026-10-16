"""Regression coverage for validation before the upstream recursive decoder."""
import math
import subprocess
import sys
import textwrap

import pytest
import dcbor


APIS = (dcbor.loads, dcbor.validate, dcbor.diagnostic, dcbor.diagnostic_flat)


@pytest.mark.parametrize("api", APIS)
@pytest.mark.parametrize("hex_data", [
    "facf000001",  # upstream incorrectly reduced -2147483904.0 to -2147483905
    "fa4f000001",  # integral float must use an unsigned integer
    "fb43e0000000000001",  # integral float above signed integer range
    "f90000", "f98000",  # both floating zero signs reduce to integer zero
    "f93c00", "f9bc00",  # positive and negative integral half precision
    "fa3fc00000", "fb3ff8000000000000",  # 1.5 fits in half precision
    "fa7f800000", "fbfff0000000000000",  # infinities fit in half precision
    "f97e01", "f9fe00", "fa7fc00000", "fb7ff8000000000000",  # canonical NaN is f97e00
])
def test_reject_noncanonical_float_before_upstream_reduction(api, hex_data):
    with pytest.raises(dcbor.CBORError):
        api(bytes.fromhex(hex_data))


@pytest.mark.parametrize("api", APIS)
@pytest.mark.parametrize("number", [
    0.0, -0.0, 1.5, -0.5, 2**-24, 2**-14, 65504.5,
    math.inf, -math.inf, math.nan, 1.1,
    float(2**64), -float(2**64), -float(2**65),
])
def test_canonical_float_encodings_remain_accepted(api, number):
    api(dcbor.dumps(number))


def nested_map_key(payload_size, depth=512):
    return (b"\xa1" * depth + dcbor.dumps(b"x" * payload_size)
            + b"\x00" * depth)


@pytest.mark.parametrize("api", APIS)
def test_reject_aggregate_encoded_map_key_cache(api):
    with pytest.raises(dcbor.CBORError, match="map key cache"):
        api(nested_map_key(256 * 1024))


@pytest.mark.parametrize("api", APIS)
def test_normal_nested_map_keys_remain_accepted(api):
    # Nested maps are valid keys even when loads needs the lossless map proxy.
    api(nested_map_key(1024, depth=8))


@pytest.mark.skipif(sys.platform != "linux", reason="uses Linux RLIMIT_AS and /proc")
@pytest.mark.parametrize("api_name", ["loads", "validate", "diagnostic", "diagnostic_flat"])
def test_key_amplification_cannot_abort_memory_limited_process(api_name):
    script = textwrap.dedent('''
        import resource
        import dcbor
        from pathlib import Path
        payload_size = 256 * 1024
        data = (b"\\xa1" * 512 + b"\\x5a" + payload_size.to_bytes(4, "big")
                + b"x" * payload_size + b"\\x00" * 512)
        status = Path("/proc/self/status").read_text()
        baseline_kib = int(next(line for line in status.splitlines()
                                if line.startswith("VmSize:")).split()[1])
        soft, hard = resource.getrlimit(resource.RLIMIT_AS)
        ceiling = baseline_kib * 1024 + 64 * 1024 * 1024
        if hard != resource.RLIM_INFINITY:
            ceiling = min(ceiling, hard)
        resource.setrlimit(resource.RLIMIT_AS, (ceiling, hard))
        try:
            getattr(dcbor, API_NAME)(data)
        except dcbor.CBORError as exc:
            assert "map key cache" in str(exc), str(exc)
        else:
            raise AssertionError("amplified keys were accepted")
    ''').replace("API_NAME", repr(api_name))
    result = subprocess.run([sys.executable, "-c", script], capture_output=True,
                            text=True, timeout=20)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("api", APIS)
@pytest.mark.parametrize("hex_data", [
    "81facf000001",  # array value
    "a1fa4f00000100",  # map key
    "a100fb43e0000000000001",  # map value
    "d864facf000001",  # tagged value
])
def test_noncanonical_float_is_checked_inside_containers(api, hex_data):
    with pytest.raises(dcbor.CBORError):
        api(bytes.fromhex(hex_data))


@pytest.mark.parametrize("api", APIS)
@pytest.mark.parametrize("hex_data", [
    "", "f9", "fa0000", "fb00000000", "5bffffffffffffffff",
    "9bffffffffffffffff", "bbffffffffffffffff", "81", "a101", "d864",
])
def test_truncated_or_overflowing_headers_raise_python_error(api, hex_data):
    with pytest.raises(dcbor.CBORError):
        api(bytes.fromhex(hex_data))
