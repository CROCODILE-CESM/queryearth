# Background and evidence

This file holds the evidence behind [design.md](../design.md): the full prior-art survey, each requirement with its evidence, and the measurements the design cites. Section numbers refer to design.md. "Design research" means the research that preceded the first draft; "this document's benchmark" means measurements made while drafting and revising, with the set-up given under [Engine measurements](#engine-measurements).

## Prior art in full

The design research surveyed generic matchers that find records by space and time, caveat and errata services that hold real content but no geometry, and standards whose vocabulary fits. In short: the matcher exists many times over, and caveat content exists without geometry, but no tool combines them. The closest structural analogue is OSV, a format for software vulnerability advisories (section [2](../design.md#2-prior-art-and-what-we-borrow)).

### Generic space and time matchers

| Tool | What it does | Why it is not the core |
|---|---|---|
| The library named in section [2](../design.md#2-prior-art-and-what-we-borrow) | A library of time-bounded shapes with a linear-scan intersection filter. | The author prefers not to depend on or contribute to it. queryearth is written without consulting its source. |
| cql2-rs (Python package `cql2`) | Evaluates CQL2 (OGC Common Query Language) expressions, including `s_intersects` and `t_intersects`, against one JSON record at a time. A 3.9 MB Rust wheel with no Python dependencies. | A predicate evaluator, not a registry: no index, no record schema, no scoping by product or version. Seam and pole behaviour unverified. A good optional input adapter later (section [17](../design.md#17-non-goals-for-v1-and-upgrade-paths)). |
| rustac with stac-geoparquet | Searches a local stac-geoparquet file by geometry, datetime and CQL2 filter through a bundled DuckDB. | A 32.4 MB wheel; records must be STAC Items with links, assets and version boilerplate; no outcome model; GeoParquet's bounding-box covering does not support antimeridian-crossing geometries. |
| geopandas with its spatial index | About ten lines: a spatial-index query, then a time mask (620 µs per query at 100,000 records, design research). | About 72 MB of wheels and 211 to 255 ms of import time; no schema; no seam or pole handling. |
| pygeofilter | Parses CQL2 and evaluates it with several backends. | In version 0.4.0 the native backend evaluates generated code per record and the geopandas backend has no temporal filters; its parser dependency, lark, took 380 ms to import. |
| Astronomy coverage indexes: IVOA MOC 2.0 and ST-MOC, the CDS MocServer, stmoc-pp | Store sky (and space-time) coverages as ranges of HEALPix cells, an equal-area pixelisation of the sphere. CDS reports finding which of about 15,000 datasets cover a region in 5 to 44 ms. | A coverage carries an id but no metadata, and time has no civil calendars such as `noleap` or `360_day`. The cell-index idea is the upgrade path for very large derived layers (section [17](../design.md#17-non-goals-for-v1-and-upgrade-paths)). |

Speed does not separate these options at realistic sizes: with 10,000 rules, a pure-Python linear scan answers a point, lake or continent query in 0.49 to 10 ms, and a shapely STRtree in 0.06 to 4.5 ms (design research; section [13](../design.md#13-performance-targets)).

### Caveat and errata services without geometry

| Source | What it holds | How issues are scoped |
|---|---|---|
| ESGF errata service for CMIP6 (Earth System Grid Federation; Coupled Model Intercomparison Project phase 6) | 468 machine-readable issues with a severity (low to critical) and a status, behind a JSON API | Dataset-id facets, file-path globs and version; region and period only in free text |
| ISIMIP caveats API (Inter-Sectoral Impact Model Intercomparison Project) | 76 caveats, each with an action: can be used, use with caution, do not use, or replaced | Facets and versions; region and period only as labels such as "global" |
| ECMWF's ERA5 known issues | 31 numbered issues, in prose | About 6 name a region and a period, 5 only a region or terrain, 7 are global and time-limited, 13 have neither |
| NCAR Climate Data Guide | About 230 dataset pages of strengths and limitations | Prose |
| NASA CMR collection metadata | A "known issues" content type | The whole collection, in free text |

These sources agree on their fields (severity, status, action, affected product and version, citations) and none has geometry or data time. Two lessons come with them. Most of OSV's value lies in its maintained database and integrations, not its schema code. GeoViQua, an EU project (2011 to 2014), built quality-aware catalogue search that faded once funding ended. Both say content should live apart from the engine, in maintained repositories, and both warn that an engine without maintained content does not get adopted. queryearth ships no content by the author's decision, so its usefulness to anyone depends on someone writing and maintaining rules (section [17](../design.md#17-non-goals-for-v1-and-upgrade-paths)).

### Standards we borrow from

| Source | What we take | What we leave |
|---|---|---|
| OSV (Open Source Vulnerability format) | Affected products with version ranges (`introduced`, `fixed`, `last_affected`, exact `versions`); `withdrawn`; `aliases`; typed references; reviewed records kept in separate repositories | Package ecosystems and URLs; semver and git range types; CVSS vectors; the hosted service |
| CAP 1.2 (Common Alerting Protocol) | Severity kept separate from certainty (our `confidence`, four of CAP's five values); headline, description and instruction (our `title`, `message`, `instruction`); areas named by reference (`region_ref`); updates by reference (`supersedes`) | XML and latitude-first coordinates; `effective` and `expires` (when an alert is in force, not which data it concerns); urgency; the value "unlikely"; the five-level severity scale, kept verbatim in `source_severity` |
| EUROCAE ED-318 (GeoJSON format for drone geozones) | A FeatureCollection with a metadata header, including technical limitations; no time means always; lists of periods or areas are unions | Aviation fields; weekday, hour and sunrise schedules, reduced to a list of months |
| OGC JSON-FG 1.0 (Features and Geometries JSON) | The `time` member (date, timestamp, or interval with `".."` for an open end); `coordRefSys`; `place`, which must be null | `place` geometries in other coordinate systems, 3D types, coordinate systems other than CRS84 |
| OGC CQL2 1.0 | Matching semantics: space intersects and time intersects, with closed intervals | CQL2 as an input language (v1 non-goal) |
| ISO 19157 (geographic data quality) | A quality statement scoped by a geographic, temporal and vertical extent; evidence as method, measure and result | The XML encoding and the full taxonomy |
| RFC 7946 (GeoJSON) | Longitude-latitude on WGS84; straight edges in that space; polygons cut at the antimeridian; counterclockwise exteriors; null geometry | Altitude |
| xclim | One switch between log, warn, raise and ignore | xclim itself; our switch is a context-local `Policy` |
| Smaller borrowings | Prefixed codes as in ruff and pylint, so `[CRU001]` can be filtered with `python -W`; an explicit registry with an application default, as in pint; named containment modes, as in H3; the fallback fields `time_start` and `time_end`, which GDAL 3.12 exposes for JSON-FG; CrocoDash's `__init_subclass__` registration, with duplicates made an error | Each library itself |

Because packs are plain GeoJSON with the JSON-FG `time` member, other tools can open them: the design research checked that GDAL 3.12 reads such a file as JSON-FG and exposes the time as fields, so QGIS and geopandas can display packs without queryearth.

### Why a small matcher of our own

- **Semantics.** queryearth needs behaviour no single tool provides: conditional matches when a query omits a dimension a rule constrains; closed-set boundaries, so grid points on a region's edge match; antimeridian normalisation enforced at load; overlap measures in area, time and on each axis; exact integer time keys; hard errors for unknown names. Wrapping a generic matcher would still mean writing all of this, and the matching that remains is small. The design research estimated the whole package at 1,000 to 2,000 lines, most of it outside the matcher.
- **Footprint.** The core depends on shapely and numpy, which both first consumers already install. The alternatives add tens of megabytes of wheels or hundreds of milliseconds of import time.
- **Preference.** The author prefers not to depend on or contribute to the library named in section [2](../design.md#2-prior-art-and-what-we-borrow). queryearth is written clean-room: that library's source is not read, copied or paraphrased, and it is cited here only as prior art.
- **Speed** does not argue for reuse: a plain list or a shapely STRtree is fast enough (section [13](../design.md#13-performance-targets)).

## Requirements with their evidence

The author set six requirements (R1 to R6) and added two after the first review (R7 and R8). The design research surfaced eight more (R9 to R16). Each has a verdict (sound, premature, or needs refinement), the evidence behind it, and the sections that meet it. Sections [3](../design.md#3-requirements) and [19](../design.md#19-requirement-and-decision-checklist) of design.md map them, and the author's decisions, to sections and checks.

| # | Requirement | Verdict | Evidence | Met in |
|---|---|---|---|---|
| R1 | Point and polygon queries | Sound, but incomplete | Cyclic domains have no bounding box; polar domains enclose a pole their boundary never reaches; NWM serves 5,782 lakes identified by id; a model grid is cell centres weighted by area. Most of all, a query must describe the support: under cell-centre masking a lake of about 150 km² selects no CRU TS cell, the root of GLHE's `polygon.buffer(0.5)` retry. | 4.4, 4.12, 8 |
| R2 | Minimal dependencies, standard library wherever possible | Sound for loading, time and emission; too strict for geometry | Overlap fractions, closed-set edges, holes and repair need a geometry engine. Decision: shapely 2.1 or later (for `orient_polygons`) and numpy are required (imports about 70-80 ms and 40-65 ms, against 211-255 ms for geopandas). Python 3.11 or later with no upper limit (author decision, 2026-10-12): CrocoDash pins Python below 3.12, which sets the floor, and nothing in the design needs a ceiling. | 4.11, 13 |
| R3 | Very fast querying | Premature for single queries; real for bulk grids and loading | At 10,000 rules every method answers in 10 ms or less. A million grid points against 10,000 rules take about 80 s in pure Python (extrapolated) and 2.5 s with shapely. A realistic pack loads in about 46 ms, which matters for stateless servers. Both workloads are in v1 (author decision). | 9, 13 |
| R4 | An easy interface layer | Sound; this is where the value lies | CrocoDash reports through `logger.warning` (7 call sites; 61 logger calls in all) and `print` (53) and never warns; GLHE uses file loggers and an event bus; the default warning filter hides repeats in a loop; `warnings.catch_warnings` is not thread-safe before Python 3.14. Findings must be the API. | 4.9, 11 |
| R5 | Rule objects that are quick to write | Sound | Two tiers: data-only packs for people who do not program, Python rules for programmers. Keeps CrocoDash's `__init_subclass__` pattern with three fixes. Unverified: whether geojson.io keeps the JSON-FG `time` member, and how long a rule takes to write. | 5, 12 |
| R6 | A user interface layer | Premature | The JSON Schema, geojson.io for drawing and GDAL or QGIS for viewing cover writing and review in v1. | 17 |
| R7 | Extra dimensions such as resolution (added) | Sound and essential | Of ERA5's 31 known issues, about 6 name a region and a period, 5 only a region or terrain, 7 are global and time-limited, and 13 have neither. Every dimension is optional on both sides; "resolution only" is a complete query. | 4.2, 4.3, 4.6, 4.7 |
| R8 | Recommendation outcomes (added) | Sound | A rule must be able to say "consider setting X", not only "beware". Suggestions are structured and never interpreted by the engine. | 4.9, 11.3, 12, 16 |
| R9 | Provenance and versioning | Surfaced by research | Product versions are often not PEP 440 (`ERA5T`, `ERA5.1`, `GEBCO_2024`) and change meaning (the ERA5 2000-2006 rerun as ERA5.1; CRU TS 4.09 dropping cohort selection for precipitation; GEBCO's TID 44 meaning different things in 2019 and 2026). Unknown product names must be errors. | 4.7, 4.8, 5.2, 12.3 |
| R10 | Overlap measures | Surfaced | A large domain that clips a regional caveat differs from a lake inside it. The closed-form spherical area matched pyproj to within 5e-9. | 4.3, 4.4, 4.6, 6.3, 7.2 |
| R11 | Computed rules | Surfaced | Object predicates and raster-derived rules, with graded severity, no silent skips, and a recorded time-aggregation rule: raw monthly `stn = 0` flags form 936,068 runs with a median length of one month, reduced to 78,068 by a 6-of-12-months rule. | 4.10, 12 |
| R12 | Coverage, and the inverse query built on it | Surfaced; inverse query in v1 by author decision | Footprints are the commonest concern; GLHE learns only inside its NWM accessor that NWM covers the contiguous US alone. Coverage has the opposite polarity to a caveat. | 4.9, 10 |
| R13 | Two time axes | Surfaced | Data time (which years are affected) differs from record time (when the rule was written or withdrawn); alerting standards use the time a warning is in force. | 7.2 |
| R14 | Calendars and long time ranges | Surfaced | numpy `datetime64[ns]` turns 1600-01-01 into 2184-07-20 silently; cftime raises across calendars; `datetime` covers years 1 to 9999 only; mid-month time stamps miss short queries. | 7, 8.3 |
| R15 | Warning fatigue | Surfaced | A "request smaller than a product cell" rule fires for nearly every lake (a 6.7 km² lake against a CRU TS cell of about 2,786 km²). Running a draft pack against 1,000 lakes and about 10 CrocoDash domains, counting findings per query, is an acceptance test (section [15.3](../design.md#153-warning-fatigue-trial)). | 11, 15.3 |
| R16 | A shared correctness fixture suite | Surfaced | The dangerous failures pass validity checks: the Fiji box, edge points, the inexact longitude wrap, the polar domain (section [6.1](../design.md#61-motivating-failures)). Every implementation and adapter must pass the suite. | 6, 7, 14 |

## Motivating examples in full

Sections [1](../design.md#1-problem-and-scope) and [1.1](../design.md#11-three-motivating-examples) in full; the numbers behind the CRU TS example are in the next section.

queryearth answers one question. Given **where** (a point or a polygon), **when** (a time range) and **anything else that matters** (axes such as grid resolution, and facets such as product and variable), which registered rules apply? How much of the request does each one cover, and what does it tell the caller to watch out for or to do?

**A recommendation: an Arctic CrocoDash domain (CROC101 and CROC104).** CrocoDash sets up regional ocean model cases for MOM6, the ocean model of CESM. For such a domain the rule should say "set parameter X to Y", not only "beware". The expert-interview knowledge base behind the Regional Ocean Debugger (a CROCODILE project tool for diagnosing regional MOM6 runs) gives two pieces of advice that fit. First, the time step has to be set from the smallest grid cells in the domain, and at high latitudes a polar projection usually makes more sense. Second, a domain that extends far north brings sea ice into play. So a computed rule, CROC104, scoped to the latitude band 66.5N to 90N and to the facet `model = mom6`, returns the MOM6 parameter suggestion `{"target": "MOM_input", "key": "DT", "value": <seconds>}`, with the value computed from the finest grid spacing. A record, CROC101, with the same scope suggests an active sea-ice component and a polar-stereographic grid. CrocoDash can log these suggestions, record them in the case's `config.json`, or apply them. The DT formula and the setting names are illustrative (sections [16.1](../design.md#161-the-example-pack-and-its-rules) and [16.2](../design.md#162-croc104-a-computed-recommendation)). The space handling must be right for the domains CrocoDash builds that cross the antimeridian, and must never silently misread a polar-stereographic grid whose boundary encloses the North Pole without reaching it.

**A rule with no area or time (CROC102).** The same knowledge base, paraphrased, says that a grid spacing of about 1/10 degree is generally considered eddy-resolving, and that finer grids may conflict with parameterizations designed for coarser resolutions. The rule "below 10 km grid spacing, revisit coarse-grid parameterizations" depends only on resolution, so a query that gives nothing but `resolution = 8 km` must be complete and must return it. Rules like this are common: about 13 of ECMWF's 31 ERA5 known issues have no area or time scope at all (tally made during the design research). The 66.5N and 10 km thresholds are author choices.

## CRU TS station counts

The design research computed these numbers from GLHE's public `CRUTS.zarr` (CRU TS 4.07). They motivate CRU001 and CRU002 (sections [1.1](../design.md#11-three-motivating-examples) and [12.4](../design.md#124-raster-derived-rules-cru002)).

**A caveat: CRU TS precipitation over Africa (CRU001, and the computed rule CRU002).** CRU TS is a gridded monthly climate dataset interpolated from weather stations. Where no station lies within the correlation-decay distance (450 km for precipitation), CRU TS writes the 1961-1990 climatology for that cell and month and records a station count `stn` of 0. The design research computed this from GLHE's public copy of CRU TS 4.07. Over the eight IPCC AR6 African land regions, the share of land cells with `stn = 0` rose from 6.8% in 1973 to 34% in 2022, and the mean station count fell from 6.3 to 2.2. For 2011 to 2022, all 76,576 African groups of one cell and one calendar month with at least two `stn = 0` years held identical values, so those cells carry no year-to-year signal. Two lessons follow:

- The faithful check is computed from `stn` for the cells and months actually used (CRU002). The static record CRU001 is the coarse fallback.
- The author's original example, South Africa, is gradual thinning rather than climatology fill: the mean station count fell from about 8 to about 3.5, while cells with `stn = 0` stayed at 2 to 10%. Severity must therefore be graded.

Some rules are best computed from a quality field the product itself ships. CRU TS ships `stn`, the number of stations within the correlation-decay distance behind each monthly value, capped at 8; `stn = 0` means the value is the 1961-1990 climatology (Harris et al. 2020). The design research confirmed this in GLHE's public `CRUTS.zarr`: a central Democratic Republic of the Congo cell has January precipitation of exactly 161.3 mm in every year from 2013 to 2022. In v1 such rules run live in the consumer's adapter, which passes the data it already holds in `Query.context`. Two findings from the data shape the rule:

- **Graded severity.** Climatology fill and station thinning are different problems. In a box over South Africa, the mean station count fell from 8.0 (1930s to 1990s) to about 3.5 (2010s) while the share of cells with `stn = 0` stayed at 2 to 10%. CRU002 reports `SEVERE` for years of climatology and `WARNING` for years with two stations or fewer on average.
- **Hysteresis.** Raw monthly flags flicker: from 1901 to 2022 there are 936,068 runs of `stn = 0`, with a median length of one month. Flagging a year only when at least 6 of its 12 months have `stn = 0` reduced this to 78,068 (cell, year range) runs. CRU002 also uses a lower threshold for leaving the flagged state, so one marginal year does not split a run; that exit threshold (3 months) is an author choice not yet tested on the data. Recent years are back-filled in later releases and box shares swing from year to year (in July, a South Africa box fell from 0.10 in 2020 to 0.01 in 2021), so flags for the latest years are provisional.

**Upgrade path: compiled cell sets.** When a consumer does not hold the data, or a bulk query needs the rule everywhere, the same rule can be compiled offline into cell sets on the product's own grid, with runs of years, keyed by product, version, variable and rule. For all of CRU TS precipitation from 1901 to 2022 this is about 78,000 rows, or 1 to 2 MB, and a numpy lookup on the grid cost about 8 ns per point against 0.8 µs with an STRtree over the mask turned into polygons (design research). Compiled layers need optional ingest dependencies (xarray, zarr, netCDF4), must be rebuilt for each product version (CRU TS 4.08 added cohort selection of stations and 4.09 dropped it for precipitation), and raise licensing questions if redistributed. A compiled layer is one more `RuleKind`, so consumers do not change (section [17](../design.md#17-non-goals-for-v1-and-upgrade-paths)).

## Geometry evidence

Each case was reproduced in memory during the design research and again while drafting (Python 3.11, shapely 2.1.2 with GEOS 3.13.1, pyproj 3.7.2, regionmask 0.13.0).

| Case | What goes wrong |
|---|---|
| A box over Fiji, written naively | The ring (170, -20), (-170, -20), (-170, -10), (170, -10) is meant as the 20 degree box from 170E to 170W. shapely reports it valid with an area of 3,400 square degrees: it is the other 340 degrees of longitude. It does not contain (175, -15) and does contain (0, -15); regionmask selects 13,600 cells of a 0.5 degree grid instead of 800. |
| A polar-stereographic domain | The outline of a square of plus or minus 1,500 km in EPSG:3995 (north polar stereographic), traced with 200 nodes, has vertex latitudes of only 70.65 to 76.26 degrees. Its naive longitude-latitude polygon intersects itself, and its convex hull does not contain the pole. Nothing in the vertex bounds says the domain covers the North Pole. |
| A region crossing 180, in regionmask | A region from 170E to 190E covers 800 cells of a 0.5 degree grid. With `wrap_lon=True` on a 0 to 360 grid, or `wrap_lon=False` on a -180 to 180 grid, regionmask selects 400. Half the region disappears without an error. |
| Edge meaning left undeclared | The box from -179 to 179 in longitude and -80 to 80 in latitude is almost the whole globe to shapely, but 0.55% of the Earth to pyproj's geodesic area, which joins vertices by the shortest great circle. |

## Time evidence

The usual time types fail in ways that matter for climate and model data (design research, numpy 2.4.6 and cftime 1.6.6, re-checked while drafting):

| Representation | Failure |
|---|---|
| numpy `datetime64[ns]` | Wraps silently outside 1677-09-22 to 2262-04-11: 1600-01-01 becomes 2184-07-20 and 3000-01-01 becomes 1830-11-23, with no warning even when warnings are errors |
| Python `datetime` | Years 1 to 9999 only, and only the proleptic Gregorian calendar |
| cftime | Comparing dates from two different calendars raises `TypeError` |
| Numeric offsets | 45000 "days since 1900-01-01" is 2023-03-17 in the standard calendar, 2023-04-16 in `noleap`, 2025-01-01 in `360_day` and 2022-12-14 in `all_leap` |

The design proposed comparing civil dates instead: the labels (year, month, day, hour, minute, second) as written. Each instant would become one integer:

```python
key = ((((year * 13 + month) * 32 + day) * 24 + hour) * 60 + minute) * 60 + second
```

This is a mixed-radix number whose digits stay below their bases, so it sorts exactly like the tuple, including negative years; that was checked on 200,000 random tuples with years from -30,000 to 30,000. Ordering needs no calendar: 30 February in a `360_day` calendar sorts between 29 February and 1 March. The arithmetic uses plain Python integers, and its range is far beyond any product. Version 0.0.1 keeps one calendar instead, the proleptic Gregorian, with integer-second keys (design.md section [7.1](../design.md#71-the-time-key-and-its-wire-format)); the civil key is an upgrade path (section [17](../design.md#17-non-goals-for-v1-and-upgrade-paths)).

## Engine measurements

Numbers labelled "this document's benchmark" were measured for this document, in memory, with Python 3.11.16, shapely 2.1.2 (GEOS 3.13.1) and numpy 2.4.6 on one core of an AMD EPYC 9555, the machine the design research used. The rule polygons are synthetic stars (10 to 200 vertices, radius log-uniform from 0.05 to 30 degrees), not real packs.

These figures are for the vectorised pipeline, which v0.0.1 removed (section [17](../design.md#17-non-goals-for-v1-and-upgrade-paths)). With N rules, stages 1 to 3 are O(N) numpy operations plus one `fnmatch` call per glob-pattern rule; stage 4 costs O(log P + c) for P normalised parts and c candidates; stage 6 is proportional to the vertex counts of each hit that neither shortcut resolves; no stage is worse than linear in N. A continent-sized query (a 30 degree radius star) against 10,000 rules with no facet pruning gave about 240 hits and took 51 to 57 ms, nearly all in polygon intersections; the "query covers rule" shortcut cut this to 47 ms with identical fractions. With 90% of rules scoped to one of ten products and the query naming none, it took 4.7 ms (this document's benchmark). An index beyond the STRtree pays off only past about 50,000 rules (section [17](../design.md#17-non-goals-for-v1-and-upgrade-paths)).

Loading matters more than query speed for short-lived processes, such as stateless servers that reload on every call. For 10,000 rules with 1.05 million vertices in 45.6 MB of GeoJSON, the design research measured 823 ms for `json.loads`, 552 ms for `shapely.from_geojson` and 45 ms for computing envelopes in pure Python. Building geometries takes most of the time after parsing, so the design built them lazily, in the steps listed in [decisions.md](decisions.md#lazy-loading-in-full); v0.0.1 builds every geometry at load (section [9.2](../design.md#92-loading-packs)). Eager and lazy loads compare as follows:

| Pack (generated in memory; this document's benchmark) | Eager: build every geometry | Lazy: envelopes only |
|---|---|---|
| 100 rules × 500 vertices, 1.3 MB | 43 ms (`json.loads` 6 ms) | 9.0 ms |
| 10,000 rules, 10 to 200 vertices, 28.9 MB | 1.21 s (`json.loads` 0.65 s) | 0.67 s (`json.loads` 0.60 s) |

These loads exclude property validation, which has not been measured. The trade-off of a lazy load is that a self-intersecting polygon is repaired at first use rather than at load; the repair is deterministic, so findings do not change, but a pack linter in continuous integration should build every geometry eagerly.

**Why tiles.** The obvious version, which v0.0.1 uses (section [9.3](../design.md#93-the-bulk-path-query_points)), tests, for each candidate rule, every point inside the rule's bounding box. When many large rules overlap a domain, every point is tested against every rule. Tiles skip the interiors and test only points near each rule's boundary. The masks were identical to the obvious version's in every case compared, and fractions differed by at most 2.2e-16 (this document's benchmark):

| 10⁶ points, 300 rules | Rules hit | Bounding box, then `intersects_xy` | Tiles, then `intersects_xy` | Peak memory, tiles |
|---|---|---|---|---|
| Global 1000 × 1000 grid; rules scattered worldwide | 263 | 0.25 s | 0.32 s | 297 MB |
| Regional 20° × 20° grid; all 300 rules overlap it; 10 to 200 vertices | 300 | 8.0 s | 1.7 s | 341 MB |
| Same domain; smooth outlines of 2,000 to 5,000 vertices | 300 | 11.0 s | 1.35 s | not measured |
| Same domain; jagged outlines whose radius jumps by up to 40% between vertices | 300 | 83 s | 52 s | 346 MB |

The last row is a pathological limit, not a target: cost grows with the number of points in tiles that a rule's boundary cuts through.

**Memory.** Besides the caller's arrays, the engine needs about 35 to 45 MB of working memory per million points plus 1 MB for every rule with at least one point inside, because masks are full boolean arrays; 300 rules with hits peaked at about 340 MB (measured with `tracemalloc`). Callers with more points should call `query_points` on chunks and join the masks.

**Do not use `STRtree.query(points, predicate=...)`.** Given a predicate, shapely's tree query prepares the input geometry, not the geometries in the tree, so with points as input every point-polygon pair is tested against an unprepared polygon. The design research measured 50.9 s against 2.5 s for a million points. This document's benchmark, with all 300 rules overlapping the domain, measured 0.96 s per 10,000 points for simple outlines (about 96 s per million) and 2.39 s per 1,000 points for detailed ones (about 2,400 s per million), against 1.7 s and 1.35 s on the tile path. The tile query in step 5 of the bulk path ([decisions.md](decisions.md#bulk-path-in-full)) is the safe direction: the input is the rule, which should be prepared, and the tree holds simple boxes.

## Emission evidence

Findings are the API. `Index.query` has no side effects: it returns a sorted list of `Finding` objects that a caller can filter, store with `to_dict()`, show in a dashboard or assert on in a test. `emit()` is an optional adapter that turns findings into log records, warnings or an exception, under a policy the caller controls. Warnings cannot be the API, for three reasons:

- Python's default warning filter shows an identical message only once per call site, so a loop over many lakes hides repeats. Five identical warnings from one line produced one record; five that differed only in the lake label produced five (design research, rechecked on Python 3.11.16).
- `warnings.catch_warnings` changes process-wide state and is not thread-safe in Python 3.11 to 3.13, so a Panel dashboard or an MCP server cannot collect warnings reliably.
- Server and web interfaces never see warnings at all.

The `-W` filtering shown in section [11.2](../design.md#112-message-text) works because `-W` escapes its message field and matches it against the start of the message, and because it imports a dotted category name (checked in the design research and on Python 3.11.16). `PYTHONWARNINGS` and pytest's `filterwarnings` accept the same strings, so the warning classes are exported at the package top level.

**Where a warning points.** A warning should name the user's line, not a line inside queryearth or inside the consumer; a fixed `stacklevel=2` points inside CrocoDash when the call passes through CrocoDash's own functions (design research). `emit()` therefore walks outward to the first frame whose module is neither queryearth nor one of `Policy.skip_packages`, and passes that depth to both `warnings.warn` and logging's `stacklevel`, as pandas does with its `find_stack_level` helper. Python 3.12's `warnings.warn(skip_file_prefixes=...)` does this job, but Python 3.11 does not have it.
