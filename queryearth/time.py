"""Time: integer-second keys, half-open intervals and their measures.

Every instant is one integer key, toordinal() * DAY plus the seconds of the day,
in the proleptic Gregorian calendar of Python's datetime, so durations are plain
subtraction. Inside the code an interval is half-open, [start, end), with None
for an open end; on the wire it is closed at its stated precision, a day or a
second (design.md section 7). cftime, pandas and numpy values are read by duck
typing; none is imported.
"""

from __future__ import annotations

import calendar
import datetime as _dt
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

__all__ = [
    "DAY",
    "Interval",
    "TimeSpec",
    "interval",
    "overlap",
    "overlaps",
    "parse_time",
    "time_fraction",
]

Precision = Literal["day", "second"]  # max() of two is the finer one

DAY = 86_400  # key units in one day


# ---- keys and the wire form --------------------------------------------------------
def _instant(value: Any) -> tuple[int, Precision] | None:
    """The key and precision of one time value; None or ".." is an open end.

    Strings are ISO 8601, where a date is day precision, and a numpy datetime64
    is read through str(). Anything else needs year, month and day attributes,
    and is second precision if it has an hour. A part of a second is dropped.
    """
    if value is None or (isinstance(value, str) and value == ".."):
        return None
    try:
        if isinstance(value, str) or "datetime64" in str(getattr(value, "dtype", "")):
            text = str(value)  # numpy writes ISO 8601, such as 2020-01-09T06:00:00
            day = len(text) <= 10  # a date, such as 2020-01-09
            value = (_dt.date if day else _dt.datetime).fromisoformat(text)
        if isinstance(value, _dt.datetime) and value.utcoffset() is not None:
            value = value.astimezone(_dt.timezone.utc)
        clock = [getattr(value, name, 0) for name in ("hour", "minute", "second")]
        when = _dt.datetime(value.year, value.month, value.day, *clock)
    except (AttributeError, TypeError):
        raise TypeError(
            f"cannot read a time from {value!r}; pass an ISO 8601 string, a date or "
            "datetime, a numpy datetime64 or an object with year, month and day"
        ) from None
    except (ValueError, OverflowError) as err:
        raise ValueError(
            f"{value!r} is not a time from year 1 to 9999 in the proleptic "
            f"Gregorian calendar: {err}"
        ) from None
    key = when.toordinal() * DAY + (when.hour * 60 + when.minute) * 60 + when.second
    return key, "second" if hasattr(value, "hour") else "day"


