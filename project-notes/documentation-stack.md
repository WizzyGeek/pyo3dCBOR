# Public documentation stack decision

**Decision, as of 2026-11-02:** use Sphinx 9.2.0, MyST-Parser 5.1.0, and
Furo 2025.12.19. Keep the authored pages in `docs/` as Markdown. Build and
check them in a dedicated Python 3.14 environment; the `dcbor` package itself
continues to support Python 3.9 and later.

## Why this stack

Sphinx supplies Python-domain API objects and cross-references, a glossary,
strict checks for unresolved references, external-link checking, and builders
for HTML, EPUB, and LaTeX source that can be compiled to PDF. MyST-Parser lets
the narrative stay in Markdown while using Sphinx directives and references.
Furo provides responsive navigation, search, and a clean theme suited to a
small documentation set. All three projects use permissive open-source
licenses: Sphinx is BSD-2-Clause; MyST-Parser and Furo are MIT.

The selected versions are compatible with the separate docs runtime:
Sphinx 9.2.0 requires Python 3.13 or later, MyST-Parser 5.1.0 requires Python
3.11 or later and its release notes include Sphinx 9 support, and Furo's
2025.12.19 changelog adds Sphinx 9 support. Pin these docs dependencies and
update them deliberately. The package's Python 3.9 minimum does not constrain
the docs build environment.

Use Sphinx's Python domain to document the public signatures by hand, checking
them against [`python/dcbor/__init__.pyi`](../python/dcbor/__init__.pyi).
`autodoc` imports the native `dcbor._dcbor` extension, so it would require
building and installing the Rust extension before the docs build. Mark
runnable examples as Sphinx doctests;
those checks likewise need the built/installed package. Run doctests in the
docs environment and enable `-W -n` for build warnings and unresolved
cross-references. Run Sphinx's `linkcheck` builder for external links; network
timeouts and rate limits can make that check intermittent, so treat it as a
separate check from local reference validation.

GitHub Pages is available at no charge for public repositories on GitHub Free,
and GitHub Actions can publish the generated static site. EPUB is a native
Sphinx output. PDF is optional: the LaTeX builder emits source that needs a
TeX installation to produce the PDF. Furo styles the HTML site; PDF layout is
controlled by the LaTeX builder and its configuration.

## Alternatives considered

Material for MkDocs remains a capable, polished Markdown site generator. Its
maintainers announced end of life on 2027-05-05, with critical bug fixes and
security updates through that date and new feature development focused on
Zensical. Zensical is a credible successor: its maintainers plan to begin a
0.1.0 dependable release line on 2026-11-05. As of this decision date, PyPI's
latest Zensical release is 0.0.74 from 2026-10-30. Zensical supports
`mkdocstrings`, API generation from `.pyi` files, and executable Markdown
examples through `markdown-exec`; its official authoring guide says output
formats beyond HTML are future work. Sphinx already provides the desired API,
glossary, doctest, EPUB, and PDF-source facilities in one mature toolchain.

PyData Sphinx Theme is another appealing Sphinx theme, with a more frequent
release cadence and multiple maintainers. Its project cautions that a newly
released Sphinx major version may need time for compatibility work; Sphinx
9.2.0 was released only days before this decision. Furo's latest release is
2025.12.19 and the project lists one maintainer, so the selected theme is a
small, deliberate tradeoff for a polished content-first site. Theme choice is
independent of the Markdown and Python-domain source, so it can be revisited
without rewriting pages.

## Official references

- [Sphinx features and supported output formats](https://www.sphinx-doc.org/en/master/)
- [Sphinx builders](https://www.sphinx-doc.org/en/master/usage/builders/index.html)
- [Sphinx Python domain](https://www.sphinx-doc.org/en/master/usage/domains/python.html)
- [Sphinx doctest extension](https://www.sphinx-doc.org/en/master/usage/extensions/doctest.html)
- [Sphinx strict reference mode](https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-the-nitpicky-mode)
- [MyST cross-references](https://myst-parser.readthedocs.io/en/latest/syntax/cross-referencing.html)
- [Sphinx 9.2.0 on PyPI](https://pypi.org/project/Sphinx/9.2.0/)
- [MyST-Parser 5.1.0 on PyPI](https://pypi.org/project/myst-parser/5.1.0/)
- [Furo 2025.12.19 on PyPI](https://pypi.org/project/furo/2025.12.19/)
- [Sphinx license](https://github.com/sphinx-doc/sphinx/blob/master/LICENSE.rst)
- [MyST-Parser license](https://github.com/executablebooks/MyST-Parser)
- [Furo license and Sphinx 9 changelog](https://github.com/pradyunsg/furo/blob/main/docs/changelog.md)
- [GitHub Pages availability and limits](https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits)
- [Publish Pages with a custom Actions workflow](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages)
- [Material for MkDocs maintenance period](https://github.com/squidfunk/mkdocs-material/issues/8523)
- [Zensical release plans](https://zensical.org/upcoming-changes/)
- [Zensical plugin compatibility](https://zensical.org/docs/compatibility/mkdocs/plugins/)
- [Zensical Markdown output formats](https://zensical.org/docs/authoring/markdown/)
- [PyData Sphinx Theme project and compatibility note](https://github.com/pydata/pydata-sphinx-theme)
