"""Registry: fixtures 12 (Registry-level), 17, 19 to 21 and 27 of
docs/reference/fixtures.md; fixtures 2, 6, 9 and 13 as queries; computed rules,
codes and lifecycle; and the fast path against the reference.
"""

import logging
import random
from dataclasses import dataclass
from typing import Any

import numpy as np
import pytest
import shapely

import queryearth as qe
from queryearth import space as sp

LAKE = sp.box(0.30, 0.30, 0.45, 0.45)


def union(*spaces):
    """One rule space covering several areas."""
    return sp.polygon(shapely.union_all([s.geometry for s in spaces]))


def make_registry(**kw):
    """A resolution axis and the default facets."""
    return qe.Registry("test", axes=[qe.Axis("resolution", "km")], **kw)


def warning_rule(code, **scope):
    return qe.Rule(
        code=code, kind="warning", title=code, message=code, scope=qe.Scope(**scope)
    )


def codes(findings):
    return [f.code for f in findings]


# ---- fixture 12: untimed rules and queries -----------------------------------------
def test_fixture_12_untimed_rules_and_queries():
    registry = make_registry()
    registry.add(warning_rule("TST001"))
    registry.add(warning_rule("TST002", time=qe.interval("2000-01-01", "2006-12-31")))
    registry.add(
        warning_rule(
            "TST003",
            time=qe.interval("2000-01-01", "2006-12-31"),
            facets={"product": "cru_ts"},
        )
    )
    (a,) = registry.query()
    assert a.code == "TST001" and a.conditional_on == () and a.time_fraction is None
    (b,) = registry.query(time=("2020-01-01", "2020-12-31"))
    assert b.time_overlap == (("2020-01-01", "2020-12-31"),) and b.time_fraction == 1.0
    c = {f.code: f for f in registry.query(include_conditional=True)}
    assert c["TST002"].conditional_on == ("time",)
    assert c["TST002"].time_overlap == (("2000-01-01", "2006-12-31"),)
    cru_ts = ("1901-01-01", "2022-12-31")
    d = {f.code: f for f in registry.query(facets={"product": "cru_ts"}, time=cru_ts)}
    assert d["TST003"].conditional_on == ()
    assert d["TST003"].time_fraction == pytest.approx(2557 / 44560)
    assert round(d["TST003"].time_fraction, 4) == 0.0574


# ---- fixture 17: resolution only -----------------------------------------------------
def croc_registry():
    registry = make_registry()
    registry.add(
        qe.Rule(
            code="CROC101",
            kind="suggestion",
            title="Arctic domain: consider active sea ice",
            message="m",
            scope=qe.Scope(space=sp.box(-180, 66.5, 180, 90), facets={"model": "mom6"}),
            suggestions=(qe.Suggestion("compset", "ice_component", "CICE"),),
        )
    )
    registry.add(
        qe.Rule(
            code="CROC102",
            kind="suggestion",
            title="Eddy-resolving grid",
            message="m",
            scope=qe.Scope(axes={"resolution": {"lt": 10.0}}),
            suggestions=(qe.Suggestion("MOM_input", "THICKNESSDIFFUSE", False),),
        )
    )
    return registry


def test_fixture_17_resolution_only():
    registry = croc_registry()
    (only,) = registry.query(axes={"resolution": 8.0})
    assert only.code == "CROC102" and only.conditional_on == ()
    assert only.axes == {"resolution": qe.AxisOverlap(8.0, 8.0, True, True)}
    found = registry.query(axes={"resolution": 8.0}, include_conditional=True)
    assert [(f.code, f.conditional_on) for f in found] == [
        ("CROC101", ("space", "model")),
        ("CROC102", ()),
    ]
    (ranged,) = registry.query(axes={"resolution": (8.0, 12.0)})
    assert ranged.axes["resolution"] == qe.AxisOverlap(8.0, 10.0, True, False)
    assert registry.query(axes={"resolution": 10.0}) == []
    with pytest.raises(qe.UnknownNameError):
        registry.query(axes={"resolutoin": 8.0})
    with pytest.raises(ValueError, match="unit"):
        registry.add(
            warning_rule("CROC109", axes={"resolution": {"lt": 10, "unit": "deg"}})
        )


