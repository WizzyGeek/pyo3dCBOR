# FEAT_001: CI environment and pipeline speedups

**Status:** sdist/test parallelization implemented; Linux image publishing
prototype implemented but not yet published or consumed; native caching
deferred pending baseline evidence.

## Problem

The CI workflow builds 42 platform/Python wheel combinations. The build
environment setup is repeated across jobs:

- Linux cibuildwheel installs Rust 1.90.0 inside its manylinux/musllinux
  containers via `before-all`.
- Python test, Rust, source-distribution, macOS, and Windows jobs install or
  select Rust 1.90.0 independently.
- The source-distribution job currently waits for both the Python matrix and
  Rust codec tests. Linux and Windows wheel jobs, as well as macOS wheel jobs,
  then wait for the sdist artifact.

This increases time to first wheel and repeats toolchain setup. macOS wheel jobs
are particularly expensive and are already skipped on pull requests; this
requirement must not re-enable them on pull requests or increase their
frequency.

## Desired outcome

Reduce end-to-end time to a tested release bundle and reduce repeated toolchain
setup where measurement shows a net benefit, without weakening validation,
increasing routine macOS usage, or making the release less reproducible.

The wheel set, source-of-truth sdist, pinned Rust version, tests, release gates,
and path-based workflow trigger behavior must remain intact.

## Scope

Research and, after PM prioritization, prototype these independently
measurable improvements:

1. **Overlap sdist work with test jobs.** Start the sdist build and its
   extracted-source test while the Python matrix and Rust codec test run.
   Allow wheel jobs to start as soon as the tested sdist artifact is ready.
   Preserve a final release-bundle gate that explicitly requires the Python
   matrix, Rust test, sdist, Linux/Windows wheels, and (on non-PR release
   workflows) macOS wheels. A faster artifact must never permit release
   publication while another required check is still running or has failed.
2. **Maintain reusable job-specific build environments.** For jobs that can run
   inside compatible containers, build and maintain pinned OCI environments
   with the tools and dependencies needed by those jobs, and publish them to
   GitHub Container Registry (GHCR). Use suitable manylinux and musllinux
   images for cibuildwheel, selected by platform and architecture through its
   supported Linux image options. The current wheel matrix needs glibc and musl
   images for x86_64 and aarch64; image production and consumption must be
   tested on all four combinations. Keep separate images only where job
   requirements differ enough to justify their maintenance cost.
3. **Optimize native macOS and Windows jobs.** OCI Linux build environments
   cannot replace native macOS or Windows runners. For those jobs, measure
   Rust 1.90.0 setup and relevant Cargo cache behavior, then use native setup
   or caching that preserves a reliable installation fallback. Keep the
   existing pull-request exclusion for macOS. Pin any additional GitHub Action
   to a reviewed immutable commit SHA and include cache keys that account for
   OS, architecture, Rust version, and relevant dependency/lockfile inputs.

## Constraints and design notes

### Job ordering and release safety

The sdist job currently has `test` and `rust` as prerequisites, even though it
can independently build and test the source archive. The proposed dependency
change is:

- Start `sdist` after change detection and metadata/version checks.
- Keep its isolated source-archive test within the sdist job.
- Let wheel jobs consume the sdist artifact as soon as it is available.
- Add or retain explicit dependencies from the release-bundle validation job
  to every required test and build job, so publication remains fully gated.

Run a workflow-graph review before merging this change, including pull-request
behavior where macOS wheels and the release-bundle job are intentionally
skipped. Compare both time-to-first-wheel and total workflow wall time; parallel
jobs can improve elapsed time while competing for hosted capacity.

### Linux build image

Each maintained container environment must be based on a compatible upstream
image. For cibuildwheel Linux builds, use the correct manylinux/musllinux image
family, preserve its auditwheel-compatible environment, and include only the
pinned tools and necessary dependencies. Publish images to GHCR with immutable
versioned tags and consume digest-pinned images rather than mutable `latest`
tags. Define environments per job or compatible job group rather than forcing
one image to serve incompatible tasks. Keep image definitions in the
repository, test each image before promotion, and routinely refresh base images
and tools for security updates. A weekly refresh is a candidate cadence, not a
substitute for dependency and vulnerability review.

