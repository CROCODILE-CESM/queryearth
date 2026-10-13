"""The Registry: declared dimensions, products, regions and rules, and the query.

Registry.query follows design.md section 9.1: it splits the query into its base
query and one sub-query per request (section 4.12), calls evaluate() on every
active rule of each part (after any plugin prefilters), adds the built-in
coverage findings QE001 and QE002, and sorts.
"""

from __future__ import annotations

import copy
import dataclasses
import functools
import math
import os
import re
import threading
import types
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from fnmatch import fnmatchcase
from typing import Any, NamedTuple

import numpy as np
import shapely

from queryearth import packs
from queryearth import space as sp
from queryearth.dimensions import (
    Axis,
    Labels,
    Patterns,
    SpaceDimension,
    TimeDimension,
    Versions,
    is_glob,
)
from queryearth.errors import DuplicateCodeError, UnknownNameError
from queryearth.objects import (
    Coverage,
    Finding,
    Product,
    Query,
    Request,
    Scope,
    Severity,
    severity_of,
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
from queryearth.time import DAY, Interval, TimeSpec, overlap, time_fraction

__all__ = ["Registry", "PointResult", "ScoreFn", "Suitability", "default_score"]

_SLUG = re.compile(r"[a-z][a-z0-9_]*")
_REGION = re.compile(r"[a-z][a-z0-9_.-]*:[A-Za-z0-9_.+-]+")
_GROUPS = {"space": -2, "time": -1, "axes": 0, "facets": 1, "dims": 2}
_KINDS = {"coverage": 0, "caveat": 1, "recommendation": 2}
_PER_REQUEST = ("product", "variable", "version")

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
    per_request: bool  # constrains product, variable or version


@dataclass(eq=False)
class _Part:
    query: Query
    rules: str  # the rules it evaluates: "all", "base" or "request"
    product: Product | None = None
    coverage: Coverage | None = None


def _strings(value: Any) -> tuple[str, ...]:
    return (value,) if isinstance(value, str) else tuple(value or ())


class Registry:
    """Declared dimensions, products, regions and rules; answers queries.

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
        self._products: dict[str, Product] = {}
        self._aliases: dict[str, str] = {}  # case-folded name or alias -> name
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
        if name == "product" and not isinstance(dimension, Labels):
            raise ValueError("the product facet is always Labels('product')")
        self._groups.append((name, dimension, group))
        self._groups.sort(key=lambda g: _GROUPS[g[2]])  # stable sort

    def add_product(self, product: Product) -> None:
        """Declare a product; its name and aliases resolve exactly, ignoring case."""
        if not isinstance(product, Product):
            raise TypeError(f"expected a Product, not {type(product).__name__}")
        keys = {n.casefold() for n in (product.name, *product.aliases)}
        taken = keys & set(self._aliases)
        if taken:
            raise ValueError(f"{sorted(taken)} already name a declared product")
        self._products[product.name] = product
        self._aliases.update(dict.fromkeys(keys, product.name))

    @property
    def products(self) -> Mapping[str, Product]:
        """The declared products by canonical name, read-only (Q4)."""
        return types.MappingProxyType(self._products)

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
        per_request = any(k in compiled.values for k in _PER_REQUEST)
        entry = _Entry(rule, form, compiled, qualname, *lifecycle, per_request)
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

    def rule_counts(self) -> dict[str | None, int]:
        """How many active rules concern each product; None counts the others (Q35)."""
        counts: dict[str | None, int] = dict.fromkeys(self._products, 0)
        counts[None] = 0
        for entry in self._active():
            patterns = entry.scope.values.get("product")
            if patterns is None:
                counts[None] += 1
                continue
            for name in self._products:
                counts[name] += patterns.admits(name)
        return counts

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

    def _product(self, name: str) -> str:
        found = self._aliases.get(name.casefold()) if isinstance(name, str) else None
        if found is None:
            raise UnknownNameError(
                f"unknown product {name!r}; declared: {list(self._products)}"
            )
        return found

    def _product_patterns(self, patterns: Patterns) -> Patterns:
        """Resolve literal product names; a glob must match a declared product (Q3)."""

        def resolve(pattern: str) -> str:
            if not is_glob(pattern):
                return self._product(pattern)
            if not any(fnmatchcase(name, pattern) for name in self._products):
                raise ValueError(
                    f"product pattern {pattern!r} matches no declared product"
                )
            return pattern

        any_of = (
            None if patterns.any_of is None else tuple(map(resolve, patterns.any_of))
        )
        return Patterns(any_of, tuple(map(resolve, patterns.none_of)))

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
                if name == "product":
                    values[name] = self._product_patterns(values[name])
        return CompiledScope(values, requires)

    def _parse_query(self, query: Query) -> dict[str, Any]:
        """The query's values, parsed by their plugins; product aliases resolved."""
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
                if name == "product":
                    value = tuple(self._product(v) for v in value)
                parsed[name] = dimension.parse_query(value)
        self._last = (query, parsed)
        return parsed

    # ---- requests (section 4.12) ----------------------------------------------------
    def expand(self, query: Query) -> tuple[Query, ...]:
        """The base query and one sub-query per request, as the engine runs them."""
        return tuple(part.query for part in self._expand(self._make_query(query, {})))

    def _make_query(self, query: Query | None, fields: dict[str, Any]) -> Query:
        query = (
            Query(**fields) if query is None else dataclasses.replace(query, **fields)
        )
        if query.request is not None or query.assumed:
            raise ValueError(
                "request and assumed are set by Registry.expand(), not callers"
            )
        return query

    def _expand(self, query: Query) -> list[_Part]:
        self._parse_query(query)  # undeclared names and bad values raise here
        facets, dims, requests = dict(query.facets), dict(query.dims), query.requests
        given = [n for n in _PER_REQUEST if n in facets or n in dims]
        if requests and given:
            raise ValueError(f"give requests or the facets {given}, not both")
        if not requests and "product" in facets:  # the facet shorthand
            names = dict.fromkeys(self._product(p) for p in facets.pop("product"))
            variables = facets.pop("variable", None) or dims.pop("variable", ())
            version = facets.pop("version", None) or dims.pop("version", None)
            if version is not None:
                version = _strings(version)
                if len(names) != 1 or len(version) != 1:
                    raise ValueError(
                        "a version in the shorthand needs exactly one product"
                    )
                version = version[0]
            requests = [Request(name, variables, version) for name in names]
        base = dataclasses.replace(query, facets=facets, dims=dims, requests=())
        parts = [_Part(base, "base" if requests else "all")]
        for i, request in enumerate(requests):
            parts.append(self._sub_query(base, i, request))
        return parts

    def _sub_query(self, base: Query, position: int, request: Request) -> _Part:
        name = self._product(request.product)
        product = self._products[name]
        assumed = set()
        space = base.space if request.support is None else request.support
        version = request.version
        has_version = any(n == "version" for n, _, _ in self._groups)
        if version is None and product.version is not None and has_version:
            version = product.version
            assumed.add("version")
        facets, dims = dict(base.facets), dict(base.dims)
        for key, value in (
            ("product", name),
            ("variable", request.variables),
            ("version", version),
        ):
            if value:
                (facets if self._dimension(key)[1] == "facets" else dims)[key] = value
        time = request.time if request.time is not None else base.time
        sub = dataclasses.replace(
            base, space=space, time=time, facets=facets, dims=dims, request=position
        )
        coverage = (
            product.coverage(sub) if callable(product.coverage) else product.coverage
        )
        if not isinstance(coverage, Coverage):
            raise TypeError(
                f"the coverage of {name} returned {coverage!r}, not a Coverage"
            )
        if time is None:  # open at both ends when the coverage has no time
            time = coverage.time
            if time is None:
                time = TimeSpec((Interval(None, None),))
            assumed.add("time")
        order = tuple(d for d in ("time", "version") if d in assumed)
        sub = dataclasses.replace(sub, time=time, assumed=order)
        return _Part(sub, "request", product, coverage)

    # ---- queries ------------------------------------------------------------------
    def query(self, query: Query | None = None, /, **fields: Any) -> list[Finding]:
        """Findings for one query with any number of requests, sorted.

        fields are Query fields (they override those of query) and
        include_conditional, which also returns findings for rules the query
        leaves undecided. Sorted by severity, kind, code, then part.
        """
        conditional = fields.pop("include_conditional", False)
        found: list[Finding] = []
        for part in self._expand(self._make_query(query, fields)):
            found += self._run(part, conditional)
        self._last = (None, None)  # holds the caller's context until cleared
        return _sorted(found)

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

    def _candidates(self, part: _Part) -> list[_Entry]:
        """The active rules one part evaluates, narrowed by any plugin prefilters."""
        parsed = self._parse_query(part.query)
        allowed = {
            name: prefilter.candidates(parsed[name])
            for name, prefilter in self._prefilters().items()
            if name in parsed
        }
        position = {id(e): i for i, e in enumerate(self._entries)}
        return [
            e
            for e in self._active()
            if (part.rules == "all" or (part.rules == "request") == e.per_request)
            and all(
                name not in e.scope.values or position[id(e)] in keep
                for name, keep in allowed.items()
            )
        ]

    def _run(self, part: _Part, conditional: bool) -> list[Finding]:
        """Evaluate one part's rules and add its coverage findings."""
        query = part.query
        found: list[Finding] = []
        for entry in self._candidates(part):
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
        found += self._coverage(part)
        return [f for f in found if conditional or not f.conditional_on]

    def _coverage(
        self, part: _Part, share: Callable[[Space], float] | None = None
    ) -> list[Finding]:
        """QE001 and QE002 for a request's product: what lies outside its coverage.

        share(space) is the bulk path's weighted share of the points inside a space.
        """
        if part.product is None:
            return []
        query, coverage, name = part.query, part.coverage, part.product.name
        finding = functools.partial(
            Finding,
            kind="coverage",
            severity="severe",
            source="builtin",
            status="reviewed",
            product=name,
            request=query.request,
            query_label=query.label,
        )
        found = []
        title = f"Outside the spatial coverage of {name}"
        inside = inside_km2 = None
        if coverage.space is None:
            pass
        elif coverage.space.geometry.is_empty:  # a callable's "not served" (Q7)
            inside = inside_km2 = 0.0
        elif share is not None:
            inside = share(coverage.space)
        elif query.space is None:
            message = f"The request gives no space to check against {name}."
            undecided = ("space",)
            found.append(
                finding(
                    code="QE001", title=title, message=message, conditional_on=undecided
                )
            )
        else:
            inside, inside_km2 = sp.measure(coverage.space, query.space)
        if inside is not None and inside < 1.0:
            area = None if query.space is None else query.space.area_km2
            found.append(
                finding(
                    code="QE001",
                    title=title,
                    message=f"{1.0 - inside:.0%} of the request lies outside it.",
                    action="do_not_use" if inside == 0.0 else "use_with_caution",
                    area_fraction=1.0 - inside,
                    overlap_km2=None if area is None else area - (inside_km2 or 0.0),
                )
            )
        if coverage.time is None or query.time is None:
            return found
        ends = [k for span in coverage.time.intervals for k in (span.start, span.end)]
        ends = [None, *ends, None]  # the gaps run from each end to the next start
        gaps = [
            Interval(
                a, b, "day" if all((k or 0) % DAY == 0 for k in (a, b)) else "second"
            )
            for a, b in zip(ends[::2], ends[1::2])
            if (a, b) != (None, None)
        ]
        outside = gaps and overlap(TimeSpec(tuple(gaps)), query.time)
        if outside:
            periods = outside.to_wire()
            found.append(
                finding(
                    code="QE002",
                    title=f"Outside the temporal coverage of {name}",
                    message="Outside it: " + ", ".join(f"{a}..{b}" for a, b in periods),
                    action=(
                        "do_not_use"
                        if overlap(coverage.time, query.time) is None
                        else "use_with_caution"
                    ),
                    time_overlap=periods,
                    time_fraction=time_fraction(outside, query.time),
                )
            )
        return found

    # ---- the inverse query (section 10) ---------------------------------------------
    def suitable(
        self,
        query: Query,
        variable: str,
        *,
        products: Sequence[str] | None = None,
        score: ScoreFn | None = None,
        include_dropped: bool = False,
    ) -> list[Suitability]:
        """The products that can serve a request, fewest known concerns first.

        Not a quality ranking: empty findings mean only that no registered rule
        matched, and a product ranks higher simply because less has been written
        about it (see rule_counts()). Each candidate is judged on one request
        added to the query (section 10.1); one entirely outside its coverage is
        dropped, or listed last with include_dropped=True.
        """
        given = [n for n in _PER_REQUEST if n in query.facets or n in query.dims]
        if query.requests or given:
            raise ValueError(
                "suitable() adds one request per product, so the query gives no "
                f"requests and none of the facets {list(_PER_REQUEST)}"
            )
        if products is None:
            names = sorted(
                n for n, p in self._products.items() if variable in p.variables
            )
        else:
            names = list(dict.fromkeys(self._product(p) for p in products))
            lacking = [n for n in names if variable not in self._products[n].variables]
            if lacking:
                raise ValueError(f"products {lacking} do not offer {variable!r}")
        ranked, dropped = [], []
        for name in names:
            product = self._products[name]
            one = self._make_query(query, {"requests": (Request(name, (variable,)),)})
            found = _sorted(self._run(self._expand(one)[1], False))
            if any(f.kind == "coverage" and f.action == "do_not_use" for f in found):
                outside = tuple(f for f in found if f.kind == "coverage")
                dropped.append(Suitability(product, (), outside))
                continue
            rank = tuple(
                float(v) for v in (score or default_score)(product, one, found)
            )
            ranked.append(Suitability(product, rank, tuple(found)))
        self._last = (None, None)
        ranked.sort(key=lambda s: (s.score, s.product.name))
        return ranked + dropped if include_dropped else ranked

    # ---- the bulk path (section 9.3) ------------------------------------------------
    def query_points(
        self, lon: Any, lat: Any, weights: Any = None, **fields: Any
    ) -> PointResult:
        """Masks and weighted fractions over many points (section 9.3).

        fields are those of query() but space, context and Request.support: the
        points are every request's support. Weights default to equal, and zero
        weights leave points out of every fraction. NaN points are inside no
        rule. A computed rule takes part through its mask(lon, lat, query) hook,
        called with the flat arrays, and is otherwise listed in skipped.
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
        query = self._make_query(None, fields)
        if any(r.support is not None for r in query.requests):
            raise ValueError("the points are the support of every request; give none")
        total = w[valid].sum()
        found: list[Finding] = []
        masks: dict[tuple[str | None, str], np.ndarray] = {}
        fractions: dict[tuple[str | None, str], float] = {}
        skipped = []

        def keep(key: tuple[str | None, str], mask: np.ndarray) -> float:
            masks[key] = mask.reshape(shape)
            fractions[key] = float(w[mask].sum() / total)
            return fractions[key]

        def share(space: Space) -> float:
            return float(w[sp.points_mask(space, x, y)].sum() / total)

        for part in self._expand(query):
            q = part.query
            product = q.facets["product"][0] if q.request is not None else None
            for entry in self._candidates(part):
                rule, key = entry.rule, (product, entry.rule.code)
                values = {k: v for k, v in entry.scope.values.items() if k != "space"}
                scope = CompiledScope(values)  # the points stand in for space
                matched = match_scope(self, scope, q)
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
                    skipped.append(key)
                    continue
                computed = entry.form == "computed"
                if not match.conditional_on:  # conditional findings get no mask
                    if computed:
                        hooked = rule.mask(x, y, q)
                        if hooked is None:
                            skipped.append(key)
                            continue
                        mask &= np.asarray(hooked, bool).reshape(-1)
                        if not mask.any():
                            continue
                    fraction = keep(key, mask)
                    match = dataclasses.replace(match, area_fraction=fraction)
                outcome = rule.outcome if computed else rule
                source = binding_of(rule).source
                found += make_findings(
                    outcome, match, q, source=source, details=details
                )
            for f in self._coverage(part, share):
                found.append(f)
                cover = part.coverage.space
                if f.code == "QE001" and not cover.geometry.is_empty:
                    keep((f.product, f.code), valid & ~sp.points_mask(cover, x, y))
                else:
                    keep((f.product, f.code), valid.copy())
        self._last = (None, None)
        found = _sorted(f for f in found if conditional or not f.conditional_on)
        return PointResult(tuple(found), masks, fractions, tuple(skipped), shape)


def _sorted(findings: Iterable[Finding]) -> list[Finding]:
    """By severity (highest first), kind, code, then part (base query first)."""
    part = lambda f: -1 if f.request is None else f.request  # noqa: E731
    return sorted(
        findings, key=lambda f: (-f.severity, _KINDS[f.kind], f.code, part(f))
    )


# ---- results of the bulk path and the inverse query -------------------------------
@dataclass(frozen=True, eq=False)
class PointResult:
    """What Registry.query_points found, keyed by (product, code), product None
    on the base query. Masks are shaped like lon; conditional findings have none.
    """

    findings: tuple[Finding, ...]
    masks: Mapping[tuple[str | None, str], np.ndarray]
    fractions: Mapping[tuple[str | None, str], float]
    skipped: tuple[tuple[str | None, str], ...] = ()
    shape: tuple[int, ...] = ()  # the shape of lon

    def any(self, min_severity: Severity | str | int = Severity.WARNING) -> np.ndarray:
        """Points inside some definite finding at or above min_severity."""
        floor = severity_of(min_severity)
        out = np.zeros(self.shape, bool)
        for f in self.findings:
            key = (f.product, f.code)
            if f.severity >= floor and key in self.masks:
                out |= self.masks[key]
        return out


class Suitability(NamedTuple):
    """A product ranked by Registry.suitable; a low score is not "good data"."""

    product: Product
    score: tuple[float, ...]  # for ordering only; () for a dropped product
    findings: tuple[Finding, ...]  # this product's definite findings


ScoreFn = Callable[[Product, Query, Sequence[Finding]], tuple[float, ...]]
_WEIGHTS = {Severity.INFO: 1.0, Severity.WARNING: 2.0, Severity.SEVERE: 4.0}


def default_score(
    product: Product, query: Query, findings: Sequence[Finding]
) -> tuple[float, float, float]:
    """(worst, burden, misfit): lower means fewer known concerns (section 10.2).

    Counts definite caveat and coverage findings not below their min_overlap;
    burden weighs severities 1, 2, 4 by area and time fractions (1.0 if None).
    """
    counted = [
        f
        for f in findings
        if not f.conditional_on
        and f.kind in ("caveat", "coverage")
        and (f.area_fraction is None or f.area_fraction >= f.min_overlap)
    ]
    worst = max((int(f.severity) for f in counted), default=0)
    burden = sum(
        _WEIGHTS[f.severity]
        * (1.0 if f.area_fraction is None else f.area_fraction)
        * (1.0 if f.time_fraction is None else f.time_fraction)
        for f in counted
    )
    misfit = 0.0
    space = query.space
    if product.resolution is not None and space is not None and space.area_km2:
        size, unit = product.resolution
        if unit == "deg":  # an equal-area square at the centroid latitude
            lat = math.radians(shapely.centroid(space.geometry).y)
            width = math.radians(size)
            size = sp.R_KM * math.sqrt(
                width * 2.0 * math.cos(lat) * math.sin(width / 2)
            )
        if size > 0.0:
            misfit = max(0.0, math.log2(size / math.sqrt(space.area_km2)))
    return float(worst), round(burden, 3), misfit
