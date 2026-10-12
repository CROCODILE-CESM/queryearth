"""Space: normalised shapes with straight lon/lat edges, and closed-set measures.

Coordinates are float64 (longitude, latitude) in degrees on WGS84 (CRS84), and
edges are straight lines in longitude-latitude. Every shape is normalised once,
when it is built: longitudes wrapped exactly, rings that go around a pole closed
along it, invalid rings repaired, shapes split at +-180 and rings oriented
(design.md section 6). Areas use a closed form on a sphere of radius R_KM.

Import as ``from queryearth import space as sp``.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

import numpy as np
import shapely

__all__ = [
    "R_KM",
    "Space",
    "area_km2",
    "box",
    "box_arc",
    "cell_mask",
    "cells",
    "comparable",
    "features",
    "from_grid",
    "lat_band",
    "measure",
    "meets",
    "nowhere",
    "point",
    "points_mask",
    "polygon",
    "resolution_of",
    "ring_area_km2",
    "unwrap_ring",
    "weighted_points",
    "wrap_lon",
]

logger = logging.getLogger(__name__)

R_KM = 6371.0088  # mean Earth radius; area fractions do not depend on it
LAT_TOLERANCE = 1e-9  # degrees beyond +-90 that are clamped rather than refused
MODES = ("centre", "overlap", "full")

Kind = Literal["point", "polygon", "points", "features", "empty"]
Pole = Literal["north", "south"]

_POLYGON = 3  # shapely type id
# In lon/lat each pole is a line and the meridians +180 and -180 are one line.
_NORTH = shapely.LineString([(-180.0, 90.0), (180.0, 90.0)])
_SOUTH = shapely.LineString([(-180.0, -90.0), (180.0, -90.0)])


@dataclass(frozen=True, eq=False)
class Space:
    """A normalised space; compares and hashes by identity.

    "point" and "polygon" hold a shapely geometry in [-180, 180] with no part
    crossing +-180; "points" holds read-only (lon, lat, weights) arrays;
    "features" holds (namespace, ids); "empty" is nowhere. area_km2 is the
    spherical area of a polygon, and poles names the pole along which each ring
    that went around one was closed (Q14).
    """

    kind: Kind
    geometry: shapely.Geometry | None = None
    points: tuple[np.ndarray, ...] | None = None
    features: tuple[str, frozenset[str]] | None = None
    area_km2: float | None = None
    poles: tuple[Pole, ...] = ()


# ---- coordinates -----------------------------------------------------------------
def wrap_lon(x: float) -> float:
    """Return x in [-180, 180] with no rounding error; 180 and -180 stay as given."""
    r = math.fmod(x, 360.0)
    if r > 180.0:
        r -= 360.0  # exact: r and 360 are within a factor of two of each other
    elif r < -180.0:
        r += 360.0
    return r


def _wrap(x: Any) -> np.ndarray:
    r = np.fmod(np.asarray(x, dtype=float), 360.0)
    return np.where(r > 180.0, r - 360.0, np.where(r < -180.0, r + 360.0, r))


def _lat(value: float) -> float:
    value = float(value)
    if not math.isfinite(value) or abs(value) > 90.0 + LAT_TOLERANCE:
        raise ValueError(f"latitude {value!r} is outside [-90, 90]")
    return min(90.0, max(-90.0, value))


def _lats(values: Any) -> np.ndarray:
    values = np.asarray(values, dtype=float)
    if np.any(np.abs(values) > 90.0 + LAT_TOLERANCE):
        raise ValueError("a latitude is outside [-90, 90]")
    return np.clip(values, -90.0, 90.0)


def _shift(geometry: shapely.Geometry, dx: float) -> shapely.Geometry:
    return shapely.transform(geometry, lambda c: c + (dx, 0.0))


def _prepare(geometry: shapely.Geometry) -> shapely.Geometry:
    if not shapely.is_prepared(geometry):
        shapely.prepare(geometry)
    return geometry


# ---- ring normalisation (design.md section 6.2) --------------------------------
def unwrap_ring(lon: Sequence[float]) -> tuple[list[float], float, int]:
    """Make a ring (first vertex not repeated) continuous in longitude.

    Returns the unwrapped longitudes, the longitude at which the ring returns to
    its first vertex, and the winding number. Each step is taken the short way,
    except that a step of exactly 180 degrees and a full-turn step of exactly 360
    degrees keep the direction they were written in. Every vertex is its wrapped
    value plus whole turns, so no rounding error builds up along the ring.
    """

    def step(raw: float) -> float:
        return raw if abs(raw) == 360.0 else wrap_lon(raw)

    wrapped = [wrap_lon(x) for x in lon]
    u = [wrapped[0]]
    for i in range(1, len(lon)):
        target = u[-1] + step(lon[i] - lon[i - 1])
        u.append(wrapped[i] + 360.0 * round((target - wrapped[i]) / 360.0))
    closing = u[-1] + step(lon[0] - lon[-1])
    return u, closing, round((closing - u[0]) / 360.0)


def _polygonal(shape: shapely.Geometry) -> shapely.Geometry:
    """The polygon parts of a geometry, merged."""
    # make_valid can nest a MultiPolygon inside a GeometryCollection
    parts = shapely.get_parts(shapely.get_parts(shape))
    return shapely.union_all(parts[shapely.get_type_id(parts) == _POLYGON])


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


def _close(
    u: list[float], closing: float, turns: int, lat: list[float], pole: Pole | None
) -> shapely.Geometry:
    """Steps 3 to 5 for one unwrapped ring: close along a pole, repair, split."""
    ring = list(zip(u, lat))
    if turns:
        # closing - 360 * turns is exact, so both sides of the closure meet after the split
        start = closing - 360.0 * turns
        cap = 90.0 if pole == "north" else -90.0
        ring[0] = (start, lat[0])
        ring += [(closing, lat[0]), (closing, cap), (start, cap)]
    raw = shapely.Polygon(ring)
    if not raw.is_valid:
        logger.debug("repairing a ring: %s", shapely.is_valid_reason(raw))
    shape = _polygonal(shapely.make_valid(raw))
    if shape.is_empty:
        raise ValueError("the ring encloses no area")
    return _split_at_seam(shape)


def _pick_pole(pole: str, lat: Sequence[float]) -> Pole:
    if pole in ("north", "south"):
        return pole
    mean = math.fsum(lat) / len(lat)
    if mean == 0.0:
        raise ValueError(
            "a ring goes around a pole with mean latitude 0; pass pole='north' or pole='south'"
        )
    chosen: Pole = "north" if mean > 0.0 else "south"
    logger.debug(
        "a ring goes around a pole; closed along the %s pole (mean latitude %g)",
        chosen,
        mean,
    )
    return chosen


def _ring(coords: Sequence[Any], pole: str) -> tuple[shapely.Geometry, Pole | None]:
    """Normalise one ring of positions; returns its shape and the pole it closed along."""
    points = [(float(p[0]), float(p[1])) for p in coords]
    if len(points) > 1 and points[0] == points[-1]:
        points.pop()
    if len(points) < 3:
        raise ValueError("a ring needs at least three distinct vertices")
    lon = [p[0] for p in points]
    if not all(math.isfinite(x) for x in lon):
        raise ValueError("a longitude is not finite")
    lat = [_lat(p[1]) for p in points]
    u, closing, turns = unwrap_ring(lon)
    if turns == 0:
        return _close(u, closing, 0, lat, None), None
    if abs(turns) > 1:
        raise ValueError("the ring winds around the globe more than once")
    chosen = _pick_pole(pole, lat)
    return _close(u, closing, turns, lat, chosen), chosen


def _polygon_rings(shape: Any) -> list[list[Any]]:
    """[[exterior, *holes], ...] from shapely, GeoJSON or one ring of positions."""
    if hasattr(shape, "__geo_interface__"):
        shape = shape.__geo_interface__
    if shape is None:
        raise ValueError("no geometry given; a rule without one is global")
    if isinstance(shape, Mapping):
        if shape.get("type") == "Feature":
            return _polygon_rings(shape.get("geometry"))
        kind, coords = shape.get("type"), shape.get("coordinates")
        if kind == "Polygon":
            polygons = [list(coords)]
        elif kind == "MultiPolygon":
            polygons = [list(p) for p in coords]
        else:
            raise ValueError(f"expected a Polygon or MultiPolygon, got {kind!r}")
        if not polygons or not all(polygons):
            raise ValueError("a polygon needs an exterior ring")
        return polygons
    return [[shape]]


def _finish(geometry: shapely.Geometry, poles: tuple[Pole, ...] = ()) -> Space:
    geometry = shapely.orient_polygons(geometry)
    return Space("polygon", geometry=geometry, area_km2=area_km2(geometry), poles=poles)


# ---- space helpers ---------------------------------------------------------------
def point(lon: float, lat: float) -> Space:
    """A point, such as a station or a grid cell centre."""
    lon = float(lon)
    if not math.isfinite(lon):
        raise ValueError(f"longitude {lon!r} is not finite")
    return Space("point", geometry=shapely.Point(wrap_lon(lon), _lat(lat)))


def _arc(west: float, width: float, south: float, north: float) -> shapely.Geometry:
    if width == 360.0:
        return shapely.box(-180.0, south, 180.0, north)
    east = west + width
    if east <= 180.0:
        return shapely.box(west, south, east, north)
    parts = [
        shapely.box(west, south, 180.0, north),
        shapely.box(-180.0, south, east - 360.0, north),
    ]
    return shapely.MultiPolygon(parts)


def box_arc(west: float, width: float, south: float, north: float) -> Space:
    """A longitude arc from west, width degrees east, between two latitudes.

    Only west is wrapped and width is kept, so the arc may cross the
    antimeridian; width 360 is a latitude band.
    """
    west, width = float(west), float(width)
    if not math.isfinite(west) or not 0.0 < width <= 360.0:
        raise ValueError(
            f"need a finite west and 0 < width <= 360, got {west!r}, {width!r}"
        )
    south, north = _lat(south), _lat(north)
    if not south < north:
        raise ValueError(f"need south < north, got {south!r}, {north!r}")
    west = wrap_lon(west)
    if west == 180.0:
        west = -180.0
    return _finish(_arc(west, width, south, north))


def box(west: float, south: float, east: float, north: float) -> Space:
    """A box from west to east; east < west crosses the antimeridian."""
    if east == west:
        raise ValueError(
            "box() with east == west is ambiguous; use lat_band() for a full circle"
        )
    width = east - west if east > west else east - west + 360.0
    return box_arc(west, width, south, north)


def lat_band(south: float, north: float) -> Space:
    """A full circle of latitude, for a domain periodic in longitude."""
    return box_arc(-180.0, 360.0, south, north)


def polygon(shape: Any, pole: Literal["auto", "north", "south"] = "auto") -> Space:
    """A normalised polygon from shapely, GeoJSON or a list of (lon, lat) positions.

    Holes are normalised as separate rings and subtracted, so a hole may itself
    go around a pole. A ring that goes around a pole is closed along the pole
    given, or with pole="auto" along the one on the side of its mean latitude.
    """
    if pole not in ("auto", "north", "south"):
        raise ValueError(f"pole must be 'auto', 'north' or 'south', not {pole!r}")
    parts, poles = [], []
    for rings in _polygon_rings(shape):
        shapes = []
        for coords in rings:
            ring_shape, chosen = _ring(coords, pole)
            shapes.append(ring_shape)
            if chosen is not None:
                poles.append(chosen)
        part = shapes[0]
        if len(shapes) > 1:
            part = shapely.difference(part, shapely.union_all(shapes[1:]))
        parts.append(part)
    geometry = _polygonal(shapely.union_all(parts))
    if geometry.is_empty:
        raise ValueError("the shape encloses no area")
    return _finish(geometry, tuple(poles))


def _winds(row: Sequence[float]) -> bool:
    """Whether a row of nodes, closed on itself, goes once around the globe."""
    steps = [wrap_lon(b - a) for a, b in zip(row[:-1], row[1:])]
    steps.append(wrap_lon(row[0] - row[-1]))
    return round(math.fsum(steps) / 360.0) != 0


def _corners(lon2d: Any, lat2d: Any) -> tuple[np.ndarray, np.ndarray]:
    lon, lat = np.asarray(lon2d, dtype=float), np.asarray(lat2d, dtype=float)
    if lon.shape != lat.shape or lon.ndim != 2 or min(lon.shape) < 2:
        raise ValueError(
            "expected two 2D arrays of cell corners of one shape, at least 2 x 2"
        )
    if not (np.all(np.isfinite(lon)) and np.all(np.isfinite(lat))):
        raise ValueError("grid corners must be finite")
    return lon, lat


def _outline(a: np.ndarray) -> np.ndarray:
    """Boundary nodes of a 2D grid, once each: bottom, right, top, left."""
    return np.concatenate([a[0, :], a[1:, -1], a[-1, -2::-1], a[-2:0:-1, 0]])


def from_grid(lon2d: Any, lat2d: Any) -> Space:
    """The outline of a 2D grid of cell corners, closed along a pole it goes around.

    A grid that goes around a pole keeps the pole whose cap covers its middle
    node. A grid periodic in longitude has no closed outline and is refused with
    a pointer to lat_band() (Q15).
    """
    lon, lat = _corners(lon2d, lat2d)
    ring_lon = _outline(lon).tolist()
    ring_lat = _lats(_outline(lat)).tolist()
    u, closing, turns = unwrap_ring(ring_lon)
    if turns == 0:
        if _winds(lon[0].tolist()) and _winds(lon[-1].tolist()):
            raise ValueError(
                "the grid is periodic in longitude, so it has no closed outline; "
                "describe it with lat_band(south, north)"
            )
        return _finish(_close(u, closing, 0, ring_lat, None))
    if abs(turns) > 1:
        raise ValueError("the grid outline winds around the globe more than once")
    ny, nx = lon.shape
    middle = _point_set(wrap_lon(lon[ny // 2, nx // 2]), _lat(lat[ny // 2, nx // 2]))
    shape = _close(u, closing, turns, ring_lat, "north")
    chosen: Pole = "north"
    if not shapely.intersects(shape, middle):
        shape, chosen = _close(u, closing, turns, ring_lat, "south"), "south"
    logger.debug("a grid outline goes around a pole; closed along the %s pole", chosen)
    return _finish(shape, (chosen,))


def weighted_points(lon: Any, lat: Any, weights: Any = None) -> Space:
    """Points with weights, such as model cell centres with cell areas.

    Equal weights if none are given; zero weights leave points out of the
    fraction, so zero on land makes an ocean-only fraction.
    """
    lon = np.asarray(lon, dtype=float).ravel()
    lat = np.asarray(lat, dtype=float).ravel()
    if lon.shape != lat.shape:
        raise ValueError(f"{lon.size} longitudes but {lat.size} latitudes")
    if weights is None:
        w = np.ones_like(lon)
    else:
        w = np.array(weights, dtype=float).ravel()
    if w.shape != lon.shape:
        raise ValueError(f"{w.size} weights for {lon.size} points")
    if not np.all(np.isfinite(w)) or np.any(w < 0.0):
        raise ValueError("weights must be finite and non-negative")
    if not w.sum() > 0.0:
        raise ValueError("the weights sum to zero")
    arrays = (_wrap(lon), _lats(lat), w)
    for array in arrays:
        array.flags.writeable = False
    return Space("points", points=arrays)


def features(ids: Iterable[str | int], namespace: str) -> Space:
    """A set of object ids in a namespace, such as National Water Model lake ids."""
    if not isinstance(namespace, str) or not namespace:
        raise ValueError("a feature namespace is a non-empty string")
    if isinstance(ids, (str, int)):
        ids = (ids,)
    return Space("features", features=(namespace, frozenset(str(i) for i in ids)))


def nowhere() -> Space:
    """The empty space, for a callable coverage that does not serve a query."""
    return Space("empty", geometry=shapely.Polygon(), area_km2=0.0)


# ---- product cells (design.md section 8.2) --------------------------------------
@dataclass(frozen=True)
class _Grid:
    """A rectilinear grid's cells: lon cells by wrapped edges, lat cells by limits."""

    west: np.ndarray  # in [-180, 180)
    east: np.ndarray  # in (-180, 180]; east <= west for a cell across +-180
    width: np.ndarray
    south: np.ndarray
    north: np.ndarray


