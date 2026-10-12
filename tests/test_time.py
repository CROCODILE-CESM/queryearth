"""queryearth.time: fixtures 11 to 16 of docs/reference/fixtures.md, and edge cases.

Fixtures 11 to 16 need no Index, so each is tested on the operations its
expected findings rely on: overlap(), time_fraction() and the wire form.
"""

import datetime as dt
import random

import numpy as np
import pytest

from queryearth.time import (
    DAY,
    Interval,
    TimeSpec,
    civil_fields,
    civil_key,
    from_bounds,
    interval,
    overlap,
    overlaps,
    parse_time,
    time_fraction,
)

key = civil_key


class Stamp(dt.datetime):
    """Stands in for pandas.Timestamp, a datetime subclass with nanoseconds."""

    nanosecond = 0


class CfDate:
    """Stands in for a cftime object: civil fields plus calendar and year zero."""

    def __init__(self, calendar, has_year_zero, y, m, d, h=0, mi=0, s=0):
        self.calendar, self.has_year_zero = calendar, has_year_zero
        self.year, self.month, self.day = y, m, d
        self.hour, self.minute, self.second, self.microsecond = h, mi, s, 0


# ---- civil keys -------------------------------------------------------------------
def test_civil_key_sorts_like_the_tuple_including_negative_years():
    rng = random.Random(1)
    labels = [
        (
            rng.randint(-30000, 30000),
            rng.randint(1, 12),
            rng.randint(1, 31),
            rng.randint(0, 23),
            rng.randint(0, 59),
            rng.randint(0, 59),
        )
        for _ in range(5000)
    ]
    assert sorted(labels) == sorted(labels, key=lambda t: civil_key(*t))
    assert all(civil_fields(civil_key(*t)) == t for t in labels)


def test_end_slots_need_no_month_lengths():
    assert key(2020, 1, 9) + DAY == key(2020, 1, 10)
    assert key(2020, 1, 31) + DAY == key(2020, 1, 32) == key(2020, 2, 0)
    assert key(2020, 12, 31) + DAY == key(2021, 0, 0)
    assert civil_fields(key(2020, 1, 32)) == (2020, 2, 0, 0, 0, 0)


def test_360_day_february_30_sorts_between_29_february_and_1_march():
    assert key(2000, 2, 29) < key(2000, 2, 30) < key(2000, 3, 1)


@pytest.mark.parametrize("labels", [(2020, 13, 1), (2020, 1, 33), (2020, 1, 1, 24)])
def test_civil_key_rejects_out_of_range_labels(labels):
    with pytest.raises(ValueError):
        civil_key(*labels)


# ---- wire form and precision ------------------------------------------------------
def test_closed_wire_ends_become_half_open_keys():
    assert interval("2020-01-09", "2020-01-09").intervals == (
        Interval(key(2020, 1, 9), key(2020, 1, 10)),
    )
    assert interval("2020-01-01", "2020-01-31").intervals[0].end == key(2020, 2, 0)
    assert interval("2020-01-01", "2020-12-31").intervals[0].end == key(2021, 0, 0)
    stamp = interval("2020-01-09T06:00:00Z", "2020-01-09T06:00:00Z").intervals[0]
    assert stamp == Interval(key(2020, 1, 9, 6), key(2020, 1, 9, 6) + 1, "second")
    assert interval("..", "2020-01-09").intervals[0].start is None
    assert interval("2020-01-09", None).intervals[0].end is None


def test_wire_form_round_trips():
    spec = interval("2000-01-01", "2006-12-31")
    assert spec.to_wire() == (("2000-01-01", "2006-12-31"),)
    stamps = interval("2006-12-31T23:59:59Z", "2007-01-01T00:00:00Z")
    assert stamps.to_wire() == (("2006-12-31T23:59:59Z", "2007-01-01T00:00:00Z"),)
    assert interval("2030-01-01", "..").to_wire() == (("2030-01-01", ".."),)


@pytest.mark.parametrize(
    "text", ["2020-01", "2020-1-01", "2020-01-01T24:00:00Z", "2020-01-01T00:00:00"]
)
def test_malformed_wire_times_are_rejected(text):
    with pytest.raises(ValueError):
        interval(text, "2021-01-01")


