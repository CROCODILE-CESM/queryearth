"""Queries: a rule applies when every dimension it constrains overlaps the query."""

import pytest

import queryearth as qe
from queryearth import space as sp


def registry_with(*rules):
    registry = qe.Registry([qe.Axis("resolution", "km"), qe.Labels("product")])
    for rule in rules:
        registry.add(rule)
    return registry


def codes(findings):
    return [rule.code for rule in findings]


gulf = qe.Rule(
    "GULF001",
    "Gulf of Mexico before 2010, fine grids",
    "...",
    scope={
        "space": sp.box(-98, 18, -80, 31),
        "time": qe.interval("..", "2009-12-31"),
        "resolution": {"lt": 10},
    },
)


def test_a_rule_applies_when_every_dimension_it_constrains_overlaps():
    registry = registry_with(gulf)
    domain = sp.box(-90, 20, -70, 30)  # half in the gulf
    year = qe.interval("2005-01-01", "2005-12-31")
    assert codes(registry.query(space=domain, time=year, resolution=8)) == ["GULF001"]
    assert registry.query(space=domain, time=year, resolution=12) == []
    assert registry.query(space=sp.point(0, 0), time=year, resolution=8) == []


def test_a_dimension_the_rule_leaves_out_matches_anything():
    fine = qe.Rule("GRID001", "Fine grid", "...", scope={"resolution": {"lt": 8}})
    registry = registry_with(fine)
    assert codes(registry.query(resolution=5, product="glorys")) == ["GRID001"]
    assert codes(registry.query(resolution=5, space=sp.point(10, 10))) == ["GRID001"]


def test_a_dimension_the_query_leaves_out_does_not_match():
    registry = registry_with(gulf)
    assert registry.query(resolution=8) == []  # no space and no time given
    assert registry.query(space=sp.point(-90, 25), resolution=8, time=None) == []


def test_a_rule_without_a_scope_applies_to_every_query():
    registry = registry_with(qe.Rule("ALL001", "Always", "..."))
    assert codes(registry.query()) == ["ALL001"]
    assert codes(registry.query(product="glorys")) == ["ALL001"]


def test_undeclared_names_are_refused_in_rules_and_queries():
    registry = registry_with()
    with pytest.raises(ValueError, match="undeclared dimension 'resolutoin'"):
        registry.query(resolutoin=8)
    with pytest.raises(ValueError, match="undeclared dimension 'model'"):
        registry.add(qe.Rule("M001", "Model", "...", scope={"model": "mom6"}))


def test_findings_come_highest_level_first_then_by_code():
    registry = registry_with(
        qe.Rule("B", "b", "...", level="info"),
        qe.Rule("C", "c", "..."),
        qe.Rule("A", "a", "...", level="info"),
        qe.Rule("D", "d", "...", level="error"),
    )
    assert codes(registry.query()) == ["D", "C", "A", "B"]


def test_the_level_is_warning_unless_given_as_a_name():
    assert qe.Rule("X", "x", "...").level == "warning"
    with pytest.raises(ValueError):
        qe.Rule("X", "x", "...", level="WARNING")
