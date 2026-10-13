"""The Registry: declared dimensions, regions and rules, and the query.

Registry.query follows design.md section 9.1: it calls evaluate() on every
active rule (after any plugin prefilters) and sorts the findings.
"""

from __future__ import annotations

import copy
import dataclasses
import functools
import logging
import os
import re
import threading
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np
import shapely

from queryearth import packs
from queryearth import space as sp
from queryearth.dimensions import Axis, Labels, SpaceDimension, TimeDimension, Versions
from queryearth.objects import (
    KINDS,
    DuplicateCodeError,
    Finding,
    Query,
    Scope,
    UnknownNameError,
    level_of,
    time_of,
)
from queryearth.rules import (
    Binding,
    CompiledScope,
    ComputedRule,
    FunctionRule,
    Rule,
    RuleFunc,
    binding_of,
    check_code,
    computed_findings,
    make_findings,
    match_scope,
)
from queryearth.space import Space

__all__ = ["Registry", "PointResult"]

_SLUG = re.compile(r"[a-z][a-z0-9_]*")
_REGION = re.compile(r"[a-z][a-z0-9_.-]*:[A-Za-z0-9_.+-]+")
_GROUPS = {"space": -2, "time": -1, "axes": 0, "facets": 1, "dims": 2}

_default: Registry | None = None
_default_lock = threading.Lock()


@dataclass(eq=False)
class _Entry:
    rule: Any
    form: str  # "record", "computed", "hooked" (has outcomes()) or "foreign"
    scope: CompiledScope
    qualname: str | None  # a redefinition with the same name replaces it (Q10)
    withdrawn: bool
    supersedes: tuple[str, ...]


def _strings(value: Any) -> tuple[str, ...]:
    return (value,) if isinstance(value, str) else tuple(value or ())


