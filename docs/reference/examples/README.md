# Example pack

This directory holds the worked examples of [section 16 of design.md](../../design.md#16-worked-examples). They check that the data model can express real rules: 14 rule records in one pack, three computed rules and one product coverage registered in Python, and the findings that five queries should return. Most examples come from the design research and published product documentation; three come from fields outside earth science. "Illustrative" marks content not checked against a source, "fictional" marks invented places, feeds or authorities, and "author choice" marks a threshold or boundary a reviewer should question. Section numbers refer to [design.md](../../design.md).

| File | Contents |
|---|---|
| [pack.toml](pack.toml) | The pack header: name, version, the seven owned code prefixes, licence, the products (`cru_ts`, `era5`, `glorys`, `gbif`, `demo_ili`) and the region namespaces `ar6` and `ne` |
| [rules.geojson](rules.geojson) | The 14 rule records as one FeatureCollection, with a `metadata` header |
| This README | What each rule shows and where it comes from, the rules and the product coverage declared in Python, and the five example queries with their expected findings |

## The pack

The pack is [pack.toml](pack.toml) plus one FeatureCollection, [rules.geojson](rules.geojson). Its seven code prefixes cover every code in the collection, whose `metadata` header repeats the name, version, prefixes and licence. ERA5 itself calls total precipitation `tp`, but `suitable(variable="pre")` matches names literally, so the pack uses `pre` for both CRU TS and ERA5 (Q36 in [decisions.md](../decisions.md#outcomes-emission-and-the-inverse-query)). The regions files are not included: `ar6` holds the IPCC AR6 reference regions keyed by abbreviation, and `ne` holds named lakes keyed by a slug such as `caspian_sea`. In this directory the collection sits next to `pack.toml`, so the toml lists `files = ["rules.geojson"]`. The pack lives only under the package's `tests/` and `docs/` directories, is excluded from the wheel, and carries the header line "Worked examples for the design document, not a curated pack", so it never ships as content (section [1.3](../../design.md#13-what-queryearth-is-and-is-not)). Only CRU TS declares a grid, so the examples show both a derived support and a product judged on the caller's own geometry.

## How the examples were checked

All 14 records validate against the JSON Schema in [schema.json](../schema.json), one at a time and as a FeatureCollection (jsonschema 4.26.0, Python 3.11.16; rechecked while revising). A script also ran the loader checks the schema cannot express: unique codes with owned prefixes; declared axis, facet, product and region-namespace names and matching units; periods inside `time` and valid dates; valid polygons with counterclockwise exteriors. Fourteen deliberately broken variants were all rejected, for example a recommendation without suggestions, a box together with a polygon, a version range with both `fixed` and `last_affected`, and a code with the reserved prefix `QE`. The Python snippets parse under the Python 3.11 grammar and black leaves them unchanged.

## Each rule in brief

Each entry says what the rule states, what it demonstrates, and whether its content is grounded in a source or illustrative.

- **CRU001** (caveat, warning). CRU TS 4.07 precipitation over the eight IPCC AR6 African land regions from 2000 onward falls back to climatology where no station is near. It shows named regions with an open-ended period, and is grounded in the design research on GLHE's `CRUTS.zarr` and in Harris et al. 2020.
- **CRU002** (computed caveat, Python). It reads the station counts `stn` the caller passes in the context: the simple form in [usage.py](../usage.py) reports SEVERE for any climatology month, and the [graded form](#cru002-graded-form) grades years as climatology or thin. It shows a raster-derived rule. In the graded form, the exit threshold (3 months) is an author choice and the thin threshold is untested ([Q49](../../design.md#182-outstanding-work)); the 6-of-12 entry rule comes from the design research.
- **CRU003** (caveat, severe, withdrawn). The first statement of the South Africa concern, that precipitation there is climatology since 2000, which the data did not support. It is kept for history and never matches.
- **CRU004** (caveat, warning). What the data do support for the South Africa box (16.5E to 33E, 35S to 22S): from about 2010 its cells rest on fewer stations. It supersedes CRU003 and shows graded severity; the 2010 start is an author choice, as the record's evidence notes say.
- **ERA5-001** (caveat, warning, action `replaced`). ERA5's 2000 to 2006 lower-stratosphere cold bias, which ECMWF reran as ERA5.1. It is global and time-only, limited to the exact version `ERA5`, and grounded in ECMWF known issue 4 and resolved issue 1.
- **ERA5-014** (caveat, warning). ERA5 2 m temperature over the Great Lakes has too strong an annual cycle before 2014. It shows a box with an open start, from ECMWF known issue 14.
- **ERA5-023** (caveat, severe, action `do_not_use`). ERA5 sea-ice cover is missing in the Caspian Sea from late 2007 to 2013. It shows a named region from a second namespace (`ne:caspian_sea`), from ECMWF known issue 23.
- **ERA5-024** (caveat, warning). ERA5 Arctic winter sea-ice skin temperature can be 5 K or more too warm. It shows a polar cap north of 66.5N with recurring months, December to February; the issue is ECMWF known issue 24, and the boundary and the months are author choices.
- **GLORYS001** (caveat, warning). GLORYS12 subsurface temperature and salinity are less constrained before the Argo array reached about 1,000 floats. It is time-only (1993 to 2003) and limited to `thetao` and `so`, grounded in Lellouche et al. 2021 and the Argo milestones.
- **CROC101** (recommendation, info). A MOM6 domain north of 66.5N should consider an active sea-ice component and a polar-stereographic grid. The message is grounded in the knowledge base, the `crs` value in mom6_forge, and the suggestion keys are illustrative.
- **CROC102** (recommendation, info). Below 10 km grid spacing, revisit coarse-grid parameterizations: a rule on resolution only. The message is grounded in the knowledge base; the `THICKNESSDIFFUSE` suggestion is illustrative and was not confirmed by it.
- **CROC103** (recommendation, info). At 25 km or coarser, keep the Strait of Gibraltar open: resolution and space together. The message is grounded in the knowledge base; the target, the key, the box and the threshold are illustrative or author choices.
- **CROC104** (computed recommendation, Python). For a MOM6 domain north of 66.5N, it suggests the MOM_input time step `DT` from the finest grid spacing. Setting the time step from the smallest cells is grounded in the knowledge base; the coefficient of 30 seconds per km is illustrative.
- **GEN001** (computed caveat, info, Python). The caller's own region is much smaller than the product cells that represent it; it runs once per request. It comes from the design research, and its threshold of 0.1 is an author choice.
- **BIO001** (caveat, warning). Presence-only occurrence records in a box over Amazonia up to 1999 reflect where people looked. It shows a custom facet (`basis_of_record`); the region and period are illustrative, and the concern follows Beck et al. 2014 (spatial bias in GBIF records) and Kadmon et al. 2004 (roadside bias).
- **UAS001** (caveat, severe). A fictional geozone at Null Island (0N, 0E), where drone flights up to 120 m need authorisation from March to August. It shows recurring months and a second axis (`altitude_agl`), and keeps the source wording `REQ_AUTHORIZATION` in `source_severity`.
- **EPI001** (caveat, warning). A fictional influenza-like-illness feed with reporting gaps at island sentinel sites, in two periods of 2021. It shows a box across the antimeridian and a union of periods.
- **`nwm_retro`** (product coverage, Python). NWM retrospective v3.0 lake output covers a set of 5,782 lakes from 1979-02-01 to 2023-01-31, declared as object ids. Outside it, QE001 and QE002 fire; the numbers come from the design research.

## Rules at a glance

| Code | What it demonstrates | Scope | Outcome | Source |
|---|---|---|---|---|
| CRU001 | Named regions with an open-ended period | 8 AR6 African regions; 2000 onward; `cru_ts`, `pre`, version 4.07 | caveat, warning | Design research on GLHE's CRUTS.zarr; Harris et al. 2020 |
| CRU002 | A raster-derived rule on data the caller holds (Python; the simple form in [usage.py](../usage.py), the [graded form](#cru002-graded-form) below) | `cru_ts`, `pre`; needs `cru_ts.stn` in the context | caveat, warning or severe | Design research |
| CRU003 | A withdrawn record | Box over South Africa; 2000 onward | caveat, severe (never matches) | Withdrawn: the data do not support it |
| CRU004 | Supersedes CRU003; graded severity | Box 16.5E to 33E, 35S to 22S; 2010 onward | caveat, warning | Design research |
| ERA5-001 | Global and time-only; fixed in a later version | 2000 to 2006; `era5`, version `ERA5` | caveat, warning, action `replaced` | ECMWF known issue 4 and resolved issue 1 |
| ERA5-014 | A region with an open start | Box around the Great Lakes; up to 2013; `t2m` | caveat, warning | ECMWF known issue 14 |
| ERA5-023 | A named region from a second namespace | `ne:caspian_sea`; October 2007 to 2013; `siconc` | caveat, severe, action `do_not_use` | ECMWF known issue 23 |
| ERA5-024 | A polar cap with recurring months | Polygon from 66.5N to the pole; December to February every year; `skt` | caveat, warning | ECMWF known issue 24 |
| GLORYS001 | Time-only, limited to ocean variables | 1993 to 2003; `glorys`; `thetao`, `so` | caveat, warning | Lellouche et al. 2021; Argo milestones |
| CROC101 | An Arctic recommendation with suggestions | Latitude band 66.5N to 90N; model `mom6` | recommendation, info | Ocean debugger knowledge base; keys illustrative |
| CROC102 | Resolution only | `resolution` below 10 km | recommendation, info | Knowledge base; suggestion illustrative |
| CROC103 | Resolution and space together | Box at the Strait of Gibraltar; `resolution` at or above 25 km | recommendation, info | Knowledge base; target and key illustrative |
| CROC104 | A computed recommendation that sets a model parameter (Python, [below](#index-setup-and-the-nwm-coverage)) | Latitude band 66.5N to 90N; model `mom6`; needs `resolution` | recommendation, info; suggests MOM_input `DT` | Knowledge base; DT formula illustrative |
| GEN001 | A predicate on the request itself, once per request (Python, [below](#gen001)) | Product `["*"]`; needs `request_km2` in the context | caveat, info | Design research |
| BIO001 | Occurrence-record sampling bias, with a custom facet | Box over Amazonia; up to 1999; `gbif`; `basis_of_record` | caveat, warning | Illustrative |
| UAS001 | A geozone for uncrewed aircraft systems (UAS, drones): recurring months and a second axis | Small polygon; March to August every year; `altitude_agl` 0 to 120 m; activity `uas` | caveat, severe | Fictional |
| EPI001 | An epidemiological surveillance gap across the antimeridian, in two periods, for a fictional feed of influenza-like illness (ILI) counts | Box from 170E to 170W; two periods in 2021 | caveat, warning | Fictional |
| `nwm_retro` | Coverage declared on a product, over object ids (Python, [below](#index-setup-and-the-nwm-coverage)) | HydroLAKES ids of NWM lakes; 1979-02-01 to 2023-01-31 | coverage, severe (QE001, QE002) | Design research |

Notes on individual records:

- **CRU003 and CRU004 (lifecycle).** CRU003 records the concern as first stated: South African precipitation is climatology. The data did not support it: in the South Africa box the share of land cells with `stn = 0` stayed at or below 10% in every year checked, while the mean station count fell from 8.0 to about 3.5. CRU003 is kept for history with `status: deprecated`, a `withdrawn` timestamp and an `x_withdrawn_reason`, and CRU004 states what the data support and lists CRU003 in `supersedes`. Either field alone would stop CRU003 matching; both are used because `withdrawn` says the statement was wrong and `supersedes` says what replaces it.
- **ERA5-001 (versions).** The rule lists the exact version `ERA5`, so a caller using `ERA5.1` gets no finding. It constrains no variable, so it also fires for ERA5 precipitation in 2000 to 2006, which over-warns (Q26 in [decisions.md](../decisions.md#geometry-and-time)).
- **ERA5-024 (polar cap).** On the wire a cap is a polygon whose top edge runs along latitude 90 from 180 to -180, a valid planar polygon any GeoJSON reader draws correctly. The loader reads its two full-turn edges as written, so it normalises to the cap (section [6.2](../../design.md#62-canonical-representation-and-normalisation), fixture 22). The loader also accepts a ring around the pole without that edge and closes it.
- **EPI001 (antimeridian).** The box `{west: 170, width: 20}` covers 170E to 170W; written naively as a shapely box from -170 to 170 it would be 340 degrees wide. Its `time` member gives the overall extent and `periods` lists the two gaps.
- **UAS001 (geozone).** The source's restriction type, `REQ_AUTHORIZATION` from the ED-318 vocabulary, is kept in `source_severity`. `action` is unset, because that vocabulary describes data use. Recurrence holds months only, so ED-318's weekday and hour windows cannot be expressed (Q22 in [decisions.md](../decisions.md#geometry-and-time)).

## Grounding of the model-parameter examples

- **CROC101 to CROC104 (grounding).** The ocean debugger knowledge base (expert interviews, paraphrased; queried again while revising this document) supports their messages: the time step has to be set from the smallest grid cells in the domain, and at higher latitudes a polar projection usually makes more sense (CROC104's `DT` and CROC101's `crs`); sea ice becomes a factor when a domain extends far north, chiefly its seasonal formation and retreat and its advection by currents; about 1/10 degree is generally considered eddy-resolving, and finer grids may conflict with parameterizations designed for coarser resolution; the Strait of Gibraltar is under 50 km wide and cannot be closed in a coarse model, because it is the Mediterranean's only exchange with the Atlantic. The keys `ice_component`, `THICKNESSDIFFUSE` and `strait_of_gibraltar` are illustrative (the knowledge base returned no advice for `THICKNESSDIFFUSE`), and so is CROC104's formula: the knowledge base says to set the time step from the smallest cells but gives no coefficient. The `crs` suggestion is grounded in mom6_forge, whose `Grid.from_projection` builds polar stereographic grids such as EPSG:3995 and, according to its docstring, keeps grid metrics accurate at high latitudes. The thresholds 66.5N, 10 km and 25 km are author choices.

## Index setup and the NWM coverage

The extra axis and facets are declared on the Index. CRU002 (the simple form in [usage.py](../usage.py)), GEN001 ([below](#gen001)) and CROC104 (below) are registered on the same Index.

```python
import queryearth as qe
from queryearth import space as sp

index = qe.Index(
    "examples",
    axes=[
        qe.Axis("resolution", "km", "horizontal grid spacing"),
        qe.Axis("altitude_agl", "m", "height above ground level"),
    ],
    facets=qe.Index.FACETS + ("activity", "basis_of_record"),
)
index.load_pack("docs/reference/examples")  # pack.toml + rules.geojson

# NWM retrospective v3.0 lake output covers a set of lakes, not an area.
# hylak_ids: HydroLAKES ids of the lakes that the 5,782 NWM lake features
# represent, from a crosswalk the adapter builds once (illustrative).
index.add_product(
    qe.Product(
        name="nwm_retro",
        aliases=("NWM", "NWM v3.0"),
        variables=("inflow", "outflow", "water_sfc_elev"),
        coverage=qe.Coverage(
            space=sp.features(hylak_ids, "hydrolakes"),
            time=qe.interval("1979-02-01", "2023-01-31"),
        ),
        resolution=(1.0, "km"),
        version="3.0",
    )
)


@index.rule(
    "CROC104",
    kind="recommendation",
    severity=qe.Severity.INFO,
    space=sp.lat_band(66.5, 90.0),
    facets={"model": "mom6"},
    axes={"resolution": {"gt": 0.0}},  # needs the spacing: conditional without it
)
def arctic_time_step(query, match):
    """High-latitude domain: set the time step from the smallest cells"""
    finest_km = match.axes["resolution"].lo  # finest spacing the query gave
    seconds = 30.0 * finest_km  # illustrative: 30 s per km, an author choice
    why = "Set DT from the finest cells (illustrative scaling, not MOM6 guidance)."
    return {"suggestions": (qe.Suggestion("MOM_input", "DT", seconds, why),)}
```

CROC104 is the parameter-style answer to the Arctic example of section [1.1](../../design.md#11-three-motivating-examples). Its scope is CROC101's, plus the axis bound `resolution > 0`, which every real spacing meets but which makes the rule conditional on `resolution` when a query leaves the spacing out, so `check()` never runs without it. It reads the finest spacing from the match and suggests the MOM_input parameter `DT`: for a domain whose finest cells are 8 km, `{"target": "MOM_input", "key": "DT", "value": 240.0}`. The coefficient of 30 seconds per km is an illustrative author choice; a real rule would compute the time step from the model's stability limit for its fastest waves.

NWM's retrospective lake output is a set of 5,782 lake features (from the CONUS `lakeout.zarr` metadata, design research), not an area, so its coverage here is a set of object ids. The hourly time axis has 385,704 steps from 1979-02-01, so its last step is 2023-01-31 23:00. A caller queries NWM with `sp.features([hylak_id], "hydrolakes")`, and a lake NWM does not represent produces QE001 (SEVERE, `do_not_use`, `area_fraction` 1.0) before any download. GLHE queries with lake polygons instead, so its adapter uses the callable coverage of section [15.2](../../design.md#152-glhe); both declarations are valid.

## GEN001

GEN001 is a function rule (section [12.2](../../design.md#122-computed-rules)): it compares the caller's own area, passed in the context, with the support the query describes, once per request.

```python
@index.rule(
    "GEN001",
    kind="caveat",
    severity=qe.Severity.INFO,
    facets={"product": ["*"]},  # one finding per request, on that request's support
    requires=["request_km2"],
)
def coarse_support(query, match):
    """The request is much smaller than the product cells that represent it"""
    if query.space is None or not query.space.area_km2:
        return None
    ratio = query.context["request_km2"] / query.space.area_km2
    if ratio < 0.1:  # threshold is an author choice
        return {"details": {"request_to_support": ratio}}
    return None
```

In the research prototype, a 6.7 km² lake was compared with a CRU TS cell of about 2,786 km² at 25.7S, a ratio of about 0.0024.

## CRU002, graded form

The graded form of CRU002 (section [12.4](../../design.md#124-raster-derived-rules-cru002)) reports SEVERE for years of climatology and WARNING for thin years, with hysteresis between them. It replaces the simple form rather than joining it: the five queries below assume the simple form of [usage.py](../usage.py), and registering both on one Index raises `DuplicateCodeError`.

```python
import numpy as np

import queryearth as qe

CRU_PRE = {"product": ["cru_ts"], "variable": ["pre"]}


def year_runs(years: list[int]) -> tuple[tuple[str, str], ...]:
    """Merge years into closed wire intervals: [2001, 2002, 2005] gives two runs."""
    runs: list[list[int]] = []
    for year in sorted(years):
        if runs and year == runs[-1][1] + 1:
            runs[-1][1] = year
        else:
            runs.append([year, year])
    return tuple((f"{a:04d}-01-01", f"{b:04d}-12-31") for a, b in runs)


class CruStations(
    qe.ComputedRule,
    code="CRU002",
    index=index,  # instead of the simple form, not alongside it
    facets=CRU_PRE,
    requires=["cru_ts.stn", "cru_ts.year"],
):
    """CRU TS precipitation from few or no stations

    stn = 0 means the value is the 1961-1990 climatology (Harris et al. 2020).
    """

    ENTER, LEAVE = 6, 3  # months per year with stn = 0 to start and to end a run
    THIN = 2.0  # mean stations per cell at or below which a year counts as thin

    def check(self, query, match):
        stn = query.context["cru_ts.stn"]  # (month, cell): the land cells used
        year = query.context["cru_ts.year"]  # (month,): calendar year of each month
        flagged, clim, thin = False, [], []
        for y in np.unique(year):
            months = stn[year == y]
            zero = float((months == 0).sum(axis=0).mean())  # stn = 0 months per cell
            flagged = zero >= self.ENTER or (flagged and zero > self.LEAVE)
            if flagged:
                clim.append(int(y))
            elif float(np.nanmean(months)) <= self.THIN:
                thin.append(int(y))
        if not clim and not thin:
            return None
        return {  # one finding per query, graded by the worst year
            "severity": qe.Severity.SEVERE if clim else qe.Severity.WARNING,
            "time_overlap": year_runs(clim + thin),
            "details": {"climatology_years": clim, "thin_years": thin},
        }
```

The rule returns a single finding with the worst grade and puts the years of each grade in `details`, which keeps one finding per rule per request. Its thresholds are applied to the mean over the cells the request uses, while the research figures were per cell. [usage.py](../usage.py) shows a simpler CRU002 (any `stn = 0` month is SEVERE) that the examples also use.

## Five example queries

```python
import numpy as np

y2013_2022 = qe.interval("2013-01-01", "2022-12-31")
cru = {"product": "CRUTS", "variable": "pre"}  # CRUTS is an alias of cru_ts

# 1. A lake and a period (GLHE): the engine derives the CRU TS cells from its grid.
kariba = sp.polygon(kariba_geojson)  # HydroLAKES outline
# stn: station counts for the support cells and months; request_km2 for GEN001
ctx = {"cru_ts.stn": stn, "request_km2": kariba.area_km2}
q1 = index.query(
    space=kariba,
    time=y2013_2022,
    requests=[qe.Request("CRUTS", variables=("pre",))],  # CRUTS: alias of cru_ts
    context=ctx,
    label="Kariba",
)

# 2. An Arctic MOM6 domain (CrocoDash): polar stereographic, +-1500 km, pole inside.
ring = sp.from_grid(qlon, qlat)  # cell corners
q2 = index.query(
    space=ring,
    time=qe.interval("2020-01-01", "2020-12-31"),
    axes={"resolution": (8.0, 12.0)},  # illustrative; from sp.resolution_of()
    facets={"model": "mom6"},
    requests=[
        qe.Request("glorys", variables=("thetao", "so")),
        qe.Request("era5", variables=("t2m", "skt")),  # illustrative variables
    ],
    label="arctic-demo",
    include_conditional=True,
)

# 3. Resolution only.
q3 = index.query(axes={"resolution": 8.0}, include_conditional=True)

# 4. Bulk: every 0.5 degree cell centre, weighted by cell area.
glon, glat = np.meshgrid(np.arange(-179.75, 180, 0.5), np.arange(-89.75, 90, 0.5))
lon, lat = glon.ravel(), glat.ravel()
q4 = index.query_points(lon, lat, weights=np.cos(np.radians(lat)), facets=cru)
weak = q4.any(qe.Severity.WARNING)  # q4.masks[("cru_ts", "CRU001")] is one mask

# 5. Which product has the fewest known concerns for precipitation at this lake?
ranked = index.suitable(
    qe.Query(space=kariba, time=y2013_2022, context={"cru_ts.stn": stn}),
    variable="pre",
)
```

**Query 1: Lake Kariba, 2013 to 2022, one request for `CRUTS` with variable `pre`.** The query passes the lake outline, and the engine derives the support, the CRU TS cells the lake touches, from the product's grid. Every finding below has `product` `cru_ts` and `request` 0.

| Code | Kind, severity | Result | What the finding records |
|---|---|---|---|
| CRU002 | caveat, SEVERE | definite | `details.stn0_fraction`: about 0.30 at the cell at the lake's location (design research, 2013 to 2022); the support as a whole may differ |
| CRU001 | caveat, WARNING | definite | `assumed=("space", "version")`: the support from the grid and version 4.07; `area_fraction` 1.0; `time_overlap` 2013-01-01 to 2022-12-31; `time_fraction` 1.0 |
| GEN001 | caveat, INFO | definite only if the lake covers less than a tenth of its support | `details.request_to_support` |

No finding: CRU004 (Kariba lies north of the box's 22S edge), CRU003 (withdrawn), the ERA5 and GLORYS rules (other products), QE001 and QE002 (2013 to 2022 is inside CRU TS coverage). CROC102, evaluated on the base query, is conditional on `resolution` and hidden; CROC101, CROC103 and CROC104 do not reach the lake.

**Query 2: an Arctic MOM6 domain in 2020**, a polar stereographic square of ±1,500 km around the North Pole with grid spacing of 8 to 12 km (illustrative), model `mom6`, and two requests: `glorys` with `thetao` and `so` (request 0) and `era5` with `t2m` and `skt` (request 1), run with `include_conditional=True`. This is the query shape of CrocoDash's adapter (section [15.1](../../design.md#151-crocodash)).

| Code | Kind, severity | Result | What the finding records |
|---|---|---|---|
| CROC101 | recommendation, INFO | definite, base query | `area_fraction` 1.0, since the whole square lies north of 70.6N; suggestions `ice_component = CICE` and `crs = EPSG:3995` |
| CROC104 | recommendation, INFO | definite, base query | `area_fraction` 1.0; `axes`: resolution [8, 12]; suggestion `DT = 240.0` seconds from the finest spacing of 8 km (illustrative formula) |
| CROC102 | recommendation, INFO | definite, base query | `axes`: resolution [8, 10), so only the finest part of the grid is below 10 km; suggestion `THICKNESSDIFFUSE = false` (illustrative) |
| ERA5-024 | caveat, WARNING | definite, request 1 (`era5`) | `area_fraction` 1.0; `time_overlap` 2020-01-01 to 2020-02-29 and 2020-12-01 to 2020-12-31; `matched_facets` `{"product": ("era5",), "variable": ("skt",)}` |
| GEN001 | caveat, INFO | conditional on `context:request_km2`, once for each request | the rule's own fields only |

No finding: ERA5-001 (2020 is outside 2000 to 2006), GLORYS001 (outside 1993 to 2003), CROC103 (no overlap with the Gibraltar box), the CRU rules (other product), QE001 and QE002 (2020 is inside GLORYS and ERA5 coverage). A request for `era5` without `skt` would give no ERA5-024 finding, and one without variables would make it conditional on `variable`.

**Query 3: resolution 8 km and nothing else, with `include_conditional=True`.**

| Result | Codes | `conditional_on` |
|---|---|---|
| Definite | CROC102 | none; `axes` records resolution [8, 8] |
| Conditional | CROC101, CROC104 | space, model |
| | ERA5-001 | time, product, version |
| | GLORYS001 | time, product, variable |
| | CRU001, CRU004 | space, time, product, variable, version |
| | ERA5-014, ERA5-023, ERA5-024, EPI001 | space, time, product, variable |
| | BIO001 | space, time, product, basis_of_record |
| | UAS001 | space, time, altitude_agl, activity |
| | CRU002 | product, variable, context:cru_ts.stn |
| | GEN001 | product, context:request_km2 |
| No finding | CROC103 (8 km is not at or above 25 km); CRU003 (withdrawn); QE001 and QE002 (no product named) | |

Recurrence counts as a time constraint, so ERA5-024 and UAS001 are conditional on `time` although their `time` member is null.

**Query 4: every 0.5 degree cell centre (259,200 points), weighted by the cosine of latitude, product `CRUTS`, variable `pre`.** The facet shorthand becomes one request for `cru_ts`, and the results are keyed by `(product, code)`, for example `("cru_ts", "CRU001")`. No time is given, so the product fills both time (its coverage, 1901 to 2022) and version; the points themselves are the support, so the grid is not used. CRU001 is definite with `assumed=("time", "version")`, a mask of the points inside the eight AR6 African regions and `time_overlap` 2000-01-01 to 2022-12-31. CRU004 is definite with the same `assumed`, a mask of the 858 cell centres in its box (732 of them land in CRU TS, design research) and `time_overlap` 2010-01-01 to 2022-12-31. CRU002 and GEN001 are listed in `q4.skipped`, because they have no `mask()` hook. `q4.any(qe.Severity.WARNING)` is the union of the CRU001 and CRU004 masks. `min_overlap` does not apply here (section [9.3](../../design.md#93-the-bulk-path-query_points)), so CRU001 keeps its mask although the African regions hold a small share of the global weight.

**Query 5: `suitable()` for precipitation at Lake Kariba, 2013 to 2022,** with the lake outline as the space (section [10.1](../../design.md#101-contract)). `cru_ts` is judged on the CRU TS cells the lake touches, derived from its grid, and `era5`, which declares no grid, on the outline. `era5` ranks first with a worst-severity term of 0 and no findings, which means only that no registered rule matched. `cru_ts` ranks second with worst severity 40, from CRU002 (SEVERE, because the station counts are passed in the context) and CRU001 (WARNING). `glorys`, `gbif`, `demo_ili` and `nwm_retro` are not ranked, because they do not offer `pre`.
