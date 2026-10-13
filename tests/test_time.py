"""queryearth.time: fixtures 12 to 14 of docs/reference/fixtures.md, and edge cases.

The fixtures need no Registry, so each is tested on the operations its expected
findings rely on: overlap(), time_fraction() and the wire form.
"""

import datetime as dt

import numpy as np
import pytest

from queryearth.time import (
    DAY,
    Interval,
    TimeSpec,
    interval,
    overlap,
    overlaps,
    parse_time,
    time_fraction,
)


def key(*labels):
    """The key of a proleptic Gregorian date and time."""
    when = dt.datetime(*labels)
    return when.toordinal() * DAY + (when.hour * 60 + when.minute) * 60 + when.second


class Stamp(dt.datetime):
    """Stands in for pandas.Timestamp, a datetime subclass with nanoseconds."""

    nanosecond = 0


class CfDate:
    """Stands in for a cftime object: date and time fields, read by duck typing."""

    def __init__(self, y, m, d, h=0, mi=0, s=0):
        self.year, self.month, self.day = y, m, d
        self.hour, self.minute, self.second = h, mi, s


class Day:
    """A date-like object without a time of day."""

    def __init__(self, y, m, d):
        self.year, self.month, self.day = y, m, d


# ---- keys and the wire form ---------------------------------------------------------
def test_keys_are_seconds_so_durations_are_subtraction():
    (year,) = interval("2020-01-01", "2020-12-31").intervals
    assert (year.start, year.end) == (key(2020, 1, 1), key(2021, 1, 1))
    assert year.end - year.start == 366 * DAY
    (stamp,) = interval("2020-01-09T06:00:00Z", "2020-01-09T06:00:00Z").intervals
    assert stamp == Interval(key(2020, 1, 9, 6), key(2020, 1, 9, 6) + 1, "second")


def test_closed_wire_ends_become_half_open_keys():
    assert interval("2020-01-09", "2020-01-09").intervals == (
        Interval(key(2020, 1, 9), key(2020, 1, 10)),
    )
    assert interval("2020-01-01", "2020-01-31").intervals[0].end == key(2020, 2, 1)
    assert interval("..", "2020-01-09").intervals[0].start is None
    assert interval("2020-01-09", None).intervals[0].end is None


def test_wire_form_round_trips():
    spec = interval("2000-01-01", "2006-12-31")
    assert spec.to_wire() == (("2000-01-01", "2006-12-31"),)
    stamps = interval("2006-12-31T23:59:59Z", "2007-01-01T00:00:00Z")
    assert stamps.to_wire() == (("2006-12-31T23:59:59Z", "2007-01-01T00:00:00Z"),)
    assert interval("2030-01-01", "..").to_wire() == (("2030-01-01", ".."),)
    assert interval("0001-01-01", "9999-12-31").to_wire() == (
        ("0001-01-01", "9999-12-31"),
    )


@pytest.mark.parametrize(
    "text", ["2020-01", "2020-1-01", "2020-01-01T24:00:00Z", "2020-13-01", "soon"]
)
def test_malformed_times_are_rejected(text):
    with pytest.raises(ValueError):
        interval(text, "2021-01-01")


@pytest.mark.parametrize(
    "value",
    [
        "2001-02-30",  # 360_day
        CfDate(2001, 2, 30),  # a cftime 360_day value
        "0000-01-01",
        "10000-01-01",
        "-5000-06-01",
        "2016-12-31T23:59:60Z",  # no leap seconds
    ],
)
def test_dates_outside_the_proleptic_gregorian_calendar_are_rejected(value):
    with pytest.raises(ValueError, match="year 1 to 9999 in the proleptic Gregorian"):
        interval(value, None)


def test_noleap_dates_are_gregorian_dates():
    spec = interval(CfDate(2001, 1, 1), CfDate(2001, 12, 31, 23, 59, 59))
    assert spec.to_wire() == (("2001-01-01T00:00:00Z", "2001-12-31T23:59:59Z"),)


