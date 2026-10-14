"""Edge rules: a rule that applies where the query's edge meets its space."""

import pytest

import queryearth as qe
from queryearth import space as sp

CURRENT = sp.box(-80, 25, -60, 45)  # a stand-in for a current


def registry(*rules):
    found = qe.Registry("edges")
    for rule in rules:
        found.add(rule)
    return found


def edge_rule(code="EDGE001", space=CURRENT, **fields):
    scope = qe.Scope(space=space, edge=True)
    return qe.Rule(code=code, title="t", message="m", scope=scope, **fields)


def codes(registry, **query):
    return [f.code for f in registry.query(**query)]


# ---- the edge of a polygon -------------------------------------------------------------
def test_the_edge_of_a_cap_is_its_circle_of_latitude():
    edge = sp.edge(sp.box(-180, 60, 180, 90))
    assert edge.length == 360.0
    assert edge.bounds == (-180.0, 60.0, 180.0, 60.0)


def test_a_cut_at_the_date_line_is_not_an_edge():
    assert sp.edge(sp.box(170, -10, -170, 10)).length == 80.0  # 20 by 20


def test_an_edge_on_the_date_line_is_an_edge():
    assert sp.edge(sp.box(170, 0, 180, 10)).length == 40.0


def test_a_band_around_the_globe_has_one_edge():
    edge = sp.edge(sp.box(-180, -90, 180, -30))
    assert edge.length == 360.0 and edge.bounds[1] == edge.bounds[3] == -30.0


def test_a_point_has_no_edge():
    with pytest.raises(ValueError):
        sp.edge(sp.point(0, 0))
    assert not sp.edge_meets(CURRENT, sp.point(-70, 30))


# ---- matching ------------------------------------------------------------------------------
def test_an_edge_rule_applies_where_the_edge_crosses_its_space():
    found = registry(edge_rule())
    assert codes(found, space=sp.box(-70, 20, -50, 40)) == ["EDGE001"]


def test_an_edge_rule_does_not_apply_to_a_domain_that_holds_its_space():
    found = registry(edge_rule())
    assert codes(found, space=sp.box(-90, 20, -50, 50)) == []


def test_an_edge_rule_applies_to_a_domain_inside_its_space():
    found = registry(edge_rule())
    assert codes(found, space=sp.box(-75, 30, -70, 35)) == ["EDGE001"]


def test_an_edge_rule_never_applies_to_a_point():
    assert codes(registry(edge_rule()), space=sp.point(-70, 30)) == []


def test_a_rule_without_edge_applies_wherever_they_overlap():
    rule = qe.Rule(code="AREA001", title="t", message="m", scope=qe.Scope(CURRENT))
    assert codes(registry(rule), space=sp.box(-90, 20, -50, 50)) == ["AREA001"]


def test_the_date_line_cut_does_not_cross_a_space_on_it():
    on_the_line = edge_rule(space=sp.box(178, -2, -178, 2))
    domain = sp.box(170, -10, -170, 10)
    assert codes(registry(on_the_line), space=domain) == []
    crossing = edge_rule(space=sp.box(178, 8, -178, 12))
    assert codes(registry(crossing), space=domain) == ["EDGE001"]


def test_the_pole_is_not_an_edge_of_a_cap():
    near_pole = edge_rule(space=sp.box(-180, 85, 180, 90))
    assert codes(registry(near_pole), space=sp.box(-180, 60, 180, 90)) == []
    on_the_circle = edge_rule(space=sp.box(0, 55, 20, 65))
    assert codes(registry(on_the_circle), space=sp.box(-180, 60, 180, 90)) == [
        "EDGE001"
    ]


def test_without_a_query_space_an_edge_rule_is_conditional():
    found = registry(edge_rule()).query(include_conditional=True)
    assert [(f.code, f.conditional_on) for f in found] == [("EDGE001", ("space",))]


def test_an_edge_rule_reports_how_much_of_the_query_it_covers():
    (found,) = registry(edge_rule()).query(space=sp.box(-70, 20, -50, 40))
    assert 0.0 < found.area_fraction < 1.0


def test_an_edge_rule_needs_a_space():
    with pytest.raises(ValueError, match="needs a space"):
        qe.Scope(edge=True)
    with pytest.raises(TypeError):
        qe.Scope(CURRENT, edge="yes")


def test_a_computed_rule_can_be_an_edge_rule():
    found = qe.Registry("computed")

    @found.rule("EDGE010", space=CURRENT, edge=True)
    def crossing(query, match):
        """The edge crosses the current"""
        return True

    assert codes(found, space=sp.box(-70, 20, -50, 40)) == ["EDGE010"]
    assert codes(found, space=sp.box(-90, 20, -50, 50)) == []


def test_the_bulk_path_leaves_edge_rules_out():
    result = registry(edge_rule()).query_points([-70.0], [30.0])
    assert result.findings == () and result.masks == {}


# ---- records ---------------------------------------------------------------------------
def test_a_record_round_trips_its_edge():
    feature = edge_rule().to_feature()
    assert feature["properties"]["edge"] is True
    assert qe.Rule.from_feature(feature).scope.edge is True
    plain = qe.Rule(code="AREA001", title="t", message="m", scope=qe.Scope(CURRENT))
    assert "edge" not in plain.to_feature()["properties"]


def test_a_record_edge_is_true_or_false():
    feature = edge_rule().to_feature()
    feature["properties"]["edge"] = "yes"
    with pytest.raises(ValueError, match="edge is true or false"):
        qe.Rule.from_feature(feature)


def test_a_record_edge_needs_a_geometry_or_box():
    feature = edge_rule().to_feature()
    feature["geometry"] = None
    with pytest.raises(ValueError, match="needs a space"):
        qe.Rule.from_feature(feature)
