"""Play with queryearth on a made-up rule file.

Run it cell by cell in VS Code (each "# %%" line starts a cell), or as a script
from the repository root:

    pip install -e .
    python examples/toy/play.py

Everything in rules.geojson is invented: the products the rules name (toy_ocean,
toy_atmos, toy_coastal), the rules (TOY...) and the parameter names; nothing
there describes real data or real model guidance. Edit rules.geojson or this
file and rerun to see what changes.
"""

# %% Set up: a Registry that declares the dimensions the rules use, a resolution
# axis and the labels product, variable and model, then load the rules.
import logging
from pathlib import Path

import numpy as np

import queryearth as qe
from queryearth import space as sp

HERE = Path(globals().get("__file__", "play.py")).resolve().parent

registry = qe.Registry(
    "toy",
    dimensions=[
        qe.Axis("resolution", "km", "horizontal grid spacing"),
        qe.Labels("product"),
        qe.Labels("variable"),
        qe.Labels("model"),
    ],
)
print("loaded:", registry.load(HERE / "rules.geojson"))


def show(findings):
    """Each finding's level, code and title, then its message and changes."""
    print(qe.report(findings) or "(no findings)", end="\n\n")


# %% 1. A Bering Sea domain that crosses the antimeridian, winter 2000-01, 8 km.
# TOY002 covers only December to March, so it reports just those months.
# TOY101 needs the Arctic, and only the top of this domain is north of 66.5N.
bering = sp.box(165, 52, -160, 70)  # west, south, east, north
winter = qe.interval("2000-11-01", "2001-03-31")
ocean = {
    "resolution": (8, 8),
    "model": ["mom6"],
    "product": ["toy_ocean"],
    "variable": ["thetao", "so"],
}
show(registry.query(space=bering, time=winter, dimensions=ocean))

# %% 2. Resolution only. TOY102 applies outright; with include_conditional=True
# the other rules come back too, each naming what the query left out.
show(registry.query(dimensions={"resolution": (3, 3)}, include_conditional=True))

# %% 3. Coverage limits are ordinary rules. toy_coastal covers one box from 2010
# to 2023 only, so asking for it in the Bering Sea gives TOY006 (outside its box)
# and in the Gulf in 2005 gives TOY004 (before 2010).
coastal = {"product": ["toy_coastal"]}
show(registry.query(space=bering, time=winter, dimensions=coastal))
gulf = sp.box(-95, 22, -85, 29)
year_2005 = qe.interval("2005-01-01", "2005-12-31")
show(registry.query(space=gulf, time=year_2005, dimensions=coastal))

# %% 4. Rules written in Python. A static rule, and a computed rule whose
# change depends on the query (a made-up time step from the finest cells).
registry.add(
    qe.Rule(
        code="TOY201",
        title="toy_atmos 2 m temperature is too cold over sea ice",
        message="Over sea ice, toy_atmos t2m runs a few kelvin too cold.",
        scope=qe.Scope(
            space=sp.box(-180, 60, 180, 90), dimensions={"product": ["toy_atmos"]}
        ),
    )
)


@registry.rule(
    "TOY202",
    dimensions={"resolution": {"gt": 0}},  # conditional without a resolution
)
def time_step(query, match):
    """Set the toy time step from the finest cells"""
    finest_km = match.dimensions["resolution"].overlap[0].lo
    seconds = 30.0 * finest_km  # made up: 30 s per km
    return {"changes": [qe.Change("MOM_input", "TOY_DT", seconds, "made up")]}


atmos = {"resolution": (4, 12), "product": ["toy_atmos"]}
show(registry.query(space=bering, time=winter, dimensions=atmos))

# %% 5. Findings are data. Log each at its own level, and raise for anything at
# ERROR or above (nothing here; try the product toy_coastal).
findings = registry.query(space=bering, time=winter, dimensions=ocean)
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s", force=True)
for f in findings:
    logging.getLogger("toy").log(f.level, f)  # str(f) is "[CODE] title (...)"

errors = [f for f in findings if f.level >= logging.ERROR]
if errors:
    raise RuntimeError("\n".join(map(str, errors)))

# %% 6. Which product suits salinity in the Gulf in 2000? Ask once per product.
# toy_coastal starts in 2010, so TOY004 says not to use it; toy_ocean has TOY001
# against it. No findings means only that no rule matched, not good data.
year_2000 = qe.interval("2000-01-01", "2000-12-31")
for product in ["toy_ocean", "toy_coastal"]:
    salinity = {"product": [product], "variable": ["so"]}
    found = registry.query(space=gulf, time=year_2000, dimensions=salinity)
    print(f"  {product:11} {[f.code for f in found]}")

# %% 7. Many points at once: every 1-degree cell centre, January 2001, toy_ocean.
lon, lat = np.meshgrid(np.arange(-179.5, 180, 1.0), np.arange(-89.5, 90, 1.0))
result = registry.query_points(
    lon,
    lat,
    time=qe.interval("2001-01-01", "2001-01-31"),
    dimensions={"product": ["toy_ocean"], "variable": ["thetao"]},
)
for code, mask in result.masks.items():
    print(f"  {code}: {mask.sum()} of {mask.size} points")

try:
    import matplotlib.pyplot as plt

    plt.pcolormesh(lon, lat, result.any(min_level="info"), shading="nearest")
    plt.title("points with a finding")
    plt.show()
except ImportError:
    pass