def test_undecided_axis_reports_the_rule_interval():
    registry = croc_registry()
    found = registry.query(include_conditional=True)
    croc102 = next(f for f in found if f.code == "CROC102")
    assert croc102.conditional_on == ("resolution",)
    assert croc102.axes["resolution"].hi == 10.0


# ---- fixture 19: conditional findings ------------------------------------------------
def cru_registry():
    registry = make_registry()
    registry.add(
        qe.Rule(
            code="CRU001",
            kind="warning",
            title="CRU TS precipitation falls back to climatology",
            message="m",
            min_overlap=0.1,
            scope=qe.Scope(
                space=union(sp.box(10, -10, 30, 10), sp.box(-20, 0, 10, 15)),
                time=qe.interval("2000-01-01", ".."),
                facets={
                    "product": ["cru_ts"],
                    "variable": ["pre"],
                    "version": {"versions": ["4.07"]},
                },
            ),
        )
    )

    class CruStations(
        qe.ComputedRule,
        code="CRU002",
        registry=registry,
        facets={"product": "cru_ts", "variable": "pre"},
        requires=["cru_ts.stn"],
    ):
        """CRU TS value from few or no stations"""

        def check(self, query, match):
            stn = query.context["cru_ts.stn"]
            zero = float((stn == 0).mean())
            if zero > 0:
                return {"level": logging.ERROR, "details": {"stn0_fraction": zero}}
            return float(stn.mean()) <= 2

    return registry


def test_fixture_19_conditional_findings():
    registry = cru_registry()
    assert registry.query(axes={"resolution": 8.0}) == []
    found = registry.query(axes={"resolution": 8.0}, include_conditional=True)
    cru001 = next(f for f in found if f.code == "CRU001")
    assert cru001.conditional_on == ("space", "time", "product", "variable", "version")
    assert cru001.area_fraction is None and cru001.time_fraction is None
    assert cru001.time_overlap == (("2000-01-01", ".."),)
    assert "CRU001" not in codes(
        registry.query(space=sp.point(0, 60), include_conditional=True)
    )
    cru_pre = {"product": "cru_ts", "variable": "pre"}
    found = registry.query(facets=cru_pre, include_conditional=True)
    cru002 = next(f for f in found if f.code == "CRU002")
    assert cru002.conditional_on == ("context:cru_ts.stn",) and cru002.details == {}
    assert "CRU002" not in codes(registry.query(facets=cru_pre))


def test_computed_rule_check_runs_for_definite_matches_only():
    registry = cru_registry()
    cru_pre = {"product": "cru_ts", "variable": "pre"}
    stn = np.array([0, 3, 4])
    found = registry.query(facets=cru_pre, context={"cru_ts.stn": stn})
    (cru002,) = [f for f in found if f.code == "CRU002"]
    assert cru002.level == logging.ERROR and cru002.source == "computed"
    assert cru002.details == {"stn0_fraction": pytest.approx(1 / 3)}
    thick = {"cru_ts.stn": np.array([5, 6])}
    found = registry.query(facets=cru_pre, context=thick)
    assert "CRU002" not in codes(found)  # check() returned False


def test_glhe_lake_query():
    registry = cru_registry()
    (cru001,) = registry.query(
        space=sp.box(20, 0, 20.1, 0.1),
        time=("1901-01-01", "2022-12-31"),
        facets={"product": "cru_ts", "variable": "pre", "version": "4.07"},
    )
    assert cru001.area_fraction == 1.0
    assert cru001.time_overlap == (("2000-01-01", "2022-12-31"),)
    assert round(cru001.time_fraction, 3) == 0.189  # section 7.3


# ---- fixture 20: facet wildcards ------------------------------------------------------
def test_product_is_a_plain_facet():
    registry = make_registry()
    registry.add(warning_rule("TST010", facets={"product": ["era5*"]}))
    registry.add(warning_rule("TST011", facets={"product": ["CRUTS"]}))
    (found,) = registry.query(facets={"product": ("era5_land", "cru_ts")})
    assert found.code == "TST010"
    assert found.matched_facets == {"product": ("era5_land",)}
    assert registry.query(facets={"product": "cruts"}) == []  # exact, no aliases


