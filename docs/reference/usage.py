"""Usage of the queryearth API (illustrative; examples/toy/play.py runs end to end).

lake_geojson, outline and stn stand for the caller's own data: a lake polygon, an
Arctic domain's outer cell corners closed along 90N, and station counts. The
demo pack declares cru_ts (alias CRUTS) and era5_land. CRU002 here is the simple
form; design.md section 12.4 describes the graded one, whose code is in
examples/README.md.
"""

import logging

import numpy as np

import queryearth as qe
from queryearth import space as sp

registry = qe.Registry(
    "demo", axes=[qe.Axis("resolution", "km", "horizontal grid spacing")]
)
registry.load_pack("packs/demo")  # products cru_ts and era5_land, CRU001, CROC101
cru, mom6 = {"product": "cru_ts", "variable": "pre"}, {"model": "mom6"}
y1991_2020 = qe.interval("1991-01-01", "2020-12-31")

croc102 = qe.Rule(  # a record built in Python; the MOM_input key is illustrative
    code="CROC102",
    kind="suggestion",  # level INFO by default
    title="Eddy-resolving grid: revisit coarse-grid parameterizations",
    message="Below about 10 km, schemes designed for coarser grids may conflict.",
    scope=qe.Scope(axes={"resolution": {"lt": 10.0}}),
    suggestions=(qe.Suggestion("MOM_input", "THICKNESSDIFFUSE", False),),
)
registry.add(croc102)  # DuplicateCodeError if the code is already registered


class CruStations(
    qe.ComputedRule,
    code="CRU002",
    registry=registry,
    facets=cru,
    requires=["cru_ts.stn"],
):
    """CRU TS value from few or no stations"""  # simple form; graded one in 12.4

    def check(self, query, match):
        stn = query.context["cru_ts.stn"]  # station counts the adapter already holds
        zero = float((stn == 0).mean())  # share of cell-months that are climatology
        if zero > 0:
            return {"level": logging.ERROR, "details": {"stn0_fraction": zero}}
        return float(stn.mean()) <= 2  # thinning: one or two gauges within 450 km


lake = sp.polygon(lake_geojson)  # a HydroLAKES polygon; never lake.buffer(0.5)
found = registry.query(  # an adapter that reads CRU TS cells passes them as support=
    space=lake,
    time=y1991_2020,
    requests=[qe.Request("CRUTS", variables=("pre",))],  # version 4.07 assumed
    context={"cru_ts.stn": stn},  # station counts for the cells read
    label="lake 1234",
)
pair = registry.query(  # each product with its own variables and time
    space=lake,
    requests=[qe.Request("cru_ts", ("pre",)), qe.Request("era5_land", ("tas",))],
    label="lake 1234",
)
named = [(f.product, f.code) for f in pair]  # every finding names its product

only_res = registry.query(axes={"resolution": 8.0}, include_conditional=True)
# CROC102 is definite; CROC101 is conditional_on ("space", "model"), and so on.

ring = sp.polygon(outline)  # outer cell corners, closed along 90N around the pole
res = (8.0, 12.0)  # (finest, coarsest) cell spacing in km, computed by the caller
arctic = registry.query(
    space=ring, time=y1991_2020, axes={"resolution": res}, facets=mom6
)
todo = [s for f in arctic if f.kind == "suggestion" for s in f.suggestions]

glon, glat = np.meshgrid(np.arange(-179.75, 180, 0.5), np.arange(-89.75, 90, 0.5))
lon, lat = glon.ravel(), glat.ravel()  # every 0.5 degree cell centre
bulk = registry.query_points(lon, lat, weights=np.cos(np.radians(lat)), facets=cru)
weak = bulk.any(logging.WARNING)  # per-point mask
share = bulk.fractions[("cru_ts", "CRU001")]  # keyed by (product, code)

ranked = registry.suitable(qe.Query(space=lake, time=y1991_2020), variable="pre")

log = logging.getLogger("glhe")
for f in found + arctic:
    log.log(f.level, f)  # "[CRU001] ... (lake 1234; area 100%; ...)"
gaps = [f for f in found if f.kind == "coverage"]  # QE001 or QE002 would stop here
if gaps:
    raise RuntimeError("\n".join(map(str, gaps)))
