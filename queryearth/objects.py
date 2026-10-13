"""Core objects: outcomes, matches, findings, scopes, products, requests, queries.

All are frozen dataclasses (design.md section 4.11). Constructors accept the
Python shorthands the design allows (a bare string for a one-item tuple, a
number for a one-point axis range, a pair of wire strings for a time) and store
the normalised form. Objects that hold mappings compare by value but are not
hashable; Request hashes, with its support by identity.
"""

from __future__ import annotations

import dataclasses
import enum
import math
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

import numpy as np

from queryearth.space import Space
from queryearth.time import Interval, TimeSpec, interval, parse_time

if TYPE_CHECKING:
    from queryearth.dimensions import DimMatch

__all__ = [
    "Action",
    "AxisOverlap",
    "Confidence",
    "Coverage",
    "Finding",
    "Kind",
    "Match",
    "Outcome",
    "Product",
    "Query",
    "Request",
    "Scope",
    "Severity",
    "Status",
    "Suggestion",
]

Kind = Literal["caveat", "coverage", "recommendation"]
Confidence = Literal["observed", "likely", "possible", "unknown"]  # CAP certainty
Action = Literal["can_be_used", "use_with_caution", "do_not_use", "replaced"]
Status = Literal["draft", "reviewed", "deprecated"]

KINDS = ("caveat", "coverage", "recommendation")
CONFIDENCES = ("observed", "likely", "possible", "unknown")
ACTIONS = ("can_be_used", "use_with_caution", "do_not_use", "replaced")
STATUSES = ("draft", "reviewed", "deprecated")

_SLUG = re.compile(r"[a-z][a-z0-9_]*")


class Severity(enum.IntEnum):
    """How bad a finding is; the values equal the logging levels."""

    INFO = 20
    WARNING = 30
    SEVERE = 40  # the number of logging.ERROR


def _set(obj: Any, name: str, value: Any) -> None:
    object.__setattr__(obj, name, value)


def severity_of(value: Any) -> Severity:
    """A Severity from itself, its value (20, 30, 40) or its name, any case."""
    if isinstance(value, Severity):
        return value
    if isinstance(value, str):
        try:
            return Severity[value.upper()]
        except KeyError:
            pass
    elif isinstance(value, (int, np.integer)) and not isinstance(value, bool):
        try:
            return Severity(int(value))
        except ValueError:
            pass
    raise ValueError(
        f"severity must be info, warning or severe (20, 30 or 40), not {value!r}"
    )


def _strings(value: Any, what: str, *, empty: bool = True) -> tuple[str, ...]:
    """A tuple of strings from one string or an iterable of them."""
    if isinstance(value, str):
        value = (value,)
    elif not isinstance(value, Iterable) or isinstance(value, Mapping):
        raise TypeError(f"{what} must be a string or strings, not {value!r}")
    items = tuple(value)
    if not all(isinstance(v, str) and v for v in items):
        raise TypeError(f"{what} must be non-empty strings, got {items!r}")
    if not empty and not items:
        raise ValueError(f"{what} needs at least one value")
    return items


def _choice(value: Any, allowed: Sequence[str], what: str) -> str:
    if value not in allowed:
        raise ValueError(f"{what} must be one of {list(allowed)}, not {value!r}")
    return value


def time_of(value: Any) -> TimeSpec | None:
    """A TimeSpec from itself, a JSON-FG time member, or a (start, end) pair.

    A member open at both ends means all time here, not an omitted time.
    """
    if value is None or isinstance(value, TimeSpec):
        return value
    if isinstance(value, Mapping):
        spec = parse_time(value)
        return spec if spec is not None else TimeSpec((Interval(None, None),))
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise TypeError(
            "a time is a TimeSpec, a JSON-FG time member or a (start, end) pair, "
            f"not {value!r}"
        )
    if len(value) != 2:
        raise ValueError(f"a time pair is (start, end), got {value!r}")
    return interval(value[0], value[1])


def _space_of(value: Any, what: str) -> Space | None:
    if value is not None and not isinstance(value, Space):
        raise TypeError(
            f"{what} is a Space from queryearth.space (or None), not "
            f"{type(value).__name__}"
        )
    return value


def _number(value: Any, what: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float, np.number)):
        raise TypeError(f"{what} must be a number, not {value!r}")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{what} must be finite, not {value!r}")
    return number


