"""queryearth.space: fixtures 1 to 10, 18 and 22 of docs/reference/fixtures.md, and edge cases.

Fixtures that speak of rules and findings are tested on the operations those
findings rely on: meets() for the closed-set predicate, measure() for
area_fraction and overlap_km2, points_mask() for the bulk path's mask, and
cells() for the support.
"""

import logging
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


def circle(lat, step=1):
    """A ring along a parallel, the seam longitude listed once."""
    return [(-180 + i, lat) for i in range(0, 360, step)]


def polar_stereographic_inverse(x, y):
    """EPSG:3995 (WGS84, true scale at 71N, central meridian 0) to lon, lat."""
    a, f = 6378137.0, 1.0 / 298.257223563
    e2 = f * (2.0 - f)
    e = math.sqrt(e2)
    phi_c = math.radians(71.0)
    t_c = math.tan(math.pi / 4.0 - phi_c / 2.0) / (
        (1.0 - e * math.sin(phi_c)) / (1.0 + e * math.sin(phi_c))
    ) ** (e / 2.0)
    m_c = math.cos(phi_c) / math.sqrt(1.0 - e2 * math.sin(phi_c) ** 2)
    chi = math.pi / 2.0 - 2.0 * np.arctan(np.hypot(x, y) * t_c / (a * m_c))
    phi = (
        chi
        + (e2 / 2 + 5 * e2**2 / 24 + e2**3 / 12 + 13 * e2**4 / 360) * np.sin(2 * chi)
        + (7 * e2**2 / 48 + 29 * e2**3 / 240 + 811 * e2**4 / 11520) * np.sin(4 * chi)
        + (7 * e2**3 / 120 + 81 * e2**4 / 1120) * np.sin(6 * chi)
        + (4279 * e2**4 / 161280) * np.sin(8 * chi)
    )
    return np.degrees(np.arctan2(x, -y)), np.degrees(phi)


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


def test_fixture_1_the_common_formula_rounds_at_the_seam():
    assert ((179.99999999999997 + 180) % 360) - 180 == -180.0


# ---- fixture 2: antimeridian box --------------------------------------------------
def test_fixture_2_antimeridian_box():
    forms = [
        sp.box_arc(170, 20, -20, -10),
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


# ---- fixture 3: pole cap from a ring ----------------------------------------------
def test_fixture_3_pole_cap_from_a_ring():
    ring = circle(70)
    assert sp.unwrap_ring([p[0] for p in ring])[2] == 1
    cap = sp.polygon(ring)
    assert cap.poles == ("north",)
    assert cap.area_km2 == pytest.approx(cap_km2(70), rel=1e-12)
    assert round(cap.area_km2) == 15_380_368
    for lon, lat in ((123, 90), (0, 90), (-45, 70)):
        assert sp.meets(cap, sp.point(lon, lat))
    assert not sp.meets(cap, sp.point(0, 69.9))


def test_fixture_3_seam_listed_twice_encloses_no_area():
    with pytest.raises(ValueError, match="the ring encloses no area"):
        sp.polygon([(-180 + i, 70) for i in range(361)])


# ---- fixture 4: polar-stereographic domain ----------------------------------------
def test_fixture_4_polar_stereographic_domain():
    xy = np.linspace(-1.5e6, 1.5e6, 51)  # 51 nodes a side: 200 outline nodes
    lon, lat = polar_stereographic_inverse(*np.meshgrid(xy, xy))
    outline_lon, outline_lat = sp._outline(lon), sp._outline(lat)
    assert outline_lon.size == 200
    assert (round(outline_lat.min(), 2), round(outline_lat.max(), 2)) == (70.65, 76.26)
    assert not shapely.Polygon(zip(outline_lon, outline_lat)).is_valid
    assert sp.unwrap_ring(outline_lon.tolist())[2] == 1
    domain = sp.from_grid(lon, lat)
    assert domain.geometry.is_valid
    assert domain.poles == ("north",)
    assert sp.meets(domain, sp.point(123, 90))
    assert sp.meets(domain, sp.point(-45, 89.9))
    assert not sp.meets(domain, sp.point(0, 60))


# ---- fixture 5: pole point ----------------------------------------------------------
def test_fixture_5_pole_point():
    rule = sp.box_arc(0, 90, 80, 90)
    assert sp.meets(rule, sp.point(123, 90))
    lon, lat = np.meshgrid(np.arange(-180, 180, 0.25), np.arange(-90, 90.25, 0.25))
    assert lon.size == 1_038_240
    mask = sp.points_mask(rule, lon, lat)
    assert mask.shape == lon.shape
    assert mask.sum() == 15_880
    assert mask[lat == 90].all() and mask[lat == 90].size == 1_440
    assert shapely.intersects_xy(rule.geometry, lon, lat).sum() == 14_801


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


# ---- fixture 8: polar band from a hole --------------------------------------------
def test_fixture_8_polar_band_from_a_hole():
    band = sp.polygon(geojson(circle(66.5), circle(85)))
    assert band.poles == ("north", "north")
    assert not sp.meets(band, sp.point(0, 86))
    assert sp.meets(band, sp.point(0, 85))
    assert sp.meets(band, sp.point(0, 80))
    assert band.area_km2 == pytest.approx(cap_km2(66.5) - cap_km2(85), rel=1e-12)


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
        sp.box_arc(170, 20, -20, -10),
        sp.polygon(geojson(square, hole)),
    ]
    for space in shapes:
        dense = shapely.segmentize(space.geometry, 0.01)
        reference = abs(geod.geometry_area_perimeter(dense)[0]) / 1e6
        assert space.area_km2 == pytest.approx(reference, rel=1e-8)


