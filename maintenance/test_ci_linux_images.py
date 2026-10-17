"""Behavioral checks for Linux image selection and publishing."""

from pathlib import Path
import copy
import json
import os
import platform
import re
import runpy
import shutil
import subprocess
import sys

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/publish-linux-images.yml"
SELECTOR = runpy.run_path(str(ROOT / "scripts/ci_linux_images.py"))
PUBLISHER_WORKFLOW = yaml.load(WORKFLOW.read_text(), Loader=yaml.BaseLoader)
PUBLISH_STEP = next(
    step
    for step in PUBLISHER_WORKFLOW["jobs"]["publish"]["steps"]
    if step.get("name") == "Publish versioned image and record digest"
)
PUBLISH_SCRIPT = PUBLISH_STEP["run"]


def image_manifest():
    return json.loads((ROOT / "containers/linux/images.json").read_text())


def test_maintained_mode_requires_all_digest_pins_and_disables_bootstrap():
    environment = SELECTOR["image_environment"]("maintained", image_manifest())
    assert len(environment) == 3
    assert "rustup-init" not in environment["CIBW_BEFORE_ALL_LINUX"]
    assert "validate-image.sh" in environment["CIBW_BEFORE_ALL_LINUX"]
    assert sum("@sha256:" in value for value in environment.values()) == 2
    assert set(environment) == {
        "CIBW_MANYLINUX_X86_64_IMAGE",
        "CIBW_MUSLLINUX_X86_64_IMAGE",
        "CIBW_BEFORE_ALL_LINUX",
    }


@pytest.mark.parametrize(
    "defect", ["missing", "unexpected_arch", "mutable", "newline", "rust"]
)
def test_bad_image_configuration_fails_before_emitting_environment(defect):
    manifest = copy.deepcopy(image_manifest())
    key = "manylinux_x86_64"
    if defect == "missing":
        manifest["images"].pop(key)
    elif defect == "unexpected_arch":
        manifest["images"]["manylinux_aarch64"] = (
            "ghcr.io/wizzygeek/pyo3dcbor@sha256:" + "a" * 64
        )
    elif defect == "mutable":
        manifest["images"][key] = "ghcr.io/wizzygeek/pyo3dcbor:latest"
    elif defect == "newline":
        manifest["images"][key] += "\nCIBW_BUILD=bad"
    else:
        manifest["rust_version"] = "stable"
    with pytest.raises(ValueError):
        SELECTOR["image_environment"]("maintained", manifest)


def test_upstream_mode_leaves_project_image_and_bootstrap_defaults_intact():
    assert SELECTOR["image_environment"]("upstream", {}) == {}
    with pytest.raises(ValueError):
        SELECTOR["image_environment"]("typo", image_manifest())


def test_selector_cli_emits_all_validated_environment_assignments(tmp_path):
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/ci_linux_images.py"), "maintained"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    )
    actual = dict(line.split("=", 1) for line in result.stdout.splitlines())
    manifest = image_manifest()
    expected = {
        f"CIBW_{key.upper()}_IMAGE": value
        for key, value in manifest["images"].items()
    }
    expected["CIBW_BEFORE_ALL_LINUX"] = (
        "bash {project}/containers/linux/validate-image.sh"
    )
    assert actual == expected


def test_publisher_matrix_covers_native_x86_64_glibc_and_musl_images():
    entries = PUBLISHER_WORKFLOW["jobs"]["publish"]["strategy"]["matrix"]["include"]
    assert len(entries) == 2
    expected = {
        (
            "manylinux_2_28",
            "x86_64",
            "linux/amd64",
            "manylinux_2_28",
            "x86_64-unknown-linux-gnu",
            "containers/linux/Dockerfile.manylinux",
        ),
        (
            "musllinux_1_2",
            "x86_64",
            "linux/amd64",
            "musllinux_1_2",
            "x86_64-unknown-linux-musl",
            "containers/linux/Dockerfile.musllinux",
        ),
    }
    actual = {
        (
            entry["family"],
            entry["arch"],
            entry["platform"],
            entry["policy"],
            entry["rust_target"],
            entry["dockerfile"],
        )
        for entry in entries
    }
    assert actual == expected
    for entry in entries:
        assert entry["runner"] == "ubuntu-24.04"
        assert re.fullmatch(
            rf"quay\.io/pypa/{re.escape(entry['family'])}_x86_64:[^@]+@sha256:[0-9a-f]{{64}}",
            entry["base_image"],
        )