def test_fixture_20_wildcard_is_not_an_omitted_facet():
    registry = make_registry()
    registry.add(warning_rule("TST020", facets={"product": ["*"]}))
    (found,) = registry.query(include_conditional=True)
    assert found.conditional_on == ("product",)
    (found,) = registry.query(facets={"product": "era5"})
    assert found.conditional_on == () and found.matched_facets == {"product": ("era5",)}


def test_fixture_20_none_of_and_case():
    registry = make_registry()
    registry.add(warning_rule("TST030", facets={"variable": {"none_of": ["tp"]}}))
    registry.add(warning_rule("TST031", facets={"variable": ["Pre"]}))
    assert registry.query(facets={"variable": "tp"}) == []
    (found,) = registry.query(facets={"variable": ("tp", "t2m")})
    assert found.code == "TST030" and found.matched_facets == {"variable": ("t2m",)}
    assert codes(registry.query(facets={"variable": "pre"})) == ["TST030"]


# ---- fixture 21: version ranges on the Registry -----------------------------------------
def test_fixture_21_version_facet():
    registry = make_registry()
    with pytest.raises(ValueError):
        registry.add(
            warning_rule("TST040", facets={"version": {"introduced": "4.07a"}})
        )
    registry.add(
        warning_rule(
            "TST041", facets={"version": {"introduced": "4.00", "fixed": "4.09"}}
        )
    )
    (found,) = registry.query(facets={"product": "cru_ts", "version": "4.07"})
    assert found.matched_facets == {"version": ("4.07",)}
    (found,) = registry.query(facets={"version": ("4.9", "4.07")})
    assert found.matched_facets == {"version": ("4.07",)}
    assert registry.query(facets={"product": "cru_ts", "version": "4.9"}) == []


# ---- fixture 27: a plugin dimension --------------------------------------------------
@dataclass(frozen=True)
class Pfafstetter:
    """HydroBASINS basin codes: basin 1423 lies inside basin 14 (section 4.13)."""

    name: str = "basin"

    def parse_rule(self, value: Any) -> tuple[str, ...]:
        return tuple(str(v) for v in value)

    def parse_query(self, value: Any) -> str:
        code = str(value)
        if not code.isdigit() or "0" in code:
            raise ValueError(f"not a Pfafstetter code: {value!r}")
        return code

    def match(self, rule: tuple[str, ...], query: str) -> qe.DimMatch | None:
        hits = [b for b in rule if query.startswith(b) or b.startswith(query)]
        if not hits:
            return None
        inside = any(query.startswith(b) for b in hits)
        return qe.DimMatch(overlap=tuple(hits), fraction=1.0 if inside else None)


class BasinPrefilter:
    def __init__(self, pairs):
        self.pairs = pairs

    def candidates(self, query):
        return {i for i, rule in self.pairs if any(b[:1] == query[:1] for b in rule)}


@dataclass(frozen=True)
class IndexedPfafstetter(Pfafstetter):
    """The same dimension with a prefilter, so the Registry's build() path runs."""

    def build(self, pairs):
        return BasinPrefilter(pairs)


@pytest.mark.parametrize("plugin", [Pfafstetter(), IndexedPfafstetter()])
def test_fixture_27_plugin_dimension(plugin):
    registry = qe.Registry("glhe", dimensions=[plugin])
    registry.add(warning_rule("BAS001", dims={"basin": ["14", "62"]}))
    (nested,) = registry.query(dims={"basin": "1423"})
    assert nested.dims == {"basin": qe.DimMatch(("14",), 1.0)}
    (partial,) = registry.query(dims={"basin": "1"})
    assert partial.dims == {"basin": qe.DimMatch(("14",), None)}
    assert registry.query(dims={"basin": "31"}) == []
    assert registry.query() == []
    (undecided,) = registry.query(include_conditional=True)
    assert undecided.conditional_on == ("basin",) and undecided.dims == {}
    with pytest.raises(ValueError, match="Pfafstetter"):
        registry.query(dims={"basin": "1203"})
    with pytest.raises(qe.UnknownNameError):
        registry.add(warning_rule("BAS002", dims={"basins": ["14"]}))
    with pytest.raises(qe.UnknownNameError):
        registry.query(facets={"basin": "14"})  # declared as a dimension, not a facet
    assert nested.to_dict()["dims"] == {"basin": {"overlap": ["14"], "fraction": 1.0}}


