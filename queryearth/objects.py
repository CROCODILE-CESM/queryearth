"""Core objects: outcomes, matches, findings, scopes, queries, and the error classes.

All are frozen dataclasses (design.md section 4.11). A time may be given as a
pair of wire strings, and is stored as a TimeSpec; a value on any other
dimension is kept as given, and the Registry parses it with its dimension.
Objects that hold mappings compare by value but are not hashable.
"""

from __future__ import annotations

import dataclasses
import logging
import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

import numpy as np

from queryearth.space import Space
from queryearth.time import Interval, TimeSpec, interval, parse_time

if TYPE_CHECKING:
    from queryearth.dimensions import DimMatch

__all__ = [
    "Action",
    "Change",
    "Confidence",
    "DuplicateCodeError",
    "Finding",
    "LoadError",
    "Match",
    "Outcome",
    "Query",
    "Scope",
    "Status",
    "UnknownNameError",
    "report",
]

Confidence = Literal["observed", "likely", "possible", "unknown"]  # CAP certainty
Action = Literal["can_be_used", "use_with_caution", "do_not_use", "replaced"]
Status = Literal["draft", "reviewed", "deprecated"]

CONFIDENCES = ("observed", "likely", "possible", "unknown")
ACTIONS = ("can_be_used", "use_with_caution", "do_not_use", "replaced")
STATUSES = ("draft", "reviewed", "deprecated")


def _set(obj: Any, name: str, value: Any) -> None:
    object.__setattr__(obj, name, value)


def level_of(value: Any) -> int:
    """A logging level from an int, such as logging.INFO, or a level name, any case."""
    if isinstance(value, str):
        value = logging.getLevelNamesMapping().get(value.upper(), value)
    if isinstance(value, (int, np.integer)) and not isinstance(value, bool):
        return int(value)
    raise ValueError(
        f"a level is a logging level such as logging.INFO or 'info', not {value!r}"
    )


def _choice(value: Any, allowed: Sequence[str], what: str) -> str:
    if value not in allowed:
        raise ValueError(f"{what} must be one of {list(allowed)}, not {value!r}")
    return value


def time_of(value: Any) -> TimeSpec | None:
    """A TimeSpec from itself, a JSON-FG time member, or a (start, end) pair.

    A member open at both ends means all time here, not an omitted time.
    """
    if value is None or isinstance(value, TimeSpec):
        return value
    if isinstance(value, Mapping):
        spec = parse_time(value)
        return spec if spec is not None else TimeSpec((Interval(None, None),))
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise TypeError(
            "a time is a TimeSpec, a JSON-FG time member or a (start, end) pair, "
            f"not {value!r}"
        )
    if len(value) != 2:
        raise ValueError(f"a time pair is (start, end), got {value!r}")
    return interval(value[0], value[1])


def _space_of(value: Any, what: str) -> Space | None:
    if value is not None and not isinstance(value, Space):
        raise TypeError(
            f"{what} is a Space from queryearth.space (or None), not "
            f"{type(value).__name__}"
        )
    return value


def _number(value: Any, what: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float, np.number)):
        raise TypeError(f"{what} must be a number, not {value!r}")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{what} must be finite, not {value!r}")
    return number


def _jsonable(value: Any) -> Any:
    """A JSON-ready copy: tuples become lists, infinities None, numpy plain."""
    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, (int, np.integer)):
        return int(value)
    if isinstance(value, (float, np.floating)):
        return float(value) if math.isfinite(value) else None
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, np.ndarray):
        return _jsonable(value.tolist())
    if callable(getattr(value, "to_dict", None)) and not isinstance(value, type):
        return _jsonable(value.to_dict())  # such as a DimMatch with a plugin's to_json
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {
            f.name: _jsonable(getattr(value, f.name)) for f in dataclasses.fields(value)
        }
    if isinstance(value, Mapping):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (set, frozenset)):
        items = [_jsonable(v) for v in value]
        try:
            return sorted(items)
        except TypeError:
            return items
    if isinstance(value, Iterable):
        return [_jsonable(v) for v in value]
    return str(value)


# ---- outcomes, matches, findings -----------------------------------------------
@dataclass(frozen=True)
class Change:
    """A structured change for the caller to apply; never interpreted here."""

    target: str
    key: str
    value: Any
    rationale: str = ""

    def __post_init__(self) -> None:
        for name in ("target", "key"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name):
                raise ValueError(f"a change's {name} is a non-empty string")
        if not isinstance(self.rationale, str):
            raise TypeError("a change's rationale is a string")


