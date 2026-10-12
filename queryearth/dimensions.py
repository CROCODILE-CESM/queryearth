"""Dimension plugins: every kind of scope other than space and time (section 4.13).

A plugin decides only whether one rule value meets one query value; the Index
does everything else (conditional findings, unknown names, requests, sorting).
Axis (numeric ranges), Labels (facets matched by glob patterns) and Versions
(OSV-style version ranges) are the built-in plugins, and a user plugin
implements the same four members.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from fnmatch import fnmatchcase
from typing import Any, ClassVar, Protocol, runtime_checkable

import numpy as np

from queryearth.model import AxisOverlap

__all__ = [
    "Axis",
    "DimMatch",
    "Dimension",
    "Labels",
    "Patterns",
    "Prefilter",
    "VersionRange",
    "Versions",
]


@dataclass(frozen=True)
class DimMatch:
    """How one rule value met one query value on one dimension."""

    overlap: Any = None  # dimension-specific; serialised with the plugin's to_json
    fraction: float | None = None  # share of the query's value covered, if measurable


@runtime_checkable
class Dimension(Protocol):
    """One kind of scope, declared on an Index under a unique name.

    Optional members, looked up with getattr: comparable(rule, query) -> bool
    (False makes the finding conditional on the dimension); build(pairs) ->
    Prefilter over the (position, rule value) pairs of the rules that constrain
    it; to_json(overlap) for Finding.to_dict(); late = True to run after the
    exact spatial test.
    """

    name: str  # key in scopes, queries, records and conditional_on
    schema: Mapping[str, Any]  # JSON Schema for the rule-side value in records

    def parse_rule(self, value: Any) -> Any: ...  # at load; ValueError if invalid

    def parse_query(self, value: Any) -> Any: ...  # at query time; ValueError

    def match(self, rule: Any, query: Any) -> DimMatch | None: ...  # None: no overlap


class Prefilter(Protocol):
    """Narrows the rules before match() runs; may return extra positions."""

    def candidates(self, query: Any) -> set[int]: ...


def _number(value: Any, what: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float, np.number)):
        raise ValueError(f"{what} must be a number, not {value!r}")
    number = float(value)
    if math.isnan(number):
        raise ValueError(f"{what} is not a number")
    return number


def _string_list(value: Any, what: str) -> tuple[str, ...]:
    if isinstance(value, str):
        value = [value]  # in Python a bare string is a one-item list
    if isinstance(value, Mapping) or not isinstance(value, Iterable):
        raise ValueError(f"{what} must be a list of strings, not {value!r}")
    items = tuple(value)
    if not items or not all(isinstance(v, str) and v for v in items):
        raise ValueError(f"{what} must be a non-empty list of non-empty strings")
    return items


# ---- Axis: a named ordered dimension in one unit ----------------------------------
_AXIS_SCHEMA: Mapping[str, Any] = {
    "type": "object",
    "properties": {
        "gt": {"type": "number"},
        "ge": {"type": "number"},
        "lt": {"type": "number"},
        "le": {"type": "number"},
        "unit": {"type": "string", "minLength": 1},
    },
    "additionalProperties": False,
    "anyOf": [
        {"required": ["gt"]},
        {"required": ["ge"]},
        {"required": ["lt"]},
        {"required": ["le"]},
    ],
    "not": {"anyOf": [{"required": ["gt", "ge"]}, {"required": ["lt", "le"]}]},
}


def axis_intersection(rule: AxisOverlap, lo: float, hi: float) -> AxisOverlap | None:
    """The intersection of a rule interval with the closed range [lo, hi]."""
    start = max(rule.lo, lo)
    end = min(rule.hi, hi)
    start_closed = rule.lo_closed if rule.lo >= lo else True
    end_closed = rule.hi_closed if rule.hi <= hi else True
    if start < end or (start == end and start_closed and end_closed):
        return AxisOverlap(start, end, start_closed, end_closed)
    return None


@dataclass(frozen=True)
class Axis:
    """A named, ordered, numeric dimension with exactly one unit.

    A rule states {gt, ge, lt, le, unit}; a query gives a number or a closed
    range (lo, hi). The overlap is the intersection, keeping open ends.
    """

    name: str
    unit: str
    description: str = ""
    schema: ClassVar[Mapping[str, Any]] = _AXIS_SCHEMA

    def __post_init__(self) -> None:
        if not isinstance(self.unit, str) or not self.unit:
            raise ValueError(f"axis {self.name!r} needs a unit")

    def parse_rule(self, value: Any) -> AxisOverlap:
        if not isinstance(value, Mapping):
            raise ValueError(f"an axis bound is a mapping of gt, ge, lt, le, unit")
        unknown = set(value) - {"gt", "ge", "lt", "le", "unit"}
        if unknown:
            raise ValueError(f"unknown axis bound keys {sorted(unknown)}")
        if {"gt", "ge"} <= set(value) or {"lt", "le"} <= set(value):
            raise ValueError("give at most one of gt and ge, and one of lt and le")
        if not set(value) & {"gt", "ge", "lt", "le"}:
            raise ValueError("an axis bound needs at least one of gt, ge, lt, le")
        unit = value.get("unit")
        if unit is not None and unit != self.unit:
            raise ValueError(
                f"unit {unit!r} does not match the unit {self.unit!r} of axis "
                f"{self.name!r}; the core does no unit conversion"
            )
        lo, lo_closed, hi, hi_closed = -math.inf, False, math.inf, False
        if "gt" in value:
            lo = _number(value["gt"], "gt")
        if "ge" in value:
            lo, lo_closed = _number(value["ge"], "ge"), True
        if "lt" in value:
            hi = _number(value["lt"], "lt")
        if "le" in value:
            hi, hi_closed = _number(value["le"], "le"), True
        if lo > hi or (lo == hi and not (lo_closed and hi_closed)):
            raise ValueError(f"the axis bounds {dict(value)} leave no value")
        return AxisOverlap(lo, hi, lo_closed, hi_closed)

    def parse_query(self, value: Any) -> tuple[float, float]:
        if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
            v = _number(value, f"axis {self.name!r}")
            lo, hi = v, v
        elif len(value) != 2:
            raise ValueError(f"axis {self.name!r} takes a number or a range (lo, hi)")
        else:
            lo, hi = (_number(v, f"axis {self.name!r}") for v in value)
        if not (math.isfinite(lo) and math.isfinite(hi)) or lo > hi:
            raise ValueError(f"axis {self.name!r} needs a finite range lo <= hi")
        return lo, hi

    def match(self, rule: AxisOverlap, query: tuple[float, float]) -> DimMatch | None:
        lo, hi = query
        found = axis_intersection(rule, lo, hi)
        if found is None:
            return None
        fraction = 1.0 if hi == lo else (found.hi - found.lo) / (hi - lo)
        return DimMatch(found, fraction)

    def extent(self, rule: AxisOverlap) -> AxisOverlap:
        """The rule's own interval, reported when the query omits the axis."""
        return rule