def _grid(grid: tuple[Any, Any]) -> _Grid:
    if len(grid) != 2:
        raise ValueError("a grid is (lon_edges, lat_edges)")
    lon, lat = np.asarray(grid[0], dtype=float), np.asarray(grid[1], dtype=float)
    if lon.ndim != 1 or lat.ndim != 1 or lon.size < 2 or lat.size < 2:
        raise ValueError("grid edges are two 1D arrays of at least two values")
    if not (np.all(np.isfinite(lon)) and np.all(np.isfinite(lat))):
        raise ValueError("grid edges must be finite")
    width = np.diff(lon)
    if np.any(width <= 0.0) or lon[-1] - lon[0] > 360.0:
        raise ValueError("longitude edges must increase and span at most 360 degrees")
    step = np.diff(lat)
    if not (np.all(step > 0.0) or np.all(step < 0.0)):
        raise ValueError("latitude edges must be strictly monotonic")
    lat = _lats(lat)
    edges = _wrap(lon)  # exact, so neighbouring cells share each edge bit for bit
    west, east = edges[:-1].copy(), edges[1:].copy()
    west[west == 180.0] = -180.0
    east[east == -180.0] = 180.0
    south, north = np.minimum(lat[:-1], lat[1:]), np.maximum(lat[:-1], lat[1:])
    return _Grid(west, east, width, south, north)