def _text(key: int, precision: Precision) -> str:
    """The wire form of the instant at key: a date, or a timestamp in UTC."""
    when = _dt.datetime.fromordinal(key // DAY) + _dt.timedelta(seconds=key % DAY)
    return when.date().isoformat() if precision == "day" else when.isoformat() + "Z"


def _lo(key: int | None) -> float:
    return -math.inf if key is None else key  # an open start comes first


def _hi(key: int | None) -> float:
    return math.inf if key is None else key  # an open end comes last


# ---- intervals -----------------------------------------------------------------
@dataclass(frozen=True)
class Interval:
    """A half-open interval [start, end) of keys; None is an open end.

    Not ordered: an open end does not compare with a key. A day-precision
    interval has its ends at midnight and is written back as dates.
    """

    start: int | None
    end: int | None
    precision: Precision = "day"

    def __post_init__(self) -> None:
        if self.precision not in ("day", "second"):
            raise ValueError(f"precision is 'day' or 'second', not {self.precision!r}")
        for key in (self.start, self.end):
            if key is not None and (not isinstance(key, int) or isinstance(key, bool)):
                raise TypeError(f"interval ends are integer keys, not {key!r}")
            if key is not None and self.precision == "day" and key % DAY:
                raise ValueError("a day-precision interval needs ends at midnight")
        if _lo(self.start) >= _hi(self.end):
            raise ValueError(f"interval ends out of order: {list(self.to_wire())}")

    def to_wire(self) -> tuple[str, str]:
        """The closed wire form: an end date covers its whole day."""
        last = DAY if self.precision == "day" else 1
        return (
            ".." if self.start is None else _text(self.start, self.precision),
            ".." if self.end is None else _text(self.end - last, self.precision),
        )


def _closed(
    a: tuple[int, Precision] | None, b: tuple[int, Precision] | None
) -> Interval:
    """The Interval from closed ends (key, precision), None for an open end."""
    precision = max(a[1] if a else "day", b[1] if b else "day")
    end = None if b is None else b[0] + (DAY if b[1] == "day" else 1)
    return Interval(None if a is None else a[0], end, precision)


@dataclass(frozen=True)
class TimeSpec:
    """A union of intervals, optionally limited to some months of every year.

    The intervals are kept sorted, and those that overlap or touch are merged.
    """

    intervals: tuple[Interval, ...]
    months: frozenset[int] | None = None

    def __post_init__(self) -> None:
        if self.months is not None:
            months = frozenset(self.months)
            if not months or not all(
                isinstance(m, int) and not isinstance(m, bool) and 1 <= m <= 12
                for m in months
            ):
                raise ValueError(
                    f"months must be integers from 1 to 12, got {self.months!r}"
                )
            object.__setattr__(self, "months", months)
        if not all(isinstance(iv, Interval) for iv in self.intervals):
            raise TypeError(f"a TimeSpec holds Interval objects, not {self.intervals}")
        merged: list[Interval] = []
        for iv in sorted(self.intervals, key=lambda iv: _lo(iv.start)):
            if merged and _lo(iv.start) <= _hi(merged[-1].end):
                last = merged.pop()
                end = max(last.end, iv.end, key=_hi)
                iv = Interval(last.start, end, max(last.precision, iv.precision))
            merged.append(iv)
        if not merged:
            raise ValueError(
                "a TimeSpec needs at least one interval; None means always"
            )
        object.__setattr__(self, "intervals", tuple(merged))

    @property
    def extent(self) -> tuple[int | None, int | None]:
        """The first start and the last end, None for an open end."""
        return self.intervals[0].start, self.intervals[-1].end

    def to_wire(self) -> tuple[tuple[str, str], ...]:
        """Every interval in closed wire form; months are not expanded here."""
        return tuple(iv.to_wire() for iv in self.intervals)


# ---- building time specifications ----------------------------------------------
def interval(start: Any, end: Any) -> TimeSpec:
    """A closed interval whose ends are inclusive at their precision.

    Ends are ISO 8601 strings, ".." or None for an open end, or date-like values.
    A date covers its whole day, and a value with a time of day covers its
    second, even at midnight.
    """
    return TimeSpec((_closed(_instant(start), _instant(end)),))


def _wire_interval(pair: Any) -> Interval:
    """A closed wire interval [start, end]; both ends at one precision (JSON-FG)."""
    if isinstance(pair, str) or not isinstance(pair, Sequence) or len(pair) != 2:
        raise ValueError(f"a wire interval is a pair [start, end], got {pair!r}")
    a, b = _instant(pair[0]), _instant(pair[1])
    if a and b and a[1] != b[1]:
        raise ValueError(f"{list(pair)} mixes a date and a timestamp (JSON-FG)")
    return _closed(a, b)


def parse_time(member: Mapping[str, Any] | None, **props: Any) -> TimeSpec | None:
    """Read a JSON-FG time member with the record's time properties.

    props may hold every record property; periods, recurrence, time_start and
    time_end are read and the rest ignored. Returns None when the record has no
    time and no recurrence, which means always; an interval open at both ends,
    with no periods or recurrence, also means always.
    """
    start, end = props.get("time_start"), props.get("time_end")
    if start is not None or end is not None:
        if member is not None:
            raise ValueError(
                "time_start and time_end cannot be combined with a non-null time"
            )
        extent = _wire_interval([start or "..", end or ".."])
    elif member is None:
        extent = None
    elif not isinstance(member, Mapping):
        raise TypeError(f"a JSON-FG time member is an object or null, not {member!r}")
    elif len(member) != 1 or not set(member) <= {"date", "timestamp", "interval"}:
        raise ValueError(
            f"a time member holds one of date, timestamp or interval: {dict(member)}"
        )
    elif "interval" in member:
        extent = _wire_interval(member["interval"])
    else:
        ((kind, value),) = member.items()
        read = _instant(value)
        if read is None or read[1] != ("day" if kind == "date" else "second"):
            raise ValueError(f"{value!r} is not a {kind}")
        extent = _closed(read, read)
    months = props.get("recurrence")
    if months is not None:
        if (
            not isinstance(months, Mapping)
            or set(months) != {"months"}
            or not isinstance(months["months"], (list, tuple))
            or len(set(months["months"])) != len(months["months"])
        ):
            raise ValueError(f'recurrence is {{"months": [...]}}, got {months!r}')
        months = frozenset(months["months"])
    periods = props.get("periods")
    if periods is not None:
        if extent is None:
            raise ValueError("periods refine the time member, so the record needs one")
        if isinstance(periods, str) or not isinstance(periods, Sequence) or not periods:
            raise ValueError(f"periods is a non-empty list of intervals: {periods!r}")
        parts = [_wire_interval(p) for p in periods]
        for part, raw in zip(parts, periods):
            if _lo(part.start) < _lo(extent.start) or _hi(part.end) > _hi(extent.end):
                raise ValueError(f"period {list(raw)} lies outside the time member")
        return TimeSpec(tuple(parts), months)
    if extent is not None and (extent.start, extent.end) != (None, None):
        return TimeSpec((extent,), months)
    if months is not None:
        return TimeSpec((Interval(None, None),), months)
    return None


# ---- measures --------------------------------------------------------------------
def overlap(rule: TimeSpec | None, query: TimeSpec) -> TimeSpec | None:
    """Where a rule's time meets a query's; None if nowhere.

    Month recurrence cuts the overlap into calendar months, merging runs that
    touch; an overlap with an open end is returned unexpanded, with its months,
    since every month occurs. An untimed rule (None) overlaps the query's whole
    period.
    """
    if rule is None:
        return query
    pieces, a, b = [], list(rule.intervals), list(query.intervals)
    while a and b:  # both sorted and disjoint; drop whichever ends first
        x, y = a[0], b[0]
        lo, hi = max(x.start, y.start, key=_lo), min(x.end, y.end, key=_hi)
        if _lo(lo) < _hi(hi):
            pieces.append(Interval(lo, hi, max(x.precision, y.precision)))
        (a if _hi(x.end) <= _hi(y.end) else b).pop(0)
    months = rule.months
    if query.months is not None:
        months = query.months if months is None else months & query.months
    if not pieces or months == frozenset():
        return None
    if months is None or any(None in (p.start, p.end) for p in pieces):
        return TimeSpec(tuple(pieces), months)
    runs = []
    for piece in pieces:  # cut into calendar months, a month at a time
        first = _dt.date.fromordinal(piece.start // DAY)
        y, m, start = first.year, first.month, first.replace(day=1).toordinal() * DAY
        while start < piece.end:
            end = start + calendar.monthrange(y, m)[1] * DAY
            if m in months:
                lo, hi = max(piece.start, start), min(piece.end, end)
                runs.append(Interval(lo, hi, piece.precision))
            y, m, start = y + m // 12, m % 12 + 1, end
    return TimeSpec(tuple(runs)) if runs else None


def overlaps(rule: TimeSpec | None, query: TimeSpec) -> bool:
    """Whether a rule's time meets a query's (see overlap)."""
    return overlap(rule, query) is not None


def time_fraction(part: TimeSpec | None, query: TimeSpec | None) -> float | None:
    """The share of the query's duration that part covers.

    None when the query has no time or an open end. A month recurrence on
    either side is expanded before durations are measured.
    """
    if query is None or None in query.extent:
        return None
    if query.months is not None:
        query = overlap(query, query)
        if query is None:
            return None
    if part is not None and part.months is not None:
        part = overlap(part, part)  # bounded, since it lies inside a bounded query
    total = sum(iv.end - iv.start for iv in query.intervals)
    covered = 0 if part is None else sum(iv.end - iv.start for iv in part.intervals)
    return covered / total if total else None