class DescribedPfafstetter(Pfafstetter):
    """The same dimension with the optional to_json and extent hooks."""

    def to_json(self, overlap):
        return "+".join(overlap)

    def extent(self, rule):
        return rule


def test_plugin_to_json_and_extent():
    registry = qe.Registry("glhe", dimensions=[DescribedPfafstetter()])
    registry.add(warning_rule("BAS001", dims={"basin": ["14", "62"]}))
    (nested,) = registry.query(dims={"basin": "1423"})
    assert nested.dims == {"basin": qe.DimMatch(("14",), 1.0)}
    assert nested.to_dict()["dims"] == {"basin": {"overlap": "14", "fraction": 1.0}}
    (undecided,) = registry.query(include_conditional=True)
    assert undecided.dims == {"basin": qe.DimMatch(("14", "62"))}


def test_dimensions_are_declared_before_rules_with_unique_names():
    registry = qe.Registry("x")
    registry.add(warning_rule("TST050"))
    with pytest.raises(ValueError):
        registry.add_dimension(Pfafstetter())
    with pytest.raises(ValueError):
        qe.Registry("x", dimensions=[Pfafstetter(), Pfafstetter()])
    with pytest.raises(ValueError):
        qe.Registry("x", axes=[qe.Axis("time", "s")])


# ---- fixtures 2, 6, 9 and 13 as queries ------------------------------------------------
def test_fixture_2_antimeridian_box_in_three_forms():
    registry = qe.Registry("geo")
    registry.add(warning_rule("FIJ001", space=sp.box(170, -20, -170, -10)))
    registry.add(
        warning_rule(
            "FIJ002",
            space=sp.polygon([(170, -20), (-170, -20), (-170, -10), (170, -10)]),
        )
    )
    registry.add(
        warning_rule(
            "FIJ003", space=sp.polygon([(170, -20), (190, -20), (190, -10), (170, -10)])
        )
    )
    for lon in (175, -175, 180, -180):
        assert codes(registry.query(space=sp.point(lon, -15))) == [
            "FIJ001",
            "FIJ002",
            "FIJ003",
        ]
    assert registry.query(space=sp.point(0, -15)) == []


def test_fixture_6_closed_edges():
    registry = qe.Registry("geo")
    registry.add(warning_rule("SQR001", space=sp.box(0, 0, 10, 10)))
    for point in [(0, 5), (10, 5), (5, 0), (5, 10), (10, 10), (0, 10)]:
        assert codes(registry.query(space=sp.point(*point))) == ["SQR001"]
    (touching,) = registry.query(space=sp.box(10, 0, 20, 10))
    assert touching.area_fraction == 0.0 and touching.conditional_on == ()


def test_fixture_9_overlap_fraction_and_area():
    registry = qe.Registry("geo")
    registry.add(warning_rule("HLF001", space=sp.box(0, 40, 5, 50)))
    registry.add(warning_rule("HLF002", space=sp.box(0, 40, 10, 45)))
    query = sp.box(0, 40, 10, 50)
    assert round(query.area_km2, 3) == 873182.018
    half, south = registry.query(space=query)
    assert half.area_fraction == pytest.approx(0.5)
    assert round(south.area_fraction, 5) == 0.52183
    assert half.overlap_km2 == pytest.approx(query.area_km2 / 2)


def test_fixture_13_open_and_inclusive_ends():
    registry = qe.Registry("time")
    registry.add(warning_rule("OPN001", time=qe.interval("2000-01-01", "..")))
    registry.add(warning_rule("YRS001", time=qe.interval("2000-01-01", "2006-12-31")))
    found = {f.code: f for f in registry.query(time=("1991-01-01", "2020-12-31"))}
    assert found["OPN001"].time_fraction == pytest.approx(7671 / 10958)
    (future,) = registry.query(time=("2030-01-01", ".."))
    assert (
        future.time_overlap == (("2030-01-01", ".."),) and future.time_fraction is None
    )
    assert registry.query(time=("..", "1999-12-31")) == []
    assert codes(registry.query(time={"timestamp": "2006-12-31T23:59:59Z"})) == [
        "OPN001",
        "YRS001",
    ]
    assert codes(registry.query(time={"date": "2007-01-01"})) == ["OPN001"]