def test_second_60_is_rejected_everywhere():
    with pytest.raises(ValueError, match="second 60"):
        interval("2016-12-31T23:59:60Z", "2017-01-01T00:00:00Z")
    with pytest.raises(ValueError, match="second 60"):
        civil_key(2016, 12, 31, 23, 59, 60)
    leap = CfDate("standard", False, 2016, 12, 31, 23, 59, 60)
    with pytest.raises(ValueError, match="second 60"):
        interval(leap, leap)


def test_dates_are_day_precision_and_datetimes_second_precision_even_at_midnight():
    assert (
        interval(dt.date(2020, 1, 1), dt.date(2020, 1, 9)).intervals[0].precision
        == "day"
    )
    days = np.datetime64("2020-01-01", "D")
    assert interval(days, days).intervals[0].precision == "day"
    midnight = dt.datetime(2020, 1, 9)
    spec = interval(midnight, midnight)
    assert spec.intervals[0] == Interval(key(2020, 1, 9), key(2020, 1, 9) + 1, "second")
    seconds = np.datetime64("2020-01-09T00:00:00", "s")
    assert interval(seconds, seconds).intervals[0].precision == "second"


def test_mixed_precision_is_written_with_timestamps_at_both_ends():
    spec = interval(dt.date(2020, 1, 1), dt.datetime(2020, 1, 9, 12))
    assert spec.intervals[0].precision == "second"
    assert spec.to_wire() == (("2020-01-01T00:00:00Z", "2020-01-09T12:00:00Z"),)


def test_aware_datetimes_are_converted_to_utc():
    plus5 = dt.timezone(dt.timedelta(hours=5))
    spec = interval(dt.datetime(2020, 1, 1, 5, tzinfo=plus5), "2020-01-02")
    assert spec.intervals[0].start == key(2020, 1, 1)


@pytest.mark.parametrize(
    ("unit", "labels"),
    [
        ("Y", (1650, 1, 1, 0, 0, 0)),
        ("M", (1650, 6, 1, 0, 0, 0)),
        ("D", (1650, 6, 15, 0, 0, 0)),
        ("h", (1650, 6, 15, 13, 0, 0)),
        ("s", (1650, 6, 15, 13, 45, 30)),
        ("ms", (1650, 6, 15, 13, 45, 30)),
        ("us", (1650, 6, 15, 13, 45, 30)),
    ],
)
def test_datetime64_is_read_in_its_own_unit(unit, labels):
    value = np.datetime64("1650-06-15T13:45:30", "s").astype(f"datetime64[{unit}]")
    assert civil_fields(interval(value, None).intervals[0].start) == labels


def test_nat_and_numbers_are_rejected():
    with pytest.raises(ValueError):
        interval(np.datetime64("NaT", "D"), None)
    with pytest.raises(TypeError):
        interval(45000, None)


# ---- fixture 11: time bounds, not stamps ------------------------------------------
def test_fixture_11_bounds_not_stamps():
    month = from_bounds(["2020-01-01T00:00:00Z"], ["2020-02-01T00:00:00Z"])
    assert month.to_wire() == (("2020-01-01", "2020-01-31"),)
    assert month.intervals[0].precision == "day"
    window = parse_time({"interval": ["2020-01-20", "2020-01-25"]})
    first_of_february = parse_time({"date": "2020-02-01"})
    found = overlap(window, month)
    assert found.to_wire() == (("2020-01-20", "2020-01-25"),)
    assert time_fraction(found, month) == pytest.approx(6 / 31)
    assert round(time_fraction(found, month), 3) == 0.194
    assert overlap(first_of_february, month) is None
    stamp = interval(dt.datetime(2020, 1, 16), dt.datetime(2020, 1, 16))
    assert not overlaps(window, stamp) and not overlaps(first_of_february, stamp)


def _check_midnight_pair(start, end):
    ninth = parse_time({"date": "2020-01-09"})
    closed = interval(start, end)
    assert closed.to_wire() == (("2020-01-01T00:00:00Z", "2020-01-09T00:00:00Z"),)
    assert overlaps(ninth, closed)
    bounds = from_bounds([start], [end])
    assert bounds.to_wire() == (("2020-01-01", "2020-01-08"),)
    assert not overlaps(ninth, bounds)


def test_fixture_11_midnight_datetimes_in_interval_and_from_bounds():
    _check_midnight_pair(Stamp(2020, 1, 1), Stamp(2020, 1, 9))


