# Releasing

This project publishes stable releases as GitHub Releases. PyPI publication is
not configured. A release starts when a maintainer pushes a version-matched
`vX.Y.Z` tag; the tag workflow validates the complete distribution bundle
before publishing any assets.

## Prepare a version

For a patch release after the first `0.1.0` release, run the patch bump script
from the repository root:

```sh
python scripts/bump_patch_version.py
```

The script increments only the patch component and updates `pyproject.toml`,
root `Cargo.toml`, `python/dcbor/__init__.py`, and root `Cargo.lock` together.
It stops without updating files if any source is malformed or the four current
versions disagree. Review the resulting diff and run the version check:

```sh
python scripts/ci.py versions
git diff -- pyproject.toml Cargo.toml python/dcbor/__init__.py Cargo.lock
```

For the initial `v0.1.0` release, the repository already carries version
`0.1.0`; do not run the patch bump script because it would advance the project
to `0.1.1`. Confirm the same four files agree instead:

```sh
python scripts/ci.py versions
```

Run the relevant tests, commit the reviewed version change, and push that
commit to `master`. The tag must point to that exact commit and match the
package version. For the initial release, for example:

```sh
git tag v0.1.0
git push origin v0.1.0
```

For later releases, substitute the version produced by the patch bump. Do not
move or rewrite a tag to retry publication. A retry, when supported, uses the
existing Actions run as described below; pushing an unchanged tag does not
create a new tag-push event.

## What the workflows build and publish

The tag workflow first looks for a successful `ci.yml` run on the tag commit
with the exact `release-vX.Y.Z` artifact. It downloads and validates that
artifact's tag version, source commit, build run ID, distribution set, and
SHA-256 checksums. A valid artifact is reused. If it is missing, expired,
cannot be downloaded, or fails validation, the release workflow calls the full
reusable build workflow for the tag. A GitHub API error while listing workflow
runs or artifacts fails the prepare job instead of starting that fallback.

The full build validates and packages 42 wheels (six CPython versions across
seven platform/architecture combinations), one source archive, `SHA256SUMS`,
and `BUILD-PROVENANCE.json` into the versioned artifact. The artifact is
retained for 30 days. The tag workflow validates the resulting bundle again
before creating or updating a GitHub Release.

The published release contains every wheel, the source archive, the checksum
manifest, build provenance, and `dcbor-vX.Y.Z-bundle.zip`. The workflow uses
the repository's `GITHUB_TOKEN` with release contents write and Actions read
permissions; it needs no personal token or PyPI credentials.

## Retry behavior

The workflow creates a release as a draft only after bundle validation. It
uploads all expected assets, checks that they are present, then publishes the
draft. A failed or interrupted upload can leave an unpublished draft.

If the publish job fails after a validated bundle has been built, open that
same failed tag-triggered release run in GitHub Actions and choose **Re-run
failed jobs**. This reuses the run's bundle and checks existing release assets
again. The staged candidate bundle is retained for one day; the full
`release-vX.Y.Z` build artifact is retained for 30 days, so this retry works
only while the artifact needed by the failed job is still available.

On retry, an existing expected asset is downloaded and compared byte for
byte. Identical assets are reused; a conflicting asset causes the workflow to
fail without replacing it. A published release is left intact when all
expected assets already match. If a published release is missing an expected
asset, the workflow fails rather than altering it.

The release workflow has no manual-dispatch trigger. Rerunning a failed publish
job is not a guaranteed recovery if bundle validation/build failed earlier,
the required artifact expired or is unavailable, or a conflicting asset or
permission problem remains. In those cases the workflow provides no automatic
same-tag retry path; a maintainer must resolve the underlying state explicitly.
Do not force-push or rewrite the tag.

The workflow accepts stable `vX.Y.Z` tags only. It does not publish to PyPI,
rewrite tags, or overwrite release assets.

## FEAT_002 acceptance and PM sign-off

Signed off by Codex GPT-6, PM agent, on **2026-10-18** following owner
confirmation and independent source/test review.

- [Published v0.1.0 release](https://github.com/WizzyGeek/pyo3dCBOR/releases/tag/v0.1.0):
  all 46 expected assets are uploaded: 42 wheels (seven platforms for each of
  CPython 3.9–3.14), one sdist, checksums, provenance, and the bundle ZIP.
  All 43 distribution digests match the published checksum manifest.
- [Successful release run 39073424944](https://github.com/WizzyGeek/pyo3dCBOR/actions/runs/39073424944):
  the full build, tests, bundle validation, and publication passed. The tag and
  published provenance both identify commit `ae43fc10ab804f9fdc4d4a3fc38112426cd9f70b`;
  provenance records that same run ID.
- Local acceptance checks cover the four-file patch bump, artifact validation,
  and publication guards. Draft lookup uses `gh release view --json isDraft`;
  the REST lookup by tag returns only published releases. Matching assets are
  compared before reuse, conflicting assets are never overwritten, and
  incomplete published releases are left untouched.

FEAT_002 is complete. Its open requirement was removed under the
[requirements cleanup protocol](requirements/README.md#sign-off-and-cleanup).
