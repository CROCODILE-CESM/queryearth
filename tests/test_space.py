"""queryearth.space: fixtures 1, 2, 6, 7, 9 and 22 of docs/reference/fixtures.md, and edge cases.

Fixtures that speak of rules and findings are tested on the operations those
findings rely on: meets() for the closed-set predicate, measure() for
area_fraction and overlap_km2, and points_mask() for the bulk path's mask.
"""

import math

import numpy as np
import pytest
import shapely

from queryearth import space as sp

R = sp.R_KM


def cap_km2(lat):
    """Exact area north of a latitude on the sphere."""
    return 2.0 * math.pi * R**2 * (1.0 - math.sin(math.radians(lat)))


def parts(space):
    return len(shapely.get_parts(space.geometry))


def geojson(*rings):
    return {"type": "Polygon", "coordinates": [list(r) for r in rings]}


# ---- fixture 1: exact longitude wrap ----------------------------------------------
@pytest.mark.parametrize(
    ("x", "wrapped"),
    [
        (179.99999999999997, 179.99999999999997),
        (540, 180),
        (-540, -180),
        (190, -170),
        (360, 0),
    ],
)
def test_fixture_1_wrap_lon_is_exact(x, wrapped):
    assert sp.wrap_lon(x) == wrapped
    assert sp.wrap_lon(np.array([x]))[0] == wrapped


def test_fixture_1_the_common_formula_rounds_at_the_seam():
    assert ((179.99999999999997 + 180) % 360) - 180 == -180.0


# ---- fixture 2: antimeridian box --------------------------------------------------
def test_fixture_2_antimeridian_box():
    forms = [
        sp.box(170, -20, -170, -10),
        sp.polygon([(170, -20), (-170, -20), (-170, -10), (170, -10)]),
        sp.polygon([(170, -20), (190, -20), (190, -10), (170, -10)]),
    ]
    for space in forms:
        assert parts(space) == 2
        assert shapely.equals(space.geometry, forms[0].geometry)
        assert round(space.area_km2) == 2_385_578
        for lon in (175, -175, 180, -180):
            assert sp.meets(space, sp.point(lon, -15))
        assert not sp.meets(space, sp.point(0, -15))


# ---- rings around a pole are refused ------------------------------------------------
def test_a_ring_around_a_pole_says_how_to_close_it():
    with pytest.raises(ValueError, match="close it along latitude 90 or -90"):
        sp.polygon([(-180 + i, 70) for i in range(360)])
    with pytest.raises(ValueError, match="encloses a pole"):
        sp.polygon([(-180 + i, 70) for i in range(0, 720, 10)])  # twice around


def test_a_ring_along_one_parallel_encloses_no_area():
    with pytest.raises(ValueError, match="the ring encloses no area"):
        sp.polygon([(-180 + i, 70) for i in range(361)])  # -180 and 180 both listed


def test_closing_a_polar_ring_along_the_pole_gives_the_cap():
    cap = sp.polygon([(-180, 70), (180, 70), (180, 90), (-180, 90)])
    assert cap.area_km2 == pytest.approx(cap_km2(70), rel=1e-12)
    assert shapely.equals(cap.geometry, sp.box(-180, 70, 180, 90).geometry)


# ---- fixture 6: closed edges -------------------------------------------------------
def test_fixture_6_closed_edges():
    rule = sp.box(0, 0, 10, 10)
    for lon, lat in ((0, 5), (10, 5), (5, 0), (5, 10), (10, 10), (0, 10)):
        assert sp.meets(rule, sp.point(lon, lat))
    lon, lat = np.meshgrid(np.arange(-1, 11.25, 0.25), np.arange(-1, 11.25, 0.25))
    assert lon.size == 2_401
    assert sp.points_mask(rule, lon, lat).sum() == 1_681
    assert shapely.contains_xy(rule.geometry, lon, lat).sum() == 1_521
    neighbour = sp.box(10, 0, 20, 10)
    assert sp.meets(rule, neighbour)
    assert sp.measure(rule, neighbour) == (0.0, 0.0)


# ---- fixture 7: holes and multipolygons -------------------------------------------
def test_fixture_7_holes():
    square = [(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)]
    hole = [(4, 4), (6, 4), (6, 6), (4, 6), (4, 4)]
    rule = sp.polygon(geojson(square, hole))
    assert not sp.meets(rule, sp.point(5, 5))
    assert sp.meets(rule, sp.point(4, 5))


def test_fixture_7_overlapping_parts_are_not_counted_twice():
    rule = sp.polygon(
        {
            "type": "MultiPolygon",
            "coordinates": [
                [[(0, 0), (4, 0), (4, 2), (0, 2), (0, 0)]],
                [[(2, 0), (6, 0), (6, 2), (2, 2), (2, 0)]],
            ],
        }
    )
    fraction, km2 = sp.measure(rule, sp.box(0, 0, 6, 2))
    assert fraction == 1.0
    assert km2 == pytest.approx(rule.area_km2)