class Registry:
    """Declared dimensions, regions and rules; answers queries.

    There is no hidden global registry: a library keeps its own Registry, and
    Registry.default() is the application default for scripts and notebooks.
    """

    FACETS = ("product", "variable", "version", "model", "component")

    def __init__(
        self,
        name: str = "",
        *,
        axes: Iterable[Axis] = (),
        facets: Iterable[str] = FACETS,  # "version" becomes Versions(), others Labels
        dimensions: Iterable[Any] = (),  # any other plugin dimensions
    ) -> None:
        self.name = name
        self._groups: list[tuple[str, Any, str]] = [  # then axes, facets, others
            ("space", SpaceDimension(), "space"),
            ("time", TimeDimension(), "time"),
        ]
        self._regions: dict[str, Space] = {}  # "namespace:id" -> polygon
        self._entries: list[_Entry] = []
        self._codes: dict[str, int] = {}
        self._packs: dict[str, tuple[str, ...]] = {}  # loaded pack -> its prefixes
        self._prefilters_cache: dict[str, Any] | None = None
        self._last: tuple[Any, Any] = (None, None)  # the last query parsed
        for axis in axes:
            if not isinstance(axis, Axis):
                raise TypeError(f"axes holds Axis objects, not {axis!r}")
            self.add_dimension(axis)
        for facet in facets:
            if isinstance(facet, str):
                facet = Versions() if facet == "version" else Labels(facet)
            self.add_dimension(facet)
        for dimension in dimensions:
            self.add_dimension(dimension)

    def __repr__(self) -> str:
        return f"Registry({self.name!r}, rules={len(self._entries)})"

    @classmethod
    def default(cls) -> Registry:
        """The application default Registry, made on first use."""
        global _default
        with _default_lock:
            if _default is None:
                _default = Registry("default")
            return _default

    # ---- declarations -------------------------------------------------------------
    def add_dimension(self, dimension: Any) -> None:
        """Declare a plugin dimension (section 4.13), before any rule is added."""
        if self._entries:
            raise ValueError("declare dimensions before adding rules")
        name = getattr(dimension, "name", None)
        if not isinstance(name, str) or not _SLUG.fullmatch(name):
            raise ValueError(f"a dimension name is a lowercase slug, not {name!r}")
        if any(n == name for n, _, _ in self._groups):
            raise ValueError(f"dimension name {name!r} is reserved or already declared")
        for member in ("parse_rule", "parse_query", "match"):
            if not callable(getattr(dimension, member, None)):
                raise TypeError(f"dimension {name!r} has no {member}() method")
        if not isinstance(getattr(dimension, "schema", None), Mapping):
            raise TypeError(f"dimension {name!r} has no schema mapping")
        group = "axes" if isinstance(dimension, Axis) else "dims"
        if isinstance(dimension, (Labels, Versions)):
            group = "facets"
        self._groups.append((name, dimension, group))
        self._groups.sort(key=lambda g: _GROUPS[g[2]])  # stable sort

    def add_regions(self, namespace: str, regions: Mapping[str, Any]) -> None:
        """Declare named regions, referred to as "namespace:id" in region_ref."""
        for rid, shape in regions.items():
            ref = f"{namespace}:{rid}"
            if not _REGION.fullmatch(ref):
                raise ValueError(f"{ref!r} is not a region reference")
            space = shape if isinstance(shape, Space) else sp.polygon(shape)
            if space.kind != "polygon":
                raise ValueError(f"region {ref} is not an area")
            if self._regions.setdefault(ref, space) is not space:
                raise ValueError(f"region {ref} is already declared")

    def add(self, rule: Any) -> None:
        """Add a Rule, a ComputedRule instance, any RuleKind or a record mapping.

        A mapping is a GeoJSON Feature or a FeatureCollection, added whole or not
        at all (LoadError). A reused code raises DuplicateCodeError, except that
        redefining a computed rule with the same qualified name replaces it (Q10).
        """
        if isinstance(rule, Mapping):
            packs.add_mapping(self, rule)
        else:
            self._add(rule, "python")

    def load_pack(self, path: str | os.PathLike[str]) -> list[str]:
        """Load a data-only pack directory (section 5.4); returns the codes loaded.

        Raises LoadError listing every problem with its file, the feature's
        position and its code, and then leaves the Registry as it was.
        """
        return packs.load_pack(self, path)

    def _add(self, rule: Any, source: str) -> None:
        """Registry.add; source names a record's pack ("python" from Python)."""
        if isinstance(rule, ComputedRule):
            form, get = "computed", rule.meta.get
            scope = Scope(
                get("space"),
                time_of(get("time")),
                get("axes", {}),
                get("facets", {}),
                get("dims", {}),
            )
        elif isinstance(getattr(rule, "scope", None), Scope) and hasattr(
            rule, "evaluate"
        ):
            form = "hooked" if hasattr(rule, "outcomes") else "foreign"
            form = "record" if isinstance(rule, Rule) else form
            scope, get = rule.scope, functools.partial(getattr, rule)
        else:
            raise TypeError(f"cannot add {rule!r}: not a Rule or a RuleKind")
        code = rule.code
        check_code(code)
        refs, requires = _strings(get("region_ref", ())), _strings(get("requires", ()))
        compiled = self._compile(scope, refs, requires, code)
        qualname = rule._qualname() if form == "computed" else None
        at = self._codes.get(code)
        if at is not None and (
            qualname is None or self._entries[at].qualname != qualname
        ):
            raise DuplicateCodeError(
                f"code {code!r} is already on registry {self.name!r}"
            )
        bound = getattr(rule, "_qe_binding", None)
        if bound is not None and bound.registry is not self:
            if form != "record":
                raise ValueError(
                    f"{code}: this rule object is already on another Registry"
                )
            rule = copy.copy(rule)
        if form == "computed":
            rule.scope = scope
        if form in ("record", "computed"):
            source = source if form == "record" else "computed"
            object.__setattr__(rule, "_qe_binding", Binding(self, compiled, source))
        lifecycle = bool(get("withdrawn", None)), _strings(get("supersedes", ()))
        entry = _Entry(rule, form, compiled, qualname, *lifecycle)
        if at is None:
            self._codes[code] = len(self._entries)
            self._entries.append(entry)
        else:
            self._entries[at] = entry
        self._prefilters_cache = None

    def rule(self, code: str, **meta: Any) -> Callable[[RuleFunc], RuleFunc]:
        """Register a function (query, match) -> CheckResult as a computed rule.

        Takes the keywords of ComputedRule; the title comes from the docstring.
        """

        def register(func: RuleFunc) -> RuleFunc:
            self.add(FunctionRule(func, code, meta))
            return func

        return register

    # ---- names --------------------------------------------------------------------
    def _dimension(self, name: str, group: str | None = None) -> tuple[Any, str]:
        for declared, dimension, kind in self._groups:
            if declared == name:
                if group is not None and kind != group:
                    raise UnknownNameError(
                        f"{name!r} is declared in {kind}, not {group}"
                    )
                return dimension, kind
        declared = [n for n, _, _ in self._groups]
        raise UnknownNameError(f"undeclared dimension {name!r}; declared: {declared}")

    def _region(self, refs: tuple[str, ...], owner: str) -> Space:
        """The union of named regions, as region_ref names them."""
        missing = [r for r in refs if r not in self._regions]
        if missing:
            raise UnknownNameError(f"{owner}: undeclared regions {missing}")
        if len(refs) == 1:
            return self._regions[refs[0]]
        parts = [self._regions[r].geometry for r in refs]
        geometry = shapely.orient_polygons(shapely.union_all(parts))
        return Space("polygon", geometry=geometry, area_km2=sp.area_km2(geometry))

    def _compile(
        self, scope: Scope, refs: tuple[str, ...], requires: tuple[str, ...], code: str
    ) -> CompiledScope:
        space = self._region(refs, code) if refs else scope.space
        if space is not None and space.kind != "polygon":
            raise ValueError(f"{code}: a rule space is a polygon, not a point")
        values = {
            k: v for k, v in (("space", space), ("time", scope.time)) if v is not None
        }
        for group in ("axes", "facets", "dims"):
            for name, value in getattr(scope, group).items():
                dimension, _ = self._dimension(name, group)
                try:
                    values[name] = dimension.parse_rule(value)
                except ValueError as err:
                    raise ValueError(f"{code}: {name}: {err}") from err
        return CompiledScope(values, requires)

    def _parse_query(self, query: Query) -> dict[str, Any]:
        """The query's values, parsed by their plugins."""
        if self._last[0] is query:
            return self._last[1]
        parsed = {
            k: v
            for k, v in (("space", query.space), ("time", query.time))
            if v is not None
        }
        for group in ("axes", "facets", "dims"):
            for name, value in getattr(query, group).items():
                dimension, _ = self._dimension(name, group)
                parsed[name] = dimension.parse_query(value)
        self._last = (query, parsed)
        return parsed

    # ---- queries ------------------------------------------------------------------
    def query(self, query: Query | None = None, /, **fields: Any) -> list[Finding]:
        """Findings for one query, sorted by level, kind, then code.

        fields are Query fields (they override those of query) and
        include_conditional, which also returns findings for rules the query
        leaves undecided.
        """
        conditional = fields.pop("include_conditional", False)
        query = (
            Query(**fields) if query is None else dataclasses.replace(query, **fields)
        )
        found: list[Finding] = []
        for entry in self._candidates(query):
            if entry.form in ("record", "computed"):
                found += entry.rule.evaluate(query)
                continue
            matched = match_scope(self, entry.scope, query)  # third-party kinds
            if matched is None:  # a definite scope failure drops the rule
                continue
            if entry.form == "foreign":  # its own evaluate() decides the rest
                found += entry.rule.evaluate(query)
            else:
                match, details = matched
                found += computed_findings(
                    entry.rule.outcome, match, query, details, entry.rule.outcomes
                )
        self._last = (None, None)  # holds the caller's context until cleared
        return _sorted(f for f in found if conditional or not f.conditional_on)

    def _active(self) -> list[_Entry]:
        """The rules that are neither withdrawn nor superseded."""
        superseded = {code for e in self._entries for code in e.supersedes}
        return [
            e
            for e in self._entries
            if not e.withdrawn and e.rule.code not in superseded
        ]

    def _prefilters(self) -> dict[str, Any]:
        """Plugin prefilters (a Dimension's optional build()), rebuilt after a change."""
        if self._prefilters_cache is None:
            entries = list(enumerate(self._entries))
            self._prefilters_cache = {
                name: dimension.build(
                    [
                        (i, e.scope.values[name])
                        for i, e in entries
                        if name in e.scope.values
                    ]
                )
                for name, dimension, _ in self._groups
                if type(dimension) not in (Axis, Labels)
                and callable(getattr(dimension, "build", None))
                and not hasattr(dimension, "comparable")
            }
        return self._prefilters_cache

    def _candidates(self, query: Query) -> list[_Entry]:
        """The active rules a query evaluates, narrowed by any plugin prefilters."""
        parsed = self._parse_query(query)
        allowed = {
            name: prefilter.candidates(parsed[name])
            for name, prefilter in self._prefilters().items()
            if name in parsed
        }
        position = {id(e): i for i, e in enumerate(self._entries)}
        return [
            e
            for e in self._active()
            if all(
                name not in e.scope.values or position[id(e)] in keep
                for name, keep in allowed.items()
            )
        ]

    # ---- the bulk path (section 9.3) ------------------------------------------------
    def query_points(
        self, lon: Any, lat: Any, weights: Any = None, **fields: Any
    ) -> PointResult:
        """Masks and weighted fractions over many points (section 9.3).

        fields are those of query() but space and context: the points are the
        support. Weights default to equal, and zero weights leave points out of
        every fraction. NaN points are inside no rule. A computed rule takes part
        through its mask(lon, lat, query) hook, called with the flat arrays, and
        is otherwise listed in skipped.
        """
        conditional = fields.pop("include_conditional", False)
        if "space" in fields or "context" in fields:
            raise TypeError("the points are the space, and there is no context")
        shape = np.shape(lon)
        x = sp.wrap_lon(np.asarray(lon, dtype=float).ravel())
        y = np.asarray(lat, dtype=float).ravel()
        valid = sp.points_mask(None, x, y)  # finite; raises for latitudes past 90
        w = np.ones_like(x) if weights is None else np.array(weights, dtype=float)
        w = w.ravel()
        if w.shape != x.shape:
            raise ValueError(f"{w.size} weights for {x.size} points")
        if not (np.all(np.isfinite(w)) and np.all(w >= 0.0) and w.sum() > 0.0):
            raise ValueError("weights must be finite, non-negative and not all zero")
        query = Query(**fields)
        total = w[valid].sum()
        found: list[Finding] = []
        masks: dict[str, np.ndarray] = {}
        fractions: dict[str, float] = {}
        skipped = []
        for entry in self._candidates(query):
            rule, code = entry.rule, entry.rule.code
            values = {k: v for k, v in entry.scope.values.items() if k != "space"}
            scope = CompiledScope(values)  # the points stand in for space
            matched = match_scope(self, scope, query)
            if matched is None:
                continue
            match, details = matched
            if match.conditional_on and not conditional:
                continue
            space = entry.scope.values.get("space")
            mask = valid.copy() if space is None else sp.points_mask(space, x, y)
            if not mask.any():
                continue
            if entry.form in ("hooked", "foreign"):  # no outcome to mask
                skipped.append(code)
                continue
            computed = entry.form == "computed"
            if not match.conditional_on:  # conditional findings get no mask
                if computed:
                    hooked = rule.mask(x, y, query)
                    if hooked is None:
                        skipped.append(code)
                        continue
                    mask &= np.asarray(hooked, bool).reshape(-1)
                    if not mask.any():
                        continue
                masks[code] = mask.reshape(shape)
                fractions[code] = float(w[mask].sum() / total)
                match = dataclasses.replace(match, area_fraction=fractions[code])
            outcome = rule.outcome if computed else rule
            source = binding_of(rule).source
            found += make_findings(
                outcome, match, query, source=source, details=details
            )
        self._last = (None, None)
        return PointResult(
            tuple(_sorted(found)), masks, fractions, tuple(skipped), shape
        )


def _sorted(findings: Iterable[Finding]) -> list[Finding]:
    """By level (highest first), kind, then code."""
    return sorted(findings, key=lambda f: (-f.level, KINDS.index(f.kind), f.code))


# ---- the result of the bulk path ----------------------------------------------------
@dataclass(frozen=True, eq=False)
class PointResult:
    """What Registry.query_points found, keyed by rule code.

    Masks are shaped like lon; conditional findings have none.
    """

    findings: tuple[Finding, ...]
    masks: Mapping[str, np.ndarray]
    fractions: Mapping[str, float]
    skipped: tuple[str, ...] = ()  # codes of matching rules with no mask
    shape: tuple[int, ...] = ()  # the shape of lon

    def any(self, min_level: int | str = logging.WARNING) -> np.ndarray:
        """Points inside some definite finding at or above min_level."""
        floor = level_of(min_level)
        out = np.zeros(self.shape, bool)
        for f in self.findings:
            if f.level >= floor and f.code in self.masks:
                out |= self.masks[f.code]
        return out