# ---- Labels: a facet matched by case-sensitive fnmatch globs ----------------------
_PATTERNS = {
    "type": "array",
    "minItems": 1,
    "items": {"type": "string", "minLength": 1},
}
_LABELS_SCHEMA: Mapping[str, Any] = {
    "oneOf": [
        _PATTERNS,
        {
            "type": "object",
            "properties": {"any_of": _PATTERNS, "none_of": _PATTERNS},
            "additionalProperties": False,
            "minProperties": 1,
        },
    ]
}
_GLOB = frozenset("*?[")


def is_glob(pattern: str) -> bool:
    """Whether a facet pattern uses fnmatch syntax rather than a literal value."""
    return not _GLOB.isdisjoint(pattern)


@dataclass(frozen=True)
class Patterns:
    """A parsed facet rule: values must match some any_of and no none_of."""

    any_of: tuple[str, ...] | None  # None: any value not excluded
    none_of: tuple[str, ...] = ()

    def admits(self, value: str) -> bool:
        if any(fnmatchcase(value, p) for p in self.none_of):
            return False
        return self.any_of is None or any(fnmatchcase(value, p) for p in self.any_of)


@dataclass(frozen=True)
class Labels:
    """A categorical facet: rule patterns against query values (section 4.7)."""

    name: str
    description: str = ""
    schema: ClassVar[Mapping[str, Any]] = _LABELS_SCHEMA

    def parse_rule(self, value: Any) -> Patterns:
        if isinstance(value, Patterns):
            return value
        if not isinstance(value, Mapping):
            return Patterns(_string_list(value, f"facet {self.name!r}"))
        unknown = set(value) - {"any_of", "none_of"}
        if unknown or not value:
            raise ValueError(
                f"facet {self.name!r} takes a list of patterns or "
                f"{{'any_of': [...], 'none_of': [...]}}, got {dict(value)!r}"
            )
        any_of = None
        if "any_of" in value:
            any_of = _string_list(value["any_of"], f"facet {self.name!r} any_of")
        none_of = ()
        if "none_of" in value:
            none_of = _string_list(value["none_of"], f"facet {self.name!r} none_of")
        return Patterns(any_of, none_of)

    def parse_query(self, value: Any) -> tuple[str, ...]:
        return tuple(dict.fromkeys(_string_list(value, f"facet {self.name!r}")))

    def match(self, rule: Patterns, query: tuple[str, ...]) -> DimMatch | None:
        hits = tuple(v for v in query if rule.admits(v))
        if not hits:
            return None
        return DimMatch(hits, len(hits) / len(query))


