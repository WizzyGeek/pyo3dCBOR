"""Behavioral checks for the shared CI plan and its environment interface."""

import json
import os
from pathlib import Path
import runpy
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
PLANNER = ROOT / "scripts/ci_plan.py"
PLAN = runpy.run_path(str(PLANNER))["plan"]


FULL_MATRIX = {
    "os": ["ubuntu-24.04", "ubuntu-24.04-arm", "windows-2022"],
    "python": ["cp39", "cp310", "cp311", "cp312", "cp313", "cp314"],
}
REDUCED_MATRIX = {
    "os": ["ubuntu-latest"],
    "python": ["cp312", "cp313", "cp314"],
}


@pytest.mark.parametrize(
    ("event_name", "ref_type", "requested", "full"),
    [
        ("workflow_dispatch", "branch", False, True),
        ("push", "tag", False, True),
        ("push", "branch", False, False),
        # A reusable caller can request full coverage while its event context
        # remains the caller's ordinary branch push.
        ("push", "branch", True, True),
        # PRs keep the reduced matrix even if a caller asks for full coverage.
        ("pull_request", "branch", True, False),
        ("pull_request", "", False, False),
        # A reusable workflow can inherit these callers' event names too.
        ("schedule", "", False, False),
        ("schedule", "", True, True),
        ("release", "", False, False),
        ("release", "", True, True),
        ("workflow_run", "", False, False),
        ("workflow_run", "", True, True),
    ],
)
def test_plan_selects_expected_coverage(event_name, ref_type, requested, full):
    result = PLAN(event_name, ref_type, requested)

    assert result == {
        "full_matrix": full,
        "wheel_matrix": FULL_MATRIX if full else REDUCED_MATRIX,
        "linux_image_mode": "upstream" if full else "maintained",
    }


def test_plan_rejects_missing_events_and_non_boolean_requests():
    with pytest.raises(ValueError, match="non-empty string"):
        PLAN("", "", False)
    with pytest.raises(ValueError, match="non-empty string"):
        PLAN(None, "", False)
    with pytest.raises(ValueError, match="must be a bool"):
        PLAN("push", "branch", "false")


def run_cli(tmp_path, **variables):
    env = os.environ.copy()
    env.update({"EVENT_NAME": "", "REF_TYPE": "", "FULL_MATRIX_REQUESTED": ""})
    env.update(variables)
    return subprocess.run(
        [sys.executable, str(PLANNER)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )


def test_cli_emits_github_output_assignments_for_requested_reusable_plan(tmp_path):
    result = run_cli(
        tmp_path,
        EVENT_NAME="push",
        REF_TYPE="branch",
        FULL_MATRIX_REQUESTED="true",
    )

    assert result.returncode == 0, result.stderr
    assignments = dict(line.split("=", 1) for line in result.stdout.splitlines())
    assert assignments == {
        "full_matrix": "true",
        "wheel_matrix": json.dumps(FULL_MATRIX, separators=(",", ":")),
        "linux_image_mode": "upstream",
    }


@pytest.mark.parametrize("requested", ["TRUE", "yes", "1", " true "])
def test_cli_rejects_invalid_request_before_emitting_output(tmp_path, requested):
    result = run_cli(
        tmp_path,
        EVENT_NAME="push",
        REF_TYPE="branch",
        FULL_MATRIX_REQUESTED=requested,
    )

    assert result.returncode != 0
    assert result.stdout == ""
    assert "FULL_MATRIX_REQUESTED" in result.stderr


def test_cli_rejects_missing_event_before_emitting_output(tmp_path):
    result = run_cli(tmp_path)

    assert result.returncode != 0
    assert result.stdout == ""
    assert "event_name must be a non-empty string" in result.stderr
