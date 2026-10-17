# Agent workflow

This guide records project-specific commands and release boundaries for coding
agents. The repository-wide contribution, diff review, commit attribution, and
sign-off requirements are in the root [AGENTS.md](../AGENTS.md); follow those
instructions for every task that changes files.

## Build and test

The Python extension is built from the Rust binding with Maturin. A local
development setup on a machine with Rust installed is:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install maturin pytest
maturin develop
python -m pytest -q
```

The project pins Rust 1.90.0 in CI. To mirror its bounded local build on an
8 GB machine, use:

```sh
CARGO_BUILD_JOBS=2 maturin develop --release --locked
python -m pytest -q
```

For the vendored Rust codec checks, run:

```sh
cargo test --manifest-path crates/dcbor/Cargo.toml --locked
```

CI runs the full Python suite on CPython 3.14/Linux and excludes only tests
marked `exhaustive` on the other supported CPython versions. It also validates
the source distribution and tests each built wheel. Leave the full platform
matrix to GitHub Actions; the local commands do not replace those checks.

If changing package versions, run `python scripts/ci.py versions`. For a
maintainer patch release, use `python scripts/bump_patch_version.py` and follow
the complete [release guide](releasing.md). Do not create or push release tags,
publish releases, or publish packages as part of an ordinary implementation
task unless the task explicitly requests that action.

## Packaging and vendored code

The patched Rust dependency under `crates/dcbor` is included in the source
distribution. Preserve its license and provenance notes in
[PATCHES.md](../crates/dcbor/PATCHES.md); do not replace it with the unpatched
registry crate. Changes to CI workflows or helpers should also consider the
focused [maintenance checks](../maintenance/README.md).
