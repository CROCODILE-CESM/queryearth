"""queryearth public API sketch (illustrative; bodies elided). Python 3.11 or later.

The sketch parses, imports and runs on Python 3.11: its dataclasses construct,
and its ComputedRule registers. Space helpers live in queryearth.space;
everything else is at the package top level. Section numbers in comments
refer to design.md, and usage.py shows the sketch in use.
"""

from __future__ import annotations

import contextlib
import enum
import os
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, ClassVar, Literal, NamedTuple, Protocol

import numpy as np
import shapely


class Severity(enum.IntEnum):  # values equal the logging levels
    INFO = 20
    WARNING = 30
    SEVERE = 40


Kind = Literal["caveat", "coverage", "recommendation"]
Confidence = Literal["observed", "likely", "possible", "unknown"]  # CAP certainty
Action = Literal["can_be_used", "use_with_caution", "do_not_use", "replaced"]
Status = Literal["draft", "reviewed", "deprecated"]


# ---- Time: civil-date keys; closed intervals on the wire, half-open inside ------
@dataclass(frozen=True)
class Interval:  # not ordered: an open end (None) does not compare with a key
    start: int | None  # inclusive civil key; None is an open end
    end: int | None  # exclusive civil key; None is an open end
    precision: Literal["day", "second"] = "day"  # "second" for datetime ends


@dataclass(frozen=True)
class TimeSpec:
    intervals: tuple[Interval, ...]  # a union
    months: frozenset[int] | None = None  # recurrence: these months of every year
    calendar: str = "proleptic_gregorian"  # validation and durations, not ordering


# civil_key = ((((y * 13 + mo) * 32 + d) * 24 + h) * 60 + mi) * 60 + s
# interval() reads closed wire ends ("2020-01-09", timestamp, "..", date-like;
# dates are day precision, datetimes second precision); parse_time() reads a
# JSON-FG time member; from_bounds() reads cell bounds, start in, end out.
def civil_key(y: int, mo: int, d: int, h: int = 0, mi: int = 0, s: int = 0) -> int: ...
def interval(start: Any, end: Any, calendar: str | None = None) -> TimeSpec: ...
def parse_time(member: Mapping[str, Any] | None, **props: Any) -> TimeSpec | None: ...
def from_bounds(starts: Any, ends: Any, calendar: str | None = None) -> TimeSpec: ...


# ---- Space: normalised once (exact wrap, split at +-180, pole caps, orient) -------
@dataclass(frozen=True, eq=False)
class Space:
    kind: Literal["point", "polygon", "points", "features", "empty"]
    geometry: shapely.Geometry | None = None  # CRS84, straight lon/lat edges
    points: tuple[np.ndarray, ...] | None = None  # lon, lat, weights
    features: tuple[str, frozenset[str]] | None = None  # namespace, ids
    area_km2: float | None = None  # spherical, closed form


# box(): east < west crosses the antimeridian. from_grid(): 2D cell corners.
# cells(): the cells of grid=(lon_edges, lat_edges) a region uses, by mode
# "centre", "overlap" or "full"; cell_mask(): the same cells as a (lat, lon)
# boolean array. resolution_of(): (finest, coarsest) spacing.
def point(lon: float, lat: float) -> Space: ...
def box(west: float, south: float, east: float, north: float) -> Space: ...
def box_arc(west: float, width: float, south: float, north: float) -> Space: ...
def lat_band(south: float, north: float) -> Space: ...
def polygon(shape: Any, pole: Literal["auto", "north", "south"] = "auto") -> Space: ...
def from_grid(lon2d: np.ndarray, lat2d: np.ndarray) -> Space: ...
def weighted_points(lon: Any, lat: Any, weights: Any = None) -> Space: ...
def features(ids: Iterable[str | int], namespace: str) -> Space: ...
def cells(grid: tuple[Any, Any], region: Space, mode: str = "overlap") -> Space: ...
def cell_mask(grid: tuple[Any, Any], region: Space, mode: str = "overlap") -> Any: ...
def resolution_of(lon2d: Any, lat2d: Any, unit: str = "km") -> tuple[float, float]: ...
def nowhere() -> Space: ...  # the empty space (kind "empty"), for callable coverage


