"""Time: calendar-free civil-date keys, half-open intervals and their measures.

Every instant becomes one integer key packed from its civil labels (year, month,
day, hour, minute, second), so ordering never needs a calendar. Inside the code
an interval is half-open, [start, end), with None for an open end; on the wire it
is closed at its stated precision, a day or a second. A calendar validates dates,
names the last day of a month and measures durations, but never orders. See
design.md section 7 and the time sections of reference/decisions.md.

cftime, pandas and numpy date values are read by duck typing; none is imported.
"""

from __future__ import annotations

import datetime as _dt
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal, NamedTuple

__all__ = [
    "CALENDARS",
    "DAY",
    "Interval",
    "TimeSpec",
    "civil_fields",
    "civil_key",
    "from_bounds",
    "interval",
    "overlap",
    "overlaps",
    "parse_time",
    "time_fraction",
]

Precision = Literal["day", "second"]

DAY = 86_400  # key units in one day
CALENDARS = frozenset(
    {
        "standard",
        "gregorian",
        "proleptic_gregorian",
        "julian",
        "noleap",
        "365_day",
        "all_leap",
        "366_day",
        "360_day",
    }
)
_SAME_AS = {"gregorian": "standard", "365_day": "noleap", "366_day": "all_leap"}
_MONTH_DAYS = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
_NO_YEAR_ZERO = ("standard", "gregorian", "julian")  # cftime's default
_WIRE = re.compile(
    r"(-?[0-9]{4,})-([0-9]{2})-([0-9]{2})(?:T([0-9]{2}):([0-9]{2}):([0-9]{2})Z)?"
)
_DATETIME64 = re.compile(r"datetime64\[([0-9]*)(Y|M|W|D|h|m|s|ms|us|ns|ps|fs|as)\]")
_SUBSECOND = {"ms": 10**3, "us": 10**6, "ns": 10**9, "ps": 10**12}
_SUBSECOND |= {"fs": 10**15, "as": 10**18}


# ---- civil keys ----------------------------------------------------------------
def civil_key(y: int, mo: int, d: int, h: int = 0, mi: int = 0, s: int = 0) -> int:
    """Pack civil labels into one integer that sorts exactly like the tuple.

    Month 0 and days 0 and 32 are allowed as the empty slots that interval ends
    use (key(2020, 1, 32) == key(2020, 2, 0)); every other field must be in range.
    """
    if s == 60:
        raise ValueError("second 60 is not accepted: no CF calendar has leap seconds")
    if not (0 <= mo <= 12 and 0 <= d <= 32 and 0 <= h < 24 and 0 <= mi < 60):
        raise ValueError(f"civil labels out of range: {(y, mo, d, h, mi, s)}")
    if not 0 <= s < 60:
        raise ValueError(f"civil labels out of range: {(y, mo, d, h, mi, s)}")
    return ((((y * 13 + mo) * 32 + d) * 24 + h) * 60 + mi) * 60 + s


def civil_fields(key: int) -> tuple[int, int, int, int, int, int]:
    """Unpack a key into (year, month, day, hour, minute, second)."""
    rest, s = divmod(key, 60)
    rest, mi = divmod(rest, 60)
    rest, h = divmod(rest, 24)
    rest, d = divmod(rest, 32)
    y, mo = divmod(rest, 13)
    return y, mo, d, h, mi, s


_REFORM = civil_key(1582, 10, 15)  # first day of the Gregorian calendar


# ---- calendars -----------------------------------------------------------------
def _calendar(name: str | None) -> str:
    """Return the CF calendar name in lower case, or raise for an unknown one."""
    if name is None:
        return "proleptic_gregorian"
    if not isinstance(name, str) or name.lower() not in CALENDARS:
        raise ValueError(
            f"unknown calendar {name!r}; expected one of {sorted(CALENDARS)}"
        )
    return name.lower()


def _is_leap(cal: str, y: int) -> bool:
    if cal in ("noleap", "365_day"):
        return False
    if cal in ("all_leap", "366_day", "360_day"):
        return True
    if cal == "julian":
        return y % 4 == 0
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)


