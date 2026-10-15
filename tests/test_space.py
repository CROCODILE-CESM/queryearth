"""Space: polygons across +-180, boxes to the poles, and closed-set meeting."""

import pytest
import shapely

from queryearth import space as sp


def test_wrapping_a_longitude_is_exact():
    assert sp.wrap_lon(190) == -170
    assert sp.wrap_lon(540) == 180 and sp.wrap_lon(-540) == -180
    # ((x + 180) % 360) - 180 would send this to -180
    assert sp.wrap_lon(179.99999999999997) == 179.99999999999997


def test_a_box_across_the_antimeridian_is_split_there():
    fiji = sp.box(170, -20, -170, -10)  # west > east
    west, east = sorted(fiji.geometry.geoms, key=lambda part: part.bounds[0])
    assert west.bounds == (-180, -20, -170, -10)
    assert east.bounds == (170, -20, 180, -10)


def test_any_longitude_convention_gives_the_same_shape():
    fiji = sp.box(170, -20, -170, -10)
    for ring in (
        [(170, -20), (190, -20), (190, -10), (170, -10)],
        [(170, -20), (-170, -20), (-170, -10), (170, -10)],
        [(-190, -20), (-170, -20), (-170, -10), (-190, -10)],
    ):
        assert shapely.equals(sp.polygon(ring).geometry, fiji.geometry)


def test_a_rule_across_the_antimeridian_meets_points_on_both_sides():
    fiji = sp.box(170, -20, -170, -10)
    for lon in (175, -175, 180, -180):
        assert sp.meets(fiji, sp.point(lon, -15))
    assert not sp.meets(fiji, sp.point(0, -15))


def test_shapes_that_touch_at_the_antimeridian_meet():
    east_of_seam = sp.box(-180, 0, -170, 10)
    assert sp.meets(sp.box(170, 0, 180, 10), east_of_seam)
    assert sp.meets(sp.box(170, 0, 180, 10), sp.point(-180, 5))


def test_a_point_on_an_edge_is_inside():
    square = sp.box(0, 0, 10, 10)
    for lon, lat in [(0, 5), (10, 5), (5, 0), (10, 10)]:
        assert sp.meets(square, sp.point(lon, lat))
    assert not sp.meets(square, sp.point(10.1, 5))


def test_a_hole_is_outside_but_its_edge_is_inside():
    square = [(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)]
    hole = [(4, 4), (6, 4), (6, 6), (4, 6), (4, 4)]
    framed = sp.polygon({"type": "Polygon", "coordinates": [square, hole]})
    assert not sp.meets(framed, sp.point(5, 5))
    assert sp.meets(framed, sp.point(4, 5))


def test_a_box_to_the_pole_covers_everything_beyond_its_latitude():
    arctic = sp.box(-180, 66.5, 180, 90)
    assert sp.meets(arctic, sp.point(123, 80)) and sp.meets(arctic, sp.point(0, 90))
    assert not sp.meets(arctic, sp.point(0, 60))
    assert sp.meets(sp.box(-180, -90, 180, -60), sp.point(45, -75))


def test_a_box_to_the_pole_can_be_written_as_a_ring():
    ring = [(-180, 70), (180, 70), (180, 90), (-180, 90)]
    assert shapely.equals(sp.polygon(ring).geometry, sp.box(-180, 70, 180, 90).geometry)


def test_a_ring_around_a_pole_is_refused_with_a_hint():
    with pytest.raises(ValueError, match="as a box to latitude 90"):
        sp.polygon([(0, 70), (90, 70), (180, 70), (-90, 70)])


def test_a_ring_that_crosses_itself_is_repaired():
    bow_tie = sp.polygon([(0, 0), (2, 2), (2, 0), (0, 2)])
    assert bow_tie.geometry.area == 2.0  # both triangles kept


def test_bad_boxes_and_latitudes_are_refused():
    with pytest.raises(ValueError):
        sp.box(10, 0, 10, 5)  # west == east
    with pytest.raises(ValueError):
        sp.box(0, 5, 10, 0)  # south > north
    with pytest.raises(ValueError):
        sp.point(0, 91)
    assert sp.point(0, 90 + 5e-10).geometry.y == 90  # rounding error is clamped
