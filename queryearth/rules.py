"""Rules: static records, computed rules, and the reference scope matching.

Every rule kind implements RuleKind: a code, a scope and evaluate(query).
Rule.evaluate and ComputedRule.evaluate are the reference semantics of
design.md section 4.3. Registry.query calls evaluate() on every active rule,
after any plugin prefilters.
"""

from __future__ import annotations

import dataclasses
import inspect
import logging
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from functools import cached_property
from typing import TYPE_CHECKING, Any, ClassVar, Protocol

import numpy as np
import shapely

from queryearth import space as sp
from queryearth.dimensions import DimMatch
from queryearth.objects import LEVELS, Finding, Match, Outcome, Query, Scope, _jsonable
from queryearth.space import Space
from queryearth.time import Interval, TimeSpec, overlap, parse_time, time_fraction

if TYPE_CHECKING:
    from queryearth.registry import Registry

__all__ = ["CheckResult", "ComputedRule", "Rule", "RuleFunc", "RuleKind"]

CheckResult = bool | Mapping[str, Any] | Iterable[Mapping[str, Any]] | None
RuleFunc = Callable[[Query, Match], CheckResult]

# A prefix plus three or four digits, with a hyphen after a prefix that ends in
# a digit, so every code parses one way (Q8).
CODE = re.compile(r"(?:[A-Z][A-Z0-9]{0,10}[A-Z]-?|[A-Z][A-Z0-9]{0,10}[0-9]-)[0-9]{3,4}")


def check_code(code: Any) -> None:
    """Raise ValueError unless code is a valid rule code."""
    if not isinstance(code, str) or not CODE.fullmatch(code):
        raise ValueError(
            f"{code!r} is not a rule code: capitals and digits plus three or four "
            "digits, such as CRU001, with a hyphen after a prefix that ends in a "
            "digit (ERA5-014)"
        )


class RuleKind(Protocol):
    """Any rule: a code, a scope, and evaluate() on one query.

    A third-party kind may also define outcomes(query, match) -> CheckResult
    and an outcome attribute (an Outcome) (Q5): the Registry then matches its scope
    itself and calls outcomes() only for definite matches.
    """

    code: str
    scope: Scope

    def evaluate(self, query: Query) -> Sequence[Finding]: ...


@dataclass(frozen=True, eq=False)
class CompiledScope:
    """A scope with its names checked and its values parsed by their dimensions."""

    values: Mapping[str, Any]  # dimension name -> parsed rule value, space and time too
    requires: tuple[str, ...] = ()


@dataclass(frozen=True, eq=False)
class Binding:
    """What a rule needs from the Registry it was added to."""

    registry: Registry
    scope: CompiledScope
    source: str


def binding_of(rule: Any) -> Binding:
    found = getattr(rule, "_qe_binding", None)
    if found is None:
        raise TypeError(f"rule {getattr(rule, 'code', rule)!r} is not on a Registry")
    return found


def match_scope(
    registry: Registry,
    scope: CompiledScope,
    query: Query,
    parsed: Mapping | None = None,
) -> tuple[Match, dict[str, Any]] | None:
    """Match one scope against one query, dimension by dimension (section 4.3).

    Returns None when some dimension fails; otherwise the Match, whose
    conditional_on names the undecided dimensions in the Registry's order (space,
    time, the declared dimensions, then context keys), and details that hold
    recurrence_months when time is undecided. Dimensions marked late run after
    the others, so the costly spatial test runs last.
    """
    if parsed is None:
        parsed = registry._parse_query(query)
    undecided: set[str] = set()
    found: dict[str, DimMatch] = {}
    for late in (False, True):
        for name, dimension in registry._dimensions.items():
            if getattr(dimension, "late", False) != late:
                continue
            rule, value = scope.values.get(name), parsed.get(name)
            if rule is None and (
                value is None or not getattr(dimension, "always", False)
            ):
                continue  # unconstrained, and nothing to measure
            comparable = getattr(dimension, "comparable", None)
            if value is None or (comparable and not comparable(rule, value)):
                undecided.add(name)
                continue
            found[name] = dimension.match(rule, value)
            if found[name] is None:
                return None
    hits: dict[str, DimMatch] = {}
    for name, dimension in registry._dimensions.items():
        if name in found:
            hits[name] = found[name]
            if hasattr(dimension, "to_json"):
                hits[name] = dataclasses.replace(hits[name], to_json=dimension.to_json)
        elif name in undecided and hasattr(dimension, "extent"):  # the rule's own
            hits[name] = DimMatch(dimension.extent(scope.values[name]))
    details: dict[str, Any] = {}
    if "time" in undecided and scope.values["time"].months is not None:
        details["recurrence_months"] = sorted(scope.values["time"].months)
    space, time = hits.pop("space", None), hits.pop("time", None)
    conditional = [name for name in registry._dimensions if name in undecided]
    conditional += [f"context:{k}" for k in scope.requires if k not in query.context]
    match = Match(
        area_fraction=None if space is None else space.fraction,
        overlap_km2=None if space is None else space.overlap,
        time_overlap=() if time is None else time.overlap,
        time_fraction=None if time is None else time.fraction,
        dimensions=hits,
        conditional_on=tuple(conditional),
    )
    return match, details


