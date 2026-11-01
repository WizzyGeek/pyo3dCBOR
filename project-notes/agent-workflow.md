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

For the native Rust binding unit checks, run:

```sh
cargo test --lib --locked
```

CI runs the native Rust unit tests and the full Python suite on CPython
3.14/Linux, and excludes only tests marked `exhaustive` on the other supported
CPython versions. It also validates the source distribution and tests each
built wheel. Leave the full platform matrix to GitHub Actions; the local
commands do not replace those checks.

If changing package versions, run `python scripts/ci.py versions`. For a
maintainer patch release, use `python scripts/bump_patch_version.py` and follow
the complete [release guide](releasing.md). Do not create or push release tags,
publish releases, or publish packages as part of an ordinary implementation
task unless the task explicitly requests that action.

## Documentation

For public documentation changes, follow the
[documentation maintenance guide](../docs/contributing.md). Use its separate
Python 3.14 environment and pinned requirements to build the pages locally:

```sh
uv venv --python 3.14 .venv-docs
uv pip install --python .venv-docs/bin/python -r requirements-docs.txt
.venv-docs/bin/python scripts/docs.py all
```

The `all` command builds strict HTML, EPUB, and single-page HTML. The guide
explains how to install a native wheel into `.venv-docs` and run doctests.

## Packaging

The native codec sources and root Cargo lockfile are included in the source
distribution. The former vendored `dcbor` crate is no longer a project
dependency.
Changes to CI workflows or helpers should also consider the focused
[maintenance checks](../maintenance/README.md).