# ---- fixture 10: small polygon and product cell -------------------------------------
GRID_HALF = (np.arange(-180, 180.5, 0.5), np.arange(-90, 90.5, 0.5))


def test_fixture_10_small_lake_and_its_cell():
    lake = sp.box(0.30, 0.30, 0.45, 0.45)
    rule = sp.box(0, 0, 0.2, 0.5)
    assert sp.cells(GRID_HALF, lake, "centre").kind == "empty"
    assert sp.cells(GRID_HALF, lake, "full").kind == "empty"
    support = sp.cells(GRID_HALF, lake, "overlap")
    assert shapely.equals(support.geometry, shapely.box(0, 0, 0.5, 0.5))
    assert not sp.meets(rule, lake)
    assert sp.meets(rule, support)
    assert sp.measure(rule, support)[0] == pytest.approx(0.4)


def test_fixture_10_grid_aligned_edge_does_not_pull_in_a_neighbour():
    lake = sp.box(0.30, 0.30, 0.50, 0.45)
    mask = sp.cell_mask(GRID_HALF, lake)
    assert mask.shape == (360, 720)
    assert mask.sum() == 1 and mask[180, 360]
    assert shapely.equals(
        sp.cells(GRID_HALF, lake).geometry, shapely.box(0, 0, 0.5, 0.5)
    )


# ---- fixture 18: resolution from a grid ----------------------------------------------
def test_fixture_18_resolution_from_corners_not_the_supergrid():
    corners = np.meshgrid(np.arange(0, 10.25, 0.25), np.arange(60, 70.25, 0.25))
    assert tuple(round(v, 2) for v in sp.resolution_of(*corners)) == (9.51, 27.80)
    x, y = np.meshgrid(np.arange(0, 10.125, 0.125), np.arange(60, 70.125, 0.125))
    assert tuple(round(v, 2) for v in sp.resolution_of(x, y)) == (4.75, 13.90)
    assert sp.resolution_of(x[::2, ::2], y[::2, ::2]) == sp.resolution_of(*corners)
    assert sp.resolution_of(*corners, unit="deg")[1] == pytest.approx(0.25)


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
    assert space.poles == ()


def test_fixture_22_points_against_the_planar_cap():
    era5_024 = sp.polygon(geojson([(-180, 66.5), (180, 66.5), (180, 90), (-180, 90)]))
    assert round(era5_024.area_km2) == 21_152_413
    assert sp.meets(era5_024, sp.point(123, 90))
    assert not sp.meets(era5_024, sp.point(0, 60))


# ---- boxes ---------------------------------------------------------------------------
def test_box_east_before_west_crosses_the_antimeridian():
    crossing = sp.box(170, -20, -170, -10)
    assert shapely.equals(crossing.geometry, sp.box_arc(170, 20, -20, -10).geometry)
    assert shapely.equals(
        sp.box(350, 0, 10, 5).geometry, sp.box(-10, 0, 10, 5).geometry
    )
    assert sp.box(0, 0, 360, 5).area_km2 == sp.lat_band(0, 5).area_km2


def test_box_arc_stores_west_180_as_minus_180():
    assert sp.box_arc(180, 10, 0, 1).geometry.bounds == (-180.0, 0.0, -170.0, 1.0)
    assert sp.box_arc(540, 10, 0, 1).geometry.bounds == (-180.0, 0.0, -170.0, 1.0)