def _jsonable(value: Any) -> Any:
    """A JSON-ready copy: tuples become lists, infinities None, numpy plain."""
    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, Severity):
        return value.name.lower()
    if isinstance(value, (int, np.integer)):
        return int(value)
    if isinstance(value, (float, np.floating)):
        return float(value) if math.isfinite(value) else None
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, np.ndarray):
        return _jsonable(value.tolist())
    if callable(getattr(value, "to_dict", None)) and not isinstance(value, type):
        return _jsonable(value.to_dict())  # such as a DimMatch with a plugin's to_json
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {
            f.name: _jsonable(getattr(value, f.name)) for f in dataclasses.fields(value)
        }
    if isinstance(value, Mapping):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (set, frozenset)):
        items = [_jsonable(v) for v in value]
        try:
            return sorted(items)
        except TypeError:
            return items
    if isinstance(value, Iterable):
        return [_jsonable(v) for v in value]
    return str(value)


# ---- outcomes, matches, findings -----------------------------------------------
@dataclass(frozen=True)
class Suggestion:
    """A structured action; the engine never interprets target or key."""

    target: str
    key: str
    value: Any
    rationale: str = ""

    def __post_init__(self) -> None:
        for name in ("target", "key"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name):
                raise ValueError(f"a suggestion's {name} is a non-empty string")
        if not isinstance(self.rationale, str):
            raise TypeError("a suggestion's rationale is a string")


def suggestion_of(value: Any) -> Suggestion:
    """A Suggestion from itself or a {target, key, value, rationale} mapping."""
    if isinstance(value, Suggestion):
        return value
    if isinstance(value, Mapping):
        return Suggestion(**value)
    raise TypeError(f"a suggestion is a Suggestion or a mapping, not {value!r}")


@dataclass(frozen=True)
class AxisOverlap:
    """An interval on one axis that keeps its open ends, such as [8, 10).

    An open end at infinity has its closed flag False.
    """

    lo: float
    hi: float
    lo_closed: bool = True
    hi_closed: bool = True

    def __post_init__(self) -> None:
        _set(self, "lo", float(self.lo))
        _set(self, "hi", float(self.hi))
        if math.isnan(self.lo) or math.isnan(self.hi) or self.lo > self.hi:
            raise ValueError(
                f"an axis interval needs lo <= hi, got {self.lo}, {self.hi}"
            )


def _outcome_post_init(o: Any) -> None:
    if not isinstance(o.code, str) or not o.code:
        raise ValueError("a code is a non-empty string")
    _choice(o.kind, KINDS, "kind")
    for name in ("title", "message", "instruction"):
        if not isinstance(getattr(o, name), str):
            raise TypeError(f"{name} must be a string")
    _set(o, "severity", severity_of(o.severity))
    if o.source_severity is not None and not isinstance(o.source_severity, str):
        raise TypeError("source_severity must be a string or None")
    _choice(o.confidence, CONFIDENCES, "confidence")
    if o.action is not None:
        _choice(o.action, ACTIONS, "action")
    _choice(o.status, STATUSES, "status")
    if isinstance(o.suggestions, (Suggestion, Mapping)):
        raise TypeError("suggestions is a sequence of suggestions")
    _set(o, "suggestions", tuple(suggestion_of(s) for s in o.suggestions))
    minimum = _number(o.min_overlap, "min_overlap")
    if not 0.0 <= minimum <= 1.0:
        raise ValueError(f"min_overlap must lie in [0, 1], not {minimum}")
    _set(o, "min_overlap", minimum)
    for name in ("references", "evidence"):
        items = getattr(o, name)
        if isinstance(items, Mapping) or not all(isinstance(i, Mapping) for i in items):
            raise TypeError(f"{name} is a sequence of mappings")
        _set(o, name, tuple(dict(i) for i in items))


@dataclass(frozen=True, kw_only=True)
class Outcome:
    """What a rule says; shared by Rule and Finding."""

    code: str
    kind: Kind
    title: str
    message: str
    severity: Severity = Severity.WARNING
    source_severity: str | None = None  # the source's own wording, verbatim
    confidence: Confidence = "unknown"
    action: Action | None = None
    instruction: str = ""
    suggestions: tuple[Suggestion, ...] = ()
    min_overlap: float = 0.0  # emit() threshold on area_fraction
    status: Status = "draft"
    references: tuple[Mapping[str, str], ...] = ()
    evidence: tuple[Mapping[str, Any], ...] = ()

    def __post_init__(self) -> None:
        _outcome_post_init(self)


