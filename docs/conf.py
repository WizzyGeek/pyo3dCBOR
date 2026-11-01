"""Sphinx configuration for the public dCBOR for Python documentation."""

from pathlib import Path
import tomllib


ROOT = Path(__file__).resolve().parents[1]
with (ROOT / "pyproject.toml").open("rb") as project_file:
    PACKAGE_VERSION = tomllib.load(project_file)["project"]["version"]

project = "dCBOR for Python"
author = "WizzyGeek"
copyright = "WizzyGeek"
version = PACKAGE_VERSION
release = PACKAGE_VERSION

extensions = [
    "myst_parser",
    "sphinx.ext.doctest",
]

root_doc = "index"
source_suffix = {".md": "markdown"}
language = "en"
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

myst_enable_extensions = ["colon_fence", "deflist"]
myst_heading_anchors = 3

# Keep API documentation independent of the compiled extension. The Python
# domain entries are authored in the reference pages rather than imported.
nitpicky = True
show_warning_types = True

html_theme = "furo"
html_title = f"{project} {release}"
html_static_path = ["_static"]
html_css_files = ["custom.css"]
html_theme_options = {
    "navigation_with_keys": True,
    "source_repository": "https://github.com/WizzyGeek/pyo3dCBOR",
    "source_branch": "master",
    "source_directory": "docs/",
}
html_show_sourcelink = True
pygments_style = "friendly"
pygments_dark_style = "monokai"

epub_basename = f"dcbor-{release}"
epub_show_urls = "footnote"
