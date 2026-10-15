"""Time: integer-second keys and intervals.

Every instant is one integer key, toordinal() * DAY plus the seconds of the day,
in the proleptic Gregorian calendar of Python's datetime. Inside the code an
interval is half-open, [start, end), with None for an open end; on the wire it
is closed at its stated precision, a day or a second, so an end date covers its
whole day. cftime, pandas and numpy values are read by duck typing; none is
imported.
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass
from typing import Any, Literal

__all__ = ["DAY", "Interval", "interval"]

Precision = Literal["day", "second"]  # max() of two is the finer one

DAY = 86_400  # key units in one day


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
            if text[11:13] == "24":  # Python 3.14 reads it as the next midnight
                raise ValueError("hour 24 is not allowed")
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


@dataclass(frozen=True)
class Interval:
    """A half-open interval [start, end) of keys; None is an open end.

    Make one with interval(). A day-precision interval has its ends at
    midnight and is written back as dates.
    """

    start: int | None
    end: int | None
    precision: Precision = "day"

    def __post_init__(self) -> None:
        if self.precision not in ("day", "second"):
            raise ValueError(f"precision is 'day' or 'second', not {self.precision!r}")
        if None not in (self.start, self.end) and self.start >= self.end:
            raise ValueError(f"interval ends out of order: {list(self.to_wire())}")

    def meets(self, other: Interval) -> bool:
        """Whether the two intervals share an instant."""
        return (self.start is None or other.end is None or self.start < other.end) and (
            other.start is None or self.end is None or other.start < self.end
        )

    def to_wire(self) -> tuple[str, str]:
        """The closed wire form, with ".." for an open end: an end date covers
        its whole day."""
        last = DAY if self.precision == "day" else 1
        return (
            ".." if self.start is None else _text(self.start, self.precision),
            ".." if self.end is None else _text(self.end - last, self.precision),
        )


def interval(start: Any, end: Any) -> Interval:
    """A closed interval whose ends are inclusive at their precision.

    Ends are ISO 8601 strings, ".." or None for an open end, or date-like values.
    A date covers its whole day, and a value with a time of day covers its
    second, even at midnight. With one end a date and the other a time of day,
    both are written as timestamps.
    """
    a, b = _instant(start), _instant(end)
    precision = max(a[1] if a else "day", b[1] if b else "day")
    stop = None if b is None else b[0] + (DAY if b[1] == "day" else 1)
    return Interval(None if a is None else a[0], stop, precision)