Image builds and GHCR storage have cost and maintenance of their own. Price
refresh jobs, image retention, and transfer time against the current per-job
setup. Ensure image generation does not consume expensive macOS runner time.

### Prototype status

The initial Linux prototype is isolated from the consuming CI workflow:

- `containers/linux/Dockerfile.manylinux` and
  `containers/linux/Dockerfile.musllinux` extend the corresponding upstream
  Pypa image and add only Rust 1.90.0, its target for the native architecture,
  and the existing `CARGO_BUILD_JOBS=2` setting.
- `.github/workflows/publish-linux-images.yml` builds and validates all four
  libc/architecture combinations on native x86_64 and ARM64 runners. Each
  matrix job validates its image before publishing that variant; digest
  collection succeeds only after all four variants publish. The workflow
  requests `packages: write` only in the publisher job, links the container
  package to this repository, reuses existing versioned tags rather than
  intentionally overwriting them, and collects the pushed image digests.
- The workflow uses the versioned Pypa base tag `2026.10.16-1`; custom tags
  include the libc family, architecture, Rust version, base-image version, and
  source commit. Each base-image reference also pins its resolved manifest
  digest. Publication reuses an existing versioned tag instead of intentionally
  overwriting it and does not create `latest` or other mutable aliases. Since a
  registry tag is still a name rather than a content guarantee, consumers must
  use the published digest, not the tag alone, as the immutable reference.

The four image definitions were built and their runtime checks passed locally
on an x86_64 host; aarch64 images ran under emulation. This verifies the selected
upstream environments, Rust targets, auditwheel policy/architecture variables,
and CPython build interpreters, but is not a substitute for native ARM CI or
building/testing dcbor wheels with cibuildwheel.

The publishing workflow has not yet run, so no GHCR image digests exist to
consume. Do not change `pyproject.toml` to reference an unverified tag or a
placeholder digest. Once the workflow has published and its four digest
outputs have been reviewed, CI integration can consume those exact digests in
a separate change. The image build checks in the publishing workflow are not
a substitute for testing cibuildwheel consumption across all four pairs.

### Native runner baseline

Recent Actions history does not yet meet the five-successful-run comparison
required before adopting caching. Of 11 inspected workflow runs, only one was
fully successful. Under the current workflow arrangement, there are two
successful macOS job samples per architecture and one successful Windows job
sample. The latest fully green run recorded job durations of 6m20s on
`macos-15-intel`, 3m38s on `macos-14` (ARM64), and 6m24s on `windows-2022`;
the Rust toolchain-install steps took approximately 12s, 8s, and 13s,
respectively. An earlier push added one successful sample for each macOS
runner (6m20s Intel, 3m14s ARM64) but its Windows wheel job failed. Older
pull-request macOS jobs used a different matrix arrangement and are not
comparable.