def change_of(value: Any) -> Change:
    """A Change from itself or a {target, key, value, rationale} mapping."""
    if isinstance(value, Change):
        return value
    if isinstance(value, Mapping):
        return Change(**value)
    raise TypeError(f"a change is a Change or a mapping, not {value!r}")


def _outcome_post_init(o: Any) -> None:
    if not isinstance(o.code, str) or not o.code:
        raise ValueError("a code is a non-empty string")
    for name in ("title", "message", "instruction"):
        if not isinstance(getattr(o, name), str):
            raise TypeError(f"{name} must be a string")
    _choice(o.confidence, CONFIDENCES, "confidence")
    if o.action is not None:
        _choice(o.action, ACTIONS, "action")
    _choice(o.status, STATUSES, "status")
    if isinstance(o.changes, (Change, Mapping)):
        raise TypeError("changes is a sequence of changes")
    _set(o, "changes", tuple(change_of(c) for c in o.changes))
    default = logging.INFO if o.changes else logging.WARNING
    _set(o, "level", default if o.level is None else level_of(o.level))
    minimum = _number(o.min_overlap, "min_overlap")
    if not 0.0 <= minimum <= 1.0:
        raise ValueError(f"min_overlap must lie in [0, 1], not {minimum}")
    _set(o, "min_overlap", minimum)
    for name in ("references", "evidence"):
        items = getattr(o, name)
        if isinstance(items, Mapping) or not all(isinstance(i, Mapping) for i in items):
            raise TypeError(f"{name} is a sequence of mappings")
        _set(o, name, tuple(dict(i) for i in items))


@dataclass(frozen=True, kw_only=True)
class Outcome:
    """What a rule says; shared by Rule and Finding."""

    code: str
    title: str
    message: str
    level: int | str | None = None  # a logging level; None: WARNING, INFO with changes
    confidence: Confidence = "unknown"
    action: Action | None = None
    instruction: str = ""
    changes: tuple[Change, ...] = ()
    min_overlap: float = 0.0  # a smaller area_fraction is too small to count
    status: Status = "draft"
    references: tuple[Mapping[str, str], ...] = ()
    evidence: tuple[Mapping[str, Any], ...] = ()

    def __post_init__(self) -> None:
        _outcome_post_init(self)


def _match_post_init(m: Any) -> None:
    pairs = tuple(tuple(p) for p in m.time_overlap)
    if not all(len(p) == 2 and all(isinstance(e, str) for e in p) for p in pairs):
        raise TypeError("time_overlap holds closed wire intervals (start, end)")
    _set(m, "time_overlap", pairs)
    _set(m, "dimensions", dict(m.dimensions))
    _set(m, "conditional_on", tuple(m.conditional_on))


@dataclass(frozen=True, kw_only=True)
class Match:
    """How a scope met a query.

    Space and time have their own fields; dimensions holds a DimMatch for each
    other dimension, by name. Measures of decided dimensions are filled; an
    undecided dimension is named in conditional_on and reports the rule's own
    extent or nothing (section 4.3).
    """

    area_fraction: float | None = None
    overlap_km2: float | None = None
    time_overlap: tuple[tuple[str, str], ...] = ()  # closed, wire form
    time_fraction: float | None = None
    dimensions: Mapping[str, DimMatch] = field(default_factory=dict)
    conditional_on: tuple[str, ...] = ()  # e.g. ("space", "product")

    def __post_init__(self) -> None:
        _match_post_init(self)


_OUTCOME_FIELDS = tuple(f.name for f in dataclasses.fields(Outcome))
_MATCH_FIELDS = tuple(f.name for f in dataclasses.fields(Match))


@dataclass(frozen=True, kw_only=True)
class Finding(Outcome, Match):
    """The result of one rule matching one query: the outcome plus the match."""

    details: Mapping[str, Any] = field(default_factory=dict)
    source: str = ""  # a loaded record's file name, "computed" or "python"
    query_label: str = ""

    def __post_init__(self) -> None:
        _outcome_post_init(self)
        _match_post_init(self)
        _set(self, "details", dict(self.details))

    def to_dict(self) -> dict[str, Any]:
        """A JSON-ready dict: the level as its number, intervals as lists."""
        names = _OUTCOME_FIELDS + _MATCH_FIELDS + ("details", "source", "query_label")
        return {name: _jsonable(getattr(self, name)) for name in names}

    def __str__(self) -> str:
        """The text to log: "[CODE] title (label; area 40%; periods; draft)"."""
        notes = [self.query_label] if self.query_label else []
        if self.area_fraction is not None:
            notes.append(f"area {self.area_fraction:.0%}")
        if self.time_overlap:  # an open end is "..", shown as nothing: "..2009-12-31"
            ends = [
                ["" if e == ".." else e for e in pair] for pair in self.time_overlap
            ]
            notes.append(", ".join(f"{a}..{b}" for a, b in ends))
        if self.status == "draft":
            notes.append("draft")
        return f"[{self.code}] {self.title}" + (
            f" ({'; '.join(notes)})" if notes else ""
        )


