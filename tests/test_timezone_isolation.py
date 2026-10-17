"""The host-timezone encoding test must not affect later tests in its process."""
import os
import subprocess
import sys
import time

import pytest


@pytest.mark.skipif(not hasattr(time, "tzset"), reason="requires process timezone control")
@pytest.mark.parametrize("outer_timezone", [None, "EST5EDT"])
def test_timezone_encoding_regression_restores_environment_and_process(outer_timezone):
    env = os.environ.copy()
    if outer_timezone is None:
        env.pop("TZ", None)
    else:
        env["TZ"] = outer_timezone
    code = r"""
import datetime
import os
import time

import dcbor

time.tzset()
before_env = os.environ.get('TZ')
before_state = (time.tzname, time.timezone, time.daylight,
                time.localtime(0), time.localtime(1720000000))
dt = datetime.datetime(
    2023, 2, 8, 12, 0, 0,
    tzinfo=datetime.timezone(datetime.timedelta(hours=5, minutes=30)),
)
expected = bytes.fromhex('c11a63e34168')
try:
    assert dcbor.dumps(dt) == expected
    assert os.environ.get('TZ') == before_env
    assert (time.tzname, time.timezone, time.daylight,
            time.localtime(0), time.localtime(1720000000)) == before_state
    os.environ['TZ'] = 'Asia/Tokyo'
    time.tzset()
    tokyo_state = (time.tzname, time.timezone, time.daylight,
                   time.localtime(0), time.localtime(1720000000))
    assert dcbor.dumps(dt) == expected
    assert os.environ.get('TZ') == 'Asia/Tokyo'
    assert (time.tzname, time.timezone, time.daylight,
            time.localtime(0), time.localtime(1720000000)) == tokyo_state
finally:
    if before_env is None:
        os.environ.pop('TZ', None)
    else:
        os.environ['TZ'] = before_env
    time.tzset()
assert os.environ.get('TZ') == before_env
assert (time.tzname, time.timezone, time.daylight,
        time.localtime(0), time.localtime(1720000000)) == before_state
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        env=env, capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, result.stderr