The workflow has no Cargo cache hit/miss instrumentation. Available Actions
data did not provide usable billed-minute values. These observations are
insufficient to show a net benefit from caching, so native toolchain/cache
changes remain deferred. Preserve the macOS pull-request exclusion and collect
at least five comparable successful runs per affected runner before deciding
whether to prototype them. Sources: [latest green run](https://github.com/WizzyGeek/pyo3dCBOR/actions/runs/39042322877)
and [earlier push run](https://github.com/WizzyGeek/pyo3dCBOR/actions/runs/39041088716).

### macOS and Windows setup

GitHub-hosted runner images are maintained by GitHub and updated weekly.
GitHub-hosted custom VM images are only available on larger runners, not the
standard macOS runners used here. GitHub's documented custom-image generation
platforms are Linux x64, Linux ARM64, and Windows x64; macOS is not listed.
Therefore a custom pre-warmed macOS image is not part of the initial solution.

For native macOS and Windows jobs, first measure the time and cache hit rate for
Rust toolchain and Cargo data. Cache restore/save overhead can exceed the cost
of downloading the relatively stable pinned toolchain, and caches are not a
guaranteed source of truth. A cache miss must always fall back to a normal,
verified toolchain installation. Do not make correctness depend on a scheduled
cache-warming run.

## Acceptance criteria

- The sdist job can run concurrently with the Python matrix and Rust test job;
  wheel jobs begin after the sdist artifact is available rather than waiting
  for those independent test jobs to finish.
- A workflow dependency/negative-path test or equivalent review demonstrates
  that a failed Python, Rust, sdist, or required wheel job prevents
  release-bundle validation/publication.
- The complete required test and artifact set is unchanged, including the
  exact 42-wheel release bundle and sdist-based wheel builds.
- The macOS wheel jobs remain excluded from pull requests.
- Any adopted cache/image prototype is compared with a recorded baseline over
  at least five comparable successful runs per affected OS/architecture.
  Report median setup-to-first-build time, end-to-end workflow duration, cache
  hit/miss behavior, and billed runner minutes; include cache/image refresh
  cost.
- Before broad adoption, set and meet a PM-approved speed target (proposed
  initial target: at least 20% lower median setup-to-first-build time on the
  targeted jobs) without an increase in macOS executions and without an
  unapproved increase in total Actions/registry cost.
- All wheel platforms pass their existing wheel tests using the proposed image
  or cache path; Linux tests cover both libc families and both architectures.
- The custom image can be rolled back to the current cibuildwheel base image
  without source changes or altered release artifacts.

## Non-goals

- Changing which files trigger CI or widening the path filter.
- Skipping or weakening tests to improve elapsed time.
- Running macOS wheels on pull requests.
- Replacing cibuildwheel, the sdist-first build provenance, or the pinned Rust
  toolchain.
- Publishing artifacts to PyPI or changing release destinations.
- Implementing image/caching changes as part of this research document.

## Suggested rollout

1. Record current per-job setup durations, total workflow duration, and billed
   minutes for comparable successful runs.
2. Implement the sdist dependency-graph change separately; verify failure gates
   and compare elapsed time.
3. Prototype an OCI image for one Linux libc/architecture pair; compare it with
   the current image/install flow before building the remaining variants.
4. Prototype Rust/Cargo caching on one macOS and one Windows job. Keep a cache
   miss path and compare hit and miss runs.
5. Adopt only the changes that meet the approved speed and cost criteria;
   retain a straightforward rollback path.

## Research references

- [Current workflow](../../.github/workflows/ci.yml) and
  [cibuildwheel configuration](../../pyproject.toml).
- [cibuildwheel Linux platform documentation](https://cibuildwheel.pypa.io/en/stable/platforms/#linux)
  and [options reference](https://cibuildwheel.pypa.io/en/stable/options/#linux-container-image)
  for Linux container builds and configurable image families.
- GitHub's [hosted runner overview](https://docs.github.com/en/actions/concepts/runners/github-hosted-runners)
  documents weekly updates to GitHub-owned runner images and the distinction
  between standard and larger runners.
- GitHub's [custom image guide](https://docs.github.com/en/actions/how-tos/manage-runners/larger-runners/use-custom-images)
  documents larger-runner requirements, image generation, weekly refresh
  guidance, and the supported Linux/Windows image-generation platforms.
- GitHub's [dependency caching reference](https://docs.github.com/en/actions/reference/workflows-and-actions/dependency-caching)
  describes cache keys, restore behavior, and scope.
- GitHub's [container registry guide](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry)
  documents GHCR publishing and use.
- [`actions-rust-lang/setup-rust-toolchain`](https://github.com/actions-rust-lang/setup-rust-toolchain)
  is one candidate for pinned Rust setup and Cargo caching; review its
  implementation, transitive actions, and immutable SHA before adoption.