def test_fixture_7_bow_ties_keep_both_triangles():
    bow_tie = sp.polygon([(0, 0), (2, 2), (2, 0), (0, 2)])
    assert bow_tie.geometry.area == pytest.approx(2.0)
    assert parts(bow_tie) == 2
    spiked = [(0, 0), (2, 2), (2, 0), (0, 2), (0, 0), (-1, -1)]
    assert shapely.make_valid(shapely.Polygon(spiked)).geom_type == "GeometryCollection"
    assert sp.polygon(spiked).geometry.area == pytest.approx(2.0)


# ---- fixture 9: overlap fraction and area ------------------------------------------
def test_fixture_9_overlap_fraction_and_area():
    query = sp.box(0, 40, 10, 50)
    assert query.area_km2 == pytest.approx(873_182.018, abs=5e-4)
    west_half, _ = sp.measure(sp.box(0, 40, 5, 50), query)
    south_half, _ = sp.measure(sp.box(0, 40, 10, 45), query)
    assert west_half == pytest.approx(0.5)
    assert round(south_half, 5) == 0.52183
    assert (
        shapely.area(sp.box(0, 40, 10, 45).geometry) / shapely.area(query.geometry)
        == 0.5
    )


def test_fixture_9_areas_match_pyproj_on_the_same_sphere():
    pyproj = pytest.importorskip("pyproj")
    geod = pyproj.Geod(a=R * 1000.0, b=R * 1000.0)
    square = [(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)]
    hole = [(4, 4), (6, 4), (6, 6), (4, 6), (4, 4)]
    shapes = [
        sp.box(0, 40, 10, 50),
        sp.box(0, 40, 5, 50),
        sp.box(0, 40, 10, 45),
        sp.box(0.30, 0.30, 0.45, 0.45),
        sp.box(170, -20, -170, -10),
        sp.polygon(geojson(square, hole)),
    ]
    for space in shapes:
        dense = shapely.segmentize(space.geometry, 0.01)
        reference = abs(geod.geometry_area_perimeter(dense)[0]) / 1e6
        assert space.area_km2 == pytest.approx(reference, rel=1e-8)


# ---- fixture 22: planar caps and bands -------------------------------------------------
@pytest.mark.parametrize(
    ("ring", "expected"),
    [
        ([(-180, 66.5), (180, 66.5), (180, 90), (-180, 90)], cap_km2(66.5)),
        (
            [(-180, -30), (180, -30), (180, 30), (-180, 30)],
            2
            * math.pi
            * R**2
            * (math.sin(math.radians(30)) - math.sin(math.radians(-30))),
        ),
        ([(-180, -90), (180, -90), (180, -60), (-180, -60)], cap_km2(60)),
    ],
)
def test_fixture_22_planar_caps_and_bands(ring, expected):
    space = sp.polygon(geojson(ring + ring[:1]))
    assert space.area_km2 == pytest.approx(expected, rel=1e-15)


def test_fixture_22_points_against_the_planar_cap():
    era5_024 = sp.polygon(geojson([(-180, 66.5), (180, 66.5), (180, 90), (-180, 90)]))
    assert round(era5_024.area_km2) == 21_152_413
    assert sp.meets(era5_024, sp.point(123, 90))
    assert not sp.meets(era5_024, sp.point(0, 60))


# ---- boxes ---------------------------------------------------------------------------
def test_box_east_before_west_crosses_the_antimeridian():
    assert shapely.equals(
        sp.box(350, 0, 10, 5).geometry, sp.box(-10, 0, 10, 5).geometry
    )
    assert sp.box(180, 0, 190, 1).geometry.bounds == (-180.0, 0.0, -170.0, 1.0)
    assert sp.box(160, 0, -180, 1).geometry.bounds == (160.0, 0.0, 180.0, 1.0)


def test_box_from_minus_180_to_180_is_a_latitude_band():
    band = sp.box(-180, 60, 180, 90)
    assert parts(band) == 1 and band.geometry.bounds == (-180.0, 60.0, 180.0, 90.0)
    assert band.area_km2 == pytest.approx(cap_km2(60), rel=1e-12)
    assert sp.box(0, 0, 360, 5).area_km2 == sp.box(-180, 0, 180, 5).area_km2
    assert sp.meets(band, sp.point(123, 75)) and not sp.meets(band, sp.point(0, 59))


@pytest.mark.parametrize(
    "call",
    [
        lambda: sp.box(10, 0, 10, 5),  # east == west
        lambda: sp.box(0, 0, 400, 5),  # more than 360 degrees
        lambda: sp.box(0, 5, 10, 5),  # south == north
        lambda: sp.box(0, 0, 10, 91),
        lambda: sp.box(np.nan, 0, 10, 5),
        lambda: sp.point(0, -90.000001),
        lambda: sp.point(0, np.nan),
    ],
)
def test_invalid_boxes_and_latitudes_are_rejected(call):
    with pytest.raises(ValueError):
        call()


