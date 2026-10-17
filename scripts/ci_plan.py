"""Choose CI matrix and Linux image settings from the triggering event."""

import json
import os
import sys


FULL_OS = ["ubuntu-24.04", "ubuntu-24.04-arm", "windows-2022"]
REDUCED_OS = ["ubuntu-latest"]
FULL_PYTHON = ["cp39", "cp310", "cp311", "cp312", "cp313", "cp314"]
REDUCED_PYTHON = ["cp312", "cp313", "cp314"]


def plan(event_name, ref_type, full_matrix_requested=False):
    """Return the CI matrix and image mode for a supported triggering event.

    Reusable workflows inherit the caller's event name, which may be any
    supported GitHub event. Their caller can set ``full_matrix_requested`` to
    request full coverage without assuming a synthetic ``workflow_call`` event.
    Pull requests always stay reduced to avoid adding cross-platform wheel cost
    to PR validation.
    """
    if not isinstance(event_name, str) or not event_name:
        raise ValueError("event_name must be a non-empty string")
    if not isinstance(full_matrix_requested, bool):
        raise ValueError("full_matrix_requested must be a bool")

    full = event_name == "workflow_dispatch" or (
        event_name == "push" and ref_type == "tag"
    )
    if event_name != "pull_request" and full_matrix_requested:
        full = True

    return {
        "full_matrix": full,
        "wheel_matrix": {
            "os": list(FULL_OS if full else REDUCED_OS),
            "python": list(FULL_PYTHON if full else REDUCED_PYTHON),
        },
        "linux_image_mode": "upstream" if full else "maintained",
    }


def _requested_flag(value):
    if value == "":
        return False
    if value == "true":
        return True
    if value == "false":
        return False
    raise ValueError("FULL_MATRIX_REQUESTED must be 'true', 'false', or empty")


def main():
    """Read the event plan from the environment and print output assignments."""
    event_name = os.environ.get("EVENT_NAME", "")
    ref_type = os.environ.get("REF_TYPE", "")
    requested = _requested_flag(os.environ.get("FULL_MATRIX_REQUESTED", ""))
    result = plan(event_name, ref_type, requested)

    # Construct all output before writing anything so invalid input cannot leave
    # a partially populated GITHUB_OUTPUT file when stdout is redirected there.
    lines = (
        f"full_matrix={'true' if result['full_matrix'] else 'false'}",
        "wheel_matrix=" + json.dumps(result["wheel_matrix"], separators=(",", ":")),
        f"linux_image_mode={result['linux_image_mode']}",
    )
    sys.stdout.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError) as error:
        print(f"ci_plan: {error}", file=sys.stderr)
        raise SystemExit(2)