def _match_post_init(m: Any) -> None:
    pairs = tuple(tuple(p) for p in m.time_overlap)
    if not all(len(p) == 2 and all(isinstance(e, str) for e in p) for p in pairs):
        raise TypeError("time_overlap holds closed wire intervals (start, end)")
    _set(m, "time_overlap", pairs)
    _set(m, "axes", dict(m.axes))
    _set(m, "matched_facets", {k: tuple(v) for k, v in m.matched_facets.items()})
    _set(m, "dims", dict(m.dims))
    _set(m, "conditional_on", tuple(m.conditional_on))
    _set(m, "assumed", tuple(m.assumed))


@dataclass(frozen=True, kw_only=True)
class Match:
    """How a scope met a query.

    Measures of decided dimensions are filled; an undecided dimension is named
    in conditional_on and reports the rule's own extent or nothing (section 4.3).
    """

    area_fraction: float | None = None
    overlap_km2: float | None = None
    time_overlap: tuple[tuple[str, str], ...] = ()  # closed, wire form
    time_fraction: float | None = None
    axes: Mapping[str, AxisOverlap] = field(default_factory=dict)
    matched_facets: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    dims: Mapping[str, DimMatch] = field(default_factory=dict)  # plugin dimensions
    conditional_on: tuple[str, ...] = ()  # e.g. ("space", "product")
    assumed: tuple[str, ...] = ()  # product-filled dimensions the rule constrains
    product: str | None = None  # the request's product; None on the base query
    request: int | None = None  # position of the request; None on the base query

    def __post_init__(self) -> None:
        _match_post_init(self)


_OUTCOME_FIELDS = tuple(f.name for f in dataclasses.fields(Outcome))
_MATCH_FIELDS = tuple(f.name for f in dataclasses.fields(Match))


@dataclass(frozen=True, kw_only=True)
class Finding(Outcome, Match):
    """The result of one rule matching one query: the outcome plus the match."""

    details: Mapping[str, Any] = field(default_factory=dict)
    source: str = ""  # pack name, "computed", "builtin" or "python"
    query_label: str = ""

    def __post_init__(self) -> None:
        _outcome_post_init(self)
        _match_post_init(self)
        _set(self, "details", dict(self.details))

    def to_dict(self) -> dict[str, Any]:
        """A JSON-ready dict: severity as its lowercase name, intervals as lists."""
        names = _OUTCOME_FIELDS + _MATCH_FIELDS + ("details", "source", "query_label")
        return {name: _jsonable(getattr(self, name)) for name in names}


