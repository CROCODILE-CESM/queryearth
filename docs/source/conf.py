"""Sphinx configuration for the public queryearth user docs.

Only docs/source is published. The design documents in docs/ (design.md and
docs/reference/) stay private, because parts paraphrase private interviews.
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
html_title = f"queryearth {version}"