DOCKER_STUB = r'''#!/usr/bin/env python3
import json
import os
import sys

args = sys.argv[1:]
with open(os.environ["DOCKER_LOG"], "a", encoding="utf-8") as log:
    log.write(json.dumps(args) + "\n")

if args[:3] == ["buildx", "imagetools", "inspect"]:
    count_file = os.environ["INSPECT_COUNT"]
    try:
        count = int(open(count_file, encoding="utf-8").read())
    except FileNotFoundError:
        count = 0
    count += 1
    with open(count_file, "w", encoding="utf-8") as count_out:
        count_out.write(str(count))

    existing = os.environ.get("EXISTING_TAG") == "1"
    if existing or count > 1:
        digest = os.environ["INSPECT_DIGEST"]
        print(f"Name: simulated-image\nDigest: {digest}")
        sys.exit(0)
    failure = os.environ.get("INSPECT_FAILURE", "notfound")
    if failure == "notfound":
        print(f"ERROR: {args[3]}: not found", file=sys.stderr)
    elif failure == "network":
        print("failed to fetch anonymous token: connection timed out", file=sys.stderr)
    elif failure == "permission":
        print(
            f"ERROR: denied: requested access to the resource is denied ({args[3]})",
            file=sys.stderr,
        )
    sys.exit(1)

if args and args[0] == "pull" and os.environ.get("PULL_FAIL") == "1":
    print("simulated pull failure", file=sys.stderr)
    sys.exit(1)

if args and args[0] == "run" and os.environ.get("RUN_FAIL") == "1":
    print("simulated runtime validation failure", file=sys.stderr)
    sys.exit(1)
'''


def publisher_prerequisites():
    if platform.system() != "Linux":
        pytest.skip("publisher shell integration requires Linux")
    if not shutil.which("bash") or not shutil.which("jq"):
        pytest.skip("publisher shell integration requires bash and jq")


def run_publisher(
    tmp_path,
    *,
    existing=False,
    digest=None,
    pull_fail=False,
    run_fail=False,
    inspect_failure="notfound",
):
    publisher_prerequisites()
    docker_dir = tmp_path / "bin"
    docker_dir.mkdir()
    docker = docker_dir / "docker"
    docker.write_text(DOCKER_STUB)
    docker.chmod(0o755)

    output_file = tmp_path / "github-output"
    output_file.write_text("")
    log_file = tmp_path / "docker.jsonl"
    inspect_count = tmp_path / "inspect-count"
    script = PUBLISH_SCRIPT.replace("${{ matrix.family }}", "manylinux_2_28")
    script = script.replace("${{ matrix.arch }}", "x86_64")
    env = os.environ.copy()
    env.update(
        {
            "ARCH": "x86_64",
            "BASE_IMAGE": (
                "quay.io/pypa/manylinux_2_28_x86_64:release-7@sha256:"
                + "a" * 64
            ),
            "DOCKER_LOG": str(log_file),
            "EXISTING_TAG": "1" if existing else "0",
            "FAMILY": "manylinux_2_28",
            "GITHUB_OUTPUT": str(output_file),
            "GITHUB_REPOSITORY": "WizzyGeek/pyo3dCBOR",
            "GITHUB_SHA": "test-commit-sha",
            "INSPECT_COUNT": str(inspect_count),
            "INSPECT_DIGEST": digest or "sha256:" + "b" * 64,
            "INSPECT_FAILURE": inspect_failure,
            "PATH": str(docker_dir) + os.pathsep + env["PATH"],
            "PLATFORM": "linux/amd64",
            "PULL_FAIL": "1" if pull_fail else "0",
            "PWD": str(tmp_path),
            "RUST_TARGET": "x86_64-unknown-linux-gnu",
            "RUN_FAIL": "1" if run_fail else "0",
        }
    )
    result = subprocess.run(
        ["bash", "-c", script],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )
    calls = [json.loads(line) for line in log_file.read_text().splitlines()]
    return result, calls, output_file


