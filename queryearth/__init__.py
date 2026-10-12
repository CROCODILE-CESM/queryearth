"""queryearth: match rules scoped by area, time and other dimensions to a request.

queryearth.time holds civil-date keys, intervals and calendars, and
queryearth.space normalised shapes, cells and closed-set measures (imported as
``from queryearth import space as sp``). The rule engine is at the top level:
an Index of dimensions, products, regions and rules answers queries with
Finding objects, and emit() reports findings under a policy. See docs/design.md
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
from queryearth.emit import (
    AdvisoryError,
    AdvisoryWarning,
    InfoAdvisory,
    Policy,
    SevereAdvisory,
    Sink,
    WarningAdvisory,
    emit,
    policy,
)
from queryearth.errors import DuplicateCodeError, LoadError, UnknownNameError
from queryearth.index import Index, PointResult, ScoreFn, Suitability, default_score
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
    "AdvisoryError",
    "AdvisoryWarning",
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
    "InfoAdvisory",
    "Interval",
    "Kind",
    "Labels",
    "LoadError",
    "Match",
    "Outcome",
    "PointResult",
    "Policy",
    "Prefilter",
    "Product",
    "Query",
    "Request",
    "Rule",
    "RuleFunc",
    "RuleKind",
    "Scope",
    "ScoreFn",
    "SevereAdvisory",
    "Severity",
    "Sink",
    "Space",
    "Status",
    "Suggestion",
    "Suitability",
    "TimeSpec",
    "UnknownNameError",
    "Versions",
    "WarningAdvisory",
    "__version__",
    "civil_key",
    "default_score",
    "emit",
    "from_bounds",
    "interval",
    "parse_time",
    "policy",
    "space",
]