def test_month_recurrence_counts_as_time():
    registry = qe.Registry("time")
    registry.add(
        warning_rule(
            "SEA001", time=qe.parse_time(None, recurrence={"months": [12, 1, 2]})
        )
    )
    (undecided,) = registry.query(include_conditional=True)
    assert undecided.conditional_on == ("time",) and undecided.time_overlap == ()
    assert undecided.details == {"recurrence_months": [1, 2, 12]}
    (winter,) = registry.query(time=("2020-11-15", "2021-03-10"))
    assert winter.time_overlap == (("2020-12-01", "2021-02-28"),)
    assert winter.time_fraction == pytest.approx(90 / 116)


# ---- computed rules, codes and lifecycle ---------------------------------------------
def test_function_rule_croc104_suggests_a_time_step():
    registry = croc_registry()

    @registry.rule(
        "CROC104",
        kind="suggestion",
        space=sp.box(-180, 66.5, 180, 90),
        facets={"model": "mom6"},
        axes={"resolution": {"gt": 0.0}},
    )
    def arctic_time_step(query, match):
        """High-latitude domain: set the time step from the smallest cells"""
        seconds = 30.0 * match.axes["resolution"].lo
        return {"suggestions": (qe.Suggestion("MOM_input", "DT", seconds, "why"),)}

    found = registry.query(
        space=sp.box(-180, 70.6, 180, 90),
        time=("2020-01-01", "2020-12-31"),
        axes={"resolution": (8.0, 12.0)},
        facets={"model": "mom6"},
    )
    assert codes(found) == ["CROC101", "CROC102", "CROC104"]
    croc104 = found[-1]
    assert croc104.level == logging.INFO and croc104.title.startswith("High-latitude")
    assert croc104.suggestions == (qe.Suggestion("MOM_input", "DT", 240.0, "why"),)
    assert croc104.axes["resolution"] == qe.AxisOverlap(8.0, 12.0, True, True)
    assert found[1].axes["resolution"] == qe.AxisOverlap(8.0, 10.0, True, False)
    without = registry.query(
        space=sp.box(-180, 70.6, 180, 90),
        facets={"model": "mom6"},
        include_conditional=True,
    )
    assert next(f for f in without if f.code == "CROC104").conditional_on == (
        "resolution",
    )


def test_gen001_compares_the_caller_area_with_the_support():
    registry = make_registry()

    @registry.rule(
        "GEN001",
        level="info",
        facets={"product": ["*"]},
        requires=["request_km2"],
    )
    def coarse_support(query, match):
        """The request is much smaller than the product cells that represent it"""
        ratio = query.context["request_km2"] / query.space.area_km2
        return {"details": {"request_to_support": ratio}} if ratio < 0.1 else None

    cru = {"product": "cru_ts"}
    (found,) = registry.query(space=LAKE, facets=cru, include_conditional=True)
    assert found.conditional_on == ("context:request_km2",)
    cell = sp.box(0, 0, 0.5, 0.5)  # the product cell the lake lies in
    context = {"request_km2": LAKE.area_km2}
    (found,) = registry.query(space=cell, facets=cru, context=context)
    assert found.details["request_to_support"] == pytest.approx(0.09, rel=0.01)


def test_check_may_return_several_findings_and_override_time():
    registry = qe.Registry("multi")

    class Multi(
        qe.ComputedRule,
        code="MUL001",
        registry=registry,
        time=qe.interval("2000-01-01", "2009-12-31"),
    ):
        """Several findings"""

        def check(self, query, match):
            first = {"time_overlap": [("2001-01-01", "2002-12-31")], "level": "error"}
            return [first, {"message": "second"}]

    error, second = registry.query(time=("2000-01-01", "2009-12-31"))
    assert error.level == logging.ERROR and second.level == logging.WARNING
    assert error.time_overlap == (("2001-01-01", "2002-12-31"),)
    assert error.time_fraction == pytest.approx(730 / 3653)
    assert second.message == "second" and second.time_fraction == 1.0

    class Locked(qe.ComputedRule, code="MUL002", registry=registry):
        """Cannot change its code"""

        def check(self, query, match):
            return {"code": "MUL003"}

    with pytest.raises(ValueError):
        registry.query()