def assert_no_success_output(tmp_path, output_file):
    assert not (tmp_path / "image-digest.json").exists()
    assert output_file.read_text() == ""


def test_publisher_pushes_tested_image_without_rebuilding_and_records_registry_digest(
    tmp_path,
):
    published_digest = "sha256:" + "c" * 64
    result, calls, output_file = run_publisher(tmp_path, digest=published_digest)

    assert result.returncode == 0, result.stderr
    tag_call = next(call for call in calls if call[0] == "tag")
    push_call = next(call for call in calls if call[0] == "push")
    pull_call = next(call for call in calls if call[0] == "pull")
    run_call = next(call for call in calls if call[0] == "run")
    assert tag_call[1] == "linux-image-check:manylinux_2_28-x86_64"
    assert tag_call[2].startswith(
        "ghcr.io/wizzygeek/pyo3dcbor:linux-manylinux_2_28-"
    )
    assert push_call[1] == tag_call[2]
    assert not any(call[:2] == ["buildx", "build"] for call in calls)
    assert (
        calls.index(tag_call)
        < calls.index(push_call)
        < calls.index(pull_call)
        < calls.index(run_call)
    )
    assert pull_call == ["pull", f"ghcr.io/wizzygeek/pyo3dcbor@{published_digest}"]
    assert run_call[-5:] == [
        f"ghcr.io/wizzygeek/pyo3dcbor@{published_digest}",
        "bash",
        "/validate-image.sh",
        "manylinux_2_28",
        "x86_64",
    ]

    artifact = json.loads((tmp_path / "image-digest.json").read_text())
    assert artifact == {
        "family": "manylinux_2_28",
        "arch": "x86_64",
        "image": "ghcr.io/wizzygeek/pyo3dcbor",
        "tag": "linux-manylinux_2_28-x86_64-rust-1.90.0-base-release-7-test-commit-sha",
        "digest": published_digest,
    }
    outputs = dict(line.split("=", 1) for line in output_file.read_text().splitlines())
    assert outputs == {
        "image": artifact["image"],
        "tag": artifact["tag"],
        "digest": published_digest,
    }


def test_publisher_reuses_existing_tag_without_pushing(tmp_path):
    existing_digest = "sha256:" + "d" * 64
    result, calls, output_file = run_publisher(
        tmp_path, existing=True, digest=existing_digest
    )

    assert result.returncode == 0, result.stderr
    assert not any(call[0] in {"tag", "push"} for call in calls)
    assert any(call[:3] == ["buildx", "imagetools", "inspect"] for call in calls)
    assert any(
        call[0] == "pull" and call[1].endswith(existing_digest) for call in calls
    )
    assert any(
        call[0] == "run"
        and call[-5] == f"ghcr.io/wizzygeek/pyo3dcbor@{existing_digest}"
        for call in calls
    )
    artifact = json.loads((tmp_path / "image-digest.json").read_text())
    assert artifact["digest"] == existing_digest
    assert f"digest={existing_digest}" in output_file.read_text().splitlines()


@pytest.mark.parametrize(
    ("failure", "digest"),
    [
        ("invalid digest", "sha256:bad"),
        ("pull", "sha256:" + "e" * 64),
        ("runtime validation", "sha256:" + "f" * 64),
    ],
)
def test_publisher_failures_return_nonzero_without_success_output(
    tmp_path, failure, digest
):
    result, _, output_file = run_publisher(
        tmp_path,
        digest=digest,
        pull_fail=failure == "pull",
        run_fail=failure == "runtime validation",
    )

    assert result.returncode != 0, result.stdout
    assert_no_success_output(tmp_path, output_file)


@pytest.mark.parametrize("inspect_failure", ["network", "permission"])
def test_ambiguous_inspect_failures_never_publish_or_emit_digest(
    tmp_path, inspect_failure
):
    result, calls, output_file = run_publisher(
        tmp_path, inspect_failure=inspect_failure
    )

    assert result.returncode != 0
    assert any(call[:3] == ["buildx", "imagetools", "inspect"] for call in calls)
    assert not any(call[0] in {"tag", "push", "pull", "run"} for call in calls)
    assert_no_success_output(tmp_path, output_file)
