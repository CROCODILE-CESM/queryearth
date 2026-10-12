"""The bulk path and the inverse query: fixtures 5 and 6 on query_points, a
property test of query_points against Index.query point by point, and
suitable() on the worked example of design.md section 10.3.
"""

import math
import random

import numpy as np
import pytest

import queryearth as qe
from queryearth import space as sp


def caveat(code, severity="warning", **scope):
    return qe.Rule(
        code=code,
        kind="caveat",
        title=code,
        message=code,
        severity=severity,
        scope=qe.Scope(**scope),
    )


# ---- fixtures 5 and 6 on the bulk path ----------------------------------------------
def test_fixture_5_pole_points_on_the_bulk_path():
    index = qe.Index("geo")
    index.add(caveat("POL001", space=sp.box_arc(0, 90, 80, 90)))
    assert [f.code for f in index.query(space=sp.point(123, 90))] == ["POL001"]
    lon, lat = np.meshgrid(np.arange(-180, 180, 0.25), np.arange(-90, 90.25, 0.25))
    assert lon.size == 1_038_240
    result = index.query_points(lon, lat)
    mask = result.masks[(None, "POL001")]
    assert mask.shape == lon.shape and mask.sum() == 15_880
    assert mask[lat == 90].all() and (lat == 90).sum() == 1_440
    (found,) = result.findings
    assert found.area_fraction == pytest.approx(15_880 / lon.size)


def test_fixture_6_closed_edges_on_the_bulk_path():
    index = qe.Index("geo")
    index.add(caveat("SQR001", space=sp.box(0, 0, 10, 10)))
    lon, lat = np.meshgrid(np.arange(-1, 11.25, 0.25), np.arange(-1, 11.25, 0.25))
    assert lon.size == 2_401
    assert index.query_points(lon, lat).masks[(None, "SQR001")].sum() == 1_681


# ---- the bulk path in detail -----------------------------------------------------------
def bulk_index():
    index = qe.Index("bulk", axes=[qe.Axis("resolution", "km")])
    index.add_product(
        qe.Product(
            "era5",
            variables=("tp",),
            version="ERA5",
            coverage=qe.Coverage(space=sp.box(-60, -60, 60, 60)),
        )
    )
    index.add_product(
        qe.Product("glorys", coverage=qe.Coverage(time=qe.interval("1993-01-01", "..")))
    )
    index.add(caveat("ALL001"))
    index.add(caveat("BOX001", "severe", space=sp.box(0, 0, 10, 10)))
    index.add(caveat("RES001", axes={"resolution": {"lt": 10}}))
    index.add(caveat("ERA001", facets={"product": ["era5"]}))
    index.add(caveat("IDS001", space=sp.features(["1"], "lakes")))

    class Wet(qe.ComputedRule, code="WET001", index=index, requires=["stn"]):
        """Points east of 5E, by a mask hook"""

        def mask(self, lon, lat, query):
            return lon > 5.0

    class Dry(qe.ComputedRule, code="DRY001", index=index):
        """A computed rule without a mask hook"""

    return index


