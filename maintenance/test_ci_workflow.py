"""Structural checks for the CI workflow's dependency and permission model.

These checks read the workflow as YAML, so harmless formatting and dependency
ordering changes do not affect them. They verify the declared job graph and
permissions only; GitHub Actions still decides whether jobs run based on event
contexts, expressions, and scheduler semantics.
"""

from pathlib import Path

import yaml


WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/ci.yml"
RELEASE_WORKFLOW = WORKFLOW.with_name("release.yml")


def workflow_jobs():
    """Load the workflow without YAML 1.1's special treatment of the `on` key."""
    workflow = yaml.load(WORKFLOW.read_text(), Loader=yaml.BaseLoader)
    return workflow, workflow["jobs"]


def release_jobs():
    workflow = yaml.load(RELEASE_WORKFLOW.read_text(), Loader=yaml.BaseLoader)
    return workflow, workflow["jobs"]


def dependencies(jobs):
    """Return each job's direct `needs` dependencies as a set."""
    graph = {}
    for name, job in jobs.items():
        needs = job.get("needs", [])
        if isinstance(needs, str):
            needs = [needs]
        graph[name] = set(needs)
    return graph


def ancestors(graph, job):
    """Return all jobs that must precede `job` in the declared needs graph."""
    found = set()
    pending = list(graph[job])
    while pending:
        dependency = pending.pop()
        if dependency not in found:
            found.add(dependency)
            pending.extend(graph[dependency])
    return found


def test_release_bundle_is_gated_by_all_required_checks_and_builds():
    _, jobs = workflow_jobs()
    graph = dependencies(jobs)
    required_before_bundle = {
        "changes",
        "metadata",
        "test",
        "rust",
        "sdist",
        "wheels",
        "macos-wheels",
    }

    assert required_before_bundle <= ancestors(graph, "distributions")
    assert "release" not in jobs


def test_tag_release_reuses_or_builds_and_then_publishes_bundle():
    workflow, jobs = release_jobs()
    triggers = workflow["on"]
    assert triggers["push"]["tags"] == ["v*"]
    assert jobs["build-if-missing"]["uses"] == "./.github/workflows/ci.yml"
    assert jobs["build-if-missing"]["with"]["full_matrix"] == "true"
    assert {"prepare", "build-if-missing"} <= set(jobs["publish"]["needs"])
    assert jobs["publish"]["permissions"] == {
        "contents": "write",
        "actions": "read",
    }
    assert workflow["permissions"] == {"contents": "read", "actions": "read"}
    publisher = "\n".join(
        step.get("run", "") for step in jobs["publish"]["steps"]
    )
    assert "gh release create" in publisher and "--draft" in publisher
    assert "gh release edit" in publisher and "--draft=false" in publisher
    assert "gh release upload" in publisher
    assert "--clobber" not in publisher

    build_workflow, _ = workflow_jobs()
    assert "tags" not in build_workflow["on"].get("push", {})


def test_build_bundle_name_is_versioned_and_contains_provenance():
    _, jobs = workflow_jobs()
    distributions = jobs["distributions"]
    upload = next(
        step
        for step in distributions["steps"]
        if step.get("uses", "").startswith("actions/upload-artifact@")
    )

    assert "${{ needs.metadata.outputs.version }}" in upload["with"]["name"]
    assert any(step.get("name") == "Record release bundle provenance" for step in distributions["steps"])


def test_source_and_wheel_builds_keep_independent_parallel_paths():
    _, jobs = workflow_jobs()
    graph = dependencies(jobs)

    # The source build, Python tests, and Rust tests share their setup gates,
    # while remaining independent of each other. Both wheel families start
    # from the source archive and can run alongside the test jobs.
    for job in ("test", "rust", "sdist"):
        assert {"changes", "metadata"} <= ancestors(graph, job)

    for build in ("wheels", "macos-wheels"):
        assert {"changes", "sdist"} <= ancestors(graph, build)
        assert not ({"test", "rust"} & ancestors(graph, build))

    for left, right in (("sdist", "test"), ("sdist", "rust"), ("test", "rust")):
        assert left not in ancestors(graph, right)
        assert right not in ancestors(graph, left)


def test_build_jobs_are_read_only_and_only_release_can_write_contents():
    workflow, jobs = workflow_jobs()
    defaults = workflow["permissions"]
    assert defaults == {"contents": "read"}

    for name, job in jobs.items():
        effective_permissions = job.get("permissions", defaults)
        assert effective_permissions == {"contents": "read"}