def test_cftime_values_are_read_by_their_fields():
    cftime = pytest.importorskip("cftime")
    noleap = cftime.DatetimeNoLeap(2001, 2, 28, 12)
    assert interval(noleap, noleap).to_wire() == (
        ("2001-02-28T12:00:00Z", "2001-02-28T12:00:00Z"),
    )
    with pytest.raises(ValueError, match="proleptic Gregorian"):
        interval(cftime.Datetime360Day(2001, 2, 30), None)


def test_dates_are_day_precision_and_datetimes_second_precision_even_at_midnight():
    assert interval(dt.date(2020, 1, 1), dt.date(2020, 1, 9)).intervals[
        0
    ].precision == ("day")
    assert interval(Day(2020, 1, 1), None).intervals[0].precision == "day"
    days = np.datetime64("2020-01-01", "D")
    assert interval(days, days).intervals[0].precision == "day"
    midnight = Stamp(2020, 1, 9)
    spec = interval(midnight, midnight)
    assert spec.intervals[0] == Interval(key(2020, 1, 9), key(2020, 1, 9) + 1, "second")
    seconds = np.datetime64("2020-01-09T00:00:00", "s")
    assert interval(seconds, seconds).intervals[0].precision == "second"


def test_midnight_pandas_timestamps_are_second_precision():
    pd = pytest.importorskip("pandas")
    spec = interval(pd.Timestamp("2020-01-01"), pd.Timestamp("2020-01-09"))
    assert spec.to_wire() == (("2020-01-01T00:00:00Z", "2020-01-09T00:00:00Z"),)
    assert overlaps(parse_time({"date": "2020-01-09"}), spec)


def test_mixed_precision_is_written_with_timestamps_at_both_ends():
    spec = interval(dt.date(2020, 1, 1), dt.datetime(2020, 1, 9, 12))
    assert spec.intervals[0].precision == "second"
    assert spec.to_wire() == (("2020-01-01T00:00:00Z", "2020-01-09T12:00:00Z"),)


def test_aware_datetimes_and_offsets_are_converted_to_utc():
    plus5 = dt.timezone(dt.timedelta(hours=5))
    spec = interval(dt.datetime(2020, 1, 1, 5, tzinfo=plus5), "2020-01-02")
    assert spec.intervals[0].start == key(2020, 1, 1)
    assert interval("2020-01-01T05:00:00+05:00", None).intervals[0].start == key(
        2020, 1, 1
    )


def test_parts_of_a_second_are_dropped():
    spec = interval(dt.datetime(2020, 1, 1, 0, 0, 0, 500), "2020-01-01T00:00:01.5Z")
    assert spec.to_wire() == (("2020-01-01T00:00:00Z", "2020-01-01T00:00:01Z"),)


@pytest.mark.parametrize(
    ("unit", "labels"),
    [
        ("D", (1650, 6, 15)),
        ("h", (1650, 6, 15, 13)),
        ("m", (1650, 6, 15, 13, 45)),
        ("s", (1650, 6, 15, 13, 45, 30)),
        ("ms", (1650, 6, 15, 13, 45, 30)),
        ("us", (1650, 6, 15, 13, 45, 30)),
    ],
)
def test_datetime64_is_read_through_its_iso_text(unit, labels):
    value = np.datetime64("1650-06-15T13:45:30", "s").astype(f"datetime64[{unit}]")
    assert interval(value, None).intervals[0].start == key(*labels)


def test_nat_numbers_and_coarse_datetime64_are_rejected():
    for value in (np.datetime64("NaT", "D"), np.datetime64("2020", "Y")):
        with pytest.raises(ValueError):
            interval(value, None)
    with pytest.raises(TypeError):
        interval(45000, None)


