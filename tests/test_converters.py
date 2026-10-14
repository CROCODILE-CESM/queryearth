"""queryearth.converters: grid outlines from cell corners."""

import numpy as np
import pytest

from queryearth import converters
from queryearth import space as sp


def corners(west, east, south, north, nx=10, ny=8):
    """Cell corners of a regular lon/lat grid, shaped (ny + 1, nx + 1)."""
    lon, lat = np.meshgrid(
        np.linspace(west, east, nx + 1), np.linspace(south, north, ny + 1)
    )
    return lon, lat


def parts(space):
    geoms = getattr(space.geometry, "geoms", [space.geometry])
    return sorted(tuple(round(v, 6) for v in g.bounds) for g in geoms)


def test_a_regular_grid_is_its_box():
    outline = converters.grid_outline(*corners(-60, -50, 30, 40))
    assert parts(outline) == [(-60, 30, -50, 40)]
    assert outline.area_km2 == pytest.approx(sp.box(-60, 30, -50, 40).area_km2)


def test_a_grid_across_the_antimeridian_is_split_in_either_convention():
    continuous = converters.grid_outline(*corners(165, 195, 52, 66))
    lon, lat = corners(165, 195, 52, 66)
    # the same grid with longitudes from -180 to 180: 165..180, then -180..-165
    wrapped = converters.grid_outline((lon + 180) % 360 - 180, lat)
    assert (
        parts(continuous)
        == parts(wrapped)
        == [(-180, 52, -165, 66), (165, 52, 180, 66)]
    )


def test_a_rotated_grid_follows_its_edges():
    i, j = np.meshgrid(np.arange(11.0), np.arange(9.0))
    angle = np.radians(30)
    lon = -40 + i * np.cos(angle) - j * np.sin(angle)
    lat = 20 + i * np.sin(angle) + j * np.cos(angle)
    outline = converters.grid_outline(lon, lat)
    assert sp.meets(outline, sp.point(lon[4, 5], lat[4, 5]))
    # inside the grid's bounding box, but outside the rotated grid
    assert not sp.meets(outline, sp.point(-40 + 10.5, 20))
    assert (
        outline.area_km2 < sp.box(lon.min(), lat.min(), lon.max(), lat.max()).area_km2
    )


def test_a_grid_all_the_way_round_is_a_band():
    outline = converters.grid_outline(*corners(0, 360, -70, -50, nx=36))
    assert parts(outline) == [(-180, -70, 180, -50)]


@pytest.mark.parametrize("hemisphere", [1, -1])
def test_a_grid_round_a_pole_becomes_the_cap(hemisphere):
    x, y = np.meshgrid(np.linspace(-10, 10, 21), np.linspace(-10, 10, 21))
    lat = hemisphere * (90 - np.hypot(x, y))  # an azimuthal grid centred on the pole
    lon = np.degrees(np.arctan2(y, x))
    outline = converters.grid_outline(lon, lat)
    farthest = hemisphere * (90 - np.hypot(10, 10))  # the outline's corners
    ((west, south, east, north),) = parts(outline)
    assert (west, east) == (-180, 180)
    if hemisphere > 0:
        assert (south, north) == (pytest.approx(farthest), 90)
    else:
        assert (south, north) == (-90, pytest.approx(farthest))
    assert sp.meets(outline, sp.point(0, hemisphere * 90))


def test_one_cell_is_that_cell():
    outline = converters.grid_outline([[0, 1], [0, 1]], [[0, 0], [1, 1]])
    assert parts(outline) == [(0, 0, 1, 1)]


@pytest.mark.parametrize(
    "lon, lat",
    [
        (np.zeros(5), np.zeros(5)),  # 1-D
        (np.zeros((3, 3)), np.zeros((3, 4))),  # shapes differ
        (np.zeros((1, 3)), np.zeros((1, 3))),  # one row of corners is no cell
        (np.array([[0, np.nan], [0, 1]]), np.array([[0, 0], [1, 1]])),  # NaN corner
    ],
)
def test_bad_corners_are_refused(lon, lat):
    with pytest.raises(ValueError):
        converters.grid_outline(lon, lat)
