"""The bulk path: fixture 6 on query_points, and a property test of
query_points against Registry.query point by point.
"""

import logging
import math
import random

import numpy as np
import pytest

import queryearth as qe
from queryearth import space as sp


def warning_rule(code, level="warning", **scope):
    return qe.Rule(
        code=code,
        kind="warning",
        title=code,
        message=code,
        level=level,
        scope=qe.Scope(**scope),
    )


# ---- fixture 6 on the bulk path --------------------------------------------------
def test_fixture_6_closed_edges_on_the_bulk_path():
    registry = qe.Registry("geo")
    registry.add(warning_rule("SQR001", space=sp.box(0, 0, 10, 10)))
    lon, lat = np.meshgrid(np.arange(-1, 11.25, 0.25), np.arange(-1, 11.25, 0.25))
    assert lon.size == 2_401
    assert registry.query_points(lon, lat).masks["SQR001"].sum() == 1_681


# ---- the bulk path in detail -----------------------------------------------------------
def bulk_registry():
    registry = qe.Registry("bulk", axes=[qe.Axis("resolution", "km")])
    registry.add(warning_rule("ALL001"))
    registry.add(warning_rule("BOX001", "error", space=sp.box(0, 0, 10, 10)))
    registry.add(warning_rule("RES001", axes={"resolution": {"lt": 10}}))
    registry.add(warning_rule("ERA001", facets={"product": ["era5"]}))

    class Wet(qe.ComputedRule, code="WET001", registry=registry, requires=["stn"]):
        """Points east of 5E, by a mask hook"""

        def mask(self, lon, lat, query):
            return lon > 5.0

    class Dry(qe.ComputedRule, code="DRY001", registry=registry):
        """A computed rule without a mask hook"""

    return registry


def test_query_points_keys_masks_and_skipped_rules_by_code():
    registry = bulk_registry()
    lon = np.array([[5.0, 8.0], [70.0, np.nan]])
    lat = np.array([[5.0, 5.0], [5.0, 5.0]])
    weights = np.array([[1.0, 1.0], [2.0, 9.0]])
    result = registry.query_points(
        lon,
        lat,
        weights,
        facets={"product": "era5"},
        time=("1990-01-01", "1999-12-31"),
    )
    assert set(result.masks) == {"ALL001", "BOX001", "WET001", "ERA001"}
    assert result.skipped == ("DRY001",)
    assert result.masks["ALL001"].tolist() == [[True, True], [True, False]]
    assert result.masks["WET001"].tolist() == [[False, True], [True, False]]
    assert result.fractions["BOX001"] == 0.5  # the NaN point weighs nothing
    found = {f.code: f for f in result.findings}
    assert found["BOX001"].area_fraction == 0.5
    assert found["ERA001"].time_overlap == (("1990-01-01", "1999-12-31"),)
    assert result.any(logging.ERROR).tolist() == [[True, True], [False, False]]
    assert result.any("warning").sum() == 3
    with_conditional = registry.query_points(lon, lat, include_conditional=True)
    conditional = [f for f in with_conditional.findings if f.conditional_on]
    assert {f.code: f.conditional_on for f in conditional} == {
        "RES001": ("resolution",),
        "ERA001": ("product",),
    }
    assert all(f.code not in with_conditional.masks for f in conditional)
    with pytest.raises(TypeError):
        registry.query_points(lon, lat, context={"stn": 1})


# ---- property test: query_points agrees with Registry.query point by point ------------------
def random_space(rng):
    pick = rng.random()
    south = rng.choice([-90, -60, -10, 0, 30, 66.5])
    north = rng.choice([n for n in (-30, 0, 10, 45, 80, 90) if n > south] or [90])
    if pick < 0.2:
        return sp.box(-180, south, 180, north)
    if pick < 0.7:  # integer edges, so grid points fall on them; some cross +-180
        west = rng.choice([-180, -170, -10, 0, 5, 150, 170])
        return sp.box(west, south, west + rng.choice([10, 20, 45, 90, 200]), north)
    ring = [(rng.uniform(-200, 200), rng.uniform(-80, 80))]
    for _ in range(5):
        x, y = ring[-1]
        ring.append(
            (x + rng.uniform(-30, 30), min(89, max(-89, y + rng.uniform(-20, 20))))
        )
    try:
        return sp.polygon(ring)
    except ValueError:
        return None


def random_bulk_registry(rng):
    registry = qe.Registry("property", axes=[qe.Axis("resolution", "km")])
    registry.add_regions(
        "reg", {"A": sp.box(-20, -20, 20, 20), "B": sp.box(170, 50, -170, 80)}
    )
    for k in range(80):
        scope, refs = {}, ()
        if rng.random() < 0.8:
            scope["space"] = random_space(rng)
        elif rng.random() < 0.5:
            refs = tuple(rng.sample(["reg:A", "reg:B"], rng.randint(1, 2)))
        if rng.random() < 0.3:
            scope["time"] = qe.interval(f"{rng.randint(1980, 2010)}-01-01", "..")
        if rng.random() < 0.3:
            scope["axes"] = {"resolution": rng.choice([{"lt": 10}, {"ge": 25}])}
        if rng.random() < 0.4:
            scope["facets"] = {"product": rng.choice([["cru_ts"], ["era5", "glorys"]])}
        level = rng.choice(["info", "warning", "error"])
        registry.add(
            qe.Rule(
                code=f"RND{k:03d}",
                kind="warning",
                title="t",
                message="m",
                level=level,
                region_ref=refs,
                scope=qe.Scope(**scope),
            )
        )
    return registry


def random_points(rng, n=60):
    lon = [rng.uniform(-180, 180) for _ in range(n)]
    lat = [rng.uniform(-90, 90) for _ in range(n)]
    for _ in range(n):  # on rule edges, the seam and the poles
        lon.append(rng.choice([-180, 180, -170, -10, 0, 5, 10, 20, 150, 170, 25, 45]))
        lat.append(rng.choice([-90, -60, -30, -10, 0, 10, 30, 45, 66.5, 80, 90, 3.3]))
    lon.append(math.nan)
    lat.append(0.0)
    return np.array(lon), np.array(lat)


def test_query_points_agrees_with_registry_query_point_by_point():
    rng = random.Random(20261012)
    registry = random_bulk_registry(rng)
    seen = 0
    for _ in range(6):
        lon, lat = random_points(rng)
        fields = {}
        if rng.random() < 0.5:
            fields["time"] = (f"{rng.randint(1985, 2015)}-01-01", "2020-12-31")
        if rng.random() < 0.5:
            fields["axes"] = {"resolution": rng.choice([8.0, 30.0, (8.0, 12.0)])}
        if rng.random() < 0.6:
            fields["facets"] = {"product": rng.sample(["cru_ts", "era5", "glorys"], 2)}
        result = registry.query_points(lon, lat, **fields)
        assert all(not m[-1] for m in result.masks.values())  # the NaN point
        for j in range(lon.size - 1):
            single = registry.query(space=sp.point(lon[j], lat[j]), **fields)
            expected = {f.code for f in single}
            got = {code for code, mask in result.masks.items() if mask[j]}
            assert got == expected, (lon[j], lat[j], fields)
            seen += len(expected)
    assert seen > 500  # the points reach the rules
