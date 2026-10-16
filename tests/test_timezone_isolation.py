"""The host-timezone encoding test must not affect later tests in its process."""
import os
from pathlib import Path
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
    regression_file = Path(__file__).with_name("test_dcbor.py")
    code = r"""
import os
import runpy
import sys
import time

import pytest

time.tzset()
before_env = os.environ.get('TZ')
before_state = (time.tzname, time.timezone, time.daylight,
                time.localtime(0), time.localtime(1720000000))
target = runpy.run_path(sys.argv[1])['test_datetime_encoding_is_timezone_independent']
patch = pytest.MonkeyPatch()
try:
    target(patch)
    assert os.environ.get('TZ') == before_env
    assert (time.tzname, time.timezone, time.daylight,
            time.localtime(0), time.localtime(1720000000)) == before_state
finally:
    patch.undo()
assert os.environ.get('TZ') == before_env
assert (time.tzname, time.timezone, time.daylight,
        time.localtime(0), time.localtime(1720000000)) == before_state
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(regression_file)],
        env=env, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
