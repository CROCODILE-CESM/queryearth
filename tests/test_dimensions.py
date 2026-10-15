"""Dimensions: Axis, time, Labels, and defining a dimension of your own."""

import datetime
from types import SimpleNamespace

import numpy as np
import pytest

import queryearth as qe

resolution = qe.Axis("resolution", "km")
time = qe.TimeDimension()
product = qe.Labels("product")


def axis_matches(rule, query):
    return resolution.matches(
        resolution.parse_rule(rule), resolution.parse_query(query)
    )


def time_matches(rule, query):
    return qe.interval(*rule).meets(qe.interval(*query))


# ---- Axis -------------------------------------------------------------------------
def test_axis_bounds_are_strict_or_inclusive():
    assert not axis_matches({"gt": 10}, 10) and axis_matches({"gt": 10}, 10.5)
    assert axis_matches({"le": 10}, 10) and not axis_matches({"lt": 10}, 10)


def test_an_axis_range_in_a_query_matches_when_it_overlaps():
    assert axis_matches({"lt": 8}, (2, 9))  # a grid from 2 km to 9 km
    assert not axis_matches({"lt": 8}, (8, 12))
    assert axis_matches({"gt": 2, "le": 10}, (10, 20))


def test_an_axis_range_in_another_unit_is_refused():
    with pytest.raises(ValueError, match="converts no units"):
        resolution.parse_rule({"lt": 10, "unit": "deg"})


def test_axis_ranges_that_hold_no_number_are_refused():
    for bad in ({"gt": 5, "lt": 5}, {}, {"gt": 1, "ge": 2}, {"lt": "8"}, [{"lt": 8}]):
        with pytest.raises(ValueError):
            resolution.parse_rule(bad)


# ---- time -------------------------------------------------------------------------
def test_an_end_date_covers_its_whole_day():
    years = ("2000-01-01", "2006-12-31")
    assert time_matches(years, ("2006-12-31T23:59:59", "2006-12-31T23:59:59"))
    assert not time_matches(years, ("2007-01-01", "2007-01-01"))


def test_an_open_end_reaches_forever():
    assert time_matches(("2000-01-01", ".."), ("2030-01-01", "2030-12-31"))
    assert not time_matches(("..", "1999-12-31"), ("2000-01-01", "2000-01-31"))


def test_times_come_from_strings_dates_numpy_and_cftime_like_objects():
    noleap = SimpleNamespace(year=2020, month=1, day=9, hour=6, minute=0, second=0)
    for end in ("2020-01-09T06:00:00", np.datetime64("2020-01-09T06:00"), noleap):
        days = qe.interval(datetime.date(2020, 1, 1), end)
        assert days.to_wire() == ("2020-01-01T00:00:00Z", "2020-01-09T06:00:00Z")


def test_a_rule_file_time_reads_back_as_written():
    member = {"interval": ["2000-01-01", ".."]}
    assert time.parse_rule(member).to_json() == member


def test_impossible_times_are_refused():
    with pytest.raises(ValueError):
        qe.interval("2021-02-29", "2021-03-01")  # not a leap year
    with pytest.raises(ValueError):
        qe.interval("2020-01-02", "2020-01-01")


# ---- Labels -------------------------------------------------------------------------
def test_labels_match_names_and_wildcards_case_sensitively():
    rule = product.parse_rule(["glorys", "era5*"])
    assert product.matches(rule, product.parse_query("era5_land"))
    assert product.matches(rule, product.parse_query(["cesm", "glorys"]))
    assert not product.matches(rule, product.parse_query("ERA5"))


def test_labels_are_non_empty_strings():
    for bad in ([], [""], 5, ["glorys", 5]):
        with pytest.raises(ValueError):
            product.parse_rule(bad)


# ---- a dimension of your own ----------------------------------------------------------
class Bathymetry(qe.Dimension):
    """The sea floor under a model: its depth in m and its slope in degrees,
    given together as one value."""

    name = "bathymetry"
    fields = {"depth": qe.Axis("depth", "m"), "slope": qe.Axis("slope", "degree")}

    def parse_rule(self, value):  # a range on either field: {"slope": {"gt": 5}}
        if not isinstance(value, dict) or not value or set(value) - set(self.fields):
            raise ValueError(f"a bathymetry rule bounds depth or slope, not {value!r}")
        return {k: self.fields[k].parse_rule(v) for k, v in value.items()}

    def parse_query(self, value):  # both fields: {"depth": 4000, "slope": 8}
        if not isinstance(value, dict) or set(value) != set(self.fields):
            raise ValueError(f"bathymetry gives depth and slope, not {value!r}")
        return {k: self.fields[k].parse_query(v) for k, v in value.items()}

    def matches(self, rule, query):
        return all(self.fields[k].matches(r, query[k]) for k, r in rule.items())


def test_a_dimension_of_your_own_takes_a_value_of_several_fields(tmp_path):
    registry = qe.Registry([Bathymetry()])
    steep = qe.Rule(
        "TOPO001",
        "Steep slopes",
        "Pressure-gradient errors grow over steep bathymetry.",
        scope={"bathymetry": {"slope": {"gt": 5}}},
    )
    registry.add(steep)
    assert registry.query(bathymetry={"depth": 4000, "slope": 8}) == [steep]
    assert registry.query(bathymetry={"depth": 4000, "slope": 2}) == []
    assert registry.query() == []  # the query leaves the bathymetry out
    with pytest.raises(ValueError, match="depth and slope"):
        registry.query(bathymetry={"slope": 8})

    registry.to_file(tmp_path / "bathymetry.geojson")
    again = qe.Registry.from_file(
        tmp_path / "bathymetry.geojson", dimensions=[Bathymetry()]
    )
    (rule,) = again.query(bathymetry={"depth": 200, "slope": 12})
    assert rule.to_feature()["properties"]["dimensions"] == {
        "bathymetry": {"slope": {"gt": 5}}
    }


def test_a_dimension_must_implement_all_three_methods():
    class OnlyMatches(qe.Dimension):
        name = "half"

        def matches(self, rule, query):
            return rule == query

    with pytest.raises(TypeError):
        OnlyMatches()