def test_computed_rule_keywords_inherit_from_an_abstract_base():  # Q9
    registry = qe.Registry("family", facets=("model",))

    class Family(
        qe.ComputedRule,
        abstract=True,
        registry=registry,
        facets={"model": "mom6"},
        kind="suggestion",
    ):
        pass

    class Child(Family, code="FAM001"):
        """Inherits the registry, the scope and the kind"""

    class Other(Family, code="FAM002", facets={"model": "cesm"}):
        """Its own facets win"""

    (child,) = registry.query(facets={"model": "mom6"})
    assert (child.code, child.kind, child.level) == ("FAM001", "suggestion", 20)
    assert codes(registry.query(facets={"model": "cesm"})) == ["FAM002"]
    with pytest.raises(TypeError):

        class NoCode(qe.ComputedRule, registry=registry):
            """Not abstract and no code"""

    with pytest.raises(TypeError):

        class Typo(
            qe.ComputedRule, code="FAM003", registry=registry, facet={"model": "x"}
        ):
            """An unknown keyword"""


def test_duplicate_codes_and_the_q10_replacement():
    registry = qe.Registry("dup", facets=("model",))
    registry.add(warning_rule("DUP001"))
    with pytest.raises(qe.DuplicateCodeError):
        registry.add(warning_rule("DUP001"))

    def define(title):
        class Redefined(qe.ComputedRule, code="DUP002", registry=registry, title=title):
            pass

    define("first")
    define("second")  # the same qualified name, as re-running a notebook cell does
    assert [f.title for f in registry.query() if f.code == "DUP002"] == ["second"]
    with pytest.raises(qe.DuplicateCodeError):

        class Different(qe.ComputedRule, code="DUP002", registry=registry):
            """Another class with the same code"""

    for _ in range(2):

        @registry.rule("DUP003")
        def same(query, match):
            """A function rule defined twice"""

    with pytest.raises(qe.DuplicateCodeError):

        @registry.rule("DUP003")
        def other(query, match):
            """Another function with the same code"""


@pytest.mark.parametrize(
    ("code", "valid"),
    [
        ("CRU001", True),
        ("ERA5-014", True),
        ("GLORYS001", True),
        ("CROC1001", True),
        ("ERA5001", True),  # prefix ERA and number 5001: one parse only (Q8)
        ("cru001", False),
        ("ABC12001", False),
        ("CRU01", False),
        ("C001", False),
    ],
)
def test_code_pattern(code, valid):
    registry = qe.Registry("codes")
    if valid:
        registry.add(warning_rule(code))
    else:
        with pytest.raises(ValueError):
            registry.add(warning_rule(code))


def test_withdrawn_and_superseded_rules_never_match():
    registry = qe.Registry("life")
    registry.add(
        qe.Rule(
            code="CRU003",
            kind="warning",
            title="t",
            message="m",
            withdrawn="2026-01-01T00:00:00Z",
        )
    )
    registry.add(qe.Rule(code="CRU005", kind="warning", title="t", message="m"))
    registry.add(
        qe.Rule(
            code="CRU004",
            kind="warning",
            title="t",
            message="m",
            supersedes=("CRU005",),
        )
    )
    assert codes(registry.query(include_conditional=True)) == ["CRU004"]
    with pytest.raises(qe.DuplicateCodeError):  # a retired code is never reused
        registry.add(warning_rule("CRU003"))


def test_findings_are_sorted_by_level_kind_and_code():
    registry = make_registry()
    registry.add(
        qe.Rule(
            code="SRT001",
            kind="warning",
            title="t",
            message="m",
            level="info",
            scope=qe.Scope(facets={"product": ["*"]}),
        )
    )
    registry.add(
        qe.Rule(
            code="SRT002",
            kind="suggestion",
            title="t",
            message="m",
            level="error",
            suggestions=({"target": "a", "key": "b", "value": 1},),
        )
    )
    registry.add(
        qe.Rule(code="SRT003", kind="warning", title="t", message="m", level="error")
    )
    found = registry.query(space=sp.point(0, 0), facets={"product": "era5"})
    assert codes(found) == ["SRT003", "SRT002", "SRT001"]


