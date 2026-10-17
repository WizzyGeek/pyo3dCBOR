# FEAT_002: Versioned release and bundle workflow

**Status:** Proposed; workflow behavior specified, implementation not started.

## Problem

The current release process requires maintainers to update the package version
in multiple files, refresh the Cargo lockfile, push a matching version tag, and
rely on the tag-push workflow to build and publish the release. The build
artifacts use generic names and are retained for a limited period, so a later
release workflow cannot reliably identify and reuse a bundle for a particular
version.

This makes releases more manual than necessary and can rebuild an already
validated version bundle, or leave a newly created GitHub Release without its
distribution files if build and release creation are not coordinated.

## Desired outcome

Provide an auditable release path that:

1. Automates synchronizing the repository's version declarations and lockfile
   for a requested new version.
2. Produces a validated, version-identified bundle containing all 42 wheels,
   the matching sdist, and `SHA256SUMS`.
3. Runs release fulfillment when a new non-draft GitHub Release is published.
   It reuses a valid bundle for that exact version and release commit when
   available; otherwise it builds and validates the bundle from the release
   tag.
4. Attaches the complete validated bundle to the GitHub Release without
   publishing partial or mismatched assets.

## Proposed release flow

### 1. Prepare and merge the version bump

Add a manually dispatched release-preparation workflow with a requested
`X.Y.Z` version input. It must:

- Accept only the repository's supported stable `major.minor.patch` version
  format and reject the current version or any prohibited regression.
- Update `pyproject.toml`, the root `Cargo.toml`, and
  `python/dcbor/__init__.py`; refresh the root `Cargo.lock` consistently.
- Run the existing version guards and focused tests, and show the resulting
  diff.
- Prefer opening a version-bump pull request rather than pushing directly to
  the protected default branch. Do not create or publish a release before the
  bump is merged and validated.

The merged version-bump commit is the source of truth for its release. A
matching `vX.Y.Z` tag and GitHub Release must refer to that commit. This avoids
having a release workflow modify the repository after the release tag has
already selected its source.

### 2. Build and identify the release bundle

The normal tag/CI build must upload the fully validated bundle under a
version-specific name, for example `release-vX.Y.Z`. The bundle must contain
exactly:

- 42 version-matched platform/Python wheels;
- one version-matched source archive (`dcbor-X.Y.Z.tar.gz`); and
- `SHA256SUMS` covering the distribution files.

Include provenance sufficient to associate the bundle with the version tag,
tag commit SHA, and successful validation run. Version alone is not enough to
reuse an artifact: the commit SHA and bundle contents must match the release.
Do not reuse an artifact from a different commit merely because its name has
the same version.

GitHub Actions artifacts have finite retention and are scoped to workflow runs.
The implementation must make version-based lookup reliable across runs and
define a retention strategy appropriate to the time between tag build and
release publication. If the expected artifact is absent, expired, inaccessible,
or fails provenance/checksum/distribution validation, treat it as unavailable
and rebuild from the release tag. A cache/artifact lookup failure must not
silently turn into a successful release with missing assets.
If the tag's CI build is still running when the release is published, the
release workflow should wait for that run to finish before treating its bundle
as missing, avoiding an unnecessary duplicate 42-wheel build.

### 3. Fulfill the published release

Add a release workflow triggered on publication of a GitHub Release
(`release` event with the publication activity type), not when a draft release
is first saved. Publish the release through an identity that triggers the
workflow: events caused by the repository's `GITHUB_TOKEN` generally do not
start another workflow run.

The workflow must:

1. Validate the release tag is exactly `vX.Y.Z` and matches all repository
   version declarations at the tagged commit.
2. Look up the version-identified bundle and verify that it was built from the
   release tag's commit and passed the complete existing distribution checks.
3. If no valid bundle exists, build the full set from the release tag and run
   the existing test, sdist, wheel, and distribution-validation gates before
   proceeding.
