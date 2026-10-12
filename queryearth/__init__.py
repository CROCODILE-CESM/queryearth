"""queryearth: match rules scoped by area, time and other dimensions to a request.

queryearth.time holds civil-date keys, intervals and calendars, and
queryearth.space normalised shapes, cells and closed-set measures (imported as
``from queryearth import space as sp``). The rule engine is at the top level:
an Index of dimensions, products, regions and rules answers queries with
Finding objects. See docs/design.md for the design.
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
from queryearth.errors import DuplicateCodeError, UnknownNameError
from queryearth.index import Index
from queryearth.model import (
    Action,
    AxisOverlap,
    Confidence,
    Coverage,
    Finding,
    Kind,
    Match,
    Outcome,
    Product,
    Query,
    Request,
    Scope,
    Severity,
    Status,
    Suggestion,
)
from queryearth.rules import CheckResult, ComputedRule, Rule, RuleFunc, RuleKind
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
    "Index",
    "Interval",
    "Kind",
    "Labels",
    "Match",
    "Outcome",
    "Prefilter",
    "Product",
    "Query",
    "Request",
    "Rule",
    "RuleFunc",
    "RuleKind",
    "Scope",
    "Severity",
    "Space",
    "Status",
    "Suggestion",
    "TimeSpec",
    "UnknownNameError",
    "Versions",
    "__version__",
    "civil_key",
    "from_bounds",
    "interval",
    "parse_time",
    "space",
]