def _days_in_month(cal: str, y: int, m: int) -> int:
    if cal == "360_day":
        return 30
    if m == 2:
        return 29 if _is_leap(cal, y) else 28
    return _MONTH_DAYS[m - 1]


def _year_start(cal: str, y: int) -> int:
    """Days from the start of year 0 to the start of year y; negative before."""
    if cal == "360_day":
        return 360 * y
    if cal in ("noleap", "365_day"):
        return 365 * y
    if cal in ("all_leap", "366_day"):
        return 366 * y
    leaps = -(-y // 4)  # ceil(y / 4): leap years in [0, y), negative for y < 0
    if cal != "julian":
        leaps += -(-y // 400) - -(-y // 100)
    return 365 * y + leaps


def _check(
    cal: str, y: int, m: int, d: int, h: int = 0, mi: int = 0, s: int = 0
) -> int:
    """Key of a real instant in cal; raise if the labels are not one."""
    if s == 60:
        raise ValueError("second 60 is not accepted: no CF calendar has leap seconds")
    if not (0 <= h < 24 and 0 <= mi < 60 and 0 <= s < 60):
        raise ValueError(f"time of day out of range: {h:02d}:{mi:02d}:{s:02d}")
    if not (1 <= m <= 12 and 1 <= d <= _days_in_month(cal, y, m)):
        raise ValueError(f"{_date_text(y, m, d)} is not a date in the {cal} calendar")
    return civil_key(y, m, d, h, mi, s)


def _is_real(cal: str, y: int, m: int, d: int) -> bool:
    return 1 <= m <= 12 and 1 <= d <= _days_in_month(cal, y, m)


def _resolve(cal: str, key: int) -> int:
    """The first key at or after key that is a real instant in cal."""
    y, m, d, _, _, _ = civil_fields(key)
    if m == 0:
        return civil_key(y, 1, 1)
    if d == 0:
        return civil_key(y, m, 1)
    if d > _days_in_month(cal, y, m):
        return civil_key(y + 1, 1, 1) if m == 12 else civil_key(y, m + 1, 1)
    return key


def _last_real_day(cal: str, y: int, m: int, d: int) -> tuple[int, int, int]:
    """The last real day of cal at or before the day slot (y, m, d)."""
    if m == 0 or (m == 1 and d == 0):
        return y - 1, 12, _days_in_month(cal, y - 1, 12)
    if d == 0:
        return y, m - 1, _days_in_month(cal, y, m - 1)
    return y, m, min(d, _days_in_month(cal, y, m))


def _seconds(cal: str, key: int) -> int:
    """Seconds from the start of year 0 to key, counted in cal."""
    y, m, d, h, mi, s = civil_fields(_resolve(cal, key))
    days = _year_start(cal, y) + sum(_days_in_month(cal, y, k) for k in range(1, m))
    return (days + d - 1) * DAY + (h * 60 + mi) * 60 + s


def _duration(cal: str, intervals: Iterable[Interval]) -> int:
    total = 0
    for iv in intervals:
        if iv.start is None or iv.end is None:
            raise ValueError("an open-ended interval has no duration")
        total += max(0, _seconds(cal, iv.end) - _seconds(cal, iv.start))
    return total


# ---- intervals -----------------------------------------------------------------
def _date_text(y: int, m: int, d: int) -> str:
    return f"{'-' if y < 0 else ''}{abs(y):04d}-{m:02d}-{d:02d}"


def _text(labels: tuple[int, ...], precision: Precision) -> str:
    y, m, d, h, mi, s = labels
    if precision == "day":
        return _date_text(y, m, d)
    return f"{_date_text(y, m, d)}T{h:02d}:{mi:02d}:{s:02d}Z"


def _last_labels(cal: str, end: int, precision: Precision) -> tuple[int, ...]:
    """Labels of the last real instant of cal before an exclusive end."""
    y, m, d, h, mi, s = civil_fields(end - (DAY if precision == "day" else 1))
    if not _is_real(cal, y, m, d):
        y, m, d = _last_real_day(cal, y, m, d)
        h, mi, s = 23, 59, 59
    return y, m, d, h, mi, s


def _closed_ends(
    cal: str, start: int, end: int, precision: Precision
) -> tuple[tuple[int, ...], tuple[int, ...]]:
    """Labels of the first and last real instants of [start, end) in cal."""
    first = civil_fields(_resolve(cal, start))
    last = _last_labels(cal, end, precision)
    if last < first:  # no real day of cal inside, e.g. 30 February in a Gregorian query
        return civil_fields(start), civil_fields(end - 1)
    return first, last


@dataclass(frozen=True)
class Interval:
    """A half-open interval [start, end) of civil keys; None is an open end.

    Not ordered: an open end does not compare with a key. A day-precision
    interval has its ends at midnight and is written back as dates.
    """

    start: int | None
    end: int | None
    precision: Precision = "day"

    def __post_init__(self) -> None:
        if self.precision not in ("day", "second"):
            raise ValueError(
                f"precision must be 'day' or 'second', not {self.precision!r}"
            )
        for key in (self.start, self.end):
            if key is None:
                continue
            if not isinstance(key, int) or isinstance(key, bool):
                raise TypeError(f"interval ends are civil keys (int), not {key!r}")
            if self.precision == "day" and key % DAY:
                raise ValueError("a day-precision interval needs ends at midnight")
        if self.start is not None and self.end is not None and self.start >= self.end:
            raise ValueError(
                f"an interval needs start < end, got {self.start}, {self.end}"
            )

    def to_wire(self, calendar: str = "proleptic_gregorian") -> tuple[str, str]:
        """The closed wire form; the calendar names the last day of a month."""
        cal = _calendar(calendar)
        if self.start is not None and self.end is not None:
            first, last = _closed_ends(cal, self.start, self.end, self.precision)
            return _text(first, self.precision), _text(last, self.precision)
        if self.start is not None:
            return _text(civil_fields(_resolve(cal, self.start)), self.precision), ".."
        if self.end is not None:
            return "..", _text(
                _last_labels(cal, self.end, self.precision), self.precision
            )
        return "..", ".."


def _start_order(iv: Interval) -> tuple[bool, int]:
    return (iv.start is not None, 0 if iv.start is None else iv.start)


def _end_order(end: int | None) -> tuple[bool, int]:
    return (end is None, 0 if end is None else end)


def _finer(a: Precision, b: Precision) -> Precision:
    return "second" if "second" in (a, b) else "day"


def _union(cal: str, intervals: Iterable[Interval]) -> tuple[Interval, ...]:
    """Sort and merge; intervals separated only by labels cal lacks are merged."""
    items = list(intervals)
    for iv in items:
        if not isinstance(iv, Interval):
            raise TypeError(f"expected Interval, got {type(iv).__name__}")
    out: list[Interval] = []
    for iv in sorted(items, key=_start_order):
        if out:
            last = out[-1]
            if (
                last.end is None
                or iv.start is None
                or iv.start <= _resolve(cal, last.end)
            ):
                end = None if None in (last.end, iv.end) else max(last.end, iv.end)
                precision = _finer(last.precision, iv.precision)
                out[-1] = Interval(last.start, end, precision)
                continue
        out.append(iv)
    return tuple(out)


@dataclass(frozen=True)
class TimeSpec:
    """A union of intervals, optionally limited to some months of every year.

    The calendar validates dates and measures durations; it never orders. The
    intervals are kept sorted and merged.
    """

    intervals: tuple[Interval, ...]
    months: frozenset[int] | None = None
    calendar: str = "proleptic_gregorian"

    def __post_init__(self) -> None:
        cal = _calendar(self.calendar)
        object.__setattr__(self, "calendar", cal)
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
        object.__setattr__(self, "intervals", _union(cal, self.intervals))
        if not self.intervals:
            raise ValueError(
                "a TimeSpec needs at least one interval; None means always"
            )

    @property
    def extent(self) -> tuple[int | None, int | None]:
        """The first start and the last end, None for an open end."""
        return self.intervals[0].start, self.intervals[-1].end

    def to_wire(self) -> tuple[tuple[str, str], ...]:
        """Every interval in closed wire form; months are not expanded here."""
        return tuple(iv.to_wire(self.calendar) for iv in self.intervals)


# ---- reading values --------------------------------------------------------------
class _Read(NamedTuple):
    labels: tuple[int, int, int, int, int, int]
    precision: Precision
    calendar: str | None  # a cftime value's own calendar
    fraction: bool = False  # a part of a second was dropped


def _parse_wire(text: Any) -> _Read:
    if not isinstance(text, str):
        raise TypeError(f"a wire time is a string, not {type(text).__name__}")
    match = _WIRE.fullmatch(text)
    if match is None:
        raise ValueError(
            f"not a wire date or timestamp: {text!r} "
            "(expected YYYY-MM-DD or YYYY-MM-DDTHH:MM:SSZ)"
        )
    y, m, d, h, mi, s = (int(g) if g is not None else None for g in match.groups())
    if h is None:
        return _Read((y, m, d, 0, 0, 0), "day", None)
    return _Read((y, m, d, h, mi, s), "second", None)


def _civil_from_days(z: int) -> tuple[int, int, int]:
    """Proleptic Gregorian date of z days after 1970-01-01."""
    z += 719_468
    era = z // 146_097
    doe = z - era * 146_097
    yoe = (doe - doe // 1460 + doe // 36_524 - doe // 146_096) // 365
    doy = doe - (365 * yoe + yoe // 4 - yoe // 100)
    mp = (5 * doy + 2) // 153
    d = doy - (153 * mp + 2) // 5 + 1
    m = mp + 3 if mp < 10 else mp - 9
    return yoe + era * 400 + (m <= 2), m, d


def _from_datetime64(value: Any) -> _Read:
    """Read a numpy datetime64 in its own unit, never through datetime64[ns].

    A value in years or months is read as its first day, as numpy itself does.
    """
    if value != value:
        raise ValueError("not a time: NaT")
    match = _DATETIME64.fullmatch(str(value.dtype))
    if match is None:
        raise ValueError(f"a datetime64 needs a unit, got {value.dtype}")
    count = int(value.astype("int64")) * int(match.group(1) or 1)
    unit = match.group(2)
    if unit == "Y":
        return _Read((1970 + count, 1, 1, 0, 0, 0), "day", None)
    if unit == "M":
        years, month = divmod(count, 12)
        return _Read((1970 + years, month + 1, 1, 0, 0, 0), "day", None)
    if unit in ("W", "D"):
        y, m, d = _civil_from_days(count * (7 if unit == "W" else 1))
        return _Read((y, m, d, 0, 0, 0), "day", None)
    fraction = False
    if unit in _SUBSECOND:
        seconds, rest = divmod(count, _SUBSECOND[unit])
        fraction = rest != 0
    else:
        seconds = count * {"h": 3600, "m": 60, "s": 1}[unit]
    days, rest = divmod(seconds, DAY)
    h, rest = divmod(rest, 3600)
    mi, s = divmod(rest, 60)
    return _Read((*_civil_from_days(days), h, mi, s), "second", None, fraction)


def _from_cftime(value: Any) -> _Read:
    """Read a cftime object; years become astronomical (year 0 is 1 BC)."""
    cal = getattr(value, "calendar", None) or None
    has_zero = getattr(value, "has_year_zero", None)
    if has_zero is None:
        has_zero = cal not in _NO_YEAR_ZERO
    y = value.year
    if not has_zero:
        if y == 0:
            raise ValueError("year 0 does not exist in a calendar without a year zero")
        if y < 0:
            y += 1
    labels = (y, value.month, value.day, value.hour, value.minute, value.second)
    fraction = bool(getattr(value, "microsecond", 0))
    return _Read(labels, "second", cal, fraction)


def _instant(value: Any) -> _Read:
    """Civil labels, precision and calendar (cftime only) of one time value."""
    if isinstance(value, str):
        return _parse_wire(value)
    if type(value).__name__ == "NaTType":
        raise ValueError("not a time: NaT")
    if isinstance(value, _dt.datetime):  # pandas Timestamp is a datetime too
        if value.utcoffset() is not None:
            value = value.astimezone(_dt.timezone.utc)
        labels = (value.year, value.month, value.day)
        fraction = bool(value.microsecond or getattr(value, "nanosecond", 0))
        clock = (value.hour, value.minute, value.second)
        return _Read((*labels, *clock), "second", None, fraction)
    if isinstance(value, _dt.date):
        return _Read((value.year, value.month, value.day, 0, 0, 0), "day", None)
    if str(getattr(value, "dtype", "")).startswith("datetime64"):
        return _from_datetime64(value)
    fields = ("year", "month", "day", "hour", "minute", "second", "calendar")
    if all(hasattr(value, name) for name in fields):
        return _from_cftime(value)
    raise TypeError(
        f"cannot read a time from {type(value).__name__}; pass a wire string, a "
        "datetime or date, a cftime object, a numpy datetime64 or a pandas Timestamp"
    )


def _read_end(value: Any) -> _Read | None:
    if value is None or (isinstance(value, str) and value == ".."):
        return None
    return _instant(value)


def _family(cal: str) -> str:
    return _SAME_AS.get(cal, cal)


def _pick_calendar(calendar: str | None, hints: Iterable[str | None]) -> str:
    """The explicit calendar, else the values' own, else proleptic_gregorian."""
    named = [_calendar(h) for h in hints if h]
    families = {_family(cal) for cal in named}
    if calendar is not None:
        cal = _calendar(calendar)
        if families and families != {_family(cal)}:
            raise ValueError(
                f"calendar {cal!r} disagrees with the values' {sorted(families)}"
            )
        return cal
    if len(families) > 1:
        raise ValueError(f"the values use different calendars: {sorted(families)}")
    return named[0] if named else "proleptic_gregorian"


def _precision(*ends: _Read | None) -> Precision:
    found: Precision = "day"
    for end in ends:
        if end is not None:
            found = _finer(found, end.precision)
    return found


# ---- building time specifications ----------------------------------------------
def interval(start: Any, end: Any, calendar: str | None = None) -> TimeSpec:
    """A closed interval whose ends are inclusive at their precision.

    Ends are wire strings, ".." or None for an open end, or date-like values.
    Dates and datetime64 values in days or coarser are day precision; every
    datetime-like value is second precision, even at midnight. A part of a
    second is dropped from the start and kept inside the end's second.
    """
    a, b = _read_end(start), _read_end(end)
    cal = _pick_calendar(calendar, [e.calendar for e in (a, b) if e is not None])
    lo = None if a is None else _check(cal, *a.labels)
    hi = None
    if b is not None:
        hi = _check(cal, *b.labels) + (DAY if b.precision == "day" else 1)
    if lo is not None and hi is not None and lo >= hi:
        raise ValueError(f"interval ends out of order: {start!r} to {end!r}")
    return TimeSpec((Interval(lo, hi, _precision(a, b)),), calendar=cal)


def _values(x: Any) -> list[Any]:
    if isinstance(x, str) or not isinstance(x, Iterable):
        return [x]
    if getattr(x, "ndim", 1) == 0:  # a 0-d numpy array
        return [x]
    return list(x)


def from_bounds(starts: Any, ends: Any, calendar: str | None = None) -> TimeSpec:
    """The query time from cell bounds: each start inclusive, each end exclusive.

    Bounds at midnight give day precision, and consecutive steps merge, so the
    monthly bounds 2020-01-01T00:00Z to 2020-02-01T00:00Z become 2020-01-01 to
    2020-01-31 on the wire.
    """
    starts, ends = _values(starts), _values(ends)
    if len(starts) != len(ends):
        raise ValueError(f"{len(starts)} starts but {len(ends)} ends")
    if not starts:
        raise ValueError("no bounds given")
    read = [(_instant(s), _instant(e)) for s, e in zip(starts, ends)]
    cal = _pick_calendar(calendar, [r.calendar for pair in read for r in pair])
    intervals = []
    for (s, e), raw in zip(read, zip(starts, ends)):
        lo = _check(cal, *s.labels)
        hi = _check(cal, *e.labels) + (1 if e.fraction else 0)
        if lo >= hi:
            raise ValueError(
                f"a bound ends at or before its start: {raw[0]!r} to {raw[1]!r}"
            )
        precision: Precision = "day" if lo % DAY == 0 and hi % DAY == 0 else "second"
        intervals.append(Interval(lo, hi, precision))
    return TimeSpec(tuple(intervals), calendar=cal)


def _wire_interval(pair: Any, cal: str) -> Interval:
    """A closed wire interval [start, end]; both ends at one precision (JSON-FG)."""
    if isinstance(pair, str) or not isinstance(pair, Sequence) or len(pair) != 2:
        raise ValueError(f"a wire interval is a pair [start, end], got {pair!r}")
    a, b = (None if v == ".." else _parse_wire(v) for v in pair)
    if a is not None and b is not None and a.precision != b.precision:
        raise ValueError(
            f"both ends of {list(pair)} must be dates or both timestamps, "
            "as JSON-FG requires"
        )
    precision = _precision(a, b)
    lo = None if a is None else _check(cal, *a.labels)
    hi = None
    if b is not None:
        hi = _check(cal, *b.labels) + (DAY if precision == "day" else 1)
    if lo is not None and hi is not None and lo >= hi:
        raise ValueError(f"interval ends out of order: {list(pair)}")
    return Interval(lo, hi, precision)


def _member_interval(member: Any, cal: str) -> Interval:
    if not isinstance(member, Mapping):
        raise TypeError(f"a JSON-FG time member is an object or null, not {member!r}")
    if len(member) != 1:
        raise ValueError(
            "a time member holds exactly one of date, timestamp or interval, "
            f"got {sorted(member)}"
        )
    ((kind, value),) = member.items()
    if kind == "interval":
        return _wire_interval(value, cal)
    if kind not in ("date", "timestamp"):
        raise ValueError(f"unknown time member {kind!r}")
    read = _parse_wire(value)
    if read.precision != ("day" if kind == "date" else "second"):
        raise ValueError(f"{kind} {value!r} is written at the wrong precision")
    key = _check(cal, *read.labels)
    return Interval(key, key + (DAY if kind == "date" else 1), read.precision)


def _months(recurrence: Any) -> frozenset[int] | None:
    if recurrence is None:
        return None
    if not isinstance(recurrence, Mapping) or set(recurrence) != {"months"}:
        raise ValueError(f'recurrence is {{"months": [...]}}, got {recurrence!r}')
    months = recurrence["months"]
    if isinstance(months, (str, bytes)) or not isinstance(months, Iterable):
        raise ValueError(f"recurrence months must be a list, got {months!r}")
    months = list(months)
    if len(set(months)) != len(months):
        raise ValueError(f"recurrence months repeat: {months!r}")
    return frozenset(months)


def _inside(part: Interval, whole: Interval) -> bool:
    after = whole.start is None or (
        part.start is not None and part.start >= whole.start
    )
    before = whole.end is None or (part.end is not None and part.end <= whole.end)
    return after and before


def parse_time(member: Mapping[str, Any] | None, **props: Any) -> TimeSpec | None:
    """Read a JSON-FG time member with the record's time properties.

    props may hold every record property; periods, recurrence, calendar,
    time_start and time_end are read and the rest ignored. Returns None when the
    record has no time and no recurrence, which means always; an interval open
    at both ends, with no periods or recurrence, also means always.
    """
    cal = _calendar(props.get("calendar"))
    start, end = props.get("time_start"), props.get("time_end")
    if start is not None or end is not None:
        if member is not None:
            raise ValueError(
                "time_start and time_end cannot be combined with a non-null time"
            )
        extent: Interval | None = _wire_interval([start or "..", end or ".."], cal)
    elif member is None:
        extent = None
    else:
        extent = _member_interval(member, cal)
    months = _months(props.get("recurrence"))
    periods = props.get("periods")
    if periods is not None:
        if extent is None:
            raise ValueError("periods refine the time member, so the record needs one")
        if isinstance(periods, str) or not isinstance(periods, Sequence) or not periods:
            raise ValueError(
                f"periods is a non-empty list of intervals, got {periods!r}"
            )
        parts = [_wire_interval(p, cal) for p in periods]
        for part, raw in zip(parts, periods):
            if not _inside(part, extent):
                raise ValueError(f"period {list(raw)} lies outside the time member")
        return TimeSpec(tuple(parts), months, cal)
    if extent is not None and (extent.start, extent.end) != (None, None):
        return TimeSpec((extent,), months, cal)
    if months is not None:
        return TimeSpec((Interval(None, None),), months, cal)
    return None


# ---- measures --------------------------------------------------------------------
def _later(a: int | None, b: int | None) -> int | None:
    return b if a is None else a if b is None else max(a, b)


def _earlier(a: int | None, b: int | None) -> int | None:
    return b if a is None else a if b is None else min(a, b)


def _intersect(a: Sequence[Interval], b: Sequence[Interval]) -> list[Interval]:
    """Pairwise intersection of two sorted, disjoint interval lists."""
    out, i, j = [], 0, 0
    while i < len(a) and j < len(b):
        x, y = a[i], b[j]
        lo, hi = _later(x.start, y.start), _earlier(x.end, y.end)
        if lo is None or hi is None or lo < hi:
            out.append(Interval(lo, hi, _finer(x.precision, y.precision)))
        if _end_order(x.end) <= _end_order(y.end):
            i += 1
        else:
            j += 1
    return out


def _month_runs(piece: Interval, months: frozenset[int]) -> list[Interval]:
    """The parts of a bounded interval that fall in the given calendar months."""
    y, m = civil_fields(piece.start)[:2]
    last_y, last_m = civil_fields(piece.end - 1)[:2]
    runs = []
    while (y, m) <= (last_y, last_m):
        ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
        if m in months:
            lo = max(piece.start, civil_key(y, m, 1))
            hi = min(piece.end, civil_key(ny, nm, 1))
            if lo < hi:
                runs.append(Interval(lo, hi, piece.precision))
        y, m = ny, nm
    return runs


def overlap(rule: TimeSpec | None, query: TimeSpec) -> TimeSpec | None:
    """Where a rule's time meets a query's, in the query's calendar; None if nowhere.

    Dates compare as civil labels whatever their calendars. Month recurrence cuts
    the overlap into calendar months, merging runs that touch; an overlap with an
    open end is returned unexpanded, with its months, since every month occurs.
    An untimed rule (None) overlaps the query's whole period.
    """
    if rule is None:
        return query
    pieces = _intersect(rule.intervals, query.intervals)
    months = rule.months
    if query.months is not None:
        months = query.months if months is None else months & query.months
    if not pieces or months == frozenset():
        return None
    if months is None:
        return TimeSpec(tuple(pieces), calendar=query.calendar)
    if any(p.start is None or p.end is None for p in pieces):
        return TimeSpec(tuple(pieces), months, query.calendar)
    runs = [run for piece in pieces for run in _month_runs(piece, months)]
    return TimeSpec(tuple(runs), calendar=query.calendar) if runs else None


def overlaps(rule: TimeSpec | None, query: TimeSpec) -> bool:
    """Whether a rule's time meets a query's (see overlap)."""
    return overlap(rule, query) is not None


def time_fraction(part: TimeSpec | None, query: TimeSpec | None) -> float | None:
    """The share of the query's duration that part covers, in the query's calendar.

    None when the query has no time or an open end, and for a standard or
    gregorian query starting before 1582-10-15, where proleptic durations would
    be wrong (Q19); julian durations use the julian day table (Q20).
    """
    if query is None:
        return None
    start, end = query.extent
    if start is None or end is None:
        return None
    if query.calendar in ("standard", "gregorian") and start < _REFORM:
        return None
    if query.months is not None:
        query = overlap(query, query)
        if query is None:
            return None
    total = _duration(query.calendar, query.intervals)
    if total == 0:
        return None
    covered = 0 if part is None else _duration(query.calendar, part.intervals)
    return covered / total
