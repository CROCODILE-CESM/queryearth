"""Converters: turn other descriptions of a place into queryearth spaces.

Each converter returns an ordinary Space (a point or a polygon), so nothing else
in queryearth needs to know where it came from.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from queryearth import space as sp
from queryearth.space import Space

__all__ = ["grid_outline"]


def grid_outline(lon: Any, lat: Any) -> Space:
    """The outline of a curvilinear grid, from the corners of its cells.

    lon and lat are 2-D arrays of cell corners in degrees, shaped (ny + 1, nx + 1),
    such as a MOM6 supergrid's corners or mom6_forge's ``grid.qlon`` and
    ``grid.qlat``. The outline is the ring of the outer corners, so its edges
    follow the grid's, and a grid across the antimeridian is split there.

    queryearth does not take a ring around a pole, so a grid that contains a pole
    becomes the whole polar cap beyond its outline's farthest latitude. The cap
    is larger than the grid: no rule that touches the grid is missed, but area
    fractions are measured against the cap.
    """
    lon, lat = np.asarray(lon, dtype=float), np.asarray(lat, dtype=float)
    if lon.ndim != 2 or lon.shape != lat.shape or min(lon.shape) < 2:
        raise ValueError(
            "lon and lat are 2-D arrays of cell corners of the same shape, "
            f"at least 2 by 2, not {lon.shape} and {lat.shape}"
        )
    if not (np.isfinite(lon).all() and np.isfinite(lat).all()):
        raise ValueError("the cell corners must all be finite")
    edges = (np.s_[0, :], np.s_[1:, -1], np.s_[-1, -2::-1], np.s_[-2::-1, 0])
    ring_lon = np.concatenate([lon[e] for e in edges])
    ring_lat = np.concatenate([lat[e] for e in edges])
    turn = np.sum((np.diff(ring_lon) + 180.0) % 360.0 - 180.0)  # ±360 round a pole
    if abs(turn) > 180.0:
        if ring_lat.mean() > 0.0:
            return sp.box(-180.0, float(ring_lat.min()), 180.0, 90.0)
        return sp.box(-180.0, -90.0, 180.0, float(ring_lat.max()))
    ring = np.column_stack([ring_lon, ring_lat]).tolist()
    return sp.polygon({"type": "Polygon", "coordinates": [ring]})
