# Consumer integration in full

This is the full text behind [section 15 of design.md](../design.md#15-consumer-integration), with every line reference, both sketches in full, the changes each consumer needs outside queryearth, and the acceptance criteria. Section numbers refer to [design.md](../design.md); questions such as Q7 and Q46 to Q48 are in its [section 18.2](../design.md#182-outstanding-work), and the others in [decisions.md](decisions.md#questions-decided-by-adopting-their-defaults).

GLHE and CrocoDash are the first two consumers. The integrations below are **acceptance tests for the design**: if the API cannot express them simply, the design is wrong. They are not changes to make now; each would become its own pull request in the consumer's repository after a prototype exists. Line numbers refer to CrocoDash `main` at 507f2d6b and GLHE `main` at e26898d. The sketches are illustrative; `sp` is `queryearth.space`, and `ADVISORIES` and `INDEX` are each consumer's own Index, defined once in its adapter module.

## CrocoDash

**In short.** CrocoDash needs queryearth to check one model domain, one date range and several forcing products in a single call, to return model-parameter recommendations for the domain, and to stop case setup before anything is written when a product cannot cover the request. The rest of this subsection says where that call goes in CrocoDash and what CrocoDash must change around it.

**Where.** The hook goes in `Case.configure_forcings`, directly after `config |= self.fcr.run_configurators(None)` (`CrocoDash/case.py:642`). The CICE, WW3, runoff and chlorophyll products are only chosen inside the configurators, so an earlier point would miss them. The line also sits inside the `try` block whose `except BaseException` (`:657-659`) restores the user_nl files, so a coverage error raised there comes before stale outputs are deleted (`:645-650`) and before `config.json` is written (`:655-656`), and the case is left as it was.

**Not elsewhere.** `ProductRegistry.call` has no production callers (only `tests/raw_data_access/test_base_registry.py`). `fetch_raw_chunk` (`forcing/utils.py:119`) runs once per 7-day chunk inside fork-based worker pools (`forcing/obc.py:529-531`), about 209 duplicate warnings per simulated year, and it receives bounding boxes that ignore the antimeridian: for an Arctic north edge it gets -179.5 to 180 instead of 135 to 225, so a rule checked against that box would match the whole latitude band.

**Query.** The adapter makes one query per case, with one request per forcing product (section [4.12](../design.md#412-several-products-in-one-query-requests)). The query carries the space `sp.from_grid(grid.qlon, grid.qlat)` (the traced corner outline, which handles rotated, seam-crossing and polar domains), or `sp.lat_band(...)` for cyclic domains; the date range; `resolution` from `sp.resolution_of(grid.qlon, grid.qlat)` in km; the facet `model = "mom6"`; and the case name as label. The date range goes through `qe.from_bounds([start], [end])`, because CrocoDash's end date is exclusive: `case.py:580` sets `self.date_range = pd.to_datetime(date_range)`, two midnight timestamps, and a run lasts `(end - start).days` days (section [8.3](../design.md#83-time-axes-and-facets)). Each request names a product from the configurators' `*product_name` inputs in `config` (`product_name`, `cice_product_name`, `ww3_obc_product_name`) and the variables CrocoDash reads from it, so a rule such as GLORYS001, which constrains `thetao` and `so`, is decided rather than conditional. Model-level rules such as CROC101, CROC102 and CROC104 are evaluated once, on the domain; product rules and coverage once per request, so variables never cross between products and every product gets its own coverage finding. CrocoDash would declare one queryearth `Product` per `ProductRegistry` product, with coverage, calendar, version and, for gridded products, `grid`, and next to it the variables it reads (`READS` below), in a new module that also holds `ADVISORIES`; none of this metadata exists today (nothing declares GLORYS's first date, for example). Products whose availability is computed at run time, such as `cesm_ww3_jra.available_range`, get a callable coverage.

**Behaviour.** Coverage findings raise `AdvisoryError`, so `configure_forcings` fails before writing anything; with `strict=False`, a new keyword (default True), they warn instead. Caveats warn. Recommendations are logged at `INFO` by `emit()` (section [11.1](../design.md#111-modes-and-policy)) and recorded in `config.json` under `"advisories"`; suggestions are not applied in v1. CrocoDash reports through `print` (53 call sites) and `logger.warning` (7) and never through `warnings.warn`; calling `setup_logger("queryearth")` once sends queryearth's log lines to standard output alongside CrocoDash's own.

```python
# CrocoDash/case.py, Case.configure_forcings, directly after case.py:642
#     config |= self.fcr.run_configurators(None)
config["advisories"] = self._advise(config, strict)


def _advise(self, config: dict, strict: bool) -> list[dict]:
    grid = self.ocn_grid
    corners = (grid.qlon.values, grid.qlat.values)
    products = sorted(
        {
            value.lower()
            for key, entry in config.items()
            if key != "caseroot"
            for name, value in entry["inputs"].items()
            if name.endswith("product_name") and value
        }
    )
    start, end = self.date_range  # end exclusive: the run lasts (end - start).days
    found = ADVISORIES.query(
        space=(
            sp.lat_band(float(grid.qlat.min()), float(grid.qlat.max()))
            if grid.cyclic_x  # cyclic domains have no bounding box
            else sp.from_grid(*corners)  # seam split and pole closed inside
        ),
        time=qe.from_bounds([start], [end]),
        axes={"resolution": sp.resolution_of(*corners)},
        facets={"model": "mom6"},
        requests=[qe.Request(p, variables=READS.get(p, ())) for p in products],
        label=self.caseroot.name,
    )
    coverage = [f for f in found if f.kind == "coverage"]
    with qe.policy(skip_packages=("CrocoDash",)):
        qe.emit([f for f in found if f.kind != "coverage"])  # warn; recommendations log
        # coverage last, so the rest is shown before a strict case stops
        qe.emit(coverage, mode="raise" if strict else "warn")
    return [f.to_dict() for f in found]
```

Every finding is kept: `emit()` de-duplicates by code, label and product, so two products outside coverage give two findings, and each finding records its product for `config.json`.

**Consumer prerequisites, outside queryearth's scope.** Recording findings in `config.json` needs one change in CrocoDash: four loops treat every key except `"caseroot"` as a configurator (`available_process_flags` at `forcing/base.py:287`, `resolve_process_targets` at `forcing/base.py:301`, `recipe.py:195` and `shareable.py:323`), so a new `"advisories"` key would make `process_forcings` fail unless they skip it too. The alternative is a sibling file, `extract_forcings/advisories.json` (Q48).

**Acceptance criteria.**

1. An Arctic domain (EPSG:3995, 25 km; its boundary ring had 960 vertices in the design research) yields CROC101 and CROC104 as definite recommendations, with `area_fraction` the share of the domain north of 66.5N. CROC104 suggests the MOM_input parameter `DT`, computed from the domain's finest spacing. Both suggestions are logged at `INFO` and recorded in `config.json`.
2. A 1/12 degree Gulf of Mexico domain, finer than 10 km everywhere (1/12 degree is about 9.3 km at the equator), yields CROC102 as a definite finding with its `axes` overlap.
3. A Pacific domain that crosses the antimeridian and a cyclic Southern Ocean channel produce no findings from rules on the far side of the globe.
4. A date range outside a product's declared coverage produces QE002; `configure_forcings` raises, the user_nl files are restored and `config.json` is unchanged. With `strict=False`, it warns instead.
5. `process_forcings`, the recipe code and the bundle code still read a `config.json` that contains `"advisories"`.
6. A date range outside the coverage of two products produces two QE002 findings, one per product, and the `AdvisoryError` holds both.
7. A GLORYS-forced case starting in 1995 yields GLORYS001 as a definite caveat, because the request for `glorys` carries the variables CrocoDash reads, `thetao` and `so` among them.

## GLHE

**In short.** GLHE needs queryearth to check one lake against several products in a single call, before anything is downloaded, and to turn the CRU TS station counts it already reads into graded, per-year caveats. The rest of this subsection says where those calls go in GLHE and what GLHE must change around them.

GLHE processes one HydroLAKES polygon per run and passes no time range: `product_driver(polygon, debug, run_cleanly)` reads each product's whole record. It needs two hooks.

**Pre-flight**, in `CLAY_driver.main` before the product loop (`GLHE/CLAY/CLAY_driver.py:140-162`). It makes one query with the lake outline and one request per product, and skips products that cannot serve the lake before anything is downloaded. Products that declare a grid, such as CRU TS and ERA5-Land, are judged on the cells the lake touches, which the engine derives from the grid (section [4.12](../design.md#412-several-products-in-one-query-requests)); NWM, which has no grid, is judged on the outline with its callable coverage. Each request takes its time and version from its own product, so time-scoped findings are definite and resolved in time although GLHE passes no period. Today NWM fails late: the NWM retrospective store GLHE reads lists 5,782 lakes, `find_lake_id` raises a generic `Exception` when the nearest of them is not inside the polygon (`data_access/NWM.py:81-83`), and the product loop logs it as "not available for this lake". With queryearth, NWM's `Product` carries a callable coverage that runs the same test once, up front, and a QE001 finding with action `do_not_use` turns off `run_on_start` and records why. `Index.suitable()` over the same lake answers the "Global Product API" that `Products.md:42-46` asks for.

**Accessor rule**, in the CRU TS accessor. Today, when no cell centre falls inside the lake's bounding box, `subset_box` raises `ValueError` and the code retries with `polygon.buffer(0.5)` (`data_access/CRUTS.py:119-125`). Selecting the overlap cells, the same cells the engine derives from CRU TS's grid, never drops a small lake, so the fallback goes; `ERA5_Land.py` has the same fallback and gets the same change. The query runs in `product_driver` once the data are known, so the cached (pickled) path is covered too, and it passes the lake, the `stn` values of exactly the support cells, and the lake's own area for GEN001. Which cells GLHE averages is GLHE's choice: today it averages, unweighted, a box padded by one cell, 50 to 100 times the lake's area for CRU TS (design research). The sketch assumes GLHE switches to the overlap cells; until it does, the adapter passes the padded box as `Request.support` (Q46). CRU001's `time_overlap` runs from 2000-01-01 to the end of CRU TS's declared coverage, 2022-12-31; CRU002's lists the flagged years.

```python
# GLHE/CLAY/CLAY_driver.py, CLAY_driver.main, before the product loop (:140)
lake = sp.polygon(self.lake_polygon)
keys = list(self.data_products)  # "ERA5_Land", "CRUTS", "NWM" are declared aliases
requests = [qe.Request(key, variables=READS[key]) for key in keys]
found = INDEX.query(space=lake, requests=requests, label=lake_name)
for i, key in enumerate(keys):  # each finding names its request, so products never mix
    mine = [f for f in found if f.request == i]
    blocked = [f for f in mine if f.kind == "coverage" and f.action == "do_not_use"]
    if blocked:
        self.data_products[key]["run_on_start"] = False  # skipped before any download
    publish(events.AdvisoryEvent(key, [f.to_dict() for f in mine]))


def nwm_coverage(query: qe.Query) -> qe.Coverage:
    """NWM serves 5,782 lakes, not an area: covered if a lake point is inside."""
    hit = shapely.intersects_xy(query.space.geometry, NWM_LON, NWM_LAT).any()
    return qe.Coverage(space=query.space if hit else sp.nowhere(), time=NWM_TIME)


# GLHE/CLAY/data_access/CRUTS.py, CRUTS.product_driver
lake = sp.polygon(polygon)
rows, cols = np.nonzero(sp.cell_mask(CRU_EDGES, lake))  # the cells the engine derives
dataset = ...  # CRU TS on its global 0.5 degree grid, opened lazily from CRUTS.zarr
ctx = {"request_km2": lake.area_km2}
if "stn" in dataset:  # absent from some local files: CRU002 is then conditional
    cell = {
        "lat": xr.DataArray(rows, dims="cell"),
        "lon": xr.DataArray(cols, dims="cell"),
    }
    stn = dataset["stn"].isel(cell)  # (time, cell): exactly the support cells
    ctx |= {"cru_ts.stn": stn.values, "cru_ts.year": dataset["time"].dt.year.values}
request = qe.Request("CRUTS", variables=("pre",))  # support derived from the grid
found = INDEX.query(space=lake, requests=[request], context=ctx, label=lake_name)
qe.emit(found, mode="log")  # reaches GLHE_root.log through the root logger
payload = [f.to_dict() for f in found]
self.send_data_product_event(events.AdvisoryEvent("CRUTS", payload))
```

`CRU_EDGES` is `(np.arange(-180, 180.5, 0.5), np.arange(-90, 90.5, 0.5))`, the edges that CRU TS's `Product.grid` declares, so `cell_mask` selects exactly the cells the engine uses as the support; `sp.nowhere()` is the empty space (Q7); `READS` maps each GLHE product key to the variables GLHE reads from it; `NWM_LON`, `NWM_LAT` and `NWM_TIME` are read once from the NWM store's consolidated metadata (5,782 lakes; hourly steps from 1979-02-01, proleptic Gregorian); `publish` is GLHE's `pubsub.EventBus.Publish`; `xr` is xarray; and `lake_name` is `GLHE.CLAY.globals.config["LAKE_NAME"]`.

**Delivery.** Findings travel as `to_dict()` payloads on GLHE's CALCITE event bus, in a new `AdvisoryEvent(product_name, findings)` dataclass in `CALCITE/events.py`. An `AdvisoryEvent` carries the complete current findings for one product, and listeners keep the latest one per product, so the accessor's event, which adds CRU002, replaces the pre-flight's for CRU TS. `CLAY_driver` subscribes listeners that add an "Advisories" section to the README (`write_and_output_README`); write `<lake>_advisories.json`, published as an `OutputFileEvent` with a new `TypeOfFileLIME` member so `write_and_output_LIME_CONFIG` lists it; and let LIME show each finding as a `pn.pane.Alert` with `alert_type` set from the severity, as LIME already does for missing gridded data (`LIME/LIME_sample_dashboard.py:68`). Log mode needs nothing extra: queryearth's logger propagates to the root logger, which `set_up_logging` already writes to `GLHE_root.log` (`CLAY_driver.py:65-77`).

**Consumer prerequisites, outside queryearth's scope.** Two existing event-bus bugs must be fixed first. `CLAY_driver.py:43-45` subscribes `read_me_data_product_run_listener` to `"OutputFileEvent"` instead of `"DataProductRunEvent"`, and that listener reads fields `DataProductRunEvent` does not have. And `EventBus.topics` is shared by the whole class while `Unsubscribe` looks the topic up by the callback's class name (`CALCITE/pubsub.py:56-58`), so it never matches; listeners pile up across driver instances, and a long-running dashboard server would duplicate every advisory.

**Acceptance criteria.**

1. For a lake outside NWM's domain, the pre-flight produces QE001 with action `do_not_use` for the NWM request; NWM is skipped, the README says why, and no exception from `NWM.py:81-83` is logged.
2. For a lake smaller than one CRU TS cell, the support is one cell and no fallback runs; GEN001 is in the findings at `INFO` and is not emitted.
3. For a Congo-basin lake, CRU002 is `SEVERE` with the climatology years in `time_overlap` (in a Congo box, 55% of land cells had zero stations in July 2021, design research), and CRU001 is definite with `space`, `time` and `version` in `assumed`.
4. For a South African lake, CRU002 grades rather than flags: `WARNING` for thin years, or nothing if its cells keep more than two stations. The expected years must be computed from `stn` before this test is written.
5. `INDEX.suitable(qe.Query(space=lake), variable="pre")` ranks the products that offer precipitation for the lake, each gridded product judged on its own cells, without describing any of them as good.
6. The pre-flight's single query returns findings that each name their product, with CRU TS findings measured on CRU TS cells and ERA5-Land findings on ERA5-Land cells, and with each product's time taken from its own coverage.

## Warning-fatigue trial

Requirement R15 asks whether a draft pack warns so often that people stop reading. Before 1.0, a draft pack is run, at the default policy, against 1,000 HydroLAKES lakes spread across size classes and regions and about 10 CrocoDash domains (regional, rotated, polar, antimeridian-crossing and cyclic). For each query the trial records how many findings are returned, how many `emit()` shows, and how many are conditional. Every code that `emit()` shows for more than half of the queries is reviewed: its severity is lowered, its `min_overlap` raised, or its scope narrowed. The one-half threshold is an author choice. The trial also settles Q11 and Q12. It is an acceptance test of the design and has not been run.