def test_the_default_registry_is_made_once():
    assert qe.Registry.default() is qe.Registry.default()


def test_rule_added_to_a_second_registry_is_bound_as_a_copy():
    rule = warning_rule("CPY001", facets={"model": "a"})
    first, second = qe.Registry("one"), qe.Registry("two")
    first.add(rule)
    second.add(rule)
    assert rule.evaluate(qe.Query(facets={"model": "a"}))[0].code == "CPY001"
    assert codes(second.query(facets={"model": "a"})) == ["CPY001"]
    with pytest.raises(TypeError):
        warning_rule("CPY002").evaluate(qe.Query())  # not on a Registry


def test_third_party_rule_kinds():
    class Foreign:  # its own evaluate() is final; the scope is only a prefilter
        code = "FOR001"
        scope = qe.Scope(facets={"model": "mom6"})

        def evaluate(self, query):
            return [qe.Finding(code=self.code, kind="warning", title="f", message="f")]

    class Hooked:  # outcomes() runs after the Registry matches the scope (Q5)
        code = "HOK001"
        scope = qe.Scope(axes={"resolution": {"le": 5}})
        outcome = qe.Outcome(code="HOK001", kind="warning", title="h", message="h")

        def outcomes(self, query, match):
            return {"details": {"lo": match.axes["resolution"].lo}}

        def evaluate(self, query):
            raise AssertionError("the Registry calls outcomes() instead")

    registry = qe.Registry("kinds", axes=[qe.Axis("resolution", "km")])
    registry.add(Foreign())
    registry.add(Hooked())
    found = registry.query(facets={"model": "mom6"}, axes={"resolution": 3})
    assert [(f.code, dict(f.details)) for f in found] == [
        ("FOR001", {}),
        ("HOK001", {"lo": 3.0}),
    ]
    assert registry.query(facets={"model": "cesm"}, axes={"resolution": 9}) == []
    assert codes(registry.query()) == ["FOR001"]  # the foreign kind decides for itself


def test_queries_need_declared_names():
    registry = make_registry(facets=("product",))
    with pytest.raises(qe.UnknownNameError):
        registry.query(facets={"product": "cru_ts", "variable": "pre"})


# ---- the fast path against the reference path ----------------------------------------
PRODUCTS = ("cru_ts", "era5", "era5_land", "glorys")


def random_box(rng):
    choice = rng.random()
    south = rng.uniform(-90, 80)
    north = rng.choice([90.0, min(90.0, south + rng.uniform(1, 40))])
    if choice < 0.2:
        return sp.box(-180, south, 180, north)
    if choice < 0.35:  # an edge on the seam
        width = rng.uniform(1, 60)
        west = rng.choice([-180.0, 180.0 - width])
    else:
        west, width = rng.uniform(-180, 180), rng.uniform(0.5, 120)
    return sp.box(west, south, west + width, north)


def random_time(rng):
    start = rng.randint(1900, 2030)
    end = start + rng.randint(1, 30)
    first = rng.choice([f"{start}-01-01", f"{start}-06-15", ".."])
    last = rng.choice([f"{end}-12-31", f"{end}-02-28", ".."])
    return qe.interval(first, last)


REGIONS = {
    "A": sp.box(-10, -10, 10, 10),
    "B": sp.box(170, 50, -170, 70),
    "C": sp.box(-180, 80, 180, 90),
}