# ---- Versions: OSV-style ranges ----------------------------------------------------
_DOTTED = re.compile(r"[0-9]+(?:\.[0-9]+)*")
_RANGE = {
    "type": "object",
    "properties": {
        "introduced": {"type": "string", "minLength": 1},
        "fixed": {"type": "string", "minLength": 1},
        "last_affected": {"type": "string", "minLength": 1},
        "versions": {
            "type": "array",
            "minItems": 1,
            "items": {"type": "string", "minLength": 1},
        },
    },
    "additionalProperties": False,
    "minProperties": 1,
    "not": {"required": ["fixed", "last_affected"]},
}
_VERSIONS_SCHEMA: Mapping[str, Any] = {
    "oneOf": [_RANGE, {"type": "array", "minItems": 1, "items": _RANGE}]
}


def dotted(version: str) -> tuple[int, ...] | None:
    """The integers of a dotted-integer version, or None for any other string."""
    if not isinstance(version, str) or not _DOTTED.fullmatch(version):
        return None
    return tuple(int(part) for part in version.split("."))


def compare_versions(a: tuple[int, ...], b: tuple[int, ...]) -> int:
    """-1, 0 or 1, comparing dotted integers padded with zeros: 4.07 == 4.7.0."""
    size = max(len(a), len(b))
    a = a + (0,) * (size - len(a))
    b = b + (0,) * (size - len(b))
    return (a > b) - (a < b)


@dataclass(frozen=True)
class VersionRange:
    """One OSV-style range: introduced (in), fixed (out) or last_affected (in),
    plus exact versions. Bounds are dotted integers; anything else goes in
    versions, where it matches literally."""

    introduced: str | None = None
    fixed: str | None = None
    last_affected: str | None = None
    versions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.fixed is not None and self.last_affected is not None:
            raise ValueError("a version range has fixed or last_affected, not both")
        for name in ("introduced", "fixed", "last_affected"):
            bound = getattr(self, name)
            if bound is not None and dotted(bound) is None:
                raise ValueError(
                    f"version bound {name}={bound!r} is not a dotted integer; "
                    "list other versions in 'versions'"
                )
        object.__setattr__(self, "versions", tuple(self.versions))
        if not all(isinstance(v, str) and v for v in self.versions):
            raise ValueError("versions must be non-empty strings")
        if not self.bounded and not self.versions:
            raise ValueError("a version range needs at least one field")

    @property
    def bounded(self) -> bool:
        return (self.introduced, self.fixed, self.last_affected) != (None, None, None)

    def contains(self, version: str) -> bool:
        number = dotted(version)
        for exact in self.versions:
            other = dotted(exact)
            if exact == version or (
                number is not None
                and other is not None
                and compare_versions(number, other) == 0
            ):
                return True
        if not self.bounded or number is None:
            return False
        if self.introduced is not None:
            if compare_versions(number, dotted(self.introduced)) < 0:
                return False
        if self.fixed is not None:
            if compare_versions(number, dotted(self.fixed)) >= 0:
                return False
        if self.last_affected is not None:
            if compare_versions(number, dotted(self.last_affected)) > 0:
                return False
        return True


@dataclass(frozen=True)
class Versions:
    """The version facet: a union of OSV-style ranges (section 4.8)."""

    name: str = "version"
    schema: ClassVar[Mapping[str, Any]] = _VERSIONS_SCHEMA

    def parse_rule(self, value: Any) -> tuple[VersionRange, ...]:
        if isinstance(value, Mapping):
            value = [value]
        if isinstance(value, str) or not isinstance(value, Iterable):
            raise ValueError(
                f"facet {self.name!r} takes a version range or a list of them, "
                f"not {value!r}"
            )
        ranges = []
        for item in value:
            if isinstance(item, VersionRange):
                ranges.append(item)
                continue
            if not isinstance(item, Mapping):
                raise ValueError(f"a version range is a mapping, not {item!r}")
            unknown = set(item) - {"introduced", "fixed", "last_affected", "versions"}
            if unknown:
                raise ValueError(f"unknown version range keys {sorted(unknown)}")
            fields = dict(item)
            if "versions" in fields:
                fields["versions"] = _string_list(fields["versions"], "versions")
            ranges.append(VersionRange(**fields))
        if not ranges:
            raise ValueError(f"facet {self.name!r} needs at least one range")
        return tuple(ranges)

    def parse_query(self, value: Any) -> tuple[str, ...]:
        return tuple(dict.fromkeys(_string_list(value, f"facet {self.name!r}")))

    def match(
        self, rule: tuple[VersionRange, ...], query: tuple[str, ...]
    ) -> DimMatch | None:
        hits = tuple(v for v in query if any(r.contains(v) for r in rule))
        if not hits:
            return None
        return DimMatch(hits, len(hits) / len(query))
