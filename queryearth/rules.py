"""Rules: what a rule says, where, when and for what it applies, and its
GeoJSON Feature in a rule file."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from queryearth.space import Space
from queryearth.time import Interval

__all__ = ["LEVELS", "Rule"]

LEVELS = ("error", "warning", "info")  # highest first, the order of query results
OWN = frozenset({"code", "title", "message", "level", "dimensions"})
FEATURE_KEYS = frozenset({"type", "id", "geometry", "time", "properties", "bbox"})
# Record properties that changed which rules apply in queryearth 0.6. They are
# refused rather than passed through, so that a rule from an older file never
# applies more widely than its author meant (docs/growth.md).
RETIRED = frozenset(
    "box edge periods recurrence time_start time_end withdrawn supersedes".split()
)


@dataclass(frozen=True)
class Rule:
    """A rule: a code, a title, a message, a level and a scope.

    code is unique, and may be a slash path such as "REGION/ITF/ITF001": its
    category is the path before the last slash. level is "info", "warning"
    (the default) or "error". scope maps each dimension the rule constrains to
    its value, such as {"space": sp.box(-98, 18, -80, 31), "time":
    qe.interval("2000-01-01", ".."), "resolution": {"lt": 8}}; a dimension it
    leaves out matches anything, and the Registry checks each value with its
    dimension when the rule is added. properties holds whatever else the rule
    carries, such as an instruction or references. The rule keeps every value
    as given, and to_feature() writes them back unchanged.
    """

    code: str
    title: str
    message: str
    level: str = "warning"
    scope: Mapping[str, Any] = field(default_factory=dict)
    properties: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.code, str) or "" in self.code.split("/"):
            raise ValueError(
                f"a code is a name, or a path such as 'REGION/ITF/ITF001', not "
                f"{self.code!r}"
            )
        for name in ("title", "message"):
            if not isinstance(getattr(self, name), str):
                raise TypeError(f"{self.code}: {name} is a string")
        if self.level not in LEVELS:
            raise ValueError(
                f"{self.code}: level is one of {LEVELS}, not {self.level!r}"
            )
        for name in ("scope", "properties"):
            value = getattr(self, name)
            if not isinstance(value, Mapping) or not all(
                isinstance(k, str) for k in value
            ):
                raise TypeError(f"{self.code}: {name} maps names to values")
            object.__setattr__(self, name, dict(value))
        if own := sorted(set(self.properties) & OWN):
            raise ValueError(
                f"{self.code}: {own} are fields of the rule, not properties"
            )
        if "category" in self.properties:
            raise ValueError(
                f"{self.code}: a rule's category is the path of its code, such as "
                "REGION/ITF in REGION/ITF/ITF001, not a property"
            )
        if retired := sorted(set(self.properties) & RETIRED):
            raise ValueError(
                f"{self.code}: {retired} changed which rules apply in queryearth "
                "0.6, and this version leaves them out (docs/growth.md)"
            )

    @property
    def category(self) -> str | None:
        """The path before the code's last slash, such as "REGION/ITF" for
        "REGION/ITF/ITF001"; None for a code without one."""
        return self.code.rpartition("/")[0] or None

    @classmethod
    def from_feature(cls, feature: Mapping[str, Any]) -> Rule:
        """A rule from the GeoJSON Feature a rule file holds: its geometry is the
        rule's space (null for none) and its JSON-FG time member the rule's
        time; its properties hold the code, title, message, an optional level,
        "dimensions", the value on each other dimension by name, and anything
        else, which is kept as given. A Registry checks the values when the
        rule is added, since it knows the dimensions."""
        props = feature.get("properties") if isinstance(feature, Mapping) else None
        if not isinstance(props, Mapping) or feature.get("type") != "Feature":
            raise ValueError("a rule is a GeoJSON Feature with properties")
        code = props.get("code", "a rule")
        if unknown := sorted(set(feature) - FEATURE_KEYS):
            raise ValueError(f"{code}: unknown Feature members {unknown}")
        if not {"code", "title", "message"} <= set(props) or "geometry" not in feature:
            raise ValueError(
                f"{code}: a rule needs a code, a title, a message and a "
                "geometry (null for none)"
            )
        scope = props.get("dimensions", {})
        if not isinstance(scope, Mapping) or {"space", "time"} & set(scope):
            raise ValueError(
                f"{code}: dimensions maps names to values; space and time go in the "
                "geometry and time members"
            )
        scope = dict(scope)
        for name, member in (("space", "geometry"), ("time", "time")):
            if feature.get(member) is not None:
                scope[name] = feature[member]
        fields = {
            k: props[k] for k in ("code", "title", "message", "level") if k in props
        }
        others = {
            k: v for k, v in props.items() if k not in fields and k != "dimensions"
        }
        return cls(**fields, scope=scope, properties=others)

    def to_feature(self) -> dict[str, Any]:
        """The GeoJSON Feature a rule file holds, which from_feature() reads
        back: the space as its geometry, the time as its JSON-FG time member,
        and every other scope value in "dimensions", each as given."""
        scope = {k: v for k, v in self.scope.items() if v is not None}
        space, time = scope.pop("space", None), scope.pop("time", None)
        props = {"code": self.code, "title": self.title, "message": self.message}
        props["level"] = self.level
        if scope:
            props["dimensions"] = scope
        return {
            "type": "Feature",
            "id": self.code,
            "geometry": space.to_json() if isinstance(space, Space) else space,
            "time": time.to_json() if isinstance(time, Interval) else time,
            "properties": props | self.properties,
        }