# ---- Dimensions: every kind of scope is a plugin (section 4.13) ------------------
@dataclass(frozen=True)
class DimMatch:  # how one rule value met one query value on one dimension
    overlap: Any = None  # dimension-specific; JSON-serialisable after to_json()
    fraction: float | None = None  # share of the query's value covered, if measurable


class Dimension(Protocol):
    """One kind of scope, declared on an Index under a unique name.

    space and time are built in. Axis (numeric ranges), Labels (facets) and
    Versions (OSV-style version ranges) are the built-in plugins; a new kind of
    matching implements the same four members. The engine supplies everything
    else: the conditional logic of section 4.3, findings, records and requests.
    """

    name: str  # key in scopes, queries, records and conditional_on
    schema: Mapping[str, Any]  # JSON Schema for the rule-side value in records

    def parse_rule(self, value: Any) -> Any: ...  # at load; ValueError if invalid
    def parse_query(self, value: Any) -> Any: ...  # at query time; ValueError
    def match(self, rule: Any, query: Any) -> DimMatch | None: ...  # None: no overlap


# Optional members a Dimension may add, all looked up with getattr:
#   comparable(rule, query) -> bool  False makes the finding conditional on name
#   build(rule_values) -> Prefilter  an index over (position, value) pairs, built
#       once per rebuild; Prefilter.candidates(query_value) -> set[int] returns
#       the positions that may match, so match() runs only on those
#   to_json(overlap) -> Any          for Finding.to_dict(); default: overlap as is
#   late: bool = False               True runs it after the exact spatial test
class Prefilter(Protocol):
    def candidates(self, query: Any) -> set[int]: ...


@dataclass(frozen=True)
class Axis:  # Dimension plugin: a named ordered dimension in one unit
    name: str
    unit: str
    description: str = ""


@dataclass(frozen=True)
class Labels:  # Dimension plugin: a facet, matched by fnmatch globs (section 4.7)
    name: str
    description: str = ""


@dataclass(frozen=True)
class Versions:  # Dimension plugin: OSV-style version ranges (section 4.8)
    name: str = "version"


@dataclass(frozen=True)
class Scope:  # a conjunction; an unconstrained dimension matches anything
    space: Space | None = None
    time: TimeSpec | None = None
    axes: Mapping[str, Mapping[str, float]] = field(default_factory=dict)
    facets: Mapping[str, Any] = field(default_factory=dict)
    dims: Mapping[str, Any] = field(default_factory=dict)  # other plugin dimensions


@dataclass(frozen=True)
class Coverage:  # None means global / all time
    space: Space | None = None
    time: TimeSpec | None = None


@dataclass(frozen=True)
class Product:
    name: str  # canonical lowercase slug, e.g. "cru_ts"
    aliases: tuple[str, ...] = ()  # e.g. ("CRUTS", "CRU TS")
    variables: tuple[str, ...] = ()
    coverage: Coverage | Callable[[Query], Coverage] = Coverage()
    resolution: tuple[float, Literal["deg", "km"]] | None = None
    calendar: str = "proleptic_gregorian"
    version: str | None = None  # version in use; fills an omitted version facet
    grid: tuple[Any, Any] | Callable[[Space], Space] | None = None  # edges or cells


@dataclass(frozen=True)
class Request:  # one product as the caller uses it (section 4.12)
    product: str  # canonical name or alias
    variables: tuple[str, ...] = ()  # a plain string means one variable
    version: str | None = None  # default: Product.version, listed in assumed
    time: TimeSpec | None = None  # default: the query's time, else the coverage
    support: Space | None = None  # default: from Product.grid, else query.space


@dataclass(frozen=True)
class Query:  # any subset; callers pass the support, never a buffered shape
    space: Space | None = None
    time: TimeSpec | None = None
    axes: Mapping[str, tuple[float, float]] = field(default_factory=dict)
    facets: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    dims: Mapping[str, Any] = field(default_factory=dict)  # other plugin dimensions
    requests: tuple[Request, ...] = ()  # one sub-query per request
    context: Mapping[str, Any] = field(default_factory=dict, compare=False)
    label: str = ""  # the caller's name for the query, used in messages


