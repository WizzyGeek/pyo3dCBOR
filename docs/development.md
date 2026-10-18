# Development and CI

## Conformance and test coverage

The documented target is RFC 8949 deterministic encoding with the dCBOR
application profile in
[draft-mcnally-deterministic-cbor-18 §2.5](https://www.ietf.org/archive/id/draft-mcnally-deterministic-cbor-18.html#section-2.5).
Project tests provide implementation evidence, not external certification. The
independent [wire-vector tests](../tests/test_spec_conformance.py) cover
numeric forms, malformed and noncanonical inputs, Unicode NFC, map ordering,
and duplicate keys. The [numeric oracle](../tests/test_numeric_oracle.py),
[wire-safety tests](../tests/test_wire_safety.py),
[datetime/depth tests](../tests/test_datetime_depth.py), and
[key-identity tests](../tests/test_key_identity.py) cover additional numeric,
resource-limit, date, and key-identity behavior.

The source-based survey of dCBOR implementations, generic CBOR libraries, and
related formats is in the [competitive landscape](competitive-landscape.md).
The binding's native wire reader and writer are maintained in the root Rust
crate and covered by the repository's Rust and Python checks.

## Local development

```sh
python3 -m venv .venv && source .venv/bin/activate
pip install maturin pytest
maturin develop
pytest
```

For coding-agent build, test, and release guidance, see the
[agent workflow](agent-workflow.md).

The full numeric-oracle and binary16 exhaustive cases run on CPython 3.14/Linux.
Other interpreter and wheel jobs run the rest of the suite, including the
independent conformance and safety tests. The source distribution runs the full
suite before wheel builds.

Current performance follow-ups are recorded in the
[allocation plan](allocation-plan.md).

## CI and releases

The [build workflow](../.github/workflows/ci.yml) runs on pull requests, pushes to
`master`/`main`, manual dispatches, and reusable workflow calls. A separate
[release workflow](../.github/workflows/release.yml) starts on version-tag pushes
and uses that build workflow for a full matrix if a matching validated bundle
is unavailable. The build workflow:

1. Check that Python and Cargo package versions agree with the public
   `dcbor.__version__`.
2. Run the native Rust binding unit tests with the root lockfile using
   `cargo test --lib --locked`.
3. Build the extension on CPython 3.9–3.14. Run the full suite on CPython
   3.14/Linux; other Python versions exclude only tests marked `exhaustive`.
4. Create an sdist and verify it installs and passes the full test suite.
5. Build release wheels **from that sdist**, then install and test every wheel
   in an isolated environment using [cibuildwheel](https://cibuildwheel.pypa.io/).
   Wheel tests exclude only tests marked `exhaustive`; all remaining conformance
   and safety tests run on every wheel.
   Routine branch pushes and pull requests build reduced Linux wheels for
   CPython 3.12–3.14 using pinned x86_64 build images. Manual dispatches and
   release builds use the full platform matrix; reusable callers request full
   coverage by default, while pull-request callers remain reduced.
6. For full-matrix builds, check distribution metadata, require all 42 wheels,
   generate `SHA256SUMS` and build provenance, and upload a versioned
   `release-vX.Y.Z` artifact. The tag-triggered release workflow validates and
   publishes the release assets.

| Platform | Architecture | Build environment | Python versions |
| --- | --- | --- | --- |
| Linux glibc 2.28+ | x86_64, aarch64 | manylinux_2_28 Docker images | 3.9–3.14 |
| Linux musl 1.2+ | x86_64, aarch64 | musllinux_1_2 Docker images | 3.9–3.14 |
| macOS 11+ | Intel, Apple Silicon | Native GitHub macOS runner images | 3.9–3.14 |
| Windows | x64 | Windows 2022 runner image with MSVC | 3.9–3.14 |

ARM builds run on native ARM runners. Linux packaging images are selected by
cibuildwheel; macOS and Windows use native runner images because their toolchains
require those operating systems. Rust is pinned to 1.90.0 in the workflow and Linux
container setup. Update both together. Dependabot checks action updates weekly.
Compiler jobs are limited to two; wheel jobs fan out by platform and interpreter.
The build workflow starts with a small Ubuntu change-detection job. If a push or
pull request changes only Markdown files, the test and build jobs are skipped;
skipped job checks report success. Manual dispatches run the full matrix. The
release workflow requires stable `vX.Y.Z` tags and publishes a GitHub Release
after validating its complete bundle; see the
[release guide](releasing.md) for its assets and retry behavior.

Separate [maintenance checks](../maintenance/README.md) cover build/release tools
in a path-filtered workflow. They do not run in the build pipeline or ship in
source distributions. Branch push runs stay independent so a docs-only push
cannot cancel earlier code validation; superseded PR runs may cancel because
their diffs are cumulative.

The sdist includes the native binding sources and Python tests, so packaging
failures are caught before release.

For the initial `v0.1.0` release and later patch releases, see the
[release guide](releasing.md). It covers version updates, tag creation,
bundle reuse or full-build fallback, release assets, retries, and GitHub-only
publication.

For a lightweight local check on an 8 GB machine:

```sh
CARGO_BUILD_JOBS=2 maturin develop --release --locked
python -m pytest -q
maturin sdist --out dist
```

Leave the full platform matrix to Actions. The versioned `release-vX.Y.Z`
artifact is retained for 30 days, with individual build artifacts retained for
14 days.
