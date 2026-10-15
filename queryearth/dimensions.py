"""Dimensions: what a rule's scope and a query give values on, and how they match.

Every dimension subclasses Dimension and implements its three methods: the base
dimensions space, time and Axis, the Labels extension that comes with them, and
any dimension you write. Space and time are on every Registry; the others are
declared on it. applies() is the matching rule, in one place.
"""

from __future__ import annotations

import abc
import math
import numbers
from collections.abc import Mapping
from dataclasses import dataclass
from fnmatch import fnmatchcase
from typing import Any

from queryearth import space as sp
from queryearth.time import Interval, interval

__all__ = ["Axis", "Dimension", "Labels", "SpaceDimension", "TimeDimension", "applies"]


class Dimension(abc.ABC):
    """One kind of scope, such as space, time or grid resolution.

    A subclass sets name, the key that scopes, queries and rule files use for
    it, and implements the three methods below; Python refuses to create one
    that leaves any out. The Registry calls them and does the rest: it refuses
    undeclared names, and applies() decides whether a rule applies. A value
    can be anything the dimension parses, such as a number, a range, a shape
    or a mapping of several fields; a dimension sees only its own value. A
    rule file holds each value as the rule gives it, so a value given in
    Python is plain JSON, apart from space and time.
    """

    name: str

    @abc.abstractmethod
    def parse_rule(self, value: Any) -> Any:
        """A rule's value, given in Python or read from a rule file's JSON, in
        the form matches() takes; ValueError if it is not valid."""

    @abc.abstractmethod
    def parse_query(self, value: Any) -> Any:
        """A query's value, in the form matches() takes; ValueError if it is
        not valid."""

    @abc.abstractmethod
    def matches(self, rule: Any, query: Any) -> bool:
        """Whether a parsed rule value and a parsed query value share at least
        one value, such as a point, an instant or a number."""


def applies(
    dimensions: Mapping[str, Dimension],
    scope: Mapping[str, Any],
    query: Mapping[str, Any],
) -> bool:
    """Whether a rule applies to a query.

    scope and query map dimension names to values parsed by those dimensions.
    A rule applies when, on every dimension its scope constrains, the query
    gives a value and the dimension's matches() says the two share at least
    one value. A dimension the rule leaves out matches anything. A dimension
    the rule constrains and the query leaves out does not match, since the
    query gives no value to share.
    """
    return all(
        name in query and dimensions[name].matches(value, query[name])
        for name, value in scope.items()
    )


class SpaceDimension(Dimension):
    """Space: a rule gives a polygon, a query a point or a polygon.

    In a rule file, a rule's space is the Feature's GeoJSON geometry.
    """

    name = "space"

    def parse_rule(self, value: Any) -> sp.Space:
        if isinstance(value, sp.Space) and value.kind != "polygon":
            raise ValueError("a rule's space is a polygon, not a point")
        return value if isinstance(value, sp.Space) else sp.polygon(value)

    def parse_query(self, value: Any) -> sp.Space:
        if not isinstance(value, sp.Space):
            raise ValueError(
                f"a query's space is a point or polygon from queryearth.space, "
                f"such as sp.box(-60, 30, -50, 40), not {value!r}"
            )
        return value

    def matches(self, rule: sp.Space, query: sp.Space) -> bool:
        return sp.meets(rule, query)


class TimeDimension(Dimension):
    """Time: a rule and a query each give an interval, made by interval().

    In a rule file, a rule's time is the Feature's JSON-FG time member,
    {"interval": [start, end]}, with ".." for an open end.
    """

    name = "time"

    def parse_rule(self, value: Any) -> Interval:
        if isinstance(value, Interval):
            return value
        pair = value.get("interval") if isinstance(value, Mapping) else None
        if not isinstance(pair, list) or len(pair) != 2 or len(value) != 1:
            raise ValueError(
                f'a time is qe.interval(start, end), or {{"interval": [start, end]}} '
                f"in a rule file, not {value!r}"
            )
        return interval(*pair)

    parse_query = parse_rule

    def matches(self, rule: Interval, query: Interval) -> bool:
        return rule.meets(query)