def test_fixture_11_midnight_pandas_timestamps():
    pd = pytest.importorskip("pandas")
    _check_midnight_pair(pd.Timestamp("2020-01-01"), pd.Timestamp("2020-01-09"))


# ---- fixture 12: untimed rules and queries ----------------------------------------
def test_fixture_12_untimed_rules_and_queries():
    assert parse_time(None) is None  # (a) an untimed rule matches always
    year = interval("2020-01-01", "2020-12-31")  # (b) untimed rule, query 2020
    assert overlap(None, year).to_wire() == (("2020-01-01", "2020-12-31"),)
    assert time_fraction(overlap(None, year), year) == 1.0
    rule = parse_time({"interval": ["2000-01-01", "2006-12-31"]})  # (c) own periods
    assert rule.to_wire() == (("2000-01-01", "2006-12-31"),)
    cru_ts = interval("1901-01-01", "2022-12-31")  # (d) the product's coverage
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


def test_recurrence_against_an_open_query_is_not_expanded():
    rule = parse_time({"interval": ["2000-01-01", ".."]}, recurrence={"months": [7]})
    found = overlap(rule, parse_time({"interval": ["2010-03-01", ".."]}))
    assert found.to_wire() == (("2010-03-01", ".."),)
    assert found.months == frozenset({7})


# ---- fixture 15: calendars --------------------------------------------------------
def test_fixture_15_dates_are_validated_in_their_calendar():
    with pytest.raises(ValueError, match="noleap"):
        parse_time({"date": "2004-02-29"}, calendar="noleap")
    assert parse_time({"date": "2001-02-30"}, calendar="360_day") is not None
    with pytest.raises(ValueError, match="360_day"):
        parse_time({"date": "2001-01-31"}, calendar="360_day")


def test_fixture_15_calendars_compare_as_civil_labels():
    rule = parse_time({"interval": ["2000-02-01", "2000-02-30"]}, calendar="360_day")
    gregorian = parse_time({"date": "2000-02-29"})
    assert overlap(rule, gregorian).to_wire() == (("2000-02-29", "2000-02-29"),)
    year = interval("2000-01-01", "2000-12-30", calendar="360_day")
    assert time_fraction(overlap(rule, year), year) == pytest.approx(30 / 360)
    assert round(time_fraction(overlap(rule, year), year), 4) == 0.0833


@pytest.mark.parametrize(
    ("calendar", "date", "valid"),
    [
        ("proleptic_gregorian", "2000-02-29", True),
        ("standard", "1900-02-29", False),
        ("gregorian", "2000-02-30", False),
        ("julian", "1900-02-29", True),
        ("julian", "1901-02-29", False),
        ("noleap", "2000-02-29", False),
        ("365_day", "2001-01-31", True),
        ("all_leap", "2001-02-29", True),
        ("366_day", "2001-02-30", False),
        ("360_day", "2001-02-30", True),
        ("360_day", "2001-03-31", False),
    ],
)
def test_calendar_table(calendar, date, valid):
    if valid:
        assert parse_time({"date": date}, calendar=calendar) is not None
    else:
        with pytest.raises(ValueError):
            parse_time({"date": date}, calendar=calendar)


def test_unknown_calendar_is_rejected():
    with pytest.raises(ValueError, match="calendar"):
        parse_time({"date": "2000-01-01"}, calendar="none")


def test_standard_durations_stop_before_the_gregorian_reform():
    early = interval("1500-01-01", "1500-12-31", calendar="standard")  # Q19
    assert time_fraction(early, early) is None
    assert time_fraction(early, interval("1500-01-01", "1500-12-31")) == 1.0
    late = interval("1582-10-15", "1582-12-31", calendar="standard")
    assert time_fraction(late, late) == 1.0


def test_julian_durations_use_the_julian_day_table():
    year = interval("1500-01-01", "1500-12-31", calendar="julian")  # Q20
    february = parse_time({"interval": ["1500-02-01", "1500-02-29"]}, calendar="julian")
    assert time_fraction(overlap(february, year), year) == pytest.approx(29 / 366)


