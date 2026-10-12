"""queryearth: match rules scoped by area, time and other dimensions to a request.

The engine is not implemented yet; see docs/design.md for the design.
"""

try:
    from queryearth._version import __version__
except ImportError:  # running from a source tree that was never built or installed
    __version__ = "0.0.0"

__all__ = ["__version__"]
