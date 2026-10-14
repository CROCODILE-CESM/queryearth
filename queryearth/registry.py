"""The Registry: declared dimensions and rules, loading rule files, and the query.

Registry.query follows design.md section 9.1: it calls evaluate() on every
active rule (after any plugin prefilters) and sorts the findings.
"""

from __future__ import annotations

import copy
import dataclasses
import functools
import json
import logging
import os
import re
import threading
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from queryearth import space as sp
from queryearth.dimensions import (
    Dimension,
    Edge,
    SpaceDimension,
    TimeDimension,
    describe_dimension,
    dimension_from,
)
from queryearth.objects import (
    DuplicateCodeError,
    Finding,
    LoadError,
    Outcome,
    Query,
    Scope,
    UnknownNameError,
    _jsonable,
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
    check_prefix,
    computed_findings,
    make_code,
    make_findings,
    match_scope,
    split_code,
)

__all__ = ["FORMAT", "Registry", "PointResult"]

# The release that last changed the rule file format. to_file() writes it in the
# "queryearth" member, and a file that needs a later release is refused.
FORMAT = "0.4"

_SLUG = re.compile(r"[a-z][a-z0-9_]*")
_RELEASE = re.compile(r"([0-9]+)\.([0-9]+)(?:\.[0-9]+)?")

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


