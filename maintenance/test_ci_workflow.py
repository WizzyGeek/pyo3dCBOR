"""Structural checks for the CI workflow's dependency and permission model.

These checks read the workflow as YAML, so harmless formatting and dependency
ordering changes do not affect them. They verify the declared job graph and
permissions only; GitHub Actions still decides whether jobs run based on event
contexts, expressions, and scheduler semantics.
"""

import json
import os
from pathlib import Path
import subprocess

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


def publisher_script():
    _, jobs = release_jobs()
    return next(
        step["run"]
        for step in jobs["publish"]["steps"]
        if step.get("name") == "Upload assets without replacing conflicting release files"
    )


def run_publisher(tmp_path, *, is_draft):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    for name in (
        "dcbor-0.1.0-cp314-cp314-manylinux_x86_64.whl",
        "dcbor-0.1.0.tar.gz",
        "SHA256SUMS",
        "BUILD-PROVENANCE.json",
        "dcbor-v0.1.0-bundle.zip",
    ):
        (dist_dir / name).write_text(name, encoding="utf-8")

    state_path = tmp_path / "release-state.json"
    calls_path = tmp_path / "gh-calls.json"
    state_path.write_text(
        json.dumps({"is_draft": is_draft, "assets": []}), encoding="utf-8"
    )
    gh = bin_dir / "gh"
    gh.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, pathlib, sys\n"
        "state_path = pathlib.Path(os.environ['GH_STATE'])\n"
        "calls_path = pathlib.Path(os.environ['GH_CALLS'])\n"
        "state = json.loads(state_path.read_text())\n"
        "calls = json.loads(calls_path.read_text()) if calls_path.exists() else []\n"
        "args = sys.argv[1:]\n"
        "calls.append(args)\n"
        "calls_path.write_text(json.dumps(calls))\n"
        "if args[:2] == ['release', 'view']:\n"
        "    if '--json' not in args:\n"
        "        sys.exit(0)\n"
        "    query = args[args.index('--json') + 1]\n"
        "    if query == 'isDraft': print(str(state['is_draft']).lower())\n"
        "    elif query == 'assets': print(json.dumps(state['assets']))\n"
        "    else: sys.exit(2)\n"
        "elif args[:2] == ['release', 'upload']:\n"
        "    repo_index = args.index('--repo')\n"
        "    state['assets'].extend(pathlib.Path(p).name for p in args[3:repo_index])\n"
        "    state_path.write_text(json.dumps(state))\n"
        "elif args[:2] == ['release', 'edit']:\n"
        "    if '--draft=false' not in args: sys.exit(2)\n"
        "    state['is_draft'] = False\n"
        "    state_path.write_text(json.dumps(state))\n"
        "elif args[:1] == ['api']:\n"
        "    print('draft tag endpoint returns 404', file=sys.stderr)\n"
        "    sys.exit(1)\n"
        "else:\n"
        "    print('unexpected gh invocation: ' + repr(args), file=sys.stderr)\n"
        "    sys.exit(2)\n",
        encoding="utf-8",
    )
    gh.chmod(0o755)
    jq = bin_dir / "jq"
    jq.write_text(
        "#!/usr/bin/env python3\n"
        "import json, sys\n"
        "args = sys.argv[1:]\n"
        "if args[:3] != ['-e', '--arg', 'name'] or args[4:] != ['index($name) != null']:\n"
        "    print('unexpected jq invocation: ' + repr(args), file=sys.stderr)\n"
        "    sys.exit(2)\n"
        "name = args[3]\n"
        "sys.exit(0 if name in json.load(sys.stdin) else 1)\n",
        encoding="utf-8",
    )
    jq.chmod(0o755)

    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{bin_dir}{os.pathsep}{env['PATH']}",
            "GH_REPO": "owner/repository",
            "RELEASE_TAG": "v0.1.0",
            "GH_STATE": str(state_path),
            "GH_CALLS": str(calls_path),
        }
    )
    result = subprocess.run(
        ["bash", "-c", publisher_script()],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    state = json.loads(state_path.read_text(encoding="utf-8"))
    calls = json.loads(calls_path.read_text(encoding="utf-8"))
    return result, state, calls


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


def test_draft_release_publishes_using_draft_aware_release_view(tmp_path):
    result, state, calls = run_publisher(tmp_path, is_draft=True)

    assert result.returncode == 0, result.stderr
    assert state["is_draft"] is False
    assert len(state["assets"]) == 5
    assert calls[-1][:2] == ["release", "edit"]
    assert any(
        call[:3] == ["release", "view", "v0.1.0"] and "isDraft" in call
        for call in calls
    )
    assert not any(call[:1] == ["api"] for call in calls)


def test_published_release_missing_assets_is_left_untouched(tmp_path):
    result, state, calls = run_publisher(tmp_path, is_draft=False)

    assert result.returncode != 0
    assert "Published release is missing expected assets; refusing to alter it." in result.stderr
    assert state["is_draft"] is False
    assert state["assets"] == []
    assert not any(call[:2] in (["release", "upload"], ["release", "edit"]) for call in calls)


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
