"""queryearth: match rules scoped by area, time and other dimensions to a request.

queryearth.time holds time keys, intervals and their measures,
queryearth.space points, polygons and closed-set measures (imported as
``from queryearth import space as sp``), and queryearth.converters turns other
descriptions of a place, such as a model grid, into spaces. The rule engine is
at the top level: a Registry of dimensions and rules answers queries with
Finding objects, which callers log with the logging module or print with
report(). See docs/design.md for the design.
"""

try:
    from queryearth._version import __version__
except ImportError:  # running from a source tree that was never built or installed
    __version__ = "0.0.0"

from queryearth import converters, space
from queryearth.dimensions import (
    Axis,
    AxisOverlap,
    DimMatch,
    Dimension,
    Labels,
    Prefilter,
    Versions,
)
from queryearth.registry import FORMAT, Registry, PointResult
from queryearth.objects import (
    Action,
    Change,
    Confidence,
    DuplicateCodeError,
    Finding,
    LoadError,
    Match,
    Outcome,
    Query,
    Scope,
    Status,
    UnknownNameError,
    report,
)
from queryearth.rules import CheckResult, ComputedRule, Rule, RuleFunc, RuleKind
from queryearth.space import Space
from queryearth.time import Interval, TimeSpec, interval, parse_time

__all__ = [
    "FORMAT",
    "Action",
    "Axis",
    "AxisOverlap",
    "Change",
    "CheckResult",
    "ComputedRule",
    "Confidence",
    "DimMatch",
    "Dimension",
    "DuplicateCodeError",
    "Finding",
    "Registry",
    "Interval",
    "Labels",
    "LoadError",
    "Match",
    "Outcome",
    "PointResult",
    "Prefilter",
    "Query",
    "Rule",
    "RuleFunc",
    "RuleKind",
    "Scope",
    "Space",
    "Status",
    "TimeSpec",
    "UnknownNameError",
    "Versions",
    "__version__",
    "interval",
    "parse_time",
    "report",
    "space",
]