@pytest.mark.parametrize(
    "call",
    [
        lambda: sp.box(10, 0, 10, 5),  # east == west
        lambda: sp.box_arc(0, 361, 0, 5),
        lambda: sp.box_arc(0, 0, 0, 5),
        lambda: sp.box(0, 5, 10, 5),  # south == north
        lambda: sp.box(0, 0, 10, 91),
        lambda: sp.lat_band(10, 0),
        lambda: sp.point(0, -90.000001),
    ],
)
def test_invalid_boxes_and_latitudes_are_rejected(call):
    with pytest.raises(ValueError):
        call()


def test_latitudes_just_beyond_the_pole_are_clamped():
    assert sp.point(0, 90 + 5e-10).geometry.y == 90.0
    assert sp.box(0, -90 - 5e-10, 10, 0).geometry.bounds[1] == -90.0


# ---- polygons ---------------------------------------------------------------------------
def test_pole_auto_follows_the_mean_latitude_and_is_logged(caplog):
    with caplog.at_level(logging.DEBUG, logger="queryearth"):
        south = sp.polygon(circle(-70, 10))
    assert south.poles == ("south",)
    assert sp.meets(south, sp.point(0, -90)) and not sp.meets(south, sp.point(0, 0))
    assert any("south pole" in r.getMessage() for r in caplog.records)
    assert sp.polygon(circle(70, 10), pole="south").poles == ("south",)


def test_pole_auto_needs_a_side_when_the_mean_latitude_is_zero():
    zigzag = [(-180 + i, 10 if i % 20 else -10) for i in range(0, 360, 10)]
    with pytest.raises(ValueError, match="pole="):
        sp.polygon(zigzag)
    assert sp.polygon(zigzag, pole="north").poles == ("north",)


def test_a_ring_that_winds_twice_is_rejected():
    twice = [(-180 + i, 70) for i in range(0, 720, 10)]
    with pytest.raises(ValueError, match="more than once"):
        sp.polygon(twice)


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
    with pytest.raises(ValueError):
        sp.polygon({"type": "LineString", "coordinates": ring})


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


# ---- grids ---------------------------------------------------------------------------
def test_a_grid_stored_from_170_to_200_normalises_to_two_parts():
    lon, lat = np.meshgrid(np.arange(170, 200.5, 0.5), np.arange(-20, -9.5, 0.5))
    domain = sp.from_grid(lon, lat)
    assert parts(domain) == 2
    assert shapely.equals(domain.geometry, sp.box(170, -20, 200, -10).geometry)


def test_a_grid_around_the_south_pole_keeps_the_south_pole():
    xy = np.linspace(-1.5e6, 1.5e6, 21)
    lon, lat = polar_stereographic_inverse(*np.meshgrid(xy, xy))
    domain = sp.from_grid(lon, -lat)
    assert domain.poles == ("south",)
    assert sp.meets(domain, sp.point(0, -90)) and not sp.meets(domain, sp.point(0, 60))


@pytest.mark.parametrize("east", [359.0, 360.0])  # with and without a repeated column
def test_a_grid_periodic_in_longitude_points_to_lat_band(east):
    lon, lat = np.meshgrid(np.arange(0, east + 0.5, 1.0), np.arange(-70, -49.5, 1.0))
    with pytest.raises(ValueError, match="lat_band"):
        sp.from_grid(lon, lat)


# ---- predicates at the seam and the poles ---------------------------------------------
def test_shapes_meet_across_the_seam():
    east_of_seam = sp.box(170, 0, 180, 10)
    assert sp.meets(east_of_seam, sp.point(-180, 5))
    west_of_seam = sp.box(-180, 0, -170, 10)
    assert sp.meets(east_of_seam, west_of_seam)
    assert sp.measure(east_of_seam, west_of_seam) == (0.0, 0.0)
    assert not sp.meets(east_of_seam, sp.box(-180, 20, -170, 30))


def test_shapes_that_reach_a_pole_meet_there():
    assert sp.meets(sp.box(0, 80, 10, 90), sp.box(100, 80, 110, 90))
    assert not sp.meets(sp.box(0, 80, 10, 89), sp.box(100, 80, 110, 90))


