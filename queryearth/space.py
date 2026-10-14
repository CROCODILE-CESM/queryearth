"""Space: points and polygons with straight lon/lat edges, and closed-set measures.

Coordinates are float64 (longitude, latitude) in degrees on WGS84 (CRS84), and
edges are straight lines in longitude-latitude. Every polygon is normalised once,
when it is built: longitudes wrapped exactly, rings cut at +-180, invalid rings
repaired and rings oriented; a ring that goes around a pole is refused (design.md
section 6). Areas use a closed form on a sphere of radius R_KM.

Import as ``from queryearth import space as sp``.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

import numpy as np
import shapely

__all__ = [
    "R_KM",
    "Space",
    "area_km2",
    "box",
    "edge",
    "edge_meets",
    "measure",
    "meets",
    "point",
    "points_mask",
    "polygon",
    "wrap_lon",
]

R_KM = 6371.0088  # mean Earth radius; area fractions do not depend on it
LAT_TOLERANCE = 1e-9  # degrees beyond +-90 that are clamped rather than refused
_EAST = shapely.LineString([(180.0, -90.0), (180.0, 90.0)])
_POLES = shapely.MultiLineString(
    [[(-180.0, 90.0), (180.0, 90.0)], [(-180.0, -90.0), (180.0, -90.0)]]
)


@dataclass(frozen=True, eq=False)
class Space:
    """A point or a normalised (multi)polygon; compares and hashes by identity.

    geometry is a shapely Point or (Multi)Polygon in [-180, 180] with no part
    crossing +-180; area_km2 is the spherical area of a polygon, None for a point.
    """

    kind: Literal["point", "polygon"]
    geometry: shapely.Geometry
    area_km2: float | None = None


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


# ---- polygon normalisation (design.md section 6.2) -----------------------------
def _polygonal(shape: shapely.Geometry) -> shapely.Geometry:
    """The polygon parts of a geometry, merged."""
    # make_valid can nest a MultiPolygon inside a GeometryCollection
    parts = shapely.get_parts(shapely.get_parts(shape))
    return shapely.union_all(parts[shapely.get_type_id(parts) == 3])  # Polygon


def _lines(shape: shapely.Geometry) -> shapely.Geometry:
    """The line parts of a geometry, merged."""
    parts = shapely.get_parts(shapely.get_parts(shape))
    return shapely.union_all(parts[shapely.get_type_id(parts) == 1])  # LineString


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
    exactly 180 degrees and a full-turn step of exactly 360 degrees keep the
    direction they were written in (fixture 22). Every vertex is its wrapped
    longitude plus whole turns, so no rounding error builds up along the ring.
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
            "supported; close it along latitude 90 or -90 first, as in (-180, 70), "
            "(180, 70), (180, 90), (-180, 90)"
        )
    shape = _polygonal(shapely.make_valid(shapely.Polygon(zip(u, _lat(lat)))))
    if shape.is_empty:
        raise ValueError("the ring encloses no area")
    return _split_at_seam(shape)


def _finish(geometry: shapely.Geometry) -> Space:
    geometry = shapely.orient_polygons(geometry)
    return Space("polygon", geometry, area_km2(geometry))


# ---- space helpers ---------------------------------------------------------------
def point(lon: float, lat: float) -> Space:
    """A point, such as a station or a grid cell centre."""
    lon, lat = float(lon), _lat(lat)
    if not (math.isfinite(lon) and math.isfinite(lat)):
        raise ValueError(f"a point needs finite coordinates, got {lon!r}, {lat!r}")
    return Space("point", shapely.Point(wrap_lon(lon), lat))


def box(west: float, south: float, east: float, north: float) -> Space:
    """A box from west to east between two latitudes.

    west > east crosses the antimeridian and gives two parts, and -180 to 180
    is a full latitude band, for a domain periodic in longitude.
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
    return _finish(_split_at_seam(shapely.box(west, south, west + width, north)))


def polygon(shape: Any) -> Space:
    """A normalised polygon from shapely, GeoJSON or a list of (lon, lat) positions.

    Longitudes may use any convention; holes are normalised as separate rings
    and subtracted. A ring that goes around a pole raises ValueError.
    """
    if hasattr(shape, "__geo_interface__"):
        shape = shape.__geo_interface__
    if isinstance(shape, Mapping) and shape.get("type") == "Feature":
        shape = shape.get("geometry")
    if shape is None:
        raise ValueError("no geometry given; a rule without one is global")
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
    return _finish(geometry)


def edge(space: Space) -> shapely.Geometry:
    """A polygon's edges on the globe, as lines.

    That is its boundary without the cuts at +-180, which join two parts of one
    shape, and without lines along latitude 90 or -90, which are a single point
    on the globe: the edge of a polar cap is its one circle of latitude.
    """
    if space.kind != "polygon":
        raise ValueError(f"only a polygon has an edge, not a {space.kind}")
    lines = _lines(shapely.boundary(space.geometry))
    east = _lines(shapely.intersection(lines, _EAST))
    west = _lines(shapely.intersection(lines, _shift(_EAST, -360.0)))
    cut = _lines(shapely.intersection(east, _shift(west, 360.0)))  # on both sides
    seams = shapely.union_all([cut, _shift(cut, -360.0), _POLES])
    return _lines(shapely.difference(lines, seams))