# ---- findings ---------------------------------------------------------------------
_LOCKED = frozenset({"code", "query_label", "source", "conditional_on"})


def _time_override(value: Any, query: TimeSpec | None) -> tuple:
    """A time_overlap set by check(), and time_fraction recomputed from it."""
    parts: list[Interval] = []
    for pair in value:
        read = parse_time({"interval": list(pair)})
        parts.extend(read.intervals if read is not None else (Interval(None, None),))
    if not parts:
        return (), time_fraction(None, query)
    spec = TimeSpec(tuple(parts))
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
_CRS84 = "http://www.opengis.net/def/crs/OGC/0/CRS84"
_FEATURE_KEYS = set(
    "type id geometry time place bbox properties featureType coordRefSys conformsTo".split()
)
_RULE_KEYS = tuple(f.name for f in dataclasses.fields(Outcome)) + tuple(
    "created updated withdrawn supersedes aliases".split()
)
_RECORD_KEYS = set(_RULE_KEYS) | set(
    "dimensions box periods recurrence time_start time_end".split()
)
_EXTENSION = re.compile(r"x_[a-z0-9_]+")


def box_of(box: Any) -> Space:
    """The box() of a record's {west, width, south, north}."""
    if (
        not isinstance(box, Mapping)
        or set(box) != {"west", "width", "south", "north"}
        or not all(type(v) in (int, float) for v in box.values())
        or not -180.0 <= box["west"] < 180.0
        or not 0.0 < box["width"] <= 360.0
    ):
        raise ValueError(f"a box is {{west, width, south, north}}, not {box!r}")
    return sp.box(box["west"], box["south"], box["west"] + box["width"], box["north"])