# ---- other query spaces ---------------------------------------------------------------
def test_weighted_points_fractions():
    rule = sp.box(0, 0, 10, 10)
    weighted = sp.weighted_points([1, 2, 3, 50], [1, 1, 1, 1], [1, 1, 0, 2])
    assert sp.measure(rule, weighted) == (0.5, None)
    assert sp.measure(rule, sp.weighted_points([1, 2, 3, 50], [1, 1, 1, 1])) == (
        0.75,
        None,
    )
    assert sp.meets(rule, weighted)
    with pytest.raises(ValueError):
        sp.weighted_points([1, 2], [1, 1], [0, 0])


def test_points_with_nan_are_inside_no_rule():
    mask = sp.points_mask(sp.box(0, 0, 10, 10), [np.nan, 5, 5], [5, np.nan, 5])
    assert mask.tolist() == [False, False, True]
    assert sp.points_mask(None, [np.nan, 5], [5, 5]).tolist() == [False, True]


def test_object_ids():
    query = sp.features([1, 2, 3], "nwm")
    fraction, km2 = sp.measure(sp.features(["2", "3", "9"], "nwm"), query)
    assert fraction == pytest.approx(2 / 3) and km2 is None
    assert sp.meets(sp.features(["3"], "nwm"), query)
    assert not sp.meets(sp.features(["9"], "nwm"), query)
    assert not sp.comparable(sp.box(0, 0, 1, 1), query)
    assert not sp.comparable(sp.features(["1"], "hydrolakes"), query)
    with pytest.raises(TypeError):
        sp.meets(sp.box(0, 0, 1, 1), query)


def test_global_rules_and_nowhere():
    lake = sp.box(0, 0, 1, 1)
    assert sp.meets(None, lake)
    assert sp.measure(None, lake) == (1.0, lake.area_km2)
    assert sp.measure(None, sp.point(0, 0)) == (1.0, None)
    nowhere = sp.nowhere()
    assert nowhere.area_km2 == 0.0
    assert not sp.meets(lake, nowhere) and not sp.meets(nowhere, lake)


def test_points_are_measured_without_area():
    assert sp.measure(sp.box(0, 0, 1, 1), sp.point(0.5, 0.5)) == (1.0, None)
    assert sp.measure(sp.box(0, 0, 1, 1), sp.point(5, 5)) == (0.0, None)


def test_spaces_compare_by_identity():
    a, b = sp.point(0, 0), sp.point(0, 0)
    assert a != b and a == a
    assert len({a, b}) == 2


# ---- cells ----------------------------------------------------------------------------
def test_cells_accept_any_longitude_convention():
    lake = sp.box(0.30, 0.30, 0.45, 0.45)
    shifted = (np.arange(0, 360.5, 0.5), GRID_HALF[1])
    assert shapely.equals(
        sp.cells(shifted, lake).geometry, sp.cells(GRID_HALF, lake).geometry
    )
    descending = (GRID_HALF[0], GRID_HALF[1][::-1])
    rows, columns = np.nonzero(sp.cell_mask(descending, lake))
    assert (rows.tolist(), columns.tolist()) == ([179], [360])


def test_cells_of_points_and_seam_crossing_cells():
    quarter = (np.arange(-180, 180.25, 0.25), np.arange(-90, 90.25, 0.25))
    assert sp.cell_mask(quarter, sp.point(0.5, 0.5)).sum() == 4  # on two grid lines
    assert sp.cell_mask(quarter, sp.point(123, 90)).sum() == 1_440  # the whole top row
    assert sp.cell_mask(quarter, sp.point(180, 0.1)).sum() == 2
    crossing = (np.array([179.75, 180.25, 180.75]), np.array([0.0, 1.0]))
    assert sp.cell_mask(crossing, sp.point(-179.9, 0.5)).tolist() == [[True, False]]
    assert parts(sp.cells(crossing, sp.point(179.9, 0.5))) == 2


def test_cells_union_merges_neighbours_with_inexact_edges():
    lon_edges = np.cumsum(np.full(21, 0.1))
    selected = sp.cells((lon_edges, np.array([0.0, 0.3, 0.7])), sp.box(0, 0, 5, 1))
    assert selected.geometry.geom_type == "Polygon"


def test_cells_reject_bad_input():
    with pytest.raises(ValueError, match="mode"):
        sp.cells(GRID_HALF, sp.point(0, 0), "center")
    with pytest.raises(TypeError):
        sp.cells(GRID_HALF, sp.features([1], "nwm"))
    with pytest.raises(ValueError):
        sp.cells((np.array([0.0, 1.0, 0.5]), np.array([0.0, 1.0])), sp.point(0, 0))
    assert sp.cells(GRID_HALF, sp.nowhere()).kind == "empty"
