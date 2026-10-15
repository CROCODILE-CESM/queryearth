"""Rules: what a rule says, and where, when and for what it applies."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

__all__ = ["LEVELS", "Rule"]

LEVELS = ("error", "warning", "info")  # highest first, the order of query results
OWN = frozenset({"code", "title", "message", "level", "dimensions"})
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
    carries, such as an instruction or references; queryearth keeps it as given
    and writes it back to a rule file unchanged.
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
