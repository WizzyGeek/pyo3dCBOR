"""Behavioral checks for versioned release bundle validation and packaging."""

import json
from pathlib import Path
import zipfile

import pytest

from maintenance import test_ci_distributions as fixtures
from scripts import ci_release


COMMIT_SHA = "a" * 40
TAG = f"v{fixtures.VERSION}"


def test_artifact_name_is_an_exact_versioned_tag_key():
    assert ci_release.artifact_name("v1.2.3") == "release-v1.2.3"
    with pytest.raises(ValueError, match="release tag must be vX.Y.Z"):
        ci_release.artifact_name("v1.2.30rc1")


def make_bundle(path: Path, *, commit_sha: str = COMMIT_SHA, version: str = fixtures.VERSION):
    fixtures._write_complete_distribution(path)
    fixtures.CI.distributions(path)
    provenance = {
        "version": version,
        "commit_sha": commit_sha,
        "run_id": 12345,
    }
    (path / "BUILD-PROVENANCE.json").write_text(
        json.dumps(provenance, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )


def test_validates_matching_tag_commit_and_complete_distribution_bundle(tmp_path):
    make_bundle(tmp_path)

    assert ci_release.validate_bundle(tmp_path, TAG, COMMIT_SHA) == fixtures.VERSION


@pytest.mark.parametrize(
    ("tag", "commit_sha", "error"),
    [
        ("v1.2.3-rc1", COMMIT_SHA, "release tag must be vX.Y.Z"),
        (TAG, "short-sha", "full lowercase Git SHA"),
    ],
)
def test_rejects_bad_tag_or_commit_before_reuse(tmp_path, tag, commit_sha, error):
    make_bundle(tmp_path)

    with pytest.raises(ValueError, match=error):
        ci_release.validate_bundle(tmp_path, tag, commit_sha)


def test_rejects_provenance_from_another_commit(tmp_path):
    make_bundle(tmp_path, commit_sha="b" * 40)

    with pytest.raises(ValueError, match="commit does not match"):
        ci_release.validate_bundle(tmp_path, TAG, COMMIT_SHA)


def test_rejects_provenance_from_another_build_run(tmp_path):
    make_bundle(tmp_path)

    with pytest.raises(ValueError, match="run_id does not match"):
        ci_release.validate_bundle(tmp_path, TAG, COMMIT_SHA, expected_run_id=54321)


def test_rejects_modified_distribution_even_when_bundle_name_matches(tmp_path):
    make_bundle(tmp_path)
    wheel = next(tmp_path.glob("*.whl"))
    wheel.write_bytes(wheel.read_bytes() + b"tampered")

    with pytest.raises(ValueError, match="checksum mismatch"):
        ci_release.validate_bundle(tmp_path, TAG, COMMIT_SHA)


def test_creates_deterministic_zip_with_every_bundle_file(tmp_path):
    bundle = tmp_path / "dist"
    make_bundle(bundle)
    first = tmp_path / "first.zip"
    second = tmp_path / "second.zip"

    ci_release.create_bundle_archive(bundle, first)
    ci_release.create_bundle_archive(bundle, second)

    assert first.read_bytes() == second.read_bytes()
    with zipfile.ZipFile(first) as archive:
        assert set(archive.namelist()) == {path.name for path in bundle.iterdir()}


def test_rejects_unexpected_bundle_file(tmp_path):
    make_bundle(tmp_path)
    (tmp_path / "unvalidated.txt").write_text("extra", encoding="utf-8")

    with pytest.raises(ValueError, match="unexpected files"):
        ci_release.validate_bundle(tmp_path, TAG, COMMIT_SHA)
