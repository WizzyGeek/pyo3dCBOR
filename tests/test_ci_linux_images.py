"""Regression checks for the standalone Linux image publishing prototype."""

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/publish-linux-images.yml"
BASE_VERSION = "2026.10.16-1"
BASE_DIGESTS = {
    "manylinux_x86_64": "sha256:1e7b8460ad8fb3fb0fbe1cd818845159ac896b4fd17452d56e892c291f3b97a8",
    "manylinux_aarch64": "sha256:b873ffc316ffe8a154e3dc4872871de2ebd170db4876c8bbd983d42ff320001e",
    "musllinux_x86_64": "sha256:915d73c75b4551f98fd7b12de655ef2e27419a6441ea07472b6e25e0d868d18d",
    "musllinux_aarch64": "sha256:75a9ccd28ccc0abda65e462133f6e324943354e4e4936b51ba7c2ddc98352f86",
}


def test_container_definitions_keep_the_upstream_wheel_environments():
    for family in ("manylinux", "musllinux"):
        dockerfile = (ROOT / f"containers/linux/Dockerfile.{family}").read_text()
        assert "ARG BASE_IMAGE=quay.io/pypa/" in dockerfile
        assert re.search(
            r"ARG BASE_IMAGE=.*@sha256:[0-9a-f]{64}$",
            dockerfile,
            re.MULTILINE,
        )
        assert (
            'LABEL org.opencontainers.image.source="https://github.com/WizzyGeek/pyo3dCBOR"'
            in dockerfile
        )
        assert "FROM ${BASE_IMAGE}" in dockerfile
        assert "ARG RUST_VERSION=1.90.0" in dockerfile
        assert "ARG RUST_TARGET" in dockerfile
        assert "rustup target add" in dockerfile
        assert "CARGO_BUILD_JOBS=2" in dockerfile
        assert "PATH=/root/.cargo/bin:${PATH}" in dockerfile
        assert "rustc --version" in dockerfile
        assert "latest" not in dockerfile


def test_publisher_covers_each_native_libc_and_architecture_pair():
    workflow = WORKFLOW.read_text()
    expected = {
        (
            "manylinux_2_28_x86_64",
            "ubuntu-24.04",
            "linux/amd64",
            "x86_64-unknown-linux-gnu",
            "Dockerfile.manylinux",
            (
                f"quay.io/pypa/manylinux_2_28_x86_64:{BASE_VERSION}"
                f"@{BASE_DIGESTS['manylinux_x86_64']}"
            ),
        ),
        (
            "manylinux_2_28_aarch64",
            "ubuntu-24.04-arm",
            "linux/arm64",
            "aarch64-unknown-linux-gnu",
            "Dockerfile.manylinux",
            (
                f"quay.io/pypa/manylinux_2_28_aarch64:{BASE_VERSION}"
                f"@{BASE_DIGESTS['manylinux_aarch64']}"
            ),
        ),
        (
            "musllinux_1_2_x86_64",
            "ubuntu-24.04",
            "linux/amd64",
            "x86_64-unknown-linux-musl",
            "Dockerfile.musllinux",
            (
                f"quay.io/pypa/musllinux_1_2_x86_64:{BASE_VERSION}"
                f"@{BASE_DIGESTS['musllinux_x86_64']}"
            ),
        ),
        (
            "musllinux_1_2_aarch64",
            "ubuntu-24.04-arm",
            "linux/arm64",
            "aarch64-unknown-linux-musl",
            "Dockerfile.musllinux",
            (
                f"quay.io/pypa/musllinux_1_2_aarch64:{BASE_VERSION}"
                f"@{BASE_DIGESTS['musllinux_aarch64']}"
            ),
        ),
    }
    found = set()
    for family, block in re.findall(
        r"(?m)^          - family: ([^\n]+)\n(.*?)(?=^          - family: |\Z)",
        workflow,
        re.DOTALL,
    ):
        fields = {
            key: re.search(rf"(?m)^            {key}: ([^\n]+)$", block).group(1)
            for key in (
                "arch",
                "runner",
                "platform",
                "rust_target",
                "dockerfile",
                "base_image",
            )
        }
        found.add(
            (
                f"{family}_{fields['arch']}",
                fields["runner"],
                fields["platform"],
                fields["rust_target"],
                fields["dockerfile"].rsplit("/", 1)[-1],
                fields["base_image"],
            )
        )

    assert found == expected
    assert workflow.count("ubuntu-24.04-arm") == 2
    assert "docker buildx build" in workflow
    assert "test \"$AUDITWHEEL_POLICY\" = \"$EXPECTED_POLICY\"" in workflow
    assert "rustup target list --installed" in workflow
    assert "cp39 cp310 cp311 cp312 cp313 cp314" in workflow


def test_publisher_is_branch_gated_least_privilege_and_returns_digests():
    workflow = WORKFLOW.read_text()

    assert "pull_request:" not in workflow
    assert (
        "if: github.ref == 'refs/heads/master' || github.ref == 'refs/heads/main'"
        in workflow
    )
    assert "permissions:\n  contents: read" in workflow
    assert "packages: write" in workflow
    assert "docker login ghcr.io" in workflow
    assert "persist-credentials: false" in workflow
    assert "image_digests: ${{ steps.collect.outputs.image_digests }}" in workflow
    assert "containerimage.digest" in workflow
    assert "Reusing the existing versioned image tag" in workflow
    assert (
        "linux-${FAMILY}-${ARCH}-rust-1.90.0-base-${base_version}-${GITHUB_SHA}"
        in workflow
    )
    assert "latest" not in workflow

    action_refs = re.findall(r"uses: ([^\s]+)", workflow)
    assert action_refs
    assert all(re.fullmatch(r"[^@]+@[0-9a-f]{40}", ref) for ref in action_refs)