def random_rule_scope(rng):
    space = time = None
    pick = rng.random()
    if pick < 0.45:
        space = random_box(rng)
    elif pick < 0.52:  # the union of one or two fixed areas
        space = union(*(REGIONS[n] for n in rng.sample("ABC", rng.randint(1, 2))))
    pick = rng.random()
    if pick < 0.4:
        time = random_time(rng)
    elif pick < 0.5:
        months = rng.sample(range(1, 13), rng.randint(1, 4))
        time = qe.parse_time(
            rng.choice([None, {"interval": ["2000-01-01", ".."]}]),
            recurrence={"months": months},
        )
    axes = {}
    if rng.random() < 0.35:
        bound = rng.choice(
            [{"lt": 10.0}, {"ge": 25.0}, {"gt": 5.0, "le": 12.0}, {"le": 8.0}]
        )
        axes["resolution"] = bound
    facets = {}
    if rng.random() < 0.4:
        facets["product"] = rng.choice(
            [["cru_ts"], ["CRUTS", "era5"], ["era5*"], ["*"], {"none_of": ["glorys"]}]
        )
    if rng.random() < 0.3:
        facets["variable"] = rng.choice(
            [["pre"], ["t*"], {"none_of": ["tp"]}, ["pre", "tas"]]
        )
    if rng.random() < 0.15:
        facets["version"] = rng.choice(
            [
                {"introduced": "4.00", "fixed": "4.09"},
                {"versions": ["ERA5"]},
                [{"last_affected": "1"}],
            ]
        )
    if rng.random() < 0.3:
        facets["model"] = rng.choice([["mom6"], ["cesm", "mom6"], ["m*"]])
    dims = {"basin": rng.choice([["14"], ["2", "31"]])} if rng.random() < 0.2 else {}
    return qe.Scope(space=space, time=time, axes=axes, facets=facets, dims=dims)


def random_registry(rng):
    registry = qe.Registry(
        "property",
        axes=[qe.Axis("resolution", "km")],
        dimensions=[IndexedPfafstetter()],
    )
    for k in range(120):
        registry.add(
            qe.Rule(
                code=f"RND{k:03d}",
                kind="warning",
                title="t",
                message="m",
                scope=random_rule_scope(rng),
                withdrawn="2026-01-01T00:00:00Z" if rng.random() < 0.05 else None,
                supersedes=(
                    (f"RND{rng.randint(0, 119):03d}",) if rng.random() < 0.05 else ()
                ),
            )
        )
    for k in range(10):
        scope = random_rule_scope(rng)

        class Computed(
            qe.ComputedRule,
            code=f"CMP{k:03d}",
            registry=registry,
            space=scope.space,
            time=scope.time,
            axes=scope.axes,
            facets=scope.facets,
            requires=["stn"] if k % 2 else [],
        ):
            """A computed rule"""

            def check(self, query, match):
                if match.area_fraction is not None and match.area_fraction < 0.5:
                    return None
                return {"details": {"area": match.area_fraction}}

    return registry


def random_query(rng):
    pick = rng.random()
    space = None
    if pick < 0.25:
        lon = rng.choice([rng.uniform(-180, 180), 180.0, -180.0])
        space = sp.point(lon, rng.choice([rng.uniform(-90, 90), 90.0, -90.0]))
    elif pick < 0.6:
        space = random_box(rng)
    fields = {"space": space}
    if rng.random() < 0.6:
        fields["time"] = random_time(rng)
    if rng.random() < 0.5:
        fields["axes"] = {
            "resolution": rng.choice([8.0, 30.0, (8.0, 12.0), (1.0, 50.0)])
        }
    facets = {}
    if rng.random() < 0.5:
        facets["model"] = rng.choice(["mom6", "cesm", ("mom6", "x")])
    if rng.random() < 0.5:
        facets["product"] = rng.sample(PRODUCTS, rng.randint(1, 2))
        facets["variable"] = rng.choice(["pre", ("tp", "t2m")])
    if rng.random() < 0.3:
        facets["version"] = rng.choice(["4.07", "ERA5", "4.10"])
    fields["facets"] = facets
    if rng.random() < 0.3:
        fields["dims"] = {"basin": rng.choice(["1423", "1", "31", "2"])}
    if rng.random() < 0.5:
        fields["context"] = {"stn": 1}
    return qe.Query(**fields)


def test_random_queries_hide_only_conditional_findings():
    rng = random.Random(20261012)
    registry = random_registry(rng)
    seen = 0
    for i in range(250):
        query = random_query(rng)
        definite = registry.query(query)
        every = registry.query(query, include_conditional=True)
        assert definite == [f for f in every if not f.conditional_on], f"query {i}"
        seen += len(every)
    assert seen > 1000  # the queries reach the rules