# ---- scopes, products, requests, queries -----------------------------------------
def _mapping(value: Any, what: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{what} is a mapping of names to values, not {value!r}")
    if not all(isinstance(k, str) for k in value):
        raise TypeError(f"{what} names must be strings")
    return dict(value)


@dataclass(frozen=True)
class Scope:
    """A conjunction; an unconstrained dimension matches anything.

    axes, facets and dims hold the rule-side values in record form; the Index
    checks every name and parses each value with its dimension plugin.
    """

    space: Space | None = None
    time: TimeSpec | None = None
    axes: Mapping[str, Mapping[str, float]] = field(default_factory=dict)
    facets: Mapping[str, Any] = field(default_factory=dict)
    dims: Mapping[str, Any] = field(default_factory=dict)  # other plugin dimensions

    def __post_init__(self) -> None:
        _space_of(self.space, "a scope's space")
        if self.time is not None and not isinstance(self.time, TimeSpec):
            raise TypeError("a scope's time is a TimeSpec or None")
        for name in ("axes", "facets", "dims"):
            _set(self, name, _mapping(getattr(self, name), f"scope {name}"))


@dataclass(frozen=True)
class Coverage:
    """Where and when a product has data; None means global or all time.

    A callable coverage gives space=sp.nowhere(), an empty polygon, for a
    request its product does not serve.
    """

    space: Space | None = None
    time: TimeSpec | None = None

    def __post_init__(self) -> None:
        _space_of(self.space, "a coverage space")
        if self.space is not None and self.space.kind != "polygon":
            raise ValueError(
                f"a coverage space is a polygon or nowhere(), not a {self.space.kind!r}"
            )
        if self.time is not None:
            if not isinstance(self.time, TimeSpec):
                raise TypeError("a coverage time is a TimeSpec or None")
            if self.time.months is not None:
                raise ValueError("a coverage time cannot carry a month recurrence")


@dataclass(frozen=True)
class Product:
    """A dataset that queries can name, with its coverage and version."""

    name: str  # canonical lowercase slug, e.g. "cru_ts"
    aliases: tuple[str, ...] = ()  # e.g. ("CRUTS", "CRU TS")
    variables: tuple[str, ...] = ()
    coverage: Coverage | Callable[[Query], Coverage] = Coverage()
    resolution: tuple[float, Literal["deg", "km"]] | None = None
    version: str | None = None  # version in use; fills an omitted version facet

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not _SLUG.fullmatch(self.name):
            raise ValueError(
                f"a product name is a lowercase slug such as 'cru_ts', not {self.name!r}"
            )
        _set(self, "aliases", _strings(self.aliases, "aliases"))
        _set(self, "variables", _strings(self.variables, "variables"))
        if not isinstance(self.coverage, Coverage) and not callable(self.coverage):
            raise TypeError("a product coverage is a Coverage or a callable")
        if self.resolution is not None:
            if isinstance(self.resolution, str) or len(self.resolution) != 2:
                raise ValueError("a resolution is (size, 'deg' or 'km')")
            size, unit = self.resolution
            _choice(unit, ("deg", "km"), "resolution unit")
            size = _number(size, "resolution")
            if size <= 0.0:
                raise ValueError("a resolution must be positive")
            _set(self, "resolution", (size, unit))
        if self.version is not None and (
            not isinstance(self.version, str) or not self.version
        ):
            raise TypeError("a product version is a non-empty string or None")


@dataclass(frozen=True)
class Request:
    """One product as the caller uses it (section 4.12)."""

    product: str  # canonical name or alias
    variables: tuple[str, ...] = ()  # a plain string means one variable
    version: str | None = None  # default: Product.version, listed in assumed
    time: TimeSpec | None = None  # default: the query's time, else the coverage
    support: Space | None = None  # a point or polygon; default: query.space

    def __post_init__(self) -> None:
        if not isinstance(self.product, str) or not self.product:
            raise TypeError("a request names its product with a non-empty string")
        _set(self, "variables", _strings(self.variables, "variables"))
        if self.version is not None and (
            not isinstance(self.version, str) or not self.version
        ):
            raise TypeError("a request version is a non-empty string or None")
        _set(self, "time", time_of(self.time))
        _space_of(self.support, "a request's support")


def request_of(value: Any) -> Request:
    """A Request from itself or a product name."""
    if isinstance(value, Request):
        return value
    if isinstance(value, str):
        return Request(value)
    raise TypeError(f"a request is a Request or a product name, not {value!r}")


def _axis_range(name: str, value: Any) -> tuple[float, float]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        v = _number(value, f"axis {name!r}")
        return v, v
    if len(value) != 2:
        raise ValueError(f"axis {name!r} takes a number or a range (lo, hi)")
    lo, hi = (_number(v, f"axis {name!r}") for v in value)
    if lo > hi:
        raise ValueError(f"axis {name!r} range needs lo <= hi, got ({lo}, {hi})")
    return lo, hi


@dataclass(frozen=True)
class Query:
    """What the caller is about to use; every part is optional.

    Pass the support (the cells and time steps a product contributes), never a
    buffered shape. A product facet, with variable and version, is shorthand
    for requests. request and assumed are set only on the sub-queries that
    Index.expand() returns: the request's position, and the dimensions filled
    from its product.
    """

    space: Space | None = None
    time: TimeSpec | None = None
    axes: Mapping[str, tuple[float, float]] = field(default_factory=dict)
    facets: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    dims: Mapping[str, Any] = field(default_factory=dict)  # other plugin dimensions
    requests: tuple[Request, ...] = ()  # one sub-query per request
    context: Mapping[str, Any] = field(default_factory=dict, compare=False)
    label: str = ""  # the caller's name for the query, used in messages
    request: int | None = None  # set by Index.expand() on a request's sub-query
    assumed: tuple[str, ...] = ()  # set by Index.expand(): filled from the product

    def __post_init__(self) -> None:
        _space_of(self.space, "a query's space")
        _set(self, "time", time_of(self.time))
        axes = _mapping(self.axes, "query axes")
        _set(self, "axes", {k: _axis_range(k, v) for k, v in axes.items()})
        facets = _mapping(self.facets, "query facets")
        _set(
            self,
            "facets",
            {k: _strings(v, f"facet {k!r}", empty=False) for k, v in facets.items()},
        )
        _set(self, "dims", _mapping(self.dims, "query dims"))
        if isinstance(self.requests, (str, Request)):
            raise TypeError("requests is a sequence of Request objects")
        _set(self, "requests", tuple(request_of(r) for r in self.requests))
        _set(self, "context", _mapping(self.context, "query context"))
        if not isinstance(self.label, str):
            raise TypeError("a query label is a string")
        if self.request is not None and (
            isinstance(self.request, bool) or not isinstance(self.request, int)
        ):
            raise TypeError("request is the position of a request, an int")
        _set(self, "assumed", tuple(self.assumed))