# ---- fixture 16: years outside the usual ranges -----------------------------------
def test_fixture_16_long_ranges():
    rule = parse_time({"interval": ["1600-01-01", "1700-12-31"]})
    day = np.datetime64("1650-06-15", "D")
    assert overlaps(rule, interval(day, day))
    far = parse_time({"interval": ["10000-01-01", ".."]})
    assert overlaps(far, interval("12000-01-01", "12000-12-31"))
    early = parse_time({"interval": ["..", "-4000-12-31"]})
    query = parse_time({"date": "-5000-06-01"})
    assert overlaps(early, query)
    assert query.to_wire() == (("-5000-06-01", "-5000-06-01"),)


def _check_year_zero(julian_1bc, gregorian_minus_1):
    rule = parse_time({"interval": ["0000-01-01", "0000-12-31"]}, calendar="julian")
    assert overlaps(rule, interval(julian_1bc, julian_1bc))
    assert not overlaps(rule, interval(gregorian_minus_1, gregorian_minus_1))


def test_fixture_16_year_zero_by_duck_typing():
    _check_year_zero(
        CfDate("julian", False, -1, 6, 1),
        CfDate("proleptic_gregorian", True, -1, 6, 1),
    )


@pytest.mark.filterwarnings("ignore::UserWarning")  # cftime: BC years are not CF
def test_fixture_16_year_zero_with_cftime():
    cftime = pytest.importorskip("cftime")
    _check_year_zero(
        cftime.DatetimeJulian(-1, 6, 1),
        cftime.DatetimeProlepticGregorian(-1, 6, 1),
    )


def test_cftime_calendars_are_taken_and_checked():
    spec = interval(
        CfDate("noleap", True, 2001, 1, 1), CfDate("365_day", True, 2001, 12, 31)
    )
    assert spec.calendar == "noleap"
    with pytest.raises(ValueError):
        interval(
            CfDate("noleap", True, 2001, 1, 1), CfDate("360_day", True, 2001, 1, 2)
        )
    with pytest.raises(ValueError):
        interval(CfDate("noleap", True, 2001, 1, 1), None, calendar="360_day")


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
        {"interval": ["2001-01-01", "2000-01-01"]},  # out of order
        {"instant": "2000-01-01"},
    ],
)
def test_invalid_time_members_are_rejected(member):
    with pytest.raises(ValueError):
        parse_time(member)


# ---- from_bounds ---------------------------------------------------------------------
def test_from_bounds_merges_consecutive_steps_and_keeps_gaps():
    starts = np.array(["2020-01-01", "2020-02-01", "2020-04-01"], dtype="datetime64[D]")
    ends = np.array(["2020-02-01", "2020-03-01", "2020-05-01"], dtype="datetime64[D]")
    assert from_bounds(starts, ends).to_wire() == (
        ("2020-01-01", "2020-02-29"),
        ("2020-04-01", "2020-04-30"),
    )


def test_from_bounds_off_midnight_is_second_precision():
    spec = from_bounds(["2020-01-01T06:00:00Z"], ["2020-02-01T06:00:00Z"])
    assert spec.to_wire() == (("2020-01-01T06:00:00Z", "2020-02-01T05:59:59Z"),)


def test_from_bounds_rejects_bad_bounds():
    with pytest.raises(ValueError):
        from_bounds(["2020-02-01"], ["2020-01-01"])
    with pytest.raises(ValueError):
        from_bounds(["2020-01-01", "2020-02-01"], ["2020-02-01"])


# ---- TimeSpec and Interval -------------------------------------------------------------
def test_timespec_sorts_and_merges_touching_intervals():
    late = Interval(key(2020, 3, 1), key(2020, 4, 1))
    early = Interval(key(2020, 1, 1), key(2020, 3, 1))
    assert TimeSpec((late, early)).intervals == (
        Interval(key(2020, 1, 1), key(2020, 4, 1)),
    )


def test_timespec_and_interval_checks():
    with pytest.raises(ValueError):
        TimeSpec(())
    with pytest.raises(ValueError):
        TimeSpec((Interval(None, None),), months={13})
    with pytest.raises(ValueError):
        Interval(key(2020, 1, 2), key(2020, 1, 1))
    with pytest.raises(ValueError, match="midnight"):
        Interval(key(2020, 1, 1, 6), key(2020, 1, 2))
    assert hash(interval("2020-01-01", "2020-01-31")) == hash(
        interval("2020-01-01", "2020-01-31")
    )