def _boxes(west, east, whole, south, north) -> np.ndarray:
    """Boxes from west to east, split at +-180 when east <= west."""
    cross = (east <= west) & ~whole
    x0 = np.where(whole, -180.0, west)
    x1 = np.where(whole | cross, 180.0, east)
    shapes = shapely.box(x0, south, x1, north)
    if cross.any():
        rest = shapely.box(-180.0, south[cross], east[cross], north[cross])
        shapes[cross] = shapely.union(shapes[cross], rest)
    return shapes


def _cell_shapes(g: _Grid, jj: np.ndarray, ii: np.ndarray) -> np.ndarray:
    """One (multi)polygon per cell (jj[k], ii[k])."""
    whole = g.width[ii] >= 360.0
    return _boxes(g.west[ii], g.east[ii], whole, g.south[jj], g.north[jj])


def _union_cells(g: _Grid, mask: np.ndarray) -> shapely.Geometry:
    """The union of the selected cells, built from runs along each row."""
    whole = g.width >= 360.0
    single = (g.east <= g.west) | whole  # cells that cross +-180 stay on their own
    chained = (g.east[:-1] == g.west[1:]) & ~single[:-1] & ~single[1:]
    joined = mask[:, :-1] & mask[:, 1:] & chained
    first, last = mask.copy(), mask.copy()
    first[:, 1:] &= ~joined
    last[:, :-1] &= ~joined
    jj, i0 = np.nonzero(first)
    _, i1 = np.nonzero(last)  # row-major, so the k-th last closes the k-th first
    runs = _boxes(g.west[i0], g.east[i1], whole[i0], g.south[jj], g.north[jj])
    return _polygonal(shapely.union_all(runs))


