"""Play with queryearth on a made-up pack.

Run it cell by cell in VS Code (each "# %%" line starts a cell), or as a script
from the repository root:

    pip install -e .
    python examples/toy/play.py

Everything in the toy pack is invented: the products (toy_ocean, toy_atmos,
toy_coastal), the rules (TOY...) and the parameter names. Edit pack.toml,
rules.geojson or this file and rerun to see what changes.
"""

# %% Set up: an Index with a resolution axis, then load the toy pack.
import logging
from pathlib import Path

import numpy as np

import queryearth as qe
from queryearth import space as sp

HERE = Path(globals().get("__file__", "play.py")).resolve().parent

index = qe.Index("toy", axes=[qe.Axis("resolution", "km")])
print("loaded:", index.load_pack(HERE))
print("products:", list(index.products))


def show(findings):
    """One line per finding, then any suggestions under it."""
    if not findings:
        print("  (no findings)")
    for f in findings:
        area, time = (
            "-" if x is None else f"{x:.0%}" for x in (f.area_fraction, f.time_fraction)
        )
        print(f"  {f.code:7} {f.kind:14} {f.severity.name:8} {f.product or '-':11}")
        print(f"          {f.title}")
        print(f"          area {area}, time {time}, periods {f.time_overlap}")
        if f.conditional_on:
            print(f"          conditional on {f.conditional_on}")
        if f.assumed:
            print(f"          filled from the product: {f.assumed}")
        for s in f.suggestions:
            print(f"          -> set {s.target}:{s.key} = {s.value!r}")


# %% 1. A Bering Sea domain that crosses the antimeridian, winter 2000-01, 8 km.
# TOY002 covers only December to March, so its time fraction is below 1.
# TOY101 needs the Arctic, and only the top of this domain is north of 66.5N.
bering = sp.box(165, 52, -160, 70)  # west, south, east, north
winter = qe.interval("2000-11-01", "2001-03-31")
show(
    index.query(
        space=bering,
        time=winter,
        axes={"resolution": (8, 8)},
        facets={"model": ["mom6"]},
        requests=[qe.Request("toy_ocean", variables=("thetao", "so"))],
    )
)

# %% 2. The same domain with no time: each product's coverage is used instead,
# and the findings say so in "filled from the product".
show(
    index.query(
        space=bering,
        axes={"resolution": (8, 8)},
        requests=[qe.Request("toy_ocean", variables="so")],
    )
)

# %% 3. Resolution only. TOY102 applies outright; with include_conditional=True
# the other rules come back too, each naming what the query left out.
show(index.query(axes={"resolution": (3, 3)}, include_conditional=True))

# %% 4. Coverage gaps. toy_coastal covers one box from 2010 to 2023 only, so
# asking for it in the Bering Sea gives QE001 (space) and in 2005 QE002 (time).
show(index.query(space=bering, time=winter, requests=["toy_coastal"]))
gulf = sp.box(-95, 22, -85, 29)
show(
    index.query(
        space=gulf,
        time=qe.interval("2005-01-01", "2005-12-31"),
        requests=["toy_coastal"],
    )
)

# %% 5. Rules written in Python. A static rule, and a computed rule whose
# suggestion depends on the query (a made-up time step from the finest cells).
index.add(
    qe.Rule(
        code="TOY201",
        kind="caveat",
        title="toy_atmos 2 m temperature is too cold over sea ice",
        message="Over sea ice, toy_atmos t2m runs a few kelvin too cold.",
        severity=qe.Severity.WARNING,
        scope=qe.Scope(
            space=sp.box(-180, 60, 180, 90), facets={"product": ["toy_atmos"]}
        ),
    )
)


@index.rule(
    "TOY202",
    kind="recommendation",
    axes={"resolution": {"gt": 0}},  # needs a resolution, so conditional without one
)
def time_step(query, match):
    """Set the toy time step from the finest cells"""
    finest_km = match.axes["resolution"].lo
    seconds = 30.0 * finest_km  # made up: 30 s per km
    return {"suggestions": [qe.Suggestion("MOM_input", "TOY_DT", seconds, "made up")]}


show(
    index.query(
        space=bering,
        time=winter,
        axes={"resolution": (4, 12)},
        requests=["toy_atmos"],
    )
)

# %% 6. Findings are data; emit() reports them. Try each mode.
findings = index.query(
    space=bering,
    time=winter,
    axes={"resolution": (8, 8)},
    facets={"model": ["mom6"]},
    requests=[qe.Request("toy_ocean", variables=("thetao", "so"))],
)

qe.emit(findings)  # default: Python warnings for caveats, log lines for advice

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s", force=True)
qe.emit(findings, mode="log")

collected = []
qe.emit(findings, mode=lambda finding, text: collected.append(text))  # a sink
print("sink got:", collected)

try:
    qe.emit(findings, mode="raise")
except qe.AdvisoryError as err:
    print("raised for:", [f.code for f in err.findings])

with qe.policy(mode="log", ignore={"TOY002"}, show_recommendations=False):
    qe.emit(findings)  # only TOY001 is left

# %% 7. Which product suits salinity in the Gulf in 2000? toy_coastal starts in
# 2010 so it drops out; toy_ocean stays, with TOY001 against it. A low score
# means fewer known concerns, not better data.
for s in index.suitable(
    qe.Query(space=gulf, time=qe.interval("2000-01-01", "2000-12-31")),
    "so",
    include_dropped=True,
):
    print(f"  {s.product.name:11} score {s.score}  {[f.code for f in s.findings]}")

# %% 8. Many points at once: every 1-degree cell centre, January 2001, toy_ocean.
lon, lat = np.meshgrid(np.arange(-179.5, 180, 1.0), np.arange(-89.5, 90, 1.0))
result = index.query_points(
    lon,
    lat,
    time=qe.interval("2001-01-01", "2001-01-31"),
    requests=[qe.Request("toy_ocean", variables="thetao")],
)
for key, mask in result.masks.items():
    print(f"  {key}: {mask.sum()} of {mask.size} points")

try:
    import matplotlib.pyplot as plt

    plt.pcolormesh(lon, lat, result.any(min_severity="info"), shading="nearest")
    plt.title("points with a finding")
    plt.show()
except ImportError:
    pass
