"""queryearth: match rules scoped by space, time and dimensions you define to a query.

A Registry holds rules; Registry.query() returns the rules that apply to a
query. Space, time and Axis are the base dimensions and Labels the extension
that comes with them, all written on the public Dimension class, as your own
dimensions are. queryearth.space makes points and polygons (import it as
``from queryearth import space as sp``) and interval() makes times.
docs/growth.md lists what queryearth 0.6.0 had beyond this core.
"""

try:
    from queryearth._version import __version__
except ImportError:  # running from a source tree that was never built or installed
    __version__ = "0.0.0"

from queryearth import space
from queryearth.dimensions import (
    Axis,
    Dimension,
    Labels,
    SpaceDimension,
    TimeDimension,
)
from queryearth.registry import DuplicateCodeError, Registry
from queryearth.rules import Rule
from queryearth.space import Space
from queryearth.time import Interval, interval

__all__ = [
    "Axis",
    "Dimension",
    "DuplicateCodeError",
    "Interval",
    "Labels",
    "Registry",
    "Rule",
    "Space",
    "SpaceDimension",
    "TimeDimension",
    "__version__",
    "interval",
    "space",
]