# ---- areas (design.md section 6.3) ---------------------------------------------
def _ring_area(coords: Any) -> float:
    """Signed area of a closed ring with straight lon/lat edges; CCW is positive.

    Each edge contributes dlon * sin(mean latitude) * sin(dlat / 2) / (dlat / 2),
    in radians, which is exact for a straight edge; an edge along a pole gives a
    pole cap its area.
    """
    # math, not numpy: the caps of fixture 22 must agree with 2 pi R^2 (1 - sin) to 1e-15
    points = [(float(p[0]), float(p[1])) for p in coords]
    terms = []
    for (lon1, lat1), (lon2, lat2) in zip(points[:-1], points[1:]):
        half = math.radians(lat2 - lat1) / 2.0
        sinc = math.sin(half) / half if half else 1.0
        mid = math.radians(lat1 + lat2) / 2.0
        terms.append(math.radians(lon2 - lon1) * math.sin(mid) * sinc)
    return -(R_KM**2) * math.fsum(terms)


def area_km2(geometry: shapely.Geometry) -> float:
    """Spherical area of the polygon parts of a geometry, holes subtracted."""
    if shapely.get_type_id(geometry) not in (3, 6) or not shapely.is_valid(geometry):
        geometry = _polygonal(geometry)  # valid (multi)polygons have no overlaps
    total = 0.0
    for part in shapely.get_parts(geometry):
        holes = sum(abs(_ring_area(h.coords)) for h in part.interiors)
        total += abs(_ring_area(part.exterior.coords)) - holes
    return total


# ---- closed-set predicates and measures (design.md sections 4.4 and 6.3) -------
Rule = Space | shapely.Geometry | None


def _shape(rule: Space | shapely.Geometry) -> shapely.Geometry:
    """The prepared geometry of a rule shape."""
    if isinstance(rule, Space):
        if rule.kind != "polygon":
            raise TypeError(f"a rule shape is a polygon, not a {rule.kind!r} space")
        rule = rule.geometry
    shapely.prepare(rule)  # preparing a prepared geometry does nothing
    return rule


def points_mask(rule: Rule, lon: Any, lat: Any) -> np.ndarray:
    """Closed-set membership of points in a rule shape, shaped like lon.

    The points inside the shape's bounding box are tested with prepared
    intersects_xy, never contains_xy, so points on an edge are inside; points
    at +-180 also test the other side of the seam. Points with a NaN coordinate
    are inside no rule.
    """
    lon, lat = np.asarray(wrap_lon(lon)), np.asarray(_lat(lat))
    if lon.shape != lat.shape:
        raise ValueError(f"lon has shape {lon.shape} but lat {lat.shape}")
    if rule is None:
        return np.isfinite(lon) & np.isfinite(lat)
    shape = _shape(rule)
    x0, y0, x1, y1 = shape.bounds
    seam = np.abs(lon) == 180.0
    near = (lat >= y0) & (lat <= y1) & ((lon >= x0) & (lon <= x1) | seam)
    mask = np.zeros(lon.shape, dtype=bool)
    mask[near] = shapely.intersects_xy(shape, lon[near], lat[near])
    seam &= near
    mask[seam] |= shapely.intersects_xy(shape, -lon[seam], lat[seam])
    return mask


def meets(rule: Rule, query: Space) -> bool:
    """Whether a query space meets a normalised rule shape, as closed sets.

    rule is a polygon Space or shapely geometry, or None for a global rule. A
    point on an edge meets the shape, and shapes that touch across +-180 meet
    there.
    """
    if rule is None:
        return True
    shape, other = _shape(rule), query.geometry
    if query.kind == "point":
        return bool(points_mask(shape, [other.x], [other.y])[0])
    if shapely.intersects(shape, other):
        return True
    x0, _, x1, _ = other.bounds
    return (x0 == -180.0 and shapely.intersects(shape, _shift(other, 360.0))) or (
        x1 == 180.0 and shapely.intersects(shape, _shift(other, -360.0))
    )


def edge_meets(rule: Space | shapely.Geometry, query: Space) -> bool:
    """Whether the edge of a query polygon (edge()) meets a rule shape, as
    closed sets. A point has no edge, so it meets no rule this way."""
    if query.kind != "polygon":
        return False
    shape, line = _shape(rule), edge(query)
    if line.is_empty:
        return False
    if shapely.intersects(shape, line):
        return True
    x0, _, x1, _ = line.bounds
    return (x0 == -180.0 and shapely.intersects(shape, _shift(line, 360.0))) or (
        x1 == 180.0 and shapely.intersects(shape, _shift(line, -360.0))
    )


def measure(rule: Rule, query: Space) -> tuple[float | None, float | None]:
    """(area_fraction, overlap_km2) of a query space against a rule shape.

    area_fraction is 1.0 or 0.0 for a point, and for a polygon the spherical
    area of the intersection over the query's area. overlap_km2 is None for a
    point. A global rule (None) covers all.
    """
    if query.kind == "point":
        return (1.0 if meets(rule, query) else 0.0), None
    if rule is None:
        return 1.0, query.area_km2
    shape, other = _shape(rule), _shape(query.geometry)
    if shapely.covers(shape, other):
        return 1.0, query.area_km2
    if shapely.covers(other, shape):
        shared = area_km2(shape)
    else:
        shared = area_km2(shapely.intersection(shape, other))
    return min(1.0, shared / query.area_km2), shared
