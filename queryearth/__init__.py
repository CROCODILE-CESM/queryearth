"""queryearth: match rules scoped by area, time and other dimensions to a request.

The correctness layer is in place: queryearth.time (civil-date keys, intervals,
calendars) and queryearth.space (normalised shapes, cells and closed-set
measures, imported as ``from queryearth import space as sp``). The rule engine
is not implemented yet; see docs/design.md for the design.
"""

try:
    from queryearth._version import __version__
except ImportError:  # running from a source tree that was never built or installed
    __version__ = "0.0.0"

from queryearth import space
from queryearth.space import Space
from queryearth.time import (
    Interval,
    TimeSpec,
    civil_key,
    from_bounds,
    interval,
    parse_time,
)

__all__ = [
    "Interval",
    "Space",
    "TimeSpec",
    "__version__",
    "civil_key",
    "from_bounds",
    "interval",
    "parse_time",
    "space",
]