def test_query_points_keys_masks_and_skipped_rules_by_product_and_code():
    index = bulk_index()
    lon = np.array([[5.0, 8.0], [70.0, np.nan]])
    lat = np.array([[5.0, 5.0], [5.0, 5.0]])
    weights = np.array([[1.0, 1.0], [2.0, 9.0]])
    result = index.query_points(
        lon,
        lat,
        weights,
        requests=["era5", "glorys"],
        time=("1990-01-01", "1999-12-31"),
    )
    assert set(result.masks) == {
        (None, "ALL001"),
        (None, "BOX001"),
        (None, "WET001"),
        ("era5", "ERA001"),
        ("era5", "QE001"),
        ("glorys", "QE002"),
    }
    assert result.skipped == ((None, "DRY001"),)
    assert result.masks[(None, "ALL001")].tolist() == [[True, True], [True, False]]
    assert result.masks[(None, "WET001")].tolist() == [[False, True], [True, False]]
    assert result.masks[("era5", "QE001")].tolist() == [[False, False], [True, False]]
    assert result.fractions[(None, "BOX001")] == 0.5  # the NaN point weighs nothing
    found = {(f.product, f.code): f for f in result.findings}
    assert found[(None, "BOX001")].area_fraction == 0.5
    assert found[("glorys", "QE002")].time_overlap == (("1990-01-01", "1992-12-31"),)
    assert result.any(qe.Severity.SEVERE).tolist() == [[True, True], [True, False]]
    assert result.any("warning").sum() == 3
    with_conditional = index.query_points(lon, lat, include_conditional=True)
    conditional = [f for f in with_conditional.findings if f.conditional_on]
    assert {f.code: f.conditional_on for f in conditional} == {
        "RES001": ("resolution",),
        "ERA001": ("product",),
        "IDS001": ("space",),
    }
    assert all((None, f.code) not in with_conditional.masks for f in conditional)
    with pytest.raises(ValueError, match="support"):
        index.query_points(
            lon, lat, requests=[qe.Request("era5", support=sp.point(0, 0))]
        )
    with pytest.raises(TypeError):
        index.query_points(lon, lat, context={"stn": 1})


# ---- property test: query_points agrees with Index.query point by point ------------------
def random_space(rng):
    pick = rng.random()
    south = rng.choice([-90, -60, -10, 0, 30, 66.5])
    north = rng.choice([n for n in (-30, 0, 10, 45, 80, 90) if n > south] or [90])
    if pick < 0.2:
        return sp.lat_band(south, north)
    if pick < 0.6:  # integer edges, so grid points fall on them; some cross +-180
        west = rng.choice([-180, -170, -10, 0, 5, 150, 170])
        return sp.box_arc(west, rng.choice([10, 20, 45, 90, 200]), south, north)
    if pick < 0.75:  # a ring around a pole, closed along it
        lat = rng.choice([60.0, -70.0, 75.5])
        return sp.polygon([(lon, lat) for lon in range(-180, 180, 15)])
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


