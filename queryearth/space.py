"""Space: points and polygons on the globe, and whether they meet.

Coordinates are float64 (longitude, latitude) in degrees on WGS84, and edges
are straight lines in longitude-latitude, as in GeoJSON. Every polygon is
normalised once, when it is made: longitudes wrapped exactly, rings cut at
+-180 and invalid rings repaired. A ring that goes around a pole is refused;
write a polar region as a box to latitude 90 or -90. Matching uses closed sets,
so a point on an edge is inside.

Import as ``from queryearth import space as sp``.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

import numpy as np
import shapely

__all__ = ["Space", "box", "meets", "point", "polygon", "wrap_lon"]

LAT_TOLERANCE = 1e-9  # degrees beyond +-90 that are clamped rather than refused


@dataclass(frozen=True, eq=False)
class Space:
    """A point or a normalised (multi)polygon; compares and hashes by identity.

    geometry is a shapely Point or (Multi)Polygon in [-180, 180] with no part
    crossing +-180. Make one with point(), box() or polygon().
    """

    kind: Literal["point", "polygon"]
    geometry: shapely.Geometry


# ---- coordinates -----------------------------------------------------------------
def wrap_lon(x: Any) -> Any:
    """x in [-180, 180] with no rounding error, as a float or an array like x.

    180 and -180 stay as given. Adding or subtracting 360 is exact, since the
    remainder and 360 are within a factor of two of each other.
    """
    r = np.fmod(x, 360.0)
    r = np.where(r > 180.0, r - 360.0, np.where(r < -180.0, r + 360.0, r))
    return r if np.ndim(r) else float(r)


def _lat(value: Any) -> Any:
    """Latitudes clamped to [-90, 90], or ValueError beyond LAT_TOLERANCE."""
    value = np.asarray(value, dtype=float)
    if np.any(np.abs(value) > 90.0 + LAT_TOLERANCE):
        raise ValueError(f"a latitude is outside [-90, 90]: {value!r}")
    value = np.clip(value, -90.0, 90.0)
    return value if np.ndim(value) else float(value)


def _shift(geometry: shapely.Geometry, dx: float) -> shapely.Geometry:
    return shapely.transform(geometry, lambda c: c + (dx, 0.0))


# ---- polygon normalisation -------------------------------------------------------
def _polygonal(shape: shapely.Geometry) -> shapely.Geometry:
    """The polygon parts of a geometry, merged."""
    # make_valid can nest a MultiPolygon inside a GeometryCollection
    parts = shapely.get_parts(shapely.get_parts(shape))
    return shapely.union_all(parts[shapely.get_type_id(parts) == 3])  # Polygon


def _split_at_seam(shape: shapely.Geometry) -> shapely.Geometry:
    """Cut an unwrapped shape into 360 degree strips and move each into [-180, 180]."""
    west, _, east, _ = shape.bounds
    pieces = []
    for k in range(
        math.floor((west + 180.0) / 360.0), math.ceil((east - 180.0) / 360.0) + 1
    ):
        strip = shapely.box(360.0 * k - 180.0, -90.0, 360.0 * k + 180.0, 90.0)
        piece = shapely.intersection(shape, strip)
        if not piece.is_empty:
            pieces.append(_shift(piece, -360.0 * k))
    return _polygonal(shapely.union_all(pieces))


def _ring(coords: Any) -> shapely.Geometry:
    """One closed ring of positions, unwrapped, repaired and cut at +-180.

    Each step between vertices is taken the short way, except that a step of
    exactly 180 degrees, and a full-turn step of exactly 360 degrees along a
    box's edge, keep the direction they were written in. Every vertex is its
    wrapped longitude plus whole turns, so no rounding error builds up.
    """
    lon, lat = np.asarray([c[:2] for c in coords][:-1], dtype=float).reshape(-1, 2).T
    if lon.size < 3 or not np.isfinite([lon, lat]).all():
        raise ValueError("a ring needs three vertices with finite coordinates")
    wrapped = wrap_lon(lon)
    steps = np.diff(lon, append=lon[0])  # the last one closes the ring
    steps = np.where(np.abs(steps) == 360.0, steps, wrap_lon(steps))
    lands = wrapped[0] + np.cumsum(steps)  # where each step lands, before rounding
    u = wrapped + 360.0 * np.round((np.r_[wrapped[0], lands[:-1]] - wrapped) / 360.0)
    if round((lands[-1] - wrapped[0]) / 360.0):
        raise ValueError(
            "the ring goes around the globe, so it encloses a pole, which is not "
            "supported; write a polar region as a box to latitude 90 or -90, as "
            "in (-180, 70), (180, 70), (180, 90), (-180, 90)"
        )
    shape = _polygonal(shapely.make_valid(shapely.Polygon(zip(u, _lat(lat)))))
    if shape.is_empty:
        raise ValueError("the ring encloses no area")
    return _split_at_seam(shape)


# ---- making spaces ---------------------------------------------------------------
def point(lon: float, lat: float) -> Space:
    """A point, such as a station or a grid cell centre."""
    lon, lat = float(lon), _lat(lat)
    if not (math.isfinite(lon) and math.isfinite(lat)):
        raise ValueError(f"a point needs finite coordinates, got {lon!r}, {lat!r}")
    return Space("point", shapely.Point(wrap_lon(lon), lat))


def box(west: float, south: float, east: float, north: float) -> Space:
    """A box from west to east between two latitudes.

    west > east crosses the antimeridian and gives two parts, and -180 to 180
    is a full latitude band; to latitude 90 or -90, it covers the pole.
    """
    west, east = float(west), float(east)
    width = east - west if east > west else east - west + 360.0
    if east == west or not 0.0 < width <= 360.0:
        raise ValueError(
            f"a box needs west != east, at most 360 degrees apart (-180 to 180 is "
            f"a latitude band), got {west!r}, {east!r}"
        )
    south, north = _lat(south), _lat(north)
    if not south < north:
        raise ValueError(f"need south < north, got {south!r}, {north!r}")
    west = -180.0 if width == 360.0 else wrap_lon(west)
    return Space(
        "polygon", _split_at_seam(shapely.box(west, south, west + width, north))
    )


def polygon(shape: Any) -> Space:
    """A normalised polygon from GeoJSON, shapely or a list of (lon, lat) positions.

    Longitudes may use any convention; holes are normalised as separate rings
    and subtracted. A ring that goes around a pole raises ValueError.
    """
    if hasattr(shape, "__geo_interface__"):
        shape = shape.__geo_interface__
    if not isinstance(shape, Mapping):
        shape = {"type": "Polygon", "coordinates": [shape]}  # one ring
    if shape.get("type") not in ("Polygon", "MultiPolygon"):
        raise ValueError(
            f"expected a Polygon or MultiPolygon, got {shape.get('type')!r}"
        )
    parts = []
    for part in shapely.get_parts(shapely.geometry.shape(shape)):
        exterior = _ring(part.exterior.coords)
        holes = shapely.union_all([_ring(h.coords) for h in part.interiors])
        parts.append(shapely.difference(exterior, holes))
    geometry = _polygonal(shapely.union_all(parts))
    if geometry.is_empty:
        raise ValueError("the shape encloses no area")
    return Space("polygon", geometry)


# ---- meeting ---------------------------------------------------------------------
def meets(rule: Space, query: Space) -> bool:
    """Whether a query point or polygon meets a rule polygon, as closed sets.

    A point on an edge meets the polygon, and shapes that touch across +-180
    meet there. A point at a pole has a longitude like any other point.
    """
    shape, other = rule.geometry, query.geometry
    shapely.prepare(shape)  # preparing a prepared geometry does nothing
    if shapely.intersects(shape, other):
        return True
    west, _, east, _ = other.bounds
    return (west == -180.0 and shapely.intersects(shape, _shift(other, 360.0))) or (
        east == 180.0 and shapely.intersects(shape, _shift(other, -360.0))
    )