# ---- fixture 12: untimed rules and queries ----------------------------------------
def test_fixture_12_untimed_rules_and_queries():
    assert parse_time(None) is None  # (a) an untimed rule matches always
    year = interval("2020-01-01", "2020-12-31")  # (b) untimed rule, query 2020
    assert overlap(None, year).to_wire() == (("2020-01-01", "2020-12-31"),)
    assert time_fraction(overlap(None, year), year) == 1.0
    rule = parse_time({"interval": ["2000-01-01", "2006-12-31"]})  # (c) own periods
    assert rule.to_wire() == (("2000-01-01", "2006-12-31"),)
    cru_ts = interval("1901-01-01", "2022-12-31")  # (d) a query over CRU TS's period
    found = overlap(rule, cru_ts)
    assert found.to_wire() == (("2000-01-01", "2006-12-31"),)
    assert time_fraction(found, cru_ts) == pytest.approx(2557 / 44560)
    assert round(time_fraction(found, cru_ts), 4) == 0.0574


# ---- fixture 13: open and inclusive ends ------------------------------------------
def test_fixture_13_open_ends():
    rule = parse_time({"interval": ["2000-01-01", ".."]})
    query = interval("1991-01-01", "2020-12-31")
    found = overlap(rule, query)
    assert found.to_wire() == (("2000-01-01", "2020-12-31"),)
    assert time_fraction(found, query) == pytest.approx(7671 / 10958)
    assert round(time_fraction(found, query), 3) == 0.700
    future = parse_time({"interval": ["2030-01-01", ".."]})
    assert overlap(rule, future).to_wire() == (("2030-01-01", ".."),)
    assert time_fraction(overlap(rule, future), future) is None
    assert overlap(rule, parse_time({"interval": ["..", "1999-12-31"]})) is None


def test_fixture_13_inclusive_ends():
    rule = parse_time({"interval": ["2000-01-01", "2006-12-31"]})
    assert overlaps(rule, parse_time({"timestamp": "2006-12-31T23:59:59Z"}))
    assert not overlaps(rule, parse_time({"date": "2007-01-01"}))


def test_a_window_inside_a_month():
    month = interval("2020-01-01", "2020-01-31")
    found = overlap(parse_time({"interval": ["2020-01-20", "2020-01-25"]}), month)
    assert found.to_wire() == (("2020-01-20", "2020-01-25"),)
    assert time_fraction(found, month) == pytest.approx(6 / 31)
    assert overlap(parse_time({"date": "2020-02-01"}), month) is None


# ---- fixture 14: month recurrence -------------------------------------------------
def test_fixture_14_month_recurrence_wraps_the_year_end():
    rule = parse_time(None, recurrence={"months": [12, 1, 2]})
    assert rule.months == frozenset({12, 1, 2})
    query = interval("2020-11-15", "2021-03-10")
    found = overlap(rule, query)
    assert found.to_wire() == (("2020-12-01", "2021-02-28"),)
    assert time_fraction(found, query) == pytest.approx(90 / 116)
    assert round(time_fraction(found, query), 3) == 0.776
    assert overlap(rule, interval("2021-06-01", "2021-08-31")) is None


def test_recurrence_over_cru_ts_gives_123_runs():
    rule = parse_time(None, recurrence={"months": [12, 1, 2]})
    assert len(overlap(rule, interval("1901-01-01", "2022-12-31")).intervals) == 123


def test_recurrence_reaches_the_last_month_of_year_9999():
    december = parse_time(None, recurrence={"months": [12]})
    found = overlap(december, interval("9999-11-01", "9999-12-31"))
    assert found.to_wire() == (("9999-12-01", "9999-12-31"),)


def test_recurrence_against_an_open_query_is_not_expanded():
    rule = parse_time({"interval": ["2000-01-01", ".."]}, recurrence={"months": [7]})
    found = overlap(rule, parse_time({"interval": ["2010-03-01", ".."]}))
    assert found.to_wire() == (("2010-03-01", ".."),)
    assert found.months == frozenset({7})


@pytest.mark.parametrize(
    "recurrence", [{"months": [1, 1]}, {"months": "12"}, {"days": [1]}, [12, 1, 2]]
)
def test_bad_recurrences_are_rejected(recurrence):
    with pytest.raises(ValueError):
        parse_time(None, recurrence=recurrence)