4. Attach all validated distributions and checksums to the release.
5. Fail visibly on an incomplete/corrupt bundle or upload error; never mark
   release fulfillment successful after attaching only part of the bundle.

Use a per-version concurrency/idempotency guard. A retry must safely recognize
already attached assets with matching checksums and must not overwrite
different existing assets or silently replace a published release's content.
Define an explicit recovery procedure for a failed partial upload.

## Acceptance criteria

- A manually requested version bump synchronizes all public version
  declarations and the root lockfile, passes existing version checks, and
  creates a reviewable change without directly bypassing default-branch
  protections.
- The build artifact name or equivalent durable lookup key identifies its
  version, and its provenance identifies the exact tag commit.
- Publishing a non-draft `vX.Y.Z` release uses a valid matching bundle when
  available and does not rerun builds unnecessarily.
- If the matching tag build is in progress, release fulfillment waits for its
  result before deciding whether to reuse or rebuild.
- With no prior bundle, the release workflow builds from the release tag,
  passes all existing required checks, and only then attaches assets.
- A same-version artifact from another commit, an expired/unavailable artifact,
  bad checksums, wrong version metadata, missing wheels, or missing sdist is
  rejected as a reuse candidate and cannot produce a successful partial
  release.
- The attached set contains exactly the expected 42 wheels, one sdist, and its
  checksum manifest. Checksums are verified before upload and can be verified
  after download.
- Draft releases do not trigger asset attachment. Existing matching assets are
  handled idempotently; conflicting assets cause a visible failure requiring
  explicit maintainer recovery.
- The release-creation method is verified to trigger the fulfillment workflow;
  the current workflow must not create a release with `GITHUB_TOKEN` and then
  assume that this release event will start a second workflow.
- Tag/version mismatch, duplicate-version attempt, insufficient permissions,
  and upload failures are tested or otherwise exercised before enabling
  automatic release fulfillment.
- The current tag-push release job is replaced or coordinated so two workflows
  cannot build/publish the same release concurrently or attach conflicting
  assets.
- Release workflow permissions are least-privilege and do not include PyPI
  publishing credentials; GitHub Releases remain the distribution destination.

## Non-goals

- Publishing to PyPI.
- Changing the supported Python/platform wheel matrix or reducing its 42
  distributions.
- Automatically editing a published tag or release after a failure.
- Reusing artifacts solely by matching a mutable artifact name, without
  checking version, commit provenance, contents, and checksums.
- Bypassing repository branch protections for version bump changes.

## Research and implementation notes

- The current [CI workflow](../../.github/workflows/ci.yml) triggers on tag
  pushes and has a release job that creates a GitHub Release after validating a
  generic `release-bundle` artifact. This behavior must be coordinated with,
  not duplicated by, the proposed `release` event workflow.
- [`scripts/ci.py`](../../scripts/ci.py) validates the package/tag version,
  exact expected wheel matrix, sdist contents, and writes `SHA256SUMS`. Reuse
  these checks rather than implementing a weaker parallel validator.
- The current workflow retains wheel artifacts for 14 days and the combined
  `release-bundle` artifact for 30 days. GitHub's
  [workflow artifact documentation](https://docs.github.com/en/actions/tutorials/store-and-share-data)
  describes artifacts as run outputs and their retention controls; the release
  design must account for lookup across runs and expiration.
- GitHub's [release event documentation](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#release)
  describes release activity types. Choose publication-time behavior so draft
  creation does not start fulfillment. GitHub's
  [workflow trigger documentation](https://docs.github.com/en/actions/concepts/security/github_token#when-github_token-triggers-workflow-runs)
  also documents the restrictions on events caused by `GITHUB_TOKEN`.
- Before implementation, decide whether the versioned bundle is retained as a
  long-lived Actions artifact or stored in another durable, access-controlled
  location until attached. In either case, expiration or lookup failure must
  take the validated rebuild path.
