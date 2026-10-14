"""Dimension plugins (Axis, Labels, Versions) and the core objects of queryearth.objects.

The Registry-level parts of fixtures 17, 20, 21 and 27 are in test_registry.py; this
file checks the plugins one rule value against one query value.
"""

import logging
import math

import pytest

import queryearth as qe
from queryearth import space as sp

AXIS = qe.Axis("resolution", "km", "horizontal grid spacing")


# ---- Axis ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("bounds", "query", "expected"),
    [
        ({"lt": 10.0}, 8.0, qe.AxisOverlap(8.0, 8.0, True, True)),
        ({"lt": 10.0}, (8.0, 12.0), qe.AxisOverlap(8.0, 10.0, True, False)),
        ({"lt": 10.0}, 10.0, None),  # strict bound
        ({"le": 10.0}, 10.0, qe.AxisOverlap(10.0, 10.0, True, True)),
        ({"ge": 25.0}, (8.0, 30.0), qe.AxisOverlap(25.0, 30.0, True, True)),
        ({"gt": 0.0}, (8.0, 12.0), qe.AxisOverlap(8.0, 12.0, True, True)),
        ({"gt": 1.0, "le": 2.0}, (0.0, 1.0), None),
    ],
)
def test_axis_match_keeps_open_ends(bounds, query, expected):
    found = AXIS.match(AXIS.parse_rule(bounds), AXIS.parse_query(query))
    assert (found and found.overlap) == expected


def test_axis_fraction_is_the_share_of_the_query_range():
    found = AXIS.match(AXIS.parse_rule({"lt": 10.0}), (8.0, 12.0))
    assert found.fraction == 0.5


def test_axis_extent_reports_the_rule_interval_with_open_infinite_ends():
    rule = AXIS.parse_rule({"lt": 10})
    assert AXIS.extent(rule) == qe.AxisOverlap(-math.inf, 10.0, False, False)


@pytest.mark.parametrize(
    "bounds",
    [
        {"lt": 10, "unit": "deg"},  # fixture 17: the unit must equal the declared one
        {"gt": 1, "ge": 1},
        {"lt": 1, "le": 1},
        {"unit": "km"},
        {"below": 1},
        {"gt": 5, "lt": 5},
        {"lt": "ten"},
        [10],
    ],
)
def test_axis_rejects_bad_bounds(bounds):
    with pytest.raises(ValueError):
        AXIS.parse_rule(bounds)


@pytest.mark.parametrize("value", [(2.0, 1.0), (1.0, 2.0, 3.0), float("nan"), "8"])
def test_axis_rejects_bad_query_values(value):
    with pytest.raises(ValueError):
        AXIS.parse_query(value)


# ---- Labels -------------------------------------------------------------------------
LABELS = qe.Labels("variable")


@pytest.mark.parametrize(
    ("rule", "query", "hits"),
    [
        (["pre"], ("pre",), ("pre",)),
        ("pre", ("pre", "tas"), ("pre",)),  # a bare string is a one-item list
        (["Pre"], ("pre",), None),  # case-sensitive
        (["t*"], ("pre", "tas", "t2m"), ("tas", "t2m")),
        ({"none_of": ["tp"]}, ("tp",), None),  # fixture 20
        ({"none_of": ["tp"]}, ("tp", "t2m"), ("t2m",)),
        ({"any_of": ["t*"], "none_of": ["tp"]}, ("tp", "tas"), ("tas",)),
        (["*"], ("anything",), ("anything",)),
    ],
)
def test_labels_match_globs_and_exclusions(rule, query, hits):
    found = LABELS.match(LABELS.parse_rule(rule), LABELS.parse_query(query))
    assert (found and found.overlap) == hits


@pytest.mark.parametrize("rule", [[], {}, {"all_of": ["x"]}, [""], [1], {"any_of": []}])
def test_labels_reject_bad_patterns(rule):
    with pytest.raises(ValueError):
        LABELS.parse_rule(rule)


def test_labels_query_values_are_deduplicated_in_order():
    assert LABELS.parse_query(("b", "a", "b")) == ("b", "a")


# ---- Versions (fixture 21) ----------------------------------------------------------
VERSIONS = qe.Versions("version")


def matches(rule, version):
    return VERSIONS.match(VERSIONS.parse_rule(rule), (version,)) is not None


@pytest.mark.parametrize(
    ("version", "expected"),
    [
        ("4.07", True),
        ("4.7", True),
        ("4.08", True),
        ("4.09", False),
        ("4.9", False),
        ("4.10", False),
        ("3.26", False),
    ],
)
def test_fixture_21_introduced_and_fixed(version, expected):
    assert matches({"introduced": "4.00", "fixed": "4.09"}, version) is expected


def test_fixture_21_last_affected_exact_and_padded():
    assert matches({"last_affected": "4.08"}, "4.08")
    assert not matches({"last_affected": "4.08"}, "4.09")
    assert matches({"versions": ["ERA5T"]}, "ERA5T")
    assert not matches({"versions": ["ERA5T"]}, "ERA5.1")
    assert matches({"versions": ["4.07"]}, "4.7")
    assert matches({"versions": ["4.07"]}, "4.7.0")


def test_versions_union_of_ranges_and_non_dotted_queries():
    rule = [{"introduced": "1.0", "fixed": "2.0"}, {"versions": ["ERA5"]}]
    assert matches(rule, "1.5") and matches(rule, "ERA5")
    assert not matches(rule, "2.0")
    assert not matches({"introduced": "1.0"}, "ERA5")  # never inside a range