def random_bulk_index(rng):
    index = qe.Index("property", axes=[qe.Axis("resolution", "km")])
    index.add_regions(
        "reg", {"A": sp.box(-20, -20, 20, 20), "B": sp.box(170, 50, -170, 80)}
    )
    index.add_product(qe.Product("cru_ts", version="4.07"))
    index.add_product(
        qe.Product("era5", coverage=qe.Coverage(space=sp.box(-90, -45, 120, 70)))
    )
    index.add_product(
        qe.Product("glorys", coverage=qe.Coverage(time=qe.interval("1993-01-01", "..")))
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
        severity = rng.choice(["info", "warning", "severe"])
        index.add(
            qe.Rule(
                code=f"RND{k:03d}",
                kind="caveat",
                title="t",
                message="m",
                severity=severity,
                region_ref=refs,
                scope=qe.Scope(**scope),
            )
        )
    return index


def random_points(rng, n=60):
    lon = [rng.uniform(-180, 180) for _ in range(n)]
    lat = [rng.uniform(-90, 90) for _ in range(n)]
    for _ in range(n):  # on rule edges, the seam and the poles
        lon.append(rng.choice([-180, 180, -170, -10, 0, 5, 10, 20, 150, 170, 25, 45]))
        lat.append(rng.choice([-90, -60, -30, -10, 0, 10, 30, 45, 66.5, 80, 90, 3.3]))
    lon.append(math.nan)
    lat.append(0.0)
    return np.array(lon), np.array(lat)


def test_query_points_agrees_with_index_query_point_by_point():
    rng = random.Random(20261012)
    index = random_bulk_index(rng)
    seen = 0
    for _ in range(6):
        lon, lat = random_points(rng)
        fields = {}
        if rng.random() < 0.5:
            fields["time"] = (f"{rng.randint(1985, 2015)}-01-01", "2020-12-31")
        if rng.random() < 0.5:
            fields["axes"] = {"resolution": rng.choice([8.0, 30.0, (8.0, 12.0)])}
        if rng.random() < 0.6:
            fields["requests"] = rng.sample(["cru_ts", "era5", "glorys"], 2)
        result = index.query_points(lon, lat, **fields)
        assert all(not m[-1] for m in result.masks.values())  # the NaN point
        for j in range(lon.size - 1):
            single = index.query(space=sp.point(lon[j], lat[j]), **fields)
            expected = {(f.product, f.code) for f in single}
            got = {key for key, mask in result.masks.items() if mask[j]}
            assert got == expected, (lon[j], lat[j], fields)
            seen += len(expected)
    assert seen > 500  # the points reach the rules


# ---- the inverse query: section 10.3 --------------------------------------------------
def lake_index():
    index = qe.Index("glhe")
    index.add_regions("ar6", {"CAF": sp.box(10, -10, 30, 10)})
    for name, size, start, space in (
        ("cru_ts", 0.5, "1901-01-01", None),
        ("era5_land", 0.1, "1950-01-01", None),
        ("nwm_retro", 1.0, "1979-02-01", sp.box(-125, 24, -66, 50)),
    ):
        unit = "km" if name == "nwm_retro" else "deg"
        end = "2022-12-31" if name == "cru_ts" else ".."
        coverage = qe.Coverage(space, qe.interval(start, end))
        index.add_product(
            qe.Product(
                name, variables=("pre",), coverage=coverage, resolution=(size, unit)
            )
        )
    index.add_product(qe.Product("glorys", variables=("thetao",)))
    index.add(
        qe.Rule(
            code="CRU001",
            kind="caveat",
            title="t",
            message="m",
            min_overlap=0.1,
            region_ref=("ar6:CAF",),
            scope=qe.Scope(
                time=qe.interval("2000-01-01", ".."),
                facets={"product": ["cru_ts"], "variable": ["pre"]},
            ),
        )
    )
    return index


LAKE = sp.box(20.0, 0.0, 20.11, 0.11)  # about 150 km2 near the equator, in CAF
Y1991_2020 = qe.interval("1991-01-01", "2020-12-31")


def test_suitable_ranks_by_known_concerns_and_drops_products_outside_coverage():
    index = lake_index()
    assert LAKE.area_km2 == pytest.approx(150, rel=0.01)
    ranked = index.suitable(qe.Query(space=LAKE, time=Y1991_2020), "pre")
    assert [s.product.name for s in ranked] == ["era5_land", "cru_ts"]
    assert ranked[0].score == (0.0, 0.0, 0.0) and ranked[0].findings == ()
    worst, burden, misfit = ranked[1].score
    assert (worst, burden, round(misfit, 2)) == (30.0, 1.4, 2.18)
    (cru001,) = ranked[1].findings
    assert cru001.assumed == () and cru001.area_fraction == 1.0
    assert round(cru001.time_fraction, 3) == 0.700
    every = index.suitable(
        qe.Query(space=LAKE, time=Y1991_2020), "pre", include_dropped=True
    )
    assert every[:2] == ranked and every[2].product.name == "nwm_retro"
    assert every[2].score == () and [f.code for f in every[2].findings] == ["QE001"]
    assert every[2].findings[0].action == "do_not_use"


def test_suitable_takes_named_products_and_a_custom_score():
    index = lake_index()
    query = qe.Query(space=LAKE, time=Y1991_2020)

    def resolution_first(product, query, findings):
        worst, burden, misfit = qe.default_score(product, query, findings)
        return (misfit, worst, burden)

    ranked = index.suitable(query, "pre", products=["CRU_TS", "era5_land"])
    assert [s.product.name for s in ranked] == ["era5_land", "cru_ts"]
    assert index.suitable(query, "pre", score=resolution_first)[1].score[0] > 2
    with pytest.raises(qe.UnknownNameError):
        index.suitable(query, "pre", products=["merra2"])
    with pytest.raises(ValueError, match="do not offer"):
        index.suitable(query, "pre", products=["glorys"])
    with pytest.raises(ValueError, match="requests"):
        index.suitable(qe.Query(space=LAKE, requests=["cru_ts"]), "pre")
    point = index.suitable(qe.Query(space=sp.point(20, 0), time=Y1991_2020), "pre")
    assert point[1].score[2] == 0.0  # no misfit without an area