_BOUNDS = {"gt", "ge", "lt", "le"}


def _number(value: Any, what: str) -> int | float:
    if isinstance(value, bool) or not isinstance(value, numbers.Real):
        raise ValueError(f"{what} must be a number, not {value!r}")
    if math.isnan(value):
        raise ValueError(f"{what} is not a number")
    return value if type(value) is int else float(value)


@dataclass(frozen=True)
class Axis(Dimension):
    """A named numeric dimension in one unit, such as grid resolution in km.

    A rule gives a range with any of gt, ge, lt and le, and optionally the
    unit, such as {"lt": 8} or {"gt": 2, "le": 10, "unit": "km"}; a query gives
    a number or a closed range (lo, hi). They match when they share a number.
    queryearth converts no units, so a rule that gives another unit is refused.
    """

    name: str
    unit: str

    def __post_init__(self) -> None:
        if not isinstance(self.unit, str) or not self.unit:
            raise ValueError(f"axis {self.name!r} needs a unit, such as 'km'")

    def parse_rule(self, value: Any) -> tuple[float, bool, float, bool]:
        """The range as (lo, lo_closed, hi, hi_closed); a missing end is infinite."""
        if not isinstance(value, Mapping) or set(value) - {*_BOUNDS, "unit"}:
            raise ValueError(
                f"axis {self.name!r} takes a range of gt, ge, lt, le and unit, "
                f"such as {{'lt': 8}}, not {value!r}"
            )
        if {"gt", "ge"} <= set(value) or {"lt", "le"} <= set(value):
            raise ValueError("give at most one of gt and ge, and one of lt and le")
        if not set(value) & _BOUNDS:
            raise ValueError("a range needs at least one of gt, ge, lt and le")
        if value.get("unit", self.unit) != self.unit:
            raise ValueError(
                f"unit {value['unit']!r} is not the unit {self.unit!r} of axis "
                f"{self.name!r}; queryearth converts no units"
            )
        lo = next((_number(value[k], k) for k in ("gt", "ge") if k in value), -math.inf)
        hi = next((_number(value[k], k) for k in ("lt", "le") if k in value), math.inf)
        lo_closed, hi_closed = "ge" in value, "le" in value
        if lo > hi or (lo == hi and not (lo_closed and hi_closed)):
            raise ValueError(f"the range {dict(value)} holds no number")
        return lo, lo_closed, hi, hi_closed

    def parse_query(self, value: Any) -> tuple[float, float]:
        pair = isinstance(value, (list, tuple)) and len(value) == 2
        lo, hi = (
            _number(v, f"axis {self.name!r}") for v in (value if pair else [value] * 2)
        )
        if not (math.isfinite(lo) and math.isfinite(hi)) or lo > hi:
            raise ValueError(f"axis {self.name!r} takes a number or a range lo <= hi")
        return lo, hi

    def matches(
        self, rule: tuple[float, bool, float, bool], query: tuple[float, float]
    ) -> bool:
        lo, lo_closed, hi, hi_closed = rule
        a, b = query
        return (lo < b or (lo == b and lo_closed)) and (
            a < hi or (a == hi and hi_closed)
        )


@dataclass(frozen=True)
class Labels(Dimension):
    """Names, such as a forcing product or a model option.

    A rule gives a name or a list of names, which may use the wildcards * and
    ? (case-sensitive), such as ["jra", "era5*"]; a query gives a name or a
    list of names. They match when a query name matches one of the rule's.
    """

    name: str

    def parse_rule(self, value: Any) -> tuple[str, ...]:
        names = [value] if isinstance(value, str) else value
        if not isinstance(names, (list, tuple)) or not names:
            raise ValueError(f"labels {self.name!r} takes a name or a list of names")
        if not all(isinstance(n, str) and n for n in names):
            raise ValueError(f"labels {self.name!r} takes names, not {value!r}")
        return tuple(names)

    parse_query = parse_rule

    def matches(self, rule: tuple[str, ...], query: tuple[str, ...]) -> bool:
        return any(fnmatchcase(name, pattern) for pattern in rule for name in query)