def _target(region: Space) -> shapely.Geometry | None:
    """The closed set a region stands for, or None if it is empty."""
    if region.kind == "features":
        raise TypeError("object ids select no cells; pass a geometry")
    if region.kind == "empty":
        return None
    if region.kind == "polygon":
        return region.geometry
    if region.kind == "point":
        return _point_set(region.geometry.x, region.geometry.y)
    lon, lat, _ = region.points
    ok = np.isfinite(lon) & np.isfinite(lat)
    lon, lat = lon[ok], lat[ok]
    if lon.size == 0:
        return None
    seam = np.abs(lon) == 180.0
    parts = [shapely.multipoints(np.column_stack([lon, lat]))]
    if seam.any():
        parts.append(shapely.multipoints(np.column_stack([-lon[seam], lat[seam]])))
    parts += [
        edge for edge, at in ((_NORTH, 90.0), (_SOUTH, -90.0)) if np.any(lat == at)
    ]
    return shapely.GeometryCollection(parts)


def _candidates(g: _Grid, target: shapely.Geometry) -> tuple[np.ndarray, np.ndarray]:
    """(lat, lon) indices of the cells that meet the bounds of a target part."""
    eps = 1e-9  # inclusive slack; the exact test follows
    found = np.zeros((g.south.size, g.west.size), dtype=bool)
    for part in shapely.get_parts(target):
        x0, y0, x1, y1 = part.bounds
        lat_ok = (g.south <= y1 + eps) & (g.north >= y0 - eps)
        on_arc = np.mod(x0 - g.west + eps, 360.0) <= g.width + 2.0 * eps
        starts_inside = np.mod(g.west - x0 + eps, 360.0) <= (x1 - x0) + 2.0 * eps
        found |= lat_ok[:, None] & (on_arc | starts_inside)[None, :]
    return np.nonzero(found)


