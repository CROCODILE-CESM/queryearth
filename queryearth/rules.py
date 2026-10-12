"""Rules: static records, computed rules, and the reference scope matching.

Every rule kind implements RuleKind: a code, a scope and evaluate(query).
Rule.evaluate and ComputedRule.evaluate are the reference semantics of
design.md section 4.3, run on one part of a query (the base query or one
request's sub-query, as Index.expand() returns them). Index.query prunes rules
with vectorised prefilters and then calls evaluate() on the survivors.
"""

from __future__ import annotations

import dataclasses
import inspect
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from functools import cached_property
from typing import TYPE_CHECKING, Any, ClassVar, Protocol

import numpy as np

from queryearth import space as sp
from queryearth.model import Finding, Match, Outcome, Query, Scope, Severity
from queryearth.space import Space
from queryearth.time import Interval, TimeSpec, overlap, parse_time, time_fraction

if TYPE_CHECKING:
    from queryearth.index import Index

__all__ = ["CheckResult", "ComputedRule", "Rule", "RuleFunc", "RuleKind"]

CheckResult = bool | Mapping[str, Any] | Iterable[Mapping[str, Any]] | None
RuleFunc = Callable[[Query, Match], CheckResult]

# A prefix plus three or four digits, with a hyphen after a prefix that ends in
# a digit, so every code parses one way (Q8); QE is reserved.
CODE = re.compile(r"(?:[A-Z][A-Z0-9]{0,10}[A-Z]-?|[A-Z][A-Z0-9]{0,10}[0-9]-)[0-9]{3,4}")


def check_code(code: Any) -> None:
    """Raise ValueError unless code is a valid rule code."""
    if not isinstance(code, str) or not CODE.fullmatch(code):
        raise ValueError(
            f"{code!r} is not a rule code: capitals and digits plus three or four "
            "digits, such as CRU001, with a hyphen after a prefix that ends in a "
            "digit (ERA5-014)"
        )
    if re.fullmatch(r"QE-?[0-9]+", code):
        raise ValueError(f"{code!r} uses the prefix QE, which is reserved")


class RuleKind(Protocol):
    """Any rule: a code, a scope, and evaluate() on one query part.

    A third-party kind may also define outcomes(query, match) -> CheckResult
    and an outcome attribute (an Outcome) (Q5): the Index then matches its scope
    itself and calls outcomes() only for definite matches.
    """

    code: str
    scope: Scope

    def evaluate(self, query: Query) -> Sequence[Finding]: ...


@dataclass(frozen=True, eq=False)
class CompiledScope:
    """A scope with its names checked and its values parsed by their plugins."""

    space: Space | None
    time: TimeSpec | None
    values: Mapping[str, Any]  # dimension name -> parsed rule value
    requires: tuple[str, ...] = ()

    def constrains(self, name: str) -> bool:
        if name in ("space", "time"):
            return getattr(self, name) is not None
        return name in self.values


@dataclass(frozen=True, eq=False)
class Binding:
    """What a rule needs from the Index it was added to."""

    index: Index
    scope: CompiledScope
    source: str


def binding_of(rule: Any) -> Binding:
    found = getattr(rule, "_qe_binding", None)
    if found is None:
        raise TypeError(f"rule {getattr(rule, 'code', rule)!r} is not on an Index")
    return found


def match_scope(
    index: Index, scope: CompiledScope, query: Query, parsed: Mapping | None = None
) -> tuple[Match, dict[str, Any]] | None:
    """Match one scope against one query part, dimension by dimension (section 4.3).

    Returns None when some dimension fails; otherwise the Match, whose
    conditional_on names the undecided dimensions in the fixed order (space,
    time, axes, facets, other plugins, context keys), and details that hold
    recurrence_months when time is undecided.
    """
    if parsed is None:
        parsed = index._parse_query(query)
    undecided: set[str] = set()
    found: dict[str, Any] = {}

    def plugins(late: bool) -> bool:
        for name, dimension, _ in index._groups:
            if name not in scope.values or getattr(dimension, "late", False) != late:
                continue
            rule = scope.values[name]
            comparable = getattr(dimension, "comparable", None)
            if name not in parsed or (
                comparable and not comparable(rule, parsed[name])
            ):
                undecided.add(name)
                continue
            found[name] = dimension.match(rule, parsed[name])
            if found[name] is None:
                return False
        return True

    if not plugins(late=False):
        return None
    details: dict[str, Any] = {}
    time_overlap, fraction = (), None
    if scope.time is not None and query.time is None:
        undecided.add("time")
        if scope.time.extent != (None, None):
            time_overlap = scope.time.to_wire()  # the rule's own periods
        if scope.time.months is not None:
            details["recurrence_months"] = sorted(scope.time.months)
    elif query.time is not None:
        both = query.time if scope.time is None else overlap(scope.time, query.time)
        if both is None:
            return None
        time_overlap, fraction = both.to_wire(), time_fraction(both, query.time)
    area_fraction = overlap_km2 = None
    if scope.space is not None and (
        query.space is None or not sp.comparable(scope.space, query.space)
    ):
        undecided.add("space")
    elif query.space is not None:
        if scope.space is not None and not sp.meets(scope.space, query.space):
            return None
        area_fraction, overlap_km2 = sp.measure(scope.space, query.space)
    if not plugins(late=True):
        return None
    groups = {"axes": {}, "facets": {}, "dims": {}}
    for name, dimension, group in index._groups:
        if name in found:
            hit = found[name]
            groups[group][name] = hit if group == "dims" else hit.overlap
        elif name in undecided and group == "axes" and hasattr(dimension, "extent"):
            groups["axes"][name] = dimension.extent(scope.values[name])
    order = ["space", "time"] + [name for name, _, _ in index._groups]
    conditional = [name for name in order if name in undecided]
    conditional += [f"context:{k}" for k in scope.requires if k not in query.context]
    match = Match(
        area_fraction=area_fraction,
        overlap_km2=overlap_km2,
        time_overlap=time_overlap,
        time_fraction=fraction,
        axes=groups["axes"],
        matched_facets=groups["facets"],
        dims=groups["dims"],
        conditional_on=tuple(conditional),
        assumed=tuple(d for d in query.assumed if scope.constrains(d)),
        product=query.facets["product"][0] if query.request is not None else None,
        request=query.request,
    )
    return match, details