@dataclass(frozen=True, kw_only=True)
class Rule(Outcome):
    """A static record: one GeoJSON Feature (Rule.from_feature) or built in Python.

    Registry.add checks its names; evaluate() then runs against that Registry
    (a rule added to a second Registry is added as a copy). to_feature() writes
    it back as a record.
    """

    scope: Scope = field(default_factory=Scope)
    created: str | None = None  # record lifecycle time, not data time
    updated: str | None = None
    withdrawn: str | None = None  # kept for history, never matched
    supersedes: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()
    extensions: Mapping[str, Any] = field(default_factory=dict)  # x_* properties

    def __post_init__(self) -> None:
        Outcome.__post_init__(self)
        if self.kind == "suggestion" and not self.suggestions:
            raise ValueError(f"{self.code}: a suggestion lists one or more suggestions")
        if not isinstance(self.scope, Scope):
            raise TypeError(f"{self.code}: scope is a Scope")
        for name in ("supersedes", "aliases"):
            value = getattr(self, name)
            object.__setattr__(
                self, name, (value,) if isinstance(value, str) else tuple(value)
            )
        object.__setattr__(self, "extensions", dict(self.extensions))

    @classmethod
    def from_feature(cls, feature: Mapping[str, Any]) -> Rule:
        """Read one GeoJSON record (section 5); errors name the record's code.

        Registry.add then checks its names, and each dimension its values.
        """
        props = feature.get("properties") if isinstance(feature, Mapping) else None
        code = props.get("code") if isinstance(props, Mapping) else None
        try:
            return cls._read(feature, props)
        except (ValueError, TypeError, KeyError) as err:
            if not isinstance(code, str) or str(err).startswith(f"{code}:"):
                raise
            raise type(err)(f"{code}: {err}") from err

    @classmethod
    def _read(cls, feature: Any, props: Any) -> Rule:
        if not isinstance(feature, Mapping) or feature.get("type") != "Feature":
            raise ValueError("a record is a GeoJSON Feature")
        if not isinstance(props, Mapping) or "geometry" not in feature:
            raise ValueError("a record has properties and a geometry (null for none)")
        unknown = sorted(set(feature) - _FEATURE_KEYS) + sorted(
            k for k in props if k not in _RECORD_KEYS and not _EXTENSION.fullmatch(k)
        )
        missing = [k for k in ("code", "kind", "title", "message") if k not in props]
        if unknown or missing:
            raise ValueError(
                f"unknown members {unknown}" if unknown else f"missing {missing}"
            )
        if (
            feature.get("place") is not None
            or feature.get("coordRefSys", _CRS84) != _CRS84
        ):
            raise ValueError(f"place must be null, and coordRefSys {_CRS84}")
        for code in (props["code"], *props.get("supersedes", ())):
            check_code(code)
        if props.get("level", "info") not in ("info", "warning", "error"):
            raise ValueError(f"level is info, warning or error, not {props['level']!r}")
        if props.get("status") == "reviewed" and not props.get("references"):
            raise ValueError("a reviewed record cites at least one reference (Q54)")
        box, geometry = props.get("box"), feature["geometry"]
        if box is not None and geometry is not None:
            raise ValueError("a record with a box has a null geometry")
        space = None if geometry is None else sp.polygon(geometry)
        if box is not None:
            space = box_of(box)
        time = parse_time(feature.get("time"), **props)
        scope = Scope(space, time, props.get("dimensions", {}))
        fields = {k: props[k] for k in _RULE_KEYS if k in props}
        extensions = {k: v for k, v in props.items() if k.startswith("x_")}
        return cls(**fields, scope=scope, extensions=extensions)

    def to_feature(self) -> dict[str, Any]:
        """This rule as a GeoJSON record, the inverse of from_feature.

        Fields at their defaults are left out, a box is written as its polygon,
        and time goes in the JSON-FG time member with periods and recurrence.
        """
        if self.scope.space is not None and self.scope.space.kind != "polygon":
            raise ValueError(f"{self.code}: a record's space is a polygon, not a point")
        level = logging.getLevelName(self.level).lower()
        if level not in ("info", "warning", "error"):
            raise ValueError(f"{self.code}: a record's level is info, warning or error")
        props = {k: getattr(self, k) for k in _RULE_KEYS}
        props["level"] = level if self.level != LEVELS[self.kind] else None
        props["dimensions"] = self.scope.dimensions
        defaults = {f.name: f.default for f in dataclasses.fields(Rule)}
        props = {k: v for k, v in props.items() if v != defaults.get(k, {})}
        time, geometry, spec = None, None, self.scope.time
        if spec is not None:
            precision = max(iv.precision for iv in spec.intervals)
            extent = Interval(*spec.extent, precision).to_wire()
            if len(spec.intervals) > 1:
                props["periods"] = spec.to_wire()
            if extent != ("..", "..") or "periods" in props:
                time = {"interval": extent}
            if spec.months is not None:
                props["recurrence"] = {"months": sorted(spec.months)}
        if self.scope.space is not None:
            # Split edges longer than 180 degrees, which a reader would take the
            # short way round; normalising makes the output the same every time.
            shape = shapely.segmentize(self.scope.space.geometry, 180.0)
            shape = shapely.orient_polygons(shapely.normalize(shape))
            geometry = shapely.geometry.mapping(shape)
        feature = {"type": "Feature", "id": self.code, "geometry": geometry}
        feature |= {"time": time, "properties": props | dict(self.extensions)}
        return _jsonable(feature)

    def evaluate(self, query: Query) -> list[Finding]:
        """Findings for one query (section 4.3)."""
        bound = binding_of(self)
        found = match_scope(bound.registry, bound.scope, query)
        if found is None:
            return []
        match, details = found
        return make_findings(self, match, query, source=bound.source, details=details)


