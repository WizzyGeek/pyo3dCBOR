"""Regression checks for the release workflow dependency graph."""

from pathlib import Path
import re


WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/ci.yml"


def job_block(workflow, job):
    match = re.search(
        rf"^  {re.escape(job)}:\n(.*?)(?=^  [\w-]+:\n|\Z)",
        workflow,
        re.MULTILINE | re.DOTALL,
    )
    assert match is not None, f"Missing workflow job: {job}"
    return match.group(1)


def job_needs(workflow, job):
    match = re.search(r"^    needs: \[(.*?)\]$", job_block(workflow, job), re.MULTILINE)
    assert match is not None, f"Missing explicit dependencies for job: {job}"
    return [dependency.strip() for dependency in match.group(1).split(",")]


def test_sdist_runs_after_metadata_without_waiting_for_test_jobs():
    workflow = WORKFLOW.read_text()

    assert job_needs(workflow, "sdist") == ["changes", "metadata"]
    assert job_needs(workflow, "wheels") == [
        "changes", "test", "rust", "sdist"
    ]
    assert job_needs(workflow, "macos-wheels") == [
        "changes", "test", "rust", "sdist"
    ]


def test_release_bundle_waits_for_all_required_jobs_and_preserves_skips():
    workflow = WORKFLOW.read_text()

    assert job_needs(workflow, "distributions") == [
        "changes", "test", "rust", "sdist", "wheels", "macos-wheels"
    ]
    skip_condition = (
        "github.event_name != 'pull_request' && "
        "needs.changes.outputs.code_changed == 'true'"
    )
    assert re.search(
        rf"^    if: {re.escape(skip_condition)}$",
        job_block(workflow, "macos-wheels"),
        re.MULTILINE,
    )
    assert re.search(
        rf"^    if: {re.escape(skip_condition)}$",
        job_block(workflow, "distributions"),
        re.MULTILINE,
    )