# ---- Outcomes, matches, findings ------------------------------------------------
@dataclass(frozen=True)
class Suggestion:  # domain-agnostic; the engine never interprets target or key
    target: str
    key: str
    value: Any
    rationale: str = ""


@dataclass(frozen=True)
class AxisOverlap:  # the intersection on one axis; keeps open ends, e.g. [8, 10)
    lo: float
    hi: float
    lo_closed: bool = True
    hi_closed: bool = True


@dataclass(frozen=True, kw_only=True)
class Outcome:  # what a rule says; shared by Rule and Finding
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


@dataclass(frozen=True, kw_only=True)
class Match:  # how a scope met a query
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


@dataclass(frozen=True, kw_only=True)
class Finding(Outcome, Match):
    details: Mapping[str, Any] = field(default_factory=dict)
    source: str = ""  # pack name, "computed" or "builtin"
    query_label: str = ""

    def to_dict(self) -> dict[str, Any]: ...


# ---- Rules ------------------------------------------------------------------------
# check() runs only for a definite match. It returns True (one default finding),
# False or None (none), a mapping of Finding fields to override (severity,
# message, area_fraction, time_overlap, suggestions, details), or an iterable of
# such mappings. An overridden time_overlap makes the engine recompute time_fraction.
CheckResult = bool | Mapping[str, Any] | Iterable[Mapping[str, Any]] | None
RuleFunc = Callable[[Query, Match], CheckResult]
ScoreFn = Callable[[Product, Query, Sequence[Finding]], tuple[float, ...]]


class RuleKind(Protocol):  # records, computed, raster-derived, built-in coverage
    code: str
    scope: Scope

    def evaluate(self, query: Query) -> Sequence[Finding]: ...


# Optional on a RuleKind (Q5): outcomes(query, match) -> CheckResult. If present,
# the Index does the scope matching itself and calls outcomes() only for the
# rules that survive it, instead of calling evaluate() on every rule.


@dataclass(frozen=True, kw_only=True)
class Rule(Outcome):  # a static record: one GeoJSON Feature + JSON-FG time
    scope: Scope = field(default_factory=Scope)
    region_ref: tuple[str, ...] = ()  # resolved into scope.space at load
    created: str | None = None  # record lifecycle time, not data time
    updated: str | None = None
    withdrawn: str | None = None  # kept for history, never matched
    supersedes: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()

    @classmethod
    def from_feature(cls, feature: Mapping[str, Any], index: Index) -> Rule: ...
    def evaluate(self, query: Query) -> Sequence[Finding]: ...


# A subclass of an abstract=True base inherits its class keywords, merged, with
# the subclass's own keywords winning (Q9). Redefining a rule with the same code
# and the same qualified name (module plus class or function), as re-running a
# notebook cell does, replaces it; any other reuse of a code raises (Q10).
class ComputedRule:  # class keywords give identity and scope; subclassing registers
    code: ClassVar[str]
    meta: ClassVar[dict[str, Any]]  # kind (default caveat), severity, title, scope...
    scope: Scope  # set by Index.add from meta, after checking the declared names

    def __init_subclass__(cls, code: str = "", index: Index | None = None, **meta: Any):
        super().__init_subclass__()
        if meta.pop("abstract", False):
            return
        if not code:
            raise TypeError(f"{cls.__name__} needs the class keyword code=...")
        cls.code, cls.meta = code, meta
        (index or Index.default()).add(cls())  # DuplicateCodeError on reuse

    def evaluate(self, query: Query) -> Sequence[Finding]: ...  # scope, then check()
    def check(self, query: Query, match: Match) -> CheckResult: ...  # override
    def mask(self, lon: Any, lat: Any, query: Query) -> np.ndarray | None: ...  # bulk


# Also DuplicateCodeError(ValueError) and UnknownNameError(KeyError).
class AdvisoryError(Exception): ...  # raised by emit(); .findings holds them


# ---- Index ------------------------------------------------------------------------
class Suitability(NamedTuple):
    product: Product
    score: tuple[float, ...]  # lower = fewer known concerns, not "good data"
    findings: tuple[Finding, ...]  # this product's findings only


