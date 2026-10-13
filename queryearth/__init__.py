"""queryearth: match rules scoped by area, time and other dimensions to a request.

queryearth.time holds time keys, intervals and their measures, and
queryearth.space points, polygons and closed-set measures (imported as
``from queryearth import space as sp``). The rule engine is at the top level:
a Registry of dimensions, products, regions and rules answers queries with
Finding objects, which callers log with the logging module. See docs/design.md
for the design.
"""

try:
    from queryearth._version import __version__
except ImportError:  # running from a source tree that was never built or installed
    __version__ = "0.0.0"

from queryearth import space
from queryearth.dimensions import (
    Axis,
    DimMatch,
    Dimension,
    Labels,
    Prefilter,
    Versions,
)
from queryearth.registry import (
    Registry,
    PointResult,
    ScoreFn,
    Suitability,
    default_score,
)
from queryearth.objects import (
    Action,
    AxisOverlap,
    Confidence,
    Coverage,
    DuplicateCodeError,
    Finding,
    Kind,
    LoadError,
    Match,
    Outcome,
    Product,
    Query,
    Request,
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
    "Coverage",
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
    "Product",
    "Query",
    "Request",
    "Rule",
    "RuleFunc",
    "RuleKind",
    "Scope",
    "ScoreFn",
    "Space",
    "Status",
    "Suggestion",
    "Suitability",
    "TimeSpec",
    "UnknownNameError",
    "Versions",
    "__version__",
    "default_score",
    "interval",
    "parse_time",
    "space",
]
