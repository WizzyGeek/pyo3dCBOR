# Maintained Linux wheel environments

Routine reduced Linux runs (PRs and branch pushes, CPython 3.12–3.14 on x86_64)
use the maintained, digest-pinned images for a fixed build environment. Full
manual, reusable, and release-tag matrices keep the existing upstream images.
This is a reproducibility choice, not a claim of faster setup.

`images.json` records all four reviewed image references by **registry manifest
digest**, plus the publisher source commit and Actions run. These are not the
hashes of the Actions artifact ZIPs named `digest-*`. Resolve the reference and
check the JSON artifact contents before updating any pin.

The current four references were obtained from the JSON artifacts in
[publisher run 39051517661](https://github.com/WizzyGeek/pyo3dCBOR/actions/runs/39051517661).
All four were anonymously readable from GHCR on 2026-10-18. Their returned
manifest bytes match the recorded SHA-256 values; their configs report the
expected amd64/arm64 architecture, libc policy, and Rust 1.90.0 toolchain.
The subsequent full trial passed all 42 wheels using these images. See the
[trial report](../../docs/ci-linux-image-trial.md) for evidence and measurements.
The trial establishes compatibility; it has not established a setup-speed win.

## Consumption policy and rollback

The image mode uses the same event condition as the full/reduced wheel matrix.
Reduced jobs select the two pinned x86_64 libc images, pull and validate each,
and then build and test wheels from the tested sdist. Their summaries record
mode and digests; pull/validation logs include timestamps. Image access is
anonymous; no package write permission or login is needed in the consumer.
ARM pins remain recorded as provenance from the successful compatibility trial;
the full ARM matrix uses upstream images under the current policy.

Maintained mode replaces cibuildwheel's Rust bootstrap with the shared
`validate-image.sh`; it does not reinstall the toolchain. macOS and Windows
keep their existing native setup. `upstream` mode leaves the image selectors
and Rust installer in `pyproject.toml` unchanged.

There is no input or repository-variable override that enables maintained images
for full builds. To roll back reduced CI, change its `IMAGE_MODE` to `upstream`
in the selection step. The image/installer defaults in `pyproject.toml` remain
available, so rollback does not alter codec source or distribution metadata.
Do not silently fall back after an image-verification failure; reduced CI should
fail visibly if its pinned build environment is unavailable or invalid.

## Publisher guarantees and limits

The publisher builds and tests a local image once, tags/pushes that same image,
then pulls and tests its registry digest before emitting the digest JSON.
Reusing an existing versioned tag also requires validating that exact digest.
Versioned tags include source commit, libc, architecture, Rust and base versions;
the same-commit concurrency group serializes publication. Consumers still pin
digests because registry tags are mutable names.

New builds pin Rustup 1.28.2 and verify its bootstrap script against a committed
SHA-256 before executing it. This publisher hardening does not retroactively
rebuild the existing images in `images.json`; trial consumption validates their
runtime explicitly. Update the four pins together only after a new publisher
run and anonymous access/runtime checks; never promote artifact ZIP hashes.

## Measurements still needed

The first trial's pull/validation, first-build, and whole-run times are recorded
in the report. Compare like-for-like matrices and source revisions over
at least five successful runs per affected architecture before claiming a
performance benefit or expanding consumption. Record billed minutes,
registry/image refresh cost, and cache telemetry where available. An isolated
successful run establishes compatibility, not the proposed 20% speedup or net
cost improvement. No native caching change is part of this experiment.