# ---- computed rules ---------------------------------------------------------------
OUTCOME_KEYS = tuple(f.name for f in dataclasses.fields(Outcome) if f.name != "code")
META_KEYS = frozenset(
    OUTCOME_KEYS
    + ("dimensions", "space", "time", "requires")
    + ("supersedes", "withdrawn")
)


def check_meta(meta: Mapping[str, Any], owner: str) -> None:
    unknown = set(meta) - META_KEYS
    if unknown:
        raise TypeError(f"{owner}: unknown keywords {sorted(unknown)}")


class ComputedRule:
    """A rule computed from the query or from data the caller holds.

    Class keywords give its identity and scope: code, registry (default
    Registry.default()), abstract, the Outcome fields (kind defaults to warning,
    level to the kind's default, title and message to the docstring), space (a
    Space), time, dimensions and requires (keys of Query.context).
    Defining a subclass registers one instance; a subclass inherits its bases'
    keywords, merged, with its own winning (Q9).

    check(query, match) runs only for a definite match and returns True (one
    finding with the declared outcome), False or None (none), a mapping of
    Finding fields to override, or several such mappings.
    """

    code: ClassVar[str]
    meta: ClassVar[dict[str, Any]]
    scope: Scope  # set by Registry.add from meta, after checking the declared names

    def __init_subclass__(
        cls, code: str = "", registry: Registry | None = None, **meta: Any
    ) -> None:
        super().__init_subclass__()
        abstract = meta.pop("abstract", False)
        cls._qe_meta = dict(
            meta, **({} if registry is None else {"registry": registry})
        )
        if abstract:
            return
        if not code:
            raise TypeError(f"{cls.__name__} needs the class keyword code=...")
        merged: dict[str, Any] = {}
        for base in reversed(cls.__mro__):
            merged.update(base.__dict__.get("_qe_meta", {}))
        target = merged.pop("registry", None)
        check_meta(merged, cls.__name__)
        cls.code, cls.meta = code, merged
        if target is None:
            from queryearth.registry import Registry

            target = Registry.default()
        target.add(cls())

    def _doc(self) -> str | None:
        return type(self).__doc__

    def _qualname(self) -> str:
        return f"{type(self).__module__}.{type(self).__qualname__}"

    @cached_property
    def outcome(self) -> Outcome:
        """The declared outcome, before check() overrides it."""
        fields = {k: self.meta[k] for k in OUTCOME_KEYS if k in self.meta}
        fields.setdefault("kind", "warning")
        lines = inspect.cleandoc(self._doc() or "").splitlines()
        fields.setdefault("title", lines[0] if lines else "")
        if not fields["title"]:
            raise TypeError(f"{self.code}: give a title= keyword or a docstring")
        fields.setdefault("message", "\n".join(lines[1:]).strip() or fields["title"])
        return Outcome(code=self.code, **fields)

    def evaluate(self, query: Query) -> list[Finding]:
        """Findings for one query: the scope, then check() if definite."""
        bound = binding_of(self)
        found = match_scope(bound.registry, bound.scope, query)
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
    """A plain function (query, match) -> CheckResult, wrapped by Registry.rule()."""

    def __init__(self, func: RuleFunc, code: str, meta: Mapping[str, Any]) -> None:
        check_meta(meta, code)
        self.func, self.code, self.meta = func, code, dict(meta)

    def _doc(self) -> str | None:
        return self.func.__doc__

    def _qualname(self) -> str:
        return f"{self.func.__module__}.{self.func.__qualname__}"

    def check(self, query: Query, match: Match) -> CheckResult:
        return self.func(query, match)
