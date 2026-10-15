"""The Registry: the dimensions, the rules, the query, and rule files.

A rule file is a GeoJSON FeatureCollection with one Feature per rule, in the
form Rule.to_feature() writes and Rule.from_feature() reads.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from queryearth.dimensions import Dimension, SpaceDimension, TimeDimension, applies
from queryearth.rules import LEVELS, Rule

__all__ = ["DuplicateCodeError", "Registry"]

# The release that last changed the rule file format. to_file() writes it in the
# "queryearth" member, and from_file() refuses a file that needs a later release.
FORMAT = "0.7"
# A list of numbers, such as a point, as json.dumps(indent=2) spreads it over
# lines. A JSON string never holds a newline, so only real lists match.
_NUMBERS = re.compile(
    r"\[\n\s*(-?[0-9][0-9.eE+-]*(?:,\n\s*-?[0-9][0-9.eE+-]*)*)\n\s*\]"
)


class DuplicateCodeError(ValueError):
    """A code the Registry already holds was added again."""


class Registry:
    """The rules, and the dimensions their scopes use; answers queries.

    Every Registry has space and time. dimensions declares the others, such as
    Axis("resolution", "km"), Labels("product") or one of your own; a
    dimension's name is its key in scopes, queries and rule files.
    """

    def __init__(self, dimensions: Iterable[Dimension] = ()) -> None:
        self.dimensions: dict[str, Dimension] = {}
        for dimension in (SpaceDimension(), TimeDimension(), *dimensions):
            if not isinstance(dimension, Dimension):
                raise TypeError(f"{dimension!r} does not subclass qe.Dimension")
            if dimension.name in self.dimensions:
                raise ValueError(f"dimension {dimension.name!r} is declared twice")
            self.dimensions[dimension.name] = dimension
        self._rules: dict[str, tuple[Rule, dict[str, Any]]] = {}  # parsed scopes

    @property
    def rules(self) -> list[Rule]:
        """Every rule, in the order added."""
        return [rule for rule, _ in self._rules.values()]

    def _dimension(self, name: str) -> Dimension:
        if name not in self.dimensions:
            raise ValueError(
                f"undeclared dimension {name!r}; this Registry has {list(self.dimensions)}"
            )
        return self.dimensions[name]

    def add(self, rule: Rule) -> None:
        """Add a rule; Rule.from_feature() makes one from a GeoJSON Feature.

        Each scope value is parsed by its dimension. A name the Registry does
        not have is refused, so a misspelt one never matches by accident, and
        a code already here raises DuplicateCodeError.
        """
        if not isinstance(rule, Rule):
            raise TypeError(f"cannot add {rule!r}: not a Rule")
        if rule.code in self._rules:
            raise DuplicateCodeError(f"{rule.code}: this code is already a rule here")
        values = {}
        for name, value in rule.scope.items():
            if value is not None:
                try:
                    values[name] = self._dimension(name).parse_rule(value)
                except (ValueError, TypeError) as err:
                    err.args = (f"{rule.code}: {name}: {err}",)
                    raise
        self._rules[rule.code] = (rule, values)

    def query(self, **values: Any) -> list[Rule]:
        """The rules that apply to a query, highest level first, then by code.

        values gives the query's value on any of the dimensions, by name, such
        as space=sp.box(-60, 30, -50, 40), time=qe.interval("2020-01-01",
        "2020-12-31") or resolution=8; None leaves a dimension out. applies()
        says what "apply" means.
        """
        query = {
            name: self._dimension(name).parse_query(value)
            for name, value in values.items()
            if value is not None
        }
        found = [
            r
            for r, scope in self._rules.values()
            if applies(self.dimensions, scope, query)
        ]
        return sorted(found, key=lambda rule: (LEVELS.index(rule.level), rule.code))

    # ---- rule files ---------------------------------------------------------------
    def to_file(self, path: str | os.PathLike[str]) -> None:
        """Write every rule to a rule file that from_file() reads back, as
        indented GeoJSON with each point on one line."""
        features = [rule.to_feature() for rule in self.rules]
        data = {"type": "FeatureCollection", "queryearth": FORMAT, "features": features}
        text = json.dumps(data, indent=2, ensure_ascii=False)
        text = _NUMBERS.sub(lambda m: "[" + re.sub(r",\n\s*", ", ", m[1]) + "]", text)
        Path(path).write_text(text + "\n", encoding="utf-8")

    @classmethod
    def from_file(
        cls, *paths: str | os.PathLike[str], dimensions: Iterable[Dimension] = ()
    ) -> Registry:
        """A Registry with the rules of one or more rule files.

        dimensions declares the dimensions other than space and time, as
        Registry() does; a rule that uses any other is refused. Codes must be
        unique across the files. Raises ValueError naming the file, the
        feature's position and its code; nothing is returned unless every
        rule was read.
        """
        registry = cls(dimensions)
        for path in paths:
            where = f"{Path(path).name}: "
            try:
                data = json.loads(Path(path).read_text(encoding="utf-8"))
                if (
                    not isinstance(data, Mapping)
                    or data.get("type") != "FeatureCollection"
                ):
                    raise ValueError("not a GeoJSON FeatureCollection")
                _check_format(data.get("queryearth", FORMAT))
                for i, feature in enumerate(data.get("features", [])):
                    where = f"{Path(path).name}: feature {i}: "
                    registry.add(Rule.from_feature(feature))
            except (ValueError, TypeError) as err:
                err.args = (where + str(err),)
                raise
        return registry


def _check_format(given: Any) -> None:
    """Refuse a file whose "queryearth" member names a later format than FORMAT."""
    found = re.fullmatch(r"([0-9]+)\.([0-9]+)(\.[0-9]+)?", str(given))
    if found is None:
        raise ValueError(f'"queryearth" is a release such as "{FORMAT}", not {given!r}')
    if (int(found[1]), int(found[2])) > tuple(map(int, FORMAT.split("."))):
        raise ValueError(
            f"this file needs queryearth {given} or later, and this queryearth "
            f"reads rule files up to {FORMAT}; upgrade queryearth to read it"
        )