def report(findings: Iterable[Finding]) -> str:
    """The text of findings for people to read, or "" for none.

    Each finding is its level and str(finding), then indented lines for its
    message, instruction, what a conditional finding is waiting on, and each
    change.
    """
    lines = []
    for f in findings:
        lines += [f"{logging.getLevelName(f.level)} {f}", f"    {f.message}"]
        if f.instruction:
            lines.append(f"    {f.instruction}")
        if f.conditional_on:
            lines.append(f"    Conditional on: {', '.join(f.conditional_on)}")
        for c in f.changes:
            why = f" ({c.rationale})" if c.rationale else ""
            lines.append(f"    Change: {c.target} {c.key} = {c.value!r}{why}")
    return "\n".join(lines)


# ---- scopes and queries -----------------------------------------------------------
def _mapping(value: Any, what: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{what} is a mapping of names to values, not {value!r}")
    if not all(isinstance(k, str) for k in value):
        raise TypeError(f"{what} names must be strings")
    return dict(value)


@dataclass(frozen=True)
class Scope:
    """A conjunction; an unconstrained dimension matches anything.

    dimensions maps the name of each other dimension the rule constrains to
    its value in record form; the Registry checks every name and parses each
    value with its dimension. With edge=True the rule applies where the
    query's edge meets its space, rather than wherever they overlap, for
    advice about where a domain's boundary falls.
    """

    space: Space | None = None
    time: TimeSpec | None = None
    dimensions: Mapping[str, Any] = field(default_factory=dict)
    edge: bool = False

    def __post_init__(self) -> None:
        _space_of(self.space, "a scope's space")
        if self.time is not None and not isinstance(self.time, TimeSpec):
            raise TypeError("a scope's time is a TimeSpec or None")
        _set(self, "dimensions", _mapping(self.dimensions, "scope dimensions"))
        if not isinstance(self.edge, bool):
            raise TypeError(f"a scope's edge is True or False, not {self.edge!r}")
        if self.edge and self.space is None:
            raise ValueError(
                "an edge rule needs a space: it applies where the query's edge meets it"
            )


@dataclass(frozen=True)
class Query:
    """What the caller is about to use; every part is optional.

    Pass the support (the cells and time steps a product contributes), never a
    buffered shape.
    """

    space: Space | None = None
    time: TimeSpec | None = None
    dimensions: Mapping[str, Any] = field(default_factory=dict)
    context: Mapping[str, Any] = field(default_factory=dict, compare=False)
    label: str = ""  # the caller's name for the query, used in messages

    def __post_init__(self) -> None:
        _space_of(self.space, "a query's space")
        _set(self, "time", time_of(self.time))
        _set(self, "dimensions", _mapping(self.dimensions, "query dimensions"))
        _set(self, "context", _mapping(self.context, "query context"))
        if not isinstance(self.label, str):
            raise TypeError("a query label is a string")


# ---- errors ---------------------------------------------------------------------
# The error classes the design names (reference/decisions.md, "Error classes").
# Where the design only says that something "is an error", the engine raises a
# plain ValueError or TypeError with a message that names the problem.
class DuplicateCodeError(ValueError):
    """A code the Registry already holds was registered again (section 12.3)."""


class UnknownNameError(KeyError):
    """An undeclared dimension name.

    A misspelt name would otherwise look like "no known issues", so the engine
    refuses it in rules and queries alike (sections 4.6 and 4.7).
    """

    def __str__(self) -> str:
        # KeyError quotes its argument, which would wrap the message in quotes
        if len(self.args) == 1:
            return str(self.args[0])
        return super().__str__()


class LoadError(ValueError):
    """A rule file or FeatureCollection failed the loader checks (section 5.3).

    .problems lists each, naming its file, the feature's position and its code.
    """

    def __init__(self, problems: list[str]) -> None:
        self.problems = tuple(problems)
        super().__init__("\n".join(self.problems))