def _select(
    grid: tuple[Any, Any], region: Space, mode: str
) -> tuple[np.ndarray, _Grid]:
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}, not {mode!r}")
    g = _grid(grid)
    mask = np.zeros((g.south.size, g.west.size), dtype=bool)
    target = _target(region)
    if target is None:
        return mask, g
    jj, ii = _candidates(g, target)
    if mode == "centre":
        centre_lon = g.west[ii] + g.width[ii] / 2.0
        hit = points_mask(target, centre_lon, (g.south[jj] + g.north[jj]) / 2.0)
    else:
        shapes = _cell_shapes(g, jj, ii)
        covered = shapely.covers(_prepare(target), shapes)
        if mode == "full":
            hit = covered
        else:
            hit = shapely.intersects(target, shapes)
            if region.kind == "polygon":
                edge = hit & ~covered
                inner = shapely.intersection(shapes[edge], target)
                hit[edge] = shapely.area(inner) > 0.0
    mask[jj[hit], ii[hit]] = True
    return mask, g


def cells(grid: tuple[Any, Any], region: Space, mode: str = "overlap") -> Space:
    """The union of the cells of grid = (lon_edges, lat_edges) that region uses.

    "centre": cells whose centre the region covers; "overlap" (default): cells
    whose intersection with the region has positive area, or for a region
    without area every cell that covers it; "full": cells the region covers.
    Longitude edges may use any convention.
    """
    mask, g = _select(grid, region, mode)
    if not mask.any():
        return nowhere()
    return _finish(_union_cells(g, mask))