# ---- parse_time ----------------------------------------------------------------------
def test_parse_time_forms():
    assert parse_time({"date": "2020-01-09"}).intervals == (
        Interval(key(2020, 1, 9), key(2020, 1, 10)),
    )
    assert parse_time({"timestamp": "2020-01-09T06:00:00Z"}).intervals[0].precision == (
        "second"
    )
    assert parse_time({"interval": ["..", ".."]}) is None
    months_only = parse_time(None, recurrence={"months": [6]})
    assert months_only.intervals == (Interval(None, None),)


def test_periods_are_a_union_inside_the_time_member():
    spec = parse_time(
        {"interval": ["2000-01-01", "2010-12-31"]},
        periods=[
            ["2005-01-01", "2005-12-31"],
            ["2000-01-01", "2000-01-31"],
            ["2000-02-01", "2000-02-10"],
        ],
        code="X001",  # other record properties are ignored
    )
    assert spec.to_wire() == (
        ("2000-01-01", "2000-02-10"),
        ("2005-01-01", "2005-12-31"),
    )
    with pytest.raises(ValueError, match="outside"):
        parse_time({"date": "2000-01-01"}, periods=[["2000-01-01", "2000-01-02"]])
    with pytest.raises(ValueError, match="time member"):
        parse_time(None, periods=[["2000-01-01", "2000-01-02"]])


def test_time_start_and_time_end_are_a_fallback():
    assert parse_time(None, time_start="2000-01-01").to_wire() == (
        ("2000-01-01", ".."),
    )
    both = parse_time(None, time_start="2000-01-01", time_end="2000-12-31")
    assert both == interval("2000-01-01", "2000-12-31")
    with pytest.raises(ValueError):
        parse_time({"date": "2000-01-01"}, time_start="2000-01-01")


@pytest.mark.parametrize(
    "member",
    [
        {"interval": ["2000-01-01", "2000-12-31T00:00:00Z"]},  # mixed precision
        {"date": "2000-01-01", "timestamp": "2000-01-01T00:00:00Z"},  # two members
        {"date": "2000-01-01T00:00:00Z"},  # a timestamp written as a date
        {"timestamp": "2000-01-01"},  # a date written as a timestamp
        {"date": ".."},
        {"interval": ["2001-01-01", "2000-01-01"]},  # out of order
        {"instant": "2000-01-01"},
    ],
)
def test_invalid_time_members_are_rejected(member):
    with pytest.raises(ValueError):
        parse_time(member)


# ---- TimeSpec and Interval -------------------------------------------------------------
def test_timespec_sorts_and_merges_touching_intervals():
    late = Interval(key(2020, 3, 1), key(2020, 4, 1))
    early = Interval(key(2020, 1, 1), key(2020, 3, 1))
    assert TimeSpec((late, early)).intervals == (
        Interval(key(2020, 1, 1), key(2020, 4, 1)),
    )
    unbounded = TimeSpec((late, Interval(None, key(2020, 1, 1)), early))
    assert unbounded.intervals == (Interval(None, key(2020, 4, 1)),)


def test_timespec_and_interval_checks():
    with pytest.raises(ValueError):
        TimeSpec(())
    with pytest.raises(ValueError):
        TimeSpec((Interval(None, None),), months={13})
    with pytest.raises(ValueError):
        Interval(key(2020, 1, 2), key(2020, 1, 1))
    with pytest.raises(ValueError, match="midnight"):
        Interval(key(2020, 1, 1, 6), key(2020, 1, 2))
    with pytest.raises(TypeError):
        Interval(1.5, None, "second")
    assert hash(interval("2020-01-01", "2020-01-31")) == hash(
        interval("2020-01-01", "2020-01-31")
    )


def test_time_fraction_expands_months_on_the_part():
    query = TimeSpec(
        interval("2020-11-15", "2021-03-10").intervals, frozenset({12, 1, 2})
    )
    assert time_fraction(query, query) == 1.0
    assert time_fraction(overlap(None, query), query) == 1.0