# The default ScoreFn of suitable(): (worst severity, burden, misfit); section 10.
def default_score(
    product: Product, query: Query, findings: Sequence[Finding]
) -> tuple[float, ...]: ...


@dataclass(frozen=True, eq=False)
class PointResult:  # keys are (product, code); product is None on the base query
    findings: tuple[Finding, ...]  # area_fraction is the weighted fraction
    masks: Mapping[tuple[str | None, str], np.ndarray]  # boolean, shaped like lon
    fractions: Mapping[tuple[str | None, str], float]
    skipped: tuple[tuple[str | None, str], ...] = ()  # computed rules without mask()

    def any(self, min_severity: Severity = Severity.WARNING) -> np.ndarray: ...


class Index:
    FACETS = ("product", "variable", "version", "model", "component")

    # query fields: space, time, axes, facets, dims, requests, context, label and
    # include_conditional; query_points fields: weights, time, axes, facets, dims,
    # requests and include_conditional.
    def __init__(
        self,
        name: str = "",
        *,
        axes: Iterable[Axis] = (),
        facets: Iterable[str] = FACETS,  # each name becomes Labels(name)
        dimensions: Iterable[Dimension] = (),  # any other plugin dimensions
    ) -> None: ...
    def add_dimension(self, dimension: Dimension) -> None: ...  # before any rule
    def add_product(self, product: Product) -> None: ...
    @property
    def products(self) -> Mapping[str, Product]: ...  # read-only, by canonical name
    def rule_counts(self) -> Mapping[str | None, int]: ...  # per product; None: any
    def add_regions(self, namespace: str, regions: Mapping[str, Space]) -> None: ...
    def add(self, rule: Rule | RuleKind | Mapping[str, Any]) -> None: ...
    def load_pack(self, path: str | os.PathLike[str]) -> list[str]: ...
    def rule(self, code: str, **meta: Any) -> Callable[[RuleFunc], RuleFunc]: ...
    def query(self, query: Query | None = None, /, **fields: Any) -> list[Finding]: ...
    def expand(self, query: Query) -> tuple[Query, ...]: ...  # base, then requests
    def query_points(self, lon: Any, lat: Any, **fields: Any) -> PointResult: ...
    def suitable(
        self,
        query: Query,
        variable: str,
        *,
        products: Sequence[str] | None = None,  # default: all offering the variable
        score: ScoreFn | None = None,  # default: default_score
        include_dropped: bool = False,  # also list dropped products, last
    ) -> list[Suitability]: ...
    @classmethod
    def default(cls) -> Index: ...  # the application default, made on first use


# ---- Emission: findings are the API; logging and warnings are adapters ----------
# Subclasses InfoAdvisory, WarningAdvisory, SevereAdvisory, one per Severity.
class AdvisoryWarning(UserWarning): ...


Sink = Callable[[Finding, str], None]  # receives each kept finding and its text


@dataclass(frozen=True)
class Policy:
    mode: Literal["log", "warn", "raise", "ignore"] | Sink = "warn"  # or a sink
    min_severity: Severity = Severity.WARNING  # for caveats and coverage only
    raise_at: Severity | None = None  # e.g. SEVERE raises AdvisoryError
    ignore: frozenset[str] = frozenset()  # codes or prefixes, e.g. {"QE", "CRU001"}
    include_drafts: bool = True
    show_recommendations: bool = True  # log them at INFO in every mode but ignore
    skip_packages: tuple[str, ...] = ()  # frames skipped when choosing stacklevel


# policy() overrides fields of the active Policy, held in a contextvars.ContextVar
# (thread- and task-safe). emit() logs, warns or raises caveats and coverage
# findings under it and logs recommendations at INFO, never warning or raising
# them. It skips conditional findings and those under min_overlap, de-duplicates
# by (code, query_label, product), starts every message with "[CODE]", raises
# only if a caveat or coverage finding is kept, and returns what it logged or warned.
# With a Sink as the mode, every kept finding, recommendations included, goes to
# the sink with its "[CODE] ..." text instead of logging or warning; raise_at
# still applies.
def policy(**changes: Any) -> contextlib.AbstractContextManager[Policy]: ...
def emit(
    findings: Iterable[Finding], mode: str | None = None, **kw: Any
) -> list[Finding]: ...
