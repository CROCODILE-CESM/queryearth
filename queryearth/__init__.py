"""queryearth: match rules scoped by area, time and other dimensions to a request.

queryearth.time holds time keys, intervals and their measures, and
queryearth.space points, polygons and closed-set measures (imported as
``from queryearth import space as sp``). The rule engine is at the top level:
a Registry of dimensions and rules answers queries with Finding
objects, which callers log with the logging module. See docs/design.md for the
design.
"""

try:
    from queryearth._version import __version__
except ImportError:  # running from a source tree that was never built or installed
    __version__ = "0.0.0"

from queryearth import space
from queryearth.dimensions import (
    Axis,
    AxisOverlap,
    DimMatch,
    Dimension,
    Labels,
    Prefilter,
    Versions,
)
from queryearth.registry import Registry, PointResult
from queryearth.objects import (
    Action,
    Confidence,
    DuplicateCodeError,
    Finding,
    Kind,
    LoadError,
    Match,
    Outcome,
    Query,
    Scope,
    Status,
    Suggestion,
    UnknownNameError,
)
from queryearth.rules import CheckResult, ComputedRule, Rule, RuleFunc, RuleKind
from queryearth.space import Space
from queryearth.time import Interval, TimeSpec, interval, parse_time

__all__ = [
    "Action",
    "Axis",
    "AxisOverlap",
    "CheckResult",
    "ComputedRule",
    "Confidence",
    "DimMatch",
    "Dimension",
    "DuplicateCodeError",
    "Finding",
    "Registry",
    "Interval",
    "Kind",
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
    "Suggestion",
    "TimeSpec",
    "UnknownNameError",
    "Versions",
    "__version__",
    "interval",
    "parse_time",
    "space",
]