def cell_mask(
    grid: tuple[Any, Any], region: Space, mode: str = "overlap"
) -> np.ndarray:
    """The cells() selection as a boolean (lat, lon) array in the grid's own order."""
    return _select(grid, region, mode)[0]


def resolution_of(lon2d: Any, lat2d: Any, unit: str = "km") -> tuple[float, float]:
    """(finest, coarsest) great-circle cell edge of a grid of cell corners.

    Lengths are on a sphere of radius R_KM, or central angles with unit="deg".
    Pass cell corners, not a MOM6 supergrid (use x[::2, ::2] and y[::2, ::2]).
    """
    if unit not in ("km", "deg"):
        raise ValueError(f"unit must be 'km' or 'deg', not {unit!r}")
    lon, lat = (np.radians(a) for a in _corners(lon2d, lat2d))

    def central_angle(x1, y1, x2, y2):
        h = (
            np.sin((y2 - y1) / 2.0) ** 2
            + np.cos(y1) * np.cos(y2) * np.sin((x2 - x1) / 2.0) ** 2
        )
        return 2.0 * np.arcsin(np.sqrt(np.clip(h, 0.0, 1.0)))

    along = central_angle(lon[:, :-1], lat[:, :-1], lon[:, 1:], lat[:, 1:])
    across = central_angle(lon[:-1], lat[:-1], lon[1:], lat[1:])
    edges = np.concatenate([along.ravel(), across.ravel()])
    edges = edges * R_KM if unit == "km" else np.degrees(edges)
    return float(edges.min()), float(edges.max())


# ---- areas (design.md section 6.3) ---------------------------------------------
def ring_area_km2(coords: Any) -> float:
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
    total = 0.0
    for part in shapely.get_parts(_polygonal(geometry)):
        holes = sum(abs(ring_area_km2(h.coords)) for h in part.interiors)
        total += abs(ring_area_km2(part.exterior.coords)) - holes
    return total


# ---- closed-set predicates and measures (design.md sections 4.4 and 6.3) -------
Rule = Space | shapely.Geometry | None


def _point_set(lon: float, lat: float) -> shapely.Geometry:
    """The closed set a point stands for: a pole is a line, +-180 one meridian."""
    if lat == 90.0:
        return _NORTH
    if lat == -90.0:
        return _SOUTH
    if abs(lon) == 180.0:
        return shapely.MultiPoint([(180.0, lat), (-180.0, lat)])
    return shapely.Point(lon, lat)


def _is_ids(rule: Rule) -> bool:
    return isinstance(rule, Space) and rule.kind == "features"


def _shape(rule: Space | shapely.Geometry) -> shapely.Geometry:
    if isinstance(rule, Space):
        if rule.kind not in ("polygon", "empty"):
            raise TypeError(f"a rule shape is a polygon, not a {rule.kind!r} space")
        return rule.geometry
    return rule


def comparable(rule: Rule, query: Space) -> bool:
    """False when ids meet a geometry or ids of another namespace (conditional)."""
    if rule is None or not (_is_ids(rule) or query.kind == "features"):
        return True
    return (
        _is_ids(rule)
        and query.kind == "features"
        and rule.features[0] == query.features[0]
    )