@pytest.mark.parametrize(
    "rule",
    [
        {"introduced": "4.07a"},  # fixture 21: a bound must be a dotted integer
        {"fixed": "1", "last_affected": "1"},
        {},
        {"since": "1"},
        "4.07",
        [],
    ],
)
def test_versions_reject_bad_ranges(rule):
    with pytest.raises(ValueError):
        VERSIONS.parse_rule(rule)


def test_built_in_plugins_are_dimensions():
    for plugin in (AXIS, LABELS, VERSIONS):
        assert isinstance(plugin, qe.Dimension)


# ---- core objects -------------------------------------------------------------------
def test_levels_default_by_kind_and_accept_level_names():
    def level(kind, **given):
        return qe.Outcome(code="X001", kind=kind, title="t", message="m", **given).level

    assert [level(k) for k in ("warning", "suggestion")] == [30, 20]
    assert level("warning", level="Error") == logging.ERROR
    assert level("suggestion", level=logging.CRITICAL) == 50
    with pytest.raises(ValueError):
        level("warning", level="severe")


def test_finding_str_is_the_text_to_log():
    def finding(code, **fields):
        return qe.Finding(
            code=code, kind="warning", title=f"{code} title", message="m", **fields
        )

    assert str(finding("CROC102")) == "[CROC102] CROC102 title (draft)"
    assert str(finding("CRU001", query_label="lake 1234", area_fraction=1.0)) == (
        "[CRU001] CRU001 title (lake 1234; area 100%; draft)"
    )
    assert str(finding("ERA5-023", time_overlap=[("2007-10-01", "2013-12-31")])) == (
        "[ERA5-023] ERA5-023 title (2007-10-01..2013-12-31; draft)"
    )
    assert str(finding("CRU004", status="reviewed")) == "[CRU004] CRU004 title"


def test_query_accepts_shorthands():
    query = qe.Query(
        time=("2020-01-01", "2020-12-31"),
        dimensions={"resolution": 8, "variable": "pre"},
    )
    assert query.dimensions == {"resolution": 8, "variable": "pre"}  # kept as given
    assert AXIS.parse_query(8) == (8.0, 8.0)  # and parsed by the dimension
    assert LABELS.parse_query("pre") == ("pre",)
    assert query.time.to_wire() == (("2020-01-01", "2020-12-31"),)
    assert qe.Query(time={"date": "2007-01-01"}).time.to_wire() == (
        ("2007-01-01", "2007-01-01"),
    )


def test_objects_with_mappings_compare_by_value_but_do_not_hash():
    assert qe.Query(dimensions={"model": ["mom6"]}) == qe.Query(
        dimensions={"model": ["mom6"]}
    )
    with pytest.raises(TypeError):
        hash(qe.Query())
    with pytest.raises(TypeError):
        hash(qe.Scope())


@pytest.mark.parametrize(
    "build",
    [
        lambda: qe.Outcome(code="X001", kind="note", title="t", message="m"),
        lambda: qe.Outcome(
            code="X001", kind="warning", title="t", message="m", min_overlap=2
        ),
    ],
)
def test_constructors_reject_bad_values(build):
    with pytest.raises((TypeError, ValueError)):
        build()


def test_rule_requires_suggestions_for_a_suggestion():
    with pytest.raises(ValueError):
        qe.Rule(code="X001", kind="suggestion", title="t", message="m")
    with pytest.raises(ValueError):
        qe.Rule(code="X001", kind="coverage", title="t", message="m")


def test_finding_to_dict_is_json_ready():
    finding = qe.Finding(
        code="CROC102",
        kind="suggestion",
        title="t",
        message="m",
        suggestions=({"target": "MOM_input", "key": "DT", "value": 240.0},),
        time_overlap=[("2020-01-01", "..")],
        dimensions={
            "resolution": qe.DimMatch(qe.AxisOverlap(-math.inf, 10.0, False, False)),
            "basin": qe.DimMatch(("14",), 1.0),
        },
    )
    out = finding.to_dict()
    assert out["level"] == logging.INFO
    assert out["suggestions"] == [
        {"target": "MOM_input", "key": "DT", "value": 240.0, "rationale": ""}
    ]
    assert out["time_overlap"] == [["2020-01-01", ".."]]
    assert out["dimensions"]["resolution"] == {
        "overlap": {"lo": None, "hi": 10.0, "lo_closed": False, "hi_closed": False},
        "fraction": None,
    }
    assert out["dimensions"]["basin"] == {"overlap": ["14"], "fraction": 1.0}
    assert out["code"] == "CROC102"


def test_rule_from_feature_needs_properties_and_a_geometry():
    with pytest.raises(ValueError, match="properties and a geometry"):
        qe.Rule.from_feature({"type": "Feature"})


def test_space_and_time_are_built_in_dimensions():
    from queryearth.dimensions import SpaceDimension, TimeDimension

    assert list(qe.Registry("x")._dimensions) == ["space", "time"]
    space, time = SpaceDimension(), TimeDimension()
    square = sp.box(0, 0, 2, 2)
    assert space.match(None, square).fraction == 1.0  # unconstrained: measured only
    assert space.match(sp.box(10, 10, 12, 12), square) is None
    half = space.match(sp.box(0, 0, 1, 2), square)
    assert half.fraction == pytest.approx(0.5) and half.overlap > 0
    year = qe.interval("2000-01-01", "2000-12-31")
    january = qe.interval("2000-01-01", "2000-01-31")
    assert time.match(january, year).overlap == (("2000-01-01", "2000-01-31"),)
    assert time.match(january, year).fraction == pytest.approx(31 / 366)
    assert time.match(qe.interval("2001-01-01", ".."), year) is None
    assert time.extent(january) == (("2000-01-01", "2000-01-31"),)
