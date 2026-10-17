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


def test_concurrency_cancels_superseded_branch_pushes_and_pr_runs():
    workflow = WORKFLOW.read_text()
    group = (
        "wheels-${{ github.workflow }}-${{ "
        "(github.event_name == 'pull_request' || "
        "(github.event_name == 'push' && github.ref_type == 'branch')) "
        "&& github.ref || github.run_id }}"
    )

    assert re.search(rf"^  group: {re.escape(group)}$", workflow, re.MULTILINE)
    assert re.search(r"^  cancel-in-progress: true$", workflow, re.MULTILINE)


def test_sdist_runs_after_metadata_without_waiting_for_test_jobs():
    workflow = WORKFLOW.read_text()

    assert job_needs(workflow, "sdist") == ["changes", "metadata"]
    assert job_needs(workflow, "wheels") == ["changes", "sdist"]
    assert job_needs(workflow, "macos-wheels") == ["changes", "sdist"]


def test_release_bundle_waits_for_all_required_jobs_and_preserves_skips():
    workflow = WORKFLOW.read_text()

    assert job_needs(workflow, "distributions") == [
        "changes", "test", "rust", "sdist", "wheels", "macos-wheels"
    ]
    full_coverage_condition = (
        "(github.event_name == 'workflow_dispatch' || "
        "github.event_name == 'workflow_call' || "
        "(github.event_name == 'push' && github.ref_type == 'tag')) && "
        "needs.changes.outputs.code_changed == 'true'"
    )
    assert re.search(
        rf"^    if: {re.escape(full_coverage_condition)}$",
        job_block(workflow, "macos-wheels"),
        re.MULTILINE,
    )
    assert re.search(
        rf"^    if: {re.escape(full_coverage_condition)}$",
        job_block(workflow, "distributions"),
        re.MULTILINE,
    )


def test_ordinary_wheel_runs_use_reduced_linux_python_matrix():
    workflow = WORKFLOW.read_text()
    wheels = job_block(workflow, "wheels")

    assert re.search(r"^  workflow_call:$", workflow, re.MULTILINE)
    assert (
        "fromJSON('[\"ubuntu-24.04\",\"ubuntu-24.04-arm\",\"windows-2022\"]') "
        "|| fromJSON('[\"ubuntu-latest\"]')"
    ) in wheels
    assert (
        "fromJSON('[\"cp39\",\"cp310\",\"cp311\",\"cp312\",\"cp313\",\"cp314\"]') "
        "|| fromJSON('[\"cp312\",\"cp313\",\"cp314\"]')"
    ) in wheels
    assert "CIBW_BUILD: ${{ matrix.python }}-*" in wheels
    assert "name: wheels-${{ matrix.os }}-${{ matrix.python }}" in wheels
    assert "max-parallel:" not in wheels


def test_full_wheel_events_build_all_platforms_and_validate_distributions():
    workflow = WORKFLOW.read_text()
    full_matrix_condition = (
        "github.event_name == 'workflow_dispatch' || "
        "github.event_name == 'workflow_call' || "
        "(github.event_name == 'push' && github.ref_type == 'tag')"
    )

    for job in ("wheels", "macos-wheels"):
        assert full_matrix_condition in job_block(workflow, job)
    assert full_matrix_condition in job_block(workflow, "distributions")
    assert job_needs(workflow, "distributions") == [
        "changes", "test", "rust", "sdist", "wheels", "macos-wheels"
    ]