def _read(path: Path) -> Any:
    """A rule file's JSON, or LoadError naming the file."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as err:
        raise LoadError([f"{path.name}: {err}"]) from err


def _format_problems(collection: Any, where: str) -> list[str]:
    """Why this queryearth cannot read a collection, from its "queryearth" member."""
    given = collection.get("queryearth") if isinstance(collection, Mapping) else None
    if given is None:
        return []
    found = _RELEASE.fullmatch(given) if isinstance(given, str) else None
    if found is None:
        return [
            f'{where}: "queryearth" is the release whose file format the file '
            f'uses, such as "{FORMAT}", not {given!r}'
        ]
    newest = tuple(int(n) for n in _RELEASE.fullmatch(FORMAT).groups()[:2])
    if tuple(int(n) for n in found.groups()[:2]) > newest:
        from queryearth import __version__

        return [
            f"{where}: this file needs queryearth {given} or later; this is "
            f"queryearth {__version__}, which reads files up to {FORMAT}"
        ]
    return []


class Registry:
    """Declared dimensions and rules; answers queries.

    Space and time are built in; dimensions lists every other dimension, such
    as Axis, Labels and Versions objects and plugins, in the order that
    conditional_on names them. There is no hidden global registry: a library
    keeps its own Registry, and Registry.default() is the application default
    for scripts and notebooks.
    """

    def __init__(
        self,
        name: str = "",
        *,
        dimensions: Iterable[Any] = (),
        groups: Mapping[str, str] | None = None,
    ) -> None:
        self.name = name
        self._dimensions: dict[str, Any] = {
            "space": SpaceDimension(),
            "time": TimeDimension(),
        }
        self._groups: dict[str, str] = {}
        self._entries: list[_Entry] = []
        self._codes: dict[str, int] = {}
        self._prefilters_cache: dict[str, Any] | None = None
        self._last: tuple[Any, Any] = (None, None)  # the last query parsed
        for dimension in dimensions:
            self.add_dimension(dimension)
        for prefix, title in (groups or {}).items():
            self.add_group(prefix, title)

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
        """Declare a dimension (section 4.13), before any rule is added."""
        if self._entries:
            raise ValueError("declare dimensions before adding rules")
        if isinstance(dimension, str):
            raise TypeError(
                f"declare a dimension with an object such as qe.Labels({dimension!r}),"
                f" not the bare name {dimension!r}"
            )
        if not isinstance(dimension, Dimension):
            raise TypeError(
                f"a dimension subclasses qe.Dimension, as qe.Axis, qe.Labels and "
                f"qe.Versions do; {type(dimension).__name__} does not"
            )
        name = getattr(dimension, "name", None)
        if not isinstance(name, str) or not _SLUG.fullmatch(name):
            raise ValueError(f"a dimension name is a lowercase slug, not {name!r}")
        if name in self._dimensions:
            raise ValueError(f"dimension name {name!r} is reserved or already declared")
        self._dimensions[name] = dimension

    def add_group(self, prefix: str, title: str) -> None:
        """Declare a group of rules, before any rule is added: the rules whose
        codes have this prefix, such as ITF for ITF001. Once a Registry declares
        groups, every rule's prefix must be one of them."""
        if self._entries:
            raise ValueError("declare groups before adding rules")
        check_prefix(prefix)
        if not isinstance(title, str) or not title.strip():
            raise ValueError(f"group {prefix!r} needs a title")
        if prefix in self._groups:
            raise ValueError(f"group {prefix!r} is already declared")
        self._groups[prefix] = title

    @property
    def groups(self) -> dict[str, str]:
        """The declared groups, prefix to title, in the order declared."""
        return dict(self._groups)

    def next_code(self, prefix: str) -> str:
        """The code for a new rule in a group: one more than the highest number
        any rule here has with that prefix, withdrawn ones too, so no number is
        given twice. ITF001 when the group has no rules yet."""
        check_prefix(prefix)
        if self._groups and prefix not in self._groups:
            raise UnknownNameError(
                f"undeclared group {prefix!r}; declared: {list(self._groups)}"
            )
        numbers = [n for p, n in map(split_code, self._codes) if p == prefix]
        return make_code(prefix, max(numbers, default=0) + 1)

    def add(self, rule: Any) -> None:
        """Add a Rule, a ComputedRule instance, any RuleKind or a record mapping.

        A mapping is a GeoJSON Feature or a FeatureCollection, added whole or not
        at all (LoadError). A reused code raises DuplicateCodeError, except that
        redefining a computed rule with the same qualified name replaces it (Q10).
        """
        if isinstance(rule, Mapping) and rule.get("type") == "FeatureCollection":
            self._add_all(rule, "collection", "python")
        elif isinstance(rule, Mapping):
            self._add(Rule.from_feature(rule), "python")
        else:
            self._add(rule, "python")

    @classmethod
    def from_file(cls, path: str | os.PathLike[str]) -> Registry:
        """A Registry made for one rule file, with its rules loaded.

        The file declares the dimensions its rules use in its "dimensions"
        member, in the form describe() gives: [{"name": "resolution", "kind":
        "axis", "unit": "km"}, {"name": "product", "kind": "labels"}]. Space and
        time need no declaring. Its optional "groups" member maps code prefixes
        to titles, and "queryearth" names the release whose format it uses.
        Raises LoadError as load() does.
        """
        path = Path(path)
        data = _read(path)
        problems = _format_problems(data, path.name)
        if problems:
            raise LoadError(problems)
        declared = data.get("dimensions", []) if isinstance(data, Mapping) else []
        try:
            if not isinstance(declared, list):
                raise ValueError("it is a list of dimensions")
            registry = cls(path.stem, dimensions=map(dimension_from, declared))
        except (ValueError, TypeError) as err:
            raise LoadError([f"{path.name}: dimensions: {err}"]) from err
        groups = data.get("groups") if isinstance(data, Mapping) else None
        try:
            if groups is not None and not isinstance(groups, Mapping):
                raise ValueError("it maps each prefix to a title")
            for prefix, title in (groups or {}).items():
                registry.add_group(prefix, title)
        except (ValueError, TypeError) as err:
            raise LoadError([f"{path.name}: groups: {err}"]) from err
        try:
            registry.load(path)
        except LoadError as err:
            if declared or not any("undeclared dimension" in p for p in err.problems):
                raise
            hint = f'{path.name}: declare the dimensions the rules use in the file\'s "dimensions" member'
            raise LoadError([*err.problems, hint]) from None
        return registry

    def load(self, path: str | os.PathLike[str]) -> list[str]:
        """Add the rules of one GeoJSON file, a FeatureCollection or a single Feature.

        Returns the codes loaded; their findings have the file name as source.
        Loading never runs code. Raises LoadError listing every problem with the
        file, the feature's position and its code, and then leaves the Registry
        as it was. A file that declares its dimensions or groups must declare
        them as this Registry does.
        """
        path = Path(path)
        data = _read(path)
        if isinstance(data, Mapping) and data.get("type") == "Feature":
            data = {"type": "FeatureCollection", "features": [data]}
        return self._add_all(data, path.name, path.name)

    def _add_all(self, collection: Any, where: str, source: str) -> list[str]:
        """Add every record of a FeatureCollection, or none of them (LoadError)."""
        features = (
            collection.get("features") if isinstance(collection, Mapping) else None
        )
        if (
            not isinstance(features, list)
            or collection.get("type") != "FeatureCollection"
        ):
            raise LoadError([f"{where}: not a GeoJSON FeatureCollection or Feature"])
        problems = _format_problems(collection, where)
        problems += self._declared_problems(collection.get("dimensions"), where)
        problems += self._group_problems(collection.get("groups"), where)
        if problems:
            raise LoadError(problems)
        saved = {k: copy.copy(v) for k, v in vars(self).items()}
        codes = []
        try:
            for i, feature in enumerate(features):
                props = (
                    feature.get("properties") if isinstance(feature, Mapping) else None
                )
                code = props.get("code") if isinstance(props, Mapping) else None
                try:
                    rule = Rule.from_feature(feature)
                    self._add(rule, source)
                    codes.append(rule.code)
                except (ValueError, TypeError, KeyError) as err:
                    text = str(err).removeprefix(f"{code}: ")
                    problems.append(f"{where}: feature {i} ({code}): {text}")
            if problems:
                raise LoadError(problems)
        except BaseException:
            vars(self).clear()
            vars(self).update(saved)
            raise
        return codes

    def _declared_problems(self, declared: Any, where: str) -> list[str]:
        """How a collection's "dimensions" member disagrees with this Registry."""
        if declared is None:
            return []
        if not isinstance(declared, list):
            return [f"{where}: dimensions: it is a list of dimensions"]
        mine = {
            name: describe_dimension(d)
            for name, d in list(self._dimensions.items())[2:]
        }
        problems = []
        for item in declared:
            try:
                theirs = describe_dimension(dimension_from(item))
            except (ValueError, TypeError) as err:
                problems.append(f"{where}: dimensions: {err}")
                continue
            ours = mine.get(theirs["name"])
            plain = {k: v for k, v in theirs.items() if k != "description"}
            if ours is None:
                problems.append(
                    f"{where}: dimension {theirs['name']!r} is not declared on registry {self.name!r}"
                )
            elif plain != {k: v for k, v in ours.items() if k != "description"}:
                problems.append(
                    f"{where}: the file declares {plain}, registry {self.name!r} has {ours}"
                )
        return problems

    def _group_problems(self, declared: Any, where: str) -> list[str]:
        """How a collection's "groups" member disagrees with this Registry; the
        titles are for people, so they may differ."""
        if declared is None:
            return []
        if not isinstance(declared, Mapping):
            return [f"{where}: groups: it maps each prefix to a title"]
        problems = []
        for prefix in declared:
            if prefix not in self._groups:
                problems.append(
                    f"{where}: group {prefix!r} is not declared on registry {self.name!r}"
                )
        return problems

    def _add(self, rule: Any, source: str) -> None:
        """Registry.add; source names a record's file ("python" from Python)."""
        if isinstance(rule, ComputedRule):
            form, get = "computed", rule.meta.get
            scope = Scope(
                get("space"),
                time_of(get("time")),
                get("dimensions", {}),
                get("edge", False),
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
        group = split_code(code)[0]
        if self._groups and group not in self._groups:
            raise UnknownNameError(
                f"{code}: undeclared group {group!r}; declared: {list(self._groups)}"
            )
        compiled = self._compile(scope, _strings(get("requires", ())), code)
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

    # ---- describing --------------------------------------------------------------
    def values(self, name: str) -> list[Any]:
        """Every distinct value the rules give on one declared dimension, as they
        give it and in the order the rules were added. A list means any of its
        items, so a list is split into its items: ["glorys", "era5*"] gives
        "glorys" and "era5*"."""
        self._dimension(name)  # an undeclared name raises UnknownNameError
        found: list[Any] = []
        for entry in self._active():
            given = entry.rule.scope.dimensions.get(name)
            if given is None:
                continue
            items = given if isinstance(given, (list, tuple)) else [given]
            found += [item for item in items if item not in found]
        return found

    def describe(self) -> dict[str, Any]:
        """What this Registry can answer, as a JSON-ready dict: its groups and
        its declared dimensions as a rule file gives them, the values its rules
        give on each dimension (values()), and each rule's code, title and level.
        Space and time are always there and are not listed."""
        declared = list(self._dimensions.items())[2:]
        rules = []
        for entry in self._active():
            rule = entry.rule
            outcome = rule if isinstance(rule, Outcome) else rule.outcome
            rules.append(
                {
                    "code": rule.code,
                    "title": outcome.title,
                    "level": logging.getLevelName(outcome.level).lower(),
                    "computed": entry.form != "record",
                }
            )
        return {
            "name": self.name,
            "groups": dict(self._groups),
            "dimensions": [describe_dimension(d) for _, d in declared],
            "values": {name: _jsonable(self.values(name)) for name, _ in declared},
            "rules": rules,
        }

    # ---- writing ------------------------------------------------------------------
    def to_collection(self) -> dict[str, Any]:
        """This Registry as a rule file, a JSON-ready FeatureCollection: the
        file format it needs, its groups, its declared dimensions and a record
        for each static rule. Computed rules are code, so they are left out;
        describe() lists them."""
        collection: dict[str, Any] = {"type": "FeatureCollection", "queryearth": FORMAT}
        if self._groups:
            collection["groups"] = dict(self._groups)
        declared = list(self._dimensions.values())[2:]
        collection["dimensions"] = [describe_dimension(d) for d in declared]
        collection["features"] = [
            e.rule.to_feature() for e in self._entries if e.form == "record"
        ]
        return collection

    def to_file(self, path: str | os.PathLike[str]) -> None:
        """Write to_collection() to a rule file that from_file() reads back."""
        text = json.dumps(self.to_collection(), indent=2, ensure_ascii=False)
        Path(path).write_text(text + "\n", encoding="utf-8")

    # ---- names --------------------------------------------------------------------
    def _dimension(self, name: str) -> Any:
        """A declared dimension; space and time have their own fields instead."""
        if name in ("space", "time") or name not in self._dimensions:
            declared = list(self._dimensions)[2:]
            raise UnknownNameError(
                f"undeclared dimension {name!r}; declared: {declared}"
            )
        return self._dimensions[name]

    def _compile(
        self, scope: Scope, requires: tuple[str, ...], code: str
    ) -> CompiledScope:
        space = scope.space
        if space is not None and space.kind != "polygon":
            raise ValueError(f"{code}: a rule space is a polygon, not a point")
        values = {
            k: v for k, v in (("space", space), ("time", scope.time)) if v is not None
        }
        if scope.edge:
            values["space"] = Edge(space)
        for name, value in scope.dimensions.items():
            try:
                values[name] = self._dimension(name).parse_rule(value)
            except ValueError as err:
                raise ValueError(f"{code}: {name}: {err}") from err
        return CompiledScope(values, requires)

    def _parse_query(self, query: Query) -> dict[str, Any]:
        """The query's values, parsed by their dimensions."""
        if self._last[0] is query:
            return self._last[1]
        parsed = {
            k: v
            for k, v in (("space", query.space), ("time", query.time))
            if v is not None
        }
        for name, value in query.dimensions.items():
            parsed[name] = self._dimension(name).parse_query(value)
        self._last = (query, parsed)
        return parsed

    # ---- queries ------------------------------------------------------------------
    def query(self, query: Query | None = None, /, **fields: Any) -> list[Finding]:
        """Findings for one query, sorted by level, changes, then code.

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
                for name, dimension in self._dimensions.items()
                if _overrides(dimension, "build")
                and not _overrides(dimension, "comparable")
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
            if isinstance(space, Edge):
                continue  # a point has no edge
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
    """By level (highest first), those without changes first, then code."""
    return sorted(findings, key=lambda f: (-f.level, bool(f.changes), f.code))


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


def _overrides(dimension: Dimension, member: str) -> bool:
    """Whether a dimension's class replaces one of Dimension's default members."""
    return getattr(type(dimension), member) is not getattr(Dimension, member)
