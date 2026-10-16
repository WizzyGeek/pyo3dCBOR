"""Regressions for strict Unicode and checked epoch date conversion."""
import datetime as dt
import subprocess
import sys

import pytest

import dcbor

UTC = dt.timezone.utc


@pytest.mark.parametrize("micros", [0, 1, 250000, 500000, 999999])
@pytest.mark.parametrize("year", [1960, 1969, 1970, 2023])
def test_fractional_datetime_round_trip(year, micros):
    value = dt.datetime(year, 12, 31, 23, 59, 59, micros, tzinfo=UTC)
    assert dcbor.loads(dcbor.dumps(value)) == value


def test_negative_half_second_both_directions():
    value = dt.datetime(1969, 12, 31, 23, 59, 59, 500000, tzinfo=UTC)
    assert dcbor.dumps(value) == bytes.fromhex("c1f9b800")
    assert dcbor.loads(bytes.fromhex("c1f9b800")) == value


@pytest.mark.parametrize("year", [1, 9999])
def test_whole_second_datetime_boundaries(year):
    value = dt.datetime(year, 1, 1, tzinfo=UTC)
    assert dcbor.loads(dcbor.dumps(value)) == value


@pytest.mark.parametrize("seconds", [-(2**64), 2**64 - 1, -62135596801, 253402300800,
                                     float("nan"), float("inf"), float("-inf")])
def test_unsupported_numeric_dates_raise_cbor_error(seconds):
    with pytest.raises(dcbor.CBORError):
        dcbor.loads(dcbor.dumps(dcbor.CBORTag(1, seconds)))


def test_former_panic_is_an_ordinary_exception_in_subprocess():
    code = """
import dcbor
try:
    dcbor.loads(bytes.fromhex('c11bffffffffffffffff'))
except Exception as error:
    assert isinstance(error, dcbor.CBORError), type(error)
else:
    raise AssertionError('unsupported date accepted')
"""
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "panicked" not in result.stderr


def test_nonnumeric_date_tag_stays_a_tag():
    decoded = dcbor.loads(dcbor.dumps(dcbor.CBORTag(1, "arbitrary")))
    assert isinstance(decoded, dcbor.CBORTag)
    assert decoded.tag == 1 and decoded.value == "arbitrary"


def test_tzinfo_returning_none_is_naive():
    class NaiveTimezone(dt.tzinfo):
        def utcoffset(self, value):
            return None

    value = dt.datetime(2023, 1, 1, tzinfo=NaiveTimezone())
    with pytest.raises(dcbor.CBORError, match="naive"):
        dcbor.dumps(value)


def test_timezone_errors_become_cbor_errors():
    class BrokenTimezone(dt.tzinfo):
        def utcoffset(self, value):
            raise ValueError("broken timezone")

    with pytest.raises(dcbor.CBORError, match="broken timezone"):
        dcbor.dumps(dt.datetime(2023, 1, 1, tzinfo=BrokenTimezone()))


@pytest.mark.parametrize("text", ["\ud800", "\udfff", "before\ud800after", "\ud83d\ude00"])
def test_surrogates_are_rejected_without_replacement(text):
    with pytest.raises(dcbor.CBORError, match="surrogate"):
        dcbor.dumps(text)


def test_string_subclass_contents_are_used_without_str_override():
    class MisleadingString(str):
        def __str__(self):
            raise AssertionError("must read actual string contents")

    assert dcbor.loads(dcbor.dumps(MisleadingString("actual"))) == "actual"


def test_valid_unicode_remains_nfc_normalized():
    assert dcbor.loads(dcbor.dumps("e\u0301😀\x00")) == "é😀\x00"


@pytest.mark.parametrize("payload", [
    # First key is an unhashable array; its value must still be decoded.
    "a180c11bffffffffffffffff",
    # Later value must be checked even after an unhashable first key.
    "a280008100c11bffffffffffffffff",
    # Later key must also be checked before returning the mapping proxy.
    "a28000c11bffffffffffffffff00",
])
def test_proxy_map_does_not_hide_unsupported_dates(payload):
    with pytest.raises(dcbor.CBORError):
        dcbor.loads(bytes.fromhex(payload))