# ---- findings ---------------------------------------------------------------------
_LOCKED = frozenset(
    {"code", "product", "request", "query_label", "source", "conditional_on", "assumed"}
)


def _time_override(value: Any, query: TimeSpec | None) -> tuple:
    """A time_overlap set by check(), and time_fraction recomputed from it."""
    calendar = "proleptic_gregorian" if query is None else query.calendar
    parts: list[Interval] = []
    for pair in value:
        read = parse_time({"interval": list(pair)}, calendar=calendar)
        parts.extend(read.intervals if read is not None else (Interval(None, None),))
    if not parts:
        return (), time_fraction(None, query)
    spec = TimeSpec(tuple(parts), calendar=calendar)
    inside = None if query is None else overlap(spec, query)
    return spec.to_wire(), (None if query is None else time_fraction(inside, query))


def make_findings(
    outcome: Outcome,
    match: Match,
    query: Query,
    *,
    source: str,
    details: Mapping[str, Any] | None = None,
    result: Any = True,
) -> list[Finding]:
    """Findings from an outcome and a match, applying check()-style results."""
    if isinstance(result, (bool, np.bool_)) or result is None:
        overrides = [{}] if result else []
    elif isinstance(result, Mapping):
        overrides = [result]
    elif isinstance(result, Iterable) and not isinstance(result, str):
        overrides = list(result)
    else:
        raise TypeError(f"{outcome.code}: check() returned {type(result).__name__}")
    base = {f.name: getattr(outcome, f.name) for f in dataclasses.fields(Outcome)}
    base.update((f.name, getattr(match, f.name)) for f in dataclasses.fields(Match))
    base.update(details=details or {}, source=source, query_label=query.label)
    found = []
    for override in overrides:
        if not isinstance(override, Mapping) or set(override) & _LOCKED:
            raise ValueError(
                f"{outcome.code}: check() returns mappings of Finding fields, "
                f"other than {sorted(_LOCKED)}"
            )
        fields = {**base, **override}
        if "time_overlap" in override:
            fields["time_overlap"], fields["time_fraction"] = _time_override(
                override["time_overlap"], query.time
            )
        found.append(Finding(**fields))
    return found


def computed_findings(
    outcome: Outcome,
    match: Match,
    query: Query,
    details: Mapping[str, Any],
    check: Callable[[Query, Match], Any],
) -> list[Finding]:
    """A computed rule's findings: check() runs only for a definite match."""
    if match.conditional_on:
        return make_findings(outcome, match, query, source="computed", details=details)
    result = check(query, match)
    return make_findings(outcome, match, query, source="computed", result=result)


# ---- static records ---------------------------------------------------------------
@dataclass(frozen=True, kw_only=True)
class Rule(Outcome):
    """A static record, built in Python and registered with Index.add(rule).

    Index.add checks its names and resolves region_ref; evaluate() then runs
    against that Index (a rule added to a second Index is added as a copy).
    """

    scope: Scope = field(default_factory=Scope)
    region_ref: tuple[str, ...] = ()  # resolved into a space by Index.add
    created: str | None = None  # record lifecycle time, not data time
    updated: str | None = None
    withdrawn: str | None = None  # kept for history, never matched
    supersedes: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        Outcome.__post_init__(self)
        if self.kind not in ("caveat", "recommendation"):
            raise ValueError(f"{self.code}: coverage is declared on products")
        if self.kind == "recommendation" and not self.suggestions:
            raise ValueError(f"{self.code}: a recommendation needs suggestions")
        if not isinstance(self.scope, Scope):
            raise TypeError(f"{self.code}: scope is a Scope")
        for name in ("region_ref", "supersedes", "aliases"):
            value = getattr(self, name)
            object.__setattr__(
                self, name, (value,) if isinstance(value, str) else tuple(value)
            )
        if self.region_ref and self.scope.space is not None:
            raise ValueError(f"{self.code}: give region_ref or a space, not both")

    @classmethod
    def from_feature(cls, feature: Mapping[str, Any], index: Index) -> Rule:
        """Read one GeoJSON record against an Index (arrives with pack loading)."""
        raise NotImplementedError(
            "Rule.from_feature arrives with pack loading; build a Rule(...) for now"
        )

    def evaluate(self, query: Query) -> list[Finding]:
        """Findings for one query part (section 4.3)."""
        bound = binding_of(self)
        found = match_scope(bound.index, bound.scope, query)
        if found is None:
            return []
        match, details = found
        return make_findings(self, match, query, source=bound.source, details=details)


