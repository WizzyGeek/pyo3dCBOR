# FEAT_002: Versioned release workflow

**Status:** Implementation is merged on `master`; release behavior still awaits
versioned release validation and owner sign-off.

## Owner-approved scope

- Provide one script that increments only the patch version and keeps
  `pyproject.toml`, root `Cargo.toml`, `python/dcbor/__init__.py`, and root
  `Cargo.lock` consistent.
- Name the complete validated build artifact `release-vX.Y.Z` and include its
  version and source commit provenance.
- On a `vX.Y.Z` tag push, reuse a complete, checksum-valid artifact for that
  exact version and tag commit. If none is available, call the existing full
  build workflow for the tag.
- Validate the bundle, create a draft GitHub Release if needed, attach every
  wheel plus the sdist, checksum manifest, provenance, and a ZIP of the bundle,
  then publish the release. Never overwrite conflicting assets or publish a
  partial set.

## Acceptance criteria

- The patch bump script rejects malformed or inconsistent version metadata and
  increments the patch number in all four version sources.
- The full build uploads exactly 42 version-matched wheels, one matching sdist,
  `SHA256SUMS`, and build provenance under the versioned artifact name.
- The tag workflow requires an exact versioned artifact from the same commit,
  validates provenance, all distributions, and checksums, and otherwise calls
  the reusable full build workflow.
- A release is created as a draft only after validation. All expected wheels,
  the sdist, checksums, provenance, and bundle ZIP are attached before it is
  published.
- Existing matching assets are verified and reused on retry; conflicting
  assets fail without overwriting them. A partial upload remains an unpublished
  draft that can be safely resumed.
- Release permissions are limited to contents write and Actions read; there is
  no PyPI publishing credential or destination.

## Explicit exclusions

- No workflow that opens a version-bump pull request; the patch script is run
  manually by a maintainer.
- No PyPI publishing, automatic tag rewriting, performance work, or unrelated
  CI changes.

## Implementation references

- [Build workflow](../../.github/workflows/ci.yml)
- [Tag release workflow](../../.github/workflows/release.yml)
- [Release bundle validator](../../scripts/ci_release.py)
- [Patch bump script](../../scripts/bump_patch_version.py)
