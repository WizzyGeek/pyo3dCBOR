"""Numeric wire checks independent of the native encoder and preflight.

Exercise IEEE exponent/sign boundaries and seeded payloads at widths larger
than binary16. These remain useful when the decoder alone checks numeric
canonicality: an encode/decode round trip cannot establish correct rejection.
"""

import math
import random
import struct

import pytest

import dcbor


READERS = (dcbor.loads, dcbor.validate, dcbor.diagnostic, dcbor.diagnostic_flat)


def _integer_wire(value):
    major = 0 if value >= 0 else 0x20
    argument = value if value >= 0 else -1 - value
    if argument < 24:
        return bytes([major | argument])
    for info, size in ((24, 1), (25, 2), (26, 4), (27, 8)):
        if argument < 1 << (8 * size):
            return bytes([major | info]) + argument.to_bytes(size, "big")
    raise AssertionError("integer oracle called outside the reduction interval")


def _canonical_wire(number):
    if math.isnan(number):
        return bytes.fromhex("f97e00")
    if math.isfinite(number) and number.is_integer() and -(2**63) <= number < 2**64:
        return _integer_wire(int(number))
    for code, header in (("e", 0xF9), ("f", 0xFA), ("d", 0xFB)):
        try:
            payload = struct.pack(">" + code, number)
        except OverflowError:
            continue
        if struct.unpack(">" + code, payload)[0] == number:
            return bytes([header]) + payload
    raise AssertionError("no IEEE encoding for the input number")


def _patterns(width, exponent_bits, fraction_bits):
    # All exponent fields, both signs, and significands around carry/rounding
    # boundaries, including normal/subnormal transitions and NaN payloads.
    fractions = (0, 1, (1 << (fraction_bits - 1)) - 1,
                 1 << (fraction_bits - 1), (1 << fraction_bits) - 2,
                 (1 << fraction_bits) - 1)
    for sign in (0, 1):
        for exponent in range(1 << exponent_bits):
            for fraction in fractions:
                yield (sign << (width - 1)) | (exponent << fraction_bits) | fraction
    rng = random.Random(20261017 + width)
    for _ in range(10000):
        yield rng.getrandbits(width)


@pytest.mark.exhaustive
@pytest.mark.parametrize("width,code,header,exponent_bits,fraction_bits", (
    (32, "f", 0xFA, 8, 23),
    (64, "d", 0xFB, 11, 52),
), ids=("binary32", "binary64"))
def test_numeric_widths_against_independent_ieee_oracle(
    width, code, header, exponent_bits, fraction_bits,
):
    for bits in _patterns(width, exponent_bits, fraction_bits):
        payload = bits.to_bytes(width // 8, "big")
        number = struct.unpack(">" + code, payload)[0]
        raw = bytes([header]) + payload
        expected = _canonical_wire(number)
        context = f"binary{width} bits={bits:0{width // 4}x}"
        assert dcbor.dumps(number) == expected, context
        decoded = dcbor.loads(expected)
        if math.isnan(number):
            assert type(decoded) is float and math.isnan(decoded), context
        else:
            assert decoded == number, context
            reduced = math.isfinite(number) and number.is_integer() and -(2**63) <= number < 2**64
            assert type(decoded) is (int if reduced else float), context
        assert dcbor.validate(expected) == len(expected), context
        for diagnostic in (dcbor.diagnostic, dcbor.diagnostic_flat):
            displayed = float(diagnostic(expected))
            assert math.isnan(displayed) if math.isnan(number) else displayed == number, context
        if raw != expected:
            for reader in READERS:
                try:
                    reader(raw)
                except dcbor.CBORError:
                    pass
                else:
                    pytest.fail(f"{reader.__name__} accepted noncanonical {context}; expected {expected.hex()}")
