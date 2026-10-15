"""Sphinx configuration for the queryearth user docs.

Only docs/source is built; docs/growth.md is not part of the site.
"""

import os
import sys

sys.path.insert(0, os.path.abspath("../.."))

from queryearth import __version__  # noqa: E402

project = "queryearth"
author = "Manish Venumuddula"
copyright = "2026, Manish Venumuddula"
release = __version__
version = __version__

extensions = ["myst_parser", "sphinx.ext.autodoc", "sphinx.ext.viewcode"]
source_suffix = {".md": "markdown", ".rst": "restructuredtext"}
exclude_patterns = ["_build"]
myst_heading_anchors = 3
autodoc_member_order = "bysource"
autodoc_typehints = "signature"

html_theme = "sphinx_rtd_theme"
html_static_path = ["_static"]
html_extra_path = ["llms.txt"]  # served as is, next to index.html, for language models
html_js_files = ["versions.js"]  # the version menu; see .github/docs_versions.py
html_title = f"queryearth {version}"
