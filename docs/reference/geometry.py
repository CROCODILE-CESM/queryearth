"""Reference code for ring normalisation and spherical area.

wrap_lon, unwrap_ring, polygonal, split_at_seam and ring_to_shape implement
steps 1 to 6 of the normalisation in design.md section 6.2 (wrap, unwrap and
count turns, close pole rings, repair, split, orient); ring_area_km2 is the
closed-form spherical area of design.md section 6.3. A polygon's area is its
exterior's minus its holes'; a multipolygon's is the sum over its parts. This
code, run as written, reproduces fixtures 1 to 3, 7 and 22 of fixtures.md.
"""

import math

import shapely
from shapely.geometry import Polygon, box


def wrap_lon(x: float) -> float:
    """Return x in [-180, 180] with no rounding error; 180 and -180 stay as given."""
    r = math.fmod(x, 360.0)  # exact
    if r > 180.0:
        r -= 360.0  # exact: r and 360 are within a factor of two of each other
    elif r < -180.0:
        r += 360.0
    return r


def unwrap_ring(lon: list[float]) -> tuple[list[float], float, int]:
    """Make a ring (first vertex not repeated) continuous in longitude.

    Returns the unwrapped longitudes, the longitude at which the ring returns to
    its first vertex, and the winding number. Each step is taken the short way; a
    step of exactly 180 degrees keeps its written direction, and a full-turn step
    of exactly 360 degrees is kept as written. Every vertex is its wrapped value
    plus whole turns, so no rounding error builds up along the ring.
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


def polygonal(shape: shapely.Geometry) -> shapely.Geometry:
    """Keep the polygon parts of a geometry, merged."""
    # make_valid can nest a MultiPolygon inside a GeometryCollection
    parts = shapely.get_parts(shapely.get_parts(shape))
    return shapely.union_all(parts[shapely.get_type_id(parts) == 3])


def split_at_seam(shape: shapely.Geometry) -> shapely.Geometry:
    """Cut an unwrapped shape into 360 degree strips and move each into [-180, 180]."""
    west, _, east, _ = shape.bounds
    pieces = []
    first, last = math.floor((west + 180) / 360), math.ceil((east - 180) / 360)
    for k in range(first, last + 1):
        strip = box(360.0 * k - 180.0, -90.0, 360.0 * k + 180.0, 90.0)
        piece = shapely.intersection(shape, strip)
        if not piece.is_empty:
            pieces.append(shapely.transform(piece, lambda c: c - (360.0 * k, 0.0)))
    return shapely.orient_polygons(polygonal(shapely.union_all(pieces)))


def ring_to_shape(lon: list[float], lat: list[float], pole: str) -> shapely.Geometry:
    """Steps 1 to 6 for one ring; pole is "north" or "south", chosen by the caller."""
    u, closing, turns = unwrap_ring(lon)
    ring = list(zip(u, lat))
    if abs(turns) == 1:  # once around a pole: close the ring along it
        cap = 90.0 if pole == "north" else -90.0
        ring += [(closing, lat[0]), (closing, cap), (u[0], cap)]
    elif turns != 0:
        raise ValueError("the ring winds around the globe more than once")
    shape = polygonal(shapely.make_valid(Polygon(ring)))
    if shape.is_empty:
        raise ValueError("the ring encloses no area")
    return split_at_seam(shape)


R_KM = 6371.0088  # mean Earth radius; area fractions do not depend on it


def ring_area_km2(coords: list[tuple[float, float]]) -> float:
    """Signed area of a closed ring with straight lon/lat edges; CCW is positive."""
    total = 0.0
    for (lon1, lat1), (lon2, lat2) in zip(coords[:-1], coords[1:]):
        half = math.radians(lat2 - lat1) / 2.0
        sinc = math.sin(half) / half if half else 1.0
        mid = math.radians(lat1 + lat2) / 2.0
        total += math.radians(lon2 - lon1) * math.sin(mid) * sinc
    return -(R_KM**2) * total
