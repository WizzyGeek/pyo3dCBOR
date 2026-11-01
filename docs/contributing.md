# Maintaining the documentation

The public documentation is written in Markdown under `docs/` and built with
Sphinx, MyST, and Furo. It is organized by purpose: the tutorial teaches a
first round trip, how-to guides solve specific tasks, explanations describe
design and behavior, and the reference lists the API contracts.

## Edit the source pages

- Add a first-time learning path under `docs/tutorials/`.
- Add a task-focused page under `docs/how-to/` and link it from
  `docs/how-to/index.md`.
- Add design context under `docs/explanation/` and link it from that section's
  index.
- Add or update API behavior under `docs/reference/`. Use Python-domain
  directives for names and signatures; do not import `dcbor` with autodoc.
- Add concise cross-reference terms to `docs/glossary.md` using the glossary
  directive.
- Add any new page to its section's toctree so the sidebar, search, EPUB, and
  single-page output can reach it.

Use MyST links and cross-references where possible, and keep each page's
examples small enough to explain in place. An executable example belongs in a
`{doctest}` block. Sphinx runs those blocks against the installed package; the
HTML, EPUB, and single-page builders do not import the native extension.
The displayed version is read from `pyproject.toml` during the Sphinx build, so
it does not need a separate docs-version edit.

## Build locally

Use Python 3.14 for the documentation tool environment. This is separate from
the package's supported Python range, which starts at 3.9. From the repository
root, create and populate a dedicated environment:

```sh
uv venv --python 3.14 .venv-docs
uv pip install --python .venv-docs/bin/python -r requirements-docs.txt
```

Build individual formats or all native-independent formats:

```sh
.venv-docs/bin/python scripts/docs.py html
.venv-docs/bin/python scripts/docs.py epub
.venv-docs/bin/python scripts/docs.py singlehtml
.venv-docs/bin/python scripts/docs.py all
```

The script runs Sphinx with warnings treated as errors and missing references
reported. Outputs go under `docs/_build/`. HTML search is provided by Furo.

To run the executable examples, build and install the extension in the same
environment first, then use the `doctest` builder:

```sh
uv pip install --python .venv-docs/bin/python 'maturin>=1.7,<2'
.venv-docs/bin/maturin build \
  --locked \
  --interpreter .venv-docs/bin/python \
  --out target/docs-wheels
uv pip install --python .venv-docs/bin/python --no-deps target/docs-wheels/dcbor-*.whl
.venv-docs/bin/python scripts/docs.py doctest
```

These commands require a compatible Rust toolchain. CI pins Rust 1.90.0; to
match it locally, install that toolchain with `rustup toolchain install 1.90.0
--profile minimal` and set `RUSTUP_TOOLCHAIN=1.90.0` when building the wheel.

Sphinx uses manual Python-domain API entries so the normal HTML and EPUB builds
remain independent of Rust and the compiled extension. Treat
`python/dcbor/__init__.pyi` and the tests as the API contract; keep manual
reference entries in sync with them and with runtime behavior. Do not generate
runtime code or duplicate behavior in documentation tooling.

## Review and publishing

The docs workflow runs strict HTML and EPUB builds, checks the Python API
inventory, executes the doctest examples, and stores HTML and EPUB artifacts
for relevant pull requests and pushes to `master`. These automated checks do
not replace visual review. Before merging, review the rendered HTML at desktop
and mobile widths and check that the navigation and links read clearly.

The workflow can publish only when manually dispatched on `master` with its
`publish` input enabled. GitHub Pages must first be configured in repository
Settings to use GitHub Actions as its source. GitHub Pages is available for
public repositories on GitHub Free; availability for private repositories
depends on the account plan. A live documentation URL should be added here only
after the repository owner enables Pages and a deployment succeeds.

See the [GitHub Pages workflow setup guide](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages)
for the repository setting required by custom workflows.
