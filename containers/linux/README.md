# Maintained Linux wheel environments

The upstream cibuildwheel images remain the default until a maintained-image
trial passes the full wheel matrix and its timing/cost evidence is reviewed.

`images.json` records all four reviewed image references by **registry manifest
digest**, plus the publisher source commit and Actions run. These are not the
hashes of the Actions artifact ZIPs named `digest-*`. Resolve the reference and
check the JSON artifact contents before updating any pin.

The current four references were obtained from the JSON artifacts in
[publisher run 39051517661](https://github.com/WizzyGeek/pyo3dCBOR/actions/runs/39051517661).
All four were anonymously readable from GHCR on 2026-10-18. Their returned
manifest bytes match the recorded SHA-256 values; their configs report the
expected amd64/arm64 architecture, libc policy, and Rust 1.90.0 toolchain.
This verifies metadata and access, not runtime or wheel-build success.

## Trial and rollback

Dispatch `ci.yml` on the reviewed branch with `linux_images=maintained` to run
the full 42-wheel matrix. The Linux jobs select the four exact digest references,
pull and validate the two images for their native architecture, and then build
and test wheels from the tested sdist. Their summaries record mode and digests;
pull/validation logs include timestamps. Image access is anonymous; no package
write permission or login is needed in the consuming workflow.

Maintained mode replaces cibuildwheel's Rust bootstrap with the shared
`validate-image.sh`; it does not reinstall the toolchain. macOS and Windows
keep their existing native setup. `upstream` mode leaves the image selectors
and Rust installer in `pyproject.toml` unchanged.

Manual/reusable workflows accept an explicit `linux_images` input, defaulting
to `upstream`. Ordinary runs may select maintained mode using repository variable
`DCBOR_LINUX_IMAGES=maintained`, **only after** a successful trial and review.
Rollback that variable to `upstream` (or delete it), or explicitly dispatch with
`linux_images=upstream`. Rollback does not alter source or distribution metadata.
Do not silently fall back after a maintained-image verification failure; that
would hide a broken trial and invalidate timing measurements.

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

Collect the trial run's image pull/validation, cibuildwheel start-to-first-build,
and end-to-end times. Compare like-for-like matrices and source revisions over
at least five successful runs per affected architecture. Record billed minutes,
registry/image refresh cost, and cache telemetry where available. An isolated
successful run establishes compatibility, not the proposed 20% speedup or net
cost improvement. No native caching change is part of this experiment.
