"""Usage of the queryearth API (illustrative; examples/toy/play.py runs end to end).

lake_geojson, outline and stn stand for the caller's own data: a lake polygon, an
Arctic domain's outer cell corners closed along 90N, and station counts. The
demo pack holds CRU001 and CROC101. CRU002 here is the simple form; design.md
section 12.4 describes the graded one, whose code is in examples/README.md.
"""

import logging

import numpy as np

import queryearth as qe
from queryearth import space as sp

registry = qe.Registry(
    "demo", axes=[qe.Axis("resolution", "km", "horizontal grid spacing")]
)
registry.load_pack("packs/demo")  # CRU001 and CROC101
cru, mom6 = {"product": "cru_ts", "variable": "pre"}, {"model": "mom6"}
cru_407 = {**cru, "version": "4.07"}  # a query names the version it uses
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
found = registry.query(
    space=lake,  # an adapter that reads CRU TS cells passes them instead
    time=y1991_2020,
    facets=cru_407,
    context={"cru_ts.stn": stn},  # station counts for the cells read
    label="lake 1234",
)
per_product = {  # one query per product, each with its own variables
    product: registry.query(
        space=lake, time=y1991_2020, facets={"product": product, "variable": var}
    )
    for product, var in [("cru_ts", "pre"), ("era5_land", "tas")]
}

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
weights = np.cos(np.radians(lat))
bulk = registry.query_points(lon, lat, weights, time=y1991_2020, facets=cru_407)
weak = bulk.any(logging.WARNING)  # per-point mask
share = bulk.fractions["CRU001"]  # keyed by code

log = logging.getLogger("glhe")
for f in found + arctic:
    log.log(f.level, f)  # "[CRU001] ... (lake 1234; area 100%; ...)"
stop = [f for f in found if f.action == "do_not_use"]  # such as a coverage rule
if stop:
    raise RuntimeError("\n".join(map(str, stop)))
