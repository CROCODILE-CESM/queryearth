# Consumer integration in full

> **Frozen.** This file was frozen on 2026-10-13 at commit e5e9d0e. It records the design as it stood then and is no longer updated. The public docs in `docs/source` and `CLAUDE.md` describe the current package.

This is the full text behind [section 15 of design.md](../design.md#15-consumer-integration), with every line reference, both sketches in full, the changes each consumer needs outside queryearth, and the acceptance criteria. Section numbers refer to [design.md](../design.md); questions such as Q46 to Q48 are in its [section 18.2](../design.md#182-outstanding-work), and the others in [decisions.md](decisions.md#questions-decided-by-adopting-their-defaults).

GLHE and CrocoDash are the first two consumers. The integrations below are **acceptance tests for the design**: if the API cannot express them simply, the design is wrong. They are not changes to make now; each would become its own pull request in the consumer's repository. Line numbers refer to CrocoDash `main` at 507f2d6b and GLHE `main` at e26898d. The sketches are illustrative; `sp` is `queryearth.space`, and `ADVISORIES` and `REGISTRY` are each consumer's own Registry, defined once in its adapter module.

## CrocoDash

**In short.** CrocoDash needs queryearth to check one model domain, one date range and several forcing products, one query per product, to return model-parameter suggestions for the domain, and to stop case setup before anything is written when a product cannot cover the request. The rest of this subsection says where that call goes in CrocoDash and what CrocoDash must change around it.

**Where.** The hook goes in `Case.configure_forcings`, directly after `config |= self.fcr.run_configurators(None)` (`CrocoDash/case.py:642`). The CICE, WW3, runoff and chlorophyll products are only chosen inside the configurators, so an earlier point would miss them. The line also sits inside the `try` block whose `except BaseException` (`:657-659`) restores the user_nl files, so a coverage error raised there comes before stale outputs are deleted (`:645-650`) and before `config.json` is written (`:655-656`), and the case is left as it was.

**Not elsewhere.** `ProductRegistry.call` has no production callers (only `tests/raw_data_access/test_base_registry.py`). `fetch_raw_chunk` (`forcing/utils.py:119`) runs once per 7-day chunk inside fork-based worker pools (`forcing/obc.py:529-531`), about 209 duplicate warnings per simulated year, and it receives bounding boxes that ignore the antimeridian: for an Arctic north edge it gets -179.5 to 180 instead of 135 to 225, so a rule checked against that box would match the whole latitude band.

**Query.** The adapter makes one query per forcing product (section [4.12](../design.md#412-several-products-one-query-each)). Each query carries the space, the outline of the grid's cell corners as a polygon (queryearth splits it at the antimeridian, and CrocoDash closes a polar domain's outline along the pole first), or `sp.box(-180, south, 180, north)` for cyclic domains; the date range; `resolution` as the grid's (finest, coarsest) cell spacing in km; the facets `model = "mom6"`, the product and the variables CrocoDash reads from it; and the case name as label. The date range is passed with closed ends, from `start` to the day before `end`, because CrocoDash's end date is exclusive: `case.py:580` sets `self.date_range = pd.to_datetime(date_range)`, two midnight timestamps, and a run lasts `(end - start).days` days (section [8.3](../design.md#83-time-axes-and-facets)). The products come from the configurators' `*product_name` inputs in `config` (`product_name`, `cice_product_name`, `ww3_obc_product_name`), and the variables make a rule such as GLORYS001, which constrains `thetao` and `so`, decided rather than conditional. Model-level rules such as CROC101 match every query, so the adapter keeps each once. CrocoDash would write each `ProductRegistry` product's coverage as rules (warnings with action `do_not_use`, scoped to the product and to the time or space outside its record), and next to them the variables it reads (`READS` below), in a new module that also holds `ADVISORIES`; none of this metadata exists today (nothing declares GLORYS's first date, for example). Products whose availability is computed at run time, such as `cesm_ww3_jra.available_range`, get a computed rule.

**Behaviour.** The adapter logs every finding at its own level with `logger.log(f.level, f)` (section [11](../design.md#11-reporting-findings)), so warnings show at `WARNING` and suggestions at `INFO`, and records every finding in `config.json` under `"advisories"`; suggestions are not applied in v1. Findings with action `do_not_use`, such as a coverage rule's, then raise a `ValueError` that lists them, so `configure_forcings` fails before writing anything; with `strict=False`, a new keyword (default True), they are only logged. CrocoDash reports through `print` (53 call sites) and `logger.warning` (7) and never through `warnings.warn`, so the findings go through CrocoDash's own logger, to standard output alongside its other lines.

```python
# CrocoDash/case.py, Case.configure_forcings, directly after case.py:642
#     config |= self.fcr.run_configurators(None)
config["advisories"] = self._advise(config, strict)


def _advise(self, config: dict, strict: bool) -> list[dict]:
    grid = self.ocn_grid
    lon, lat = grid.qlon.values, grid.qlat.values  # cell corners
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
    domain = qe.Query(
        space=(
            sp.box(-180, float(lat.min()), 180, float(lat.max()))  # a latitude band
            if grid.cyclic_x  # cyclic domains have no closed outline
            else sp.polygon(outline(lon, lat))  # queryearth splits it at the seam
        ),
        time=qe.interval(start.date(), (end - pd.Timedelta(days=1)).date()),
        axes={"resolution": spacing_km(lon, lat)},  # (finest, coarsest)
        label=self.caseroot.name,
    )
    found = {}  # one query per product; a model-level rule is kept once
    for p in products:
        facets = {"model": "mom6", "product": p, "variable": READS[p]}
        for f in ADVISORIES.query(domain, facets=facets):
            found.setdefault((f.code, f.matched_facets.get("product")), f)
    stop = [f for f in found.values() if f.action == "do_not_use"]
    for f in sorted(found.values(), key=lambda f: f.action == "do_not_use"):
        logger.log(f.level, f)  # the do_not_use findings last
    if stop and strict:  # stop before anything is written
        raise ValueError("\n".join(map(str, stop)))
    return [f.to_dict() for f in found.values()]
```

`outline(lon, lat)` and `spacing_km(lon, lat)` are CrocoDash helpers, since queryearth takes polygons and numbers: the first returns the ring of the grid's outer corners, closed along latitude 90 or -90 when the domain goes around a pole, and the second the shortest and longest cell edge in km. Two products outside coverage give two findings, and a product rule's finding records its product in `matched_facets` for `config.json`.

**Consumer prerequisites, outside queryearth's scope.** Recording findings in `config.json` needs one change in CrocoDash: four loops treat every key except `"caseroot"` as a configurator (`available_process_flags` at `forcing/base.py:287`, `resolve_process_targets` at `forcing/base.py:301`, `recipe.py:195` and `shareable.py:323`), so a new `"advisories"` key would make `process_forcings` fail unless they skip it too. The alternative is a sibling file, `extract_forcings/advisories.json` (Q48).

**Acceptance criteria.**

1. An Arctic domain (EPSG:3995, 25 km; its boundary ring had 960 vertices in the design research) yields CROC101 and CROC104 as definite suggestions, with `area_fraction` the share of the domain north of 66.5N. CROC104 suggests the MOM_input parameter `DT`, computed from the domain's finest spacing. Both suggestions are logged at `INFO` and recorded in `config.json`.
2. A 1/12 degree Gulf of Mexico domain, finer than 10 km everywhere (1/12 degree is about 9.3 km at the equator), yields CROC102 as a definite finding with its `axes` overlap.
3. A Pacific domain that crosses the antimeridian and a cyclic Southern Ocean channel produce no findings from rules on the far side of the globe.
4. A date range outside a product's coverage produces that product's coverage rule; `configure_forcings` raises, the user_nl files are restored and `config.json` is unchanged. With `strict=False`, it logs the finding instead.
5. `process_forcings`, the recipe code and the bundle code still read a `config.json` that contains `"advisories"`.
6. A date range outside the coverage of two products produces two coverage findings, one per product, and the error lists both.
7. A GLORYS-forced case starting in 1995 yields GLORYS001 as a definite warning, because the query for `glorys` carries the variables CrocoDash reads, `thetao` and `so` among them.

## GLHE

**In short.** GLHE needs queryearth to check one lake against several products, one query each, before anything is downloaded, and to turn the CRU TS station counts it already reads into graded, per-year warnings. The rest of this subsection says where those calls go in GLHE and what GLHE must change around them.

GLHE processes one HydroLAKES polygon per run and passes no time range: `product_driver(polygon, debug, run_cleanly)` reads each product's whole record. It needs two hooks.

**Pre-flight**, in `CLAY_driver.main` before the product loop (`GLHE/CLAY/CLAY_driver.py:140-162`). It makes one query per product with the lake outline (section [4.12](../design.md#412-several-products-one-query-each)), and skips products that cannot serve the lake before anything is downloaded. Each query gives the product's whole record as its time and the version GLHE reads, so time-scoped findings are definite. Today NWM fails late: the NWM retrospective store GLHE reads lists 5,782 lakes, `find_lake_id` raises a generic `Exception` when the nearest of them is not inside the polygon (`data_access/NWM.py:81-83`), and the product loop logs it as "not available for this lake". With queryearth, NWM's coverage is a rule: a polygon outside its domain, or, as sketched below, a computed rule that runs the same test once, up front, and its finding, with action `do_not_use`, turns off `run_on_start` and records why. The same queries over every product start the "Global Product API" that `Products.md:42-46` asks for.

**Accessor rule**, in the CRU TS accessor. Today, when no cell centre falls inside the lake's bounding box, `subset_box` raises `ValueError` and the code retries with `polygon.buffer(0.5)` (`data_access/CRUTS.py:119-125`). Selecting the overlap cells, every cell whose intersection with the lake has positive area, never drops a small lake, so the fallback goes; `ERA5_Land.py` has the same fallback and gets the same change. The query runs in `product_driver` once the data are known, so the cached (pickled) path is covered too, and it passes the overlap cells as the query's space, the `stn` values of exactly those cells, and the lake's own area for GEN001. Which cells GLHE averages is GLHE's choice: today it averages, unweighted, a box padded by one cell, 50 to 100 times the lake's area for CRU TS (design research). The sketch assumes GLHE switches to the overlap cells; until it does, the adapter passes the padded box as the query's space (Q46). CRU001's `time_overlap` runs from 2000-01-01 to the end of CRU TS's record, 2022-12-31, which GLHE passes as the time; CRU002's lists the flagged years.

```python
# GLHE/CLAY/CLAY_driver.py, CLAY_driver.main, before the product loop (:140)
lake = sp.polygon(self.lake_polygon)
for key in self.data_products:  # "ERA5_Land", "CRUTS" and "NWM": one query each
    product = {"time": RECORDS[key], "facets": FACETS[key], "label": lake_name}
    found = REGISTRY.query(space=lake, **product)
    if any(f.action == "do_not_use" for f in found):  # such as NWM001
        self.data_products[key]["run_on_start"] = False  # skipped before any download
    publish(events.AdvisoryEvent(key, [f.to_dict() for f in found]))


@REGISTRY.rule("NWM001", level="error", action="do_not_use", facets=NWM)
def outside_nwm(query, match):
    """NWM serves 5,782 lakes, not an area: none of them lies inside this lake"""
    return not shapely.intersects_xy(query.space.geometry, NWM_LON, NWM_LAT).any()


# GLHE/CLAY/data_access/CRUTS.py, CRUTS.product_driver
lake = sp.polygon(polygon)
rows, cols = overlap_cells(lake)  # cells that meet the lake with positive area
support = sp.polygon(cell_union(rows, cols))  # those cells, as one polygon
dataset = ...  # CRU TS on its global 0.5 degree grid, opened lazily from CRUTS.zarr
ctx = {"request_km2": lake.area_km2}
if "stn" in dataset:  # absent from some local files: CRU002 is then conditional
    cell = {
        "lat": xr.DataArray(rows, dims="cell"),
        "lon": xr.DataArray(cols, dims="cell"),
    }
    stn = dataset["stn"].isel(cell)  # (time, cell): exactly the support cells
    ctx |= {"cru_ts.stn": stn.values, "cru_ts.year": dataset["time"].dt.year.values}
cru = {"time": RECORDS["CRUTS"], "facets": FACETS["CRUTS"], "label": lake_name}
found = REGISTRY.query(space=support, context=ctx, **cru)
for f in found:  # reaches GLHE_root.log through the root logger
    logging.getLogger(__name__).log(f.level, f)
payload = [f.to_dict() for f in found]
self.send_data_product_event(events.AdvisoryEvent("CRUTS", payload))
```

`overlap_cells` and `cell_union` are GLHE helpers on CRU TS's grid, whose cell edges are `(np.arange(-180, 180.5, 0.5), np.arange(-90, 90.5, 0.5))`: the first returns the row and column of every cell whose intersection with the lake has positive area, and the second the union of those cells as a shapely geometry; `FACETS` maps each GLHE product key to its query's facets (the pack's product name, the variables GLHE reads and the version), and `RECORDS` to the product's whole record, for NWM hourly from 1979-02-01; `NWM` is `{"product": ["nwm_retro"]}`; `NWM_LON` and `NWM_LAT` are read once from the NWM store's consolidated metadata (5,782 lakes); `publish` is GLHE's `pubsub.EventBus.Publish`; `xr` is xarray; and `lake_name` is `GLHE.CLAY.globals.config["LAKE_NAME"]`.

**Delivery.** Findings travel as `to_dict()` payloads on GLHE's CALCITE event bus, in a new `AdvisoryEvent(product_name, findings)` dataclass in `CALCITE/events.py`. An `AdvisoryEvent` carries the complete current findings for one product, and listeners keep the latest one per product, so the accessor's event, which adds CRU002, replaces the pre-flight's for CRU TS. `CLAY_driver` subscribes listeners that add an "Advisories" section to the README (`write_and_output_README`); write `<lake>_advisories.json`, published as an `OutputFileEvent` with a new `TypeOfFileLIME` member so `write_and_output_LIME_CONFIG` lists it; and let LIME show each finding as a `pn.pane.Alert` with `alert_type` set from the level, as LIME already does for missing gridded data (`LIME/LIME_sample_dashboard.py:68`). Logging needs nothing extra: GLHE's module loggers propagate to the root logger, which `set_up_logging` already writes to `GLHE_root.log` (`CLAY_driver.py:65-77`).

**Consumer prerequisites, outside queryearth's scope.** Two existing event-bus bugs must be fixed first. `CLAY_driver.py:43-45` subscribes `read_me_data_product_run_listener` to `"OutputFileEvent"` instead of `"DataProductRunEvent"`, and that listener reads fields `DataProductRunEvent` does not have. And `EventBus.topics` is shared by the whole class while `Unsubscribe` looks the topic up by the callback's class name (`CALCITE/pubsub.py:56-58`), so it never matches; listeners pile up across driver instances, and a long-running dashboard server would duplicate every advisory.

**Acceptance criteria.**

1. For a lake outside NWM's domain, the pre-flight's NWM query produces NWM001 with action `do_not_use`; NWM is skipped, the README says why, and no exception from `NWM.py:81-83` is logged.
2. For a lake smaller than one CRU TS cell, the support is one cell and no fallback runs; GEN001 is in the findings at `INFO`, so a log at `WARNING` and above does not show it.
3. For a Congo-basin lake, CRU002 is `ERROR` with the climatology years in `time_overlap` (in a Congo box, 55% of land cells had zero stations in July 2021, design research), and CRU001 is definite.
4. For a South African lake, CRU002 grades rather than flags: `WARNING` for thin years, or nothing if its cells keep more than two stations. The expected years must be computed from `stn` before this test is written.
5. Dropped in v0.1.0 with the inverse query ([design.md section 17](../design.md#17-non-goals-for-v1-and-upgrade-paths)): `REGISTRY.suitable()` ranked the products that offer precipitation for the lake.
6. Each pre-flight query's findings concern its own product only, over that product's record.

## Warning-fatigue trial

Requirement R15 asks whether a draft pack warns so often that people stop reading. Before 1.0, a draft pack is run against 1,000 HydroLAKES lakes spread across size classes and regions and about 10 CrocoDash domains (regional, rotated, polar, antimeridian-crossing and cyclic). For each query the trial records how many findings are returned, how many a log at `WARNING` and above shows (definite, and not below their `min_overlap`), and how many are conditional. Every code shown for more than half of the queries is reviewed: its level is lowered, its `min_overlap` raised, or its scope narrowed. The one-half threshold is an author choice. The trial also settles Q11 and Q12. It is an acceptance test of the design and has not been run.