def test_latitudes_just_beyond_the_pole_are_clamped():
    assert sp.point(0, 90 + 5e-10).geometry.y == 90.0
    assert sp.box(0, -90 - 5e-10, 10, 0).geometry.bounds[1] == -90.0


# ---- polygons ---------------------------------------------------------------------------
def test_polygon_input_forms_agree():
    ring = [(0, 0), (1, 0), (1, 1), (0, 1)]
    expected = sp.polygon(ring).geometry
    for shape in (
        shapely.Polygon(ring),
        geojson(ring + ring[:1]),
        {"type": "Feature", "geometry": geojson(ring), "properties": {}},
        [(x, y, 100.0) for x, y in ring],
    ):
        assert shapely.equals(sp.polygon(shape).geometry, expected)
    for bad in ({"type": "LineString", "coordinates": ring}, None, [(0, 0), (1, 1)]):
        with pytest.raises(ValueError):
            sp.polygon(bad)


def test_exteriors_run_counterclockwise():
    space = sp.polygon(list(reversed([(0, 0), (1, 0), (1, 1), (0, 1)])))
    assert shapely.is_ccw(space.geometry.exterior)


def test_any_longitude_convention_gives_the_same_shape():
    east = sp.polygon([(350.0, 0.0), (350.25, 0.0), (350.25, 0.25), (350.0, 0.25)])
    west = sp.polygon([(-10.0, 0.0), (-9.75, 0.0), (-9.75, 0.25), (-10.0, 0.25)])
    assert shapely.equals(east.geometry, west.geometry)
    lake_east = sp.polygon([(350.0, 0.0), (350.15, 0.0), (350.15, 0.15), (350.0, 0.15)])
    lake_west = sp.polygon([(-10.0, 0.0), (-9.85, 0.0), (-9.85, 0.15), (-10.0, 0.15)])
    rule = sp.box(-9.9, -1, 0, 1)
    assert lake_east.area_km2 == pytest.approx(lake_west.area_km2, rel=1e-9)
    assert sp.measure(rule, lake_east)[0] == pytest.approx(
        sp.measure(rule, lake_west)[0]
    )


# ---- predicates at the seam ------------------------------------------------------------
def test_shapes_meet_across_the_seam():
    east_of_seam = sp.box(170, 0, 180, 10)
    assert sp.meets(east_of_seam, sp.point(-180, 5))
    west_of_seam = sp.box(-180, 0, -170, 10)
    assert sp.meets(east_of_seam, west_of_seam)
    assert sp.measure(east_of_seam, west_of_seam) == (0.0, 0.0)
    assert not sp.meets(east_of_seam, sp.box(-180, 20, -170, 30))


def test_points_mask_tests_both_sides_of_the_seam_and_any_convention():
    fiji = sp.box(170, -20, -170, -10)
    lon = np.array([175.0, -175.0, 180.0, -180.0, 0.0, 185.0, 540.0])
    mask = sp.points_mask(fiji, lon, np.full(lon.shape, -15.0))
    assert mask.tolist() == [True, True, True, True, False, True, True]


def test_points_at_a_pole_follow_their_longitude():  # the pole-edge rule is dropped
    rule = sp.box(0, 80, 90, 90)
    assert sp.meets(rule, sp.point(45, 90)) and not sp.meets(rule, sp.point(123, 90))


# ---- other query spaces ---------------------------------------------------------------
def test_points_with_nan_are_inside_no_rule():
    mask = sp.points_mask(sp.box(0, 0, 10, 10), [np.nan, 5, 5], [5, np.nan, 5])
    assert mask.tolist() == [False, False, True]
    assert sp.points_mask(None, [np.nan, 5], [5, 5]).tolist() == [False, True]
    with pytest.raises(ValueError):
        sp.points_mask(None, [0, 1], [0])


def test_global_rules():
    lake = sp.box(0, 0, 1, 1)
    assert sp.meets(None, lake)
    assert sp.measure(None, lake) == (1.0, lake.area_km2)
    assert sp.measure(None, sp.point(0, 0)) == (1.0, None)


def test_points_are_measured_without_area():
    assert sp.measure(sp.box(0, 0, 1, 1), sp.point(0.5, 0.5)) == (1.0, None)
    assert sp.measure(sp.box(0, 0, 1, 1), sp.point(5, 5)) == (0.0, None)
    with pytest.raises(TypeError):
        sp.meets(sp.point(0, 0), sp.box(0, 0, 1, 1))  # a rule shape is a polygon


def test_spaces_compare_by_identity():
    a, b = sp.point(0, 0), sp.point(0, 0)
    assert a != b and a == a
    assert len({a, b}) == 2