def _shared(rule: Rule, query: Space) -> tuple[int, int]:
    if rule is None or not comparable(rule, query):
        raise TypeError("object ids compare only with ids of the same namespace")
    return len(rule.features[1] & query.features[1]), len(query.features[1])


def _areas_meet(shape: shapely.Geometry, other: shapely.Geometry) -> bool:
    if shapely.intersects(_prepare(shape), other):
        return True
    rx0, ry0, rx1, ry1 = shape.bounds
    qx0, qy0, qx1, qy1 = other.bounds
    if (ry1 == 90.0 and qy1 == 90.0) or (ry0 == -90.0 and qy0 == -90.0):
        return True
    if (
        qx0 == -180.0
        and rx1 == 180.0
        and shapely.intersects(shape, _shift(other, 360.0))
    ):
        return True
    return (
        qx1 == 180.0
        and rx0 == -180.0
        and shapely.intersects(shape, _shift(other, -360.0))
    )


def points_mask(rule: Rule, lon: Any, lat: Any) -> np.ndarray:
    """Closed-set membership of points in a rule shape, shaped like lon.

    Uses intersects_xy, never contains_xy, so points on an edge are inside;
    points at +-180 also test the other side of the seam, and points at
    latitude +-90 test the whole pole edge. Points with a NaN coordinate are
    inside no rule.
    """
    lon, lat = _wrap(lon), _lats(lat)
    if lon.shape != lat.shape:
        raise ValueError(f"lon has shape {lon.shape} but lat {lat.shape}")
    if rule is None:
        return np.isfinite(lon) & np.isfinite(lat)
    shape = _prepare(_shape(rule))
    mask = shapely.intersects_xy(shape, lon, lat)
    seam = np.abs(lon) == 180.0
    if seam.any():
        mask[seam] |= shapely.intersects_xy(shape, -lon[seam], lat[seam])
    for edge, at in ((_NORTH, 90.0), (_SOUTH, -90.0)):
        pole = lat == at
        if pole.any():
            mask[pole] = shapely.intersects(shape, edge)
    return mask


def meets(rule: Rule, query: Space) -> bool:
    """Whether a query space meets a normalised rule shape, as closed sets.

    rule is a polygon Space or shapely geometry, a features Space, or None for
    a global rule. A point uses prepared covers (a point at a pole meets every
    shape that reaches that pole), and an area uses prepared intersects, where
    shapes that both reach a pole, or touch across +-180, meet there. Raises
    TypeError when the two are not comparable (see comparable()).
    """
    if rule is None:
        return query.kind != "empty"
    if _is_ids(rule) or query.kind == "features":
        return _shared(rule, query)[0] > 0
    shape = _shape(rule)
    if query.kind == "empty" or shape.is_empty:
        return False
    if query.kind == "points":
        return bool(points_mask(shape, query.points[0], query.points[1]).any())
    if query.kind == "point":
        target = _point_set(query.geometry.x, query.geometry.y)
        if isinstance(target, shapely.Point):
            return bool(shapely.covers(_prepare(shape), target))
        return bool(shapely.intersects(_prepare(shape), target))
    return _areas_meet(shape, query.geometry)


def measure(rule: Rule, query: Space) -> tuple[float | None, float | None]:
    """(area_fraction, overlap_km2) of a query space against a rule shape.

    area_fraction is 1.0 or 0.0 for a point; the covered share of the weights
    for weighted points; shared ids over query ids for object ids; and for an
    area, the spherical area of the intersection over the query's area.
    overlap_km2 is None for spaces without area. A global rule (None) covers all.
    """
    kind = query.kind
    if kind == "empty":
        return None, None
    if rule is None:
        return 1.0, query.area_km2
    if _is_ids(rule) or kind == "features":
        shared, total = _shared(rule, query)
        return (shared / total if total else None), None
    if kind == "point":
        return (1.0 if meets(rule, query) else 0.0), None
    shape = _shape(rule)
    if kind == "points":
        lon, lat, weights = query.points
        inside = points_mask(shape, lon, lat)
        return float(weights[inside].sum() / weights.sum()), None
    other = _prepare(query.geometry)
    if shapely.covers(_prepare(shape), other):
        return 1.0, query.area_km2
    if shapely.covers(other, shape):
        shared = area_km2(shape)
    else:
        shared = area_km2(shapely.intersection(shape, other))
    return min(1.0, shared / query.area_km2), shared