# ---- computed rules ---------------------------------------------------------------
OUTCOME_KEYS = tuple(f.name for f in dataclasses.fields(Outcome) if f.name != "code")
META_KEYS = frozenset(
    OUTCOME_KEYS
    + ("facets", "axes", "dims", "space", "time", "requires")
    + ("supersedes", "withdrawn")
)


def check_meta(meta: Mapping[str, Any], owner: str) -> None:
    unknown = set(meta) - META_KEYS
    if unknown:
        raise TypeError(f"{owner}: unknown keywords {sorted(unknown)}")


class ComputedRule:
    """A rule computed from the request or from data the caller holds.

    Class keywords give its identity and scope: code, index (default
    Index.default()), abstract, the Outcome fields (kind defaults to caveat,
    severity to WARNING or INFO for a recommendation, title and message to the
    docstring), facets, axes, dims, space (a Space), time and requires (keys
    of Query.context). Defining a subclass registers one instance; a subclass
    inherits its bases' keywords, merged, with its own winning (Q9).

    check(query, match) runs only for a definite match and returns True (one
    finding with the declared outcome), False or None (none), a mapping of
    Finding fields to override, or several such mappings.
    """

    code: ClassVar[str]
    meta: ClassVar[dict[str, Any]]
    scope: Scope  # set by Index.add from meta, after checking the declared names

    def __init_subclass__(
        cls, code: str = "", index: Index | None = None, **meta: Any
    ) -> None:
        super().__init_subclass__()
        abstract = meta.pop("abstract", False)
        cls._qe_meta = dict(meta, **({} if index is None else {"index": index}))
        if abstract:
            return
        if not code:
            raise TypeError(f"{cls.__name__} needs the class keyword code=...")
        merged: dict[str, Any] = {}
        for base in reversed(cls.__mro__):
            merged.update(base.__dict__.get("_qe_meta", {}))
        target = merged.pop("index", None)
        check_meta(merged, cls.__name__)
        cls.code, cls.meta = code, merged
        if target is None:
            from queryearth.index import Index

            target = Index.default()
        target.add(cls())

    def _doc(self) -> str | None:
        return type(self).__doc__

    def _qualname(self) -> str:
        return f"{type(self).__module__}.{type(self).__qualname__}"

    @cached_property
    def outcome(self) -> Outcome:
        """The declared outcome, before check() overrides it."""
        fields = {k: self.meta[k] for k in OUTCOME_KEYS if k in self.meta}
        kind = fields.setdefault("kind", "caveat")
        if kind not in ("caveat", "recommendation"):
            raise ValueError(
                f"{self.code}: a computed rule is a caveat or a recommendation"
            )
        default = Severity.INFO if kind == "recommendation" else Severity.WARNING
        fields.setdefault("severity", default)
        lines = inspect.cleandoc(self._doc() or "").splitlines()
        fields.setdefault("title", lines[0] if lines else "")
        if not fields["title"]:
            raise TypeError(f"{self.code}: give a title= keyword or a docstring")
        fields.setdefault("message", "\n".join(lines[1:]).strip() or fields["title"])
        return Outcome(code=self.code, **fields)

    def evaluate(self, query: Query) -> list[Finding]:
        """Findings for one query part: the scope, then check() if definite."""
        bound = binding_of(self)
        found = match_scope(bound.index, bound.scope, query)
        if found is None:
            return []
        match, details = found
        return computed_findings(self.outcome, match, query, details, self.check)

    def check(self, query: Query, match: Match) -> CheckResult:
        """Override to compute the rule; the default gives one finding."""
        return True

    def mask(self, lon: Any, lat: Any, query: Query) -> np.ndarray | None:
        """A per-point mask for the bulk path; None means the rule has none."""
        return None

    def __repr__(self) -> str:
        return f"<{type(self).__name__} {getattr(self, 'code', '?')}>"


class FunctionRule(ComputedRule, abstract=True):
    """A plain function (query, match) -> CheckResult, wrapped by Index.rule()."""

    def __init__(self, func: RuleFunc, code: str, meta: Mapping[str, Any]) -> None:
        check_meta(meta, code)
        self.func, self.code, self.meta = func, code, dict(meta)

    def _doc(self) -> str | None:
        return self.func.__doc__

    def _qualname(self) -> str:
        return f"{self.func.__module__}.{self.func.__qualname__}"

    def check(self, query: Query, match: Match) -> CheckResult:
        return self.func(query, match)
