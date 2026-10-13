# queryearth design

**Status:** draft for review. Written 2026-10-09; revised 2026-10-10 after two design reviews and two decisions by the author (section 18.1); restructured on 2026-10-10 into this main document and the reference files below; corrected on 2026-10-11 after a verification pass; extended on 2026-10-12 with plugin dimensions, emission sinks and an extension-points section, and with no upper limit on the Python version; on the same day the author adopted every recommended default (section 18.1). Nothing is implemented yet; the name, the interfaces and every number marked as a target are proposals.

**How this document is organised.** This file holds the narrative, the decisions and the contracts. Field-level detail, evidence, data and code live in reference files, and nothing was dropped in the split: every table, measurement and example condensed here appears in full in one of them.

| Reference file | Contents |
|---|---|
| [reference/decisions.md](reference/decisions.md) | The choices made while drafting, the open questions that can wait (each with the recommended default the draft follows), and the detailed contracts: every field of the core objects, record properties, loader checks, error classes, version ranges, time conversion, calendars and engine internals |
| [reference/schema.json](reference/schema.json) | The JSON Schema (2020-12) for one rule record or one pack file |
| [reference/api_sketch.py](reference/api_sketch.py) | The public API as a Python sketch, bodies elided, that imports and runs on Python 3.11 |
| [reference/usage.py](reference/usage.py) | A longer usage example of that API |
| [reference/geometry.py](reference/geometry.py) | Reference code for ring normalisation and spherical area (section 6) |
| [reference/fixtures.md](reference/fixtures.md) | The 28 correctness fixtures every implementation must pass |
| [reference/examples/README.md](reference/examples/README.md), [pack.toml](reference/examples/pack.toml), [rules.geojson](reference/examples/rules.geojson) | The example pack of 14 records, its computed rules, and five worked queries with their expected findings |
| [reference/consumers.md](reference/consumers.md) | The CrocoDash and GLHE integrations in full, with line references, sketches and acceptance criteria |
| [reference/background.md](reference/background.md) | Prior art in full, the evidence behind each requirement, and the measurements this document cites |
| [reference/glossary.md](reference/glossary.md) | Product, project, geometry and software names, for readers outside earth-system science |

## 0. Summary

- **What it is.** queryearth is a small, general-purpose Python package (shapely, numpy and the standard library) that answers one question: given where, when and anything else that matters (axes such as grid resolution, facets such as product and variable), which registered rules apply, how much of the request does each one cover, and what does it say to watch out for or to do?
- **What is commodity and what is new.** Checking whether a shape overlaps a shape, or an interval overlaps an interval, is a commodity. The value is the layer around it: a scope model in which every dimension is optional, with exact "conditional" results when a query leaves one out (so "resolution only" is a complete query); one `Finding` type for caveats, coverage and recommendations; a tested correctness layer for the antimeridian (the 180 degree meridian, where longitude jumps from +180 to -180), the poles, cell edges and calendars; a query contract based on the support (the cells and time steps a product actually contributes); and an emission policy that keeps findings as data.
- **Key decisions.** Engine only, with no curated content. Rules are GeoJSON Features with the OGC JSON-FG `time` member, or short Python classes, and they live on explicit `Index` objects. Shapes use straight longitude-latitude edges and are normalised once. Time uses calendar-free civil-date integer keys. One query can name several products as requests, each checked with its own variables, default time and version, and support. A bulk path serves about a million grid points. An inverse query ranks products by their known concerns, never by "quality". Every part is extensible: each kind of scope, space and time aside, is a `Dimension` plugin, so a new kind of matching (a basin hierarchy, a taxonomy, a network) is one small class rather than a fork, and rules, products, regions, ranking and emission all take user code (section 12.5).
- **Out of scope for v1.** Curated rule packs, a user interface, an MCP (Model Context Protocol) server for AI agents, database or cell-index backends, CQL2 input and unit conversion (section 17).
- **First consumers.** GLHE (lake hydrology) and CrocoDash (regional ocean model cases); their integrations are the acceptance tests (section 15).
- **Terms.** Section 4.1 defines queryearth's own vocabulary; [reference/glossary.md](reference/glossary.md) defines the product names, project names and geometry terms the document uses.

### 0.1 The API at a glance

A first look, written against the API sketch. `lake_geojson`, `qlon` and `qlat` stand for the caller's own data, and the demo pack declares the products `cru_ts` (alias `CRUTS`, with its grid) and `era5_land`. [reference/usage.py](reference/usage.py) is a longer version, and [reference/api_sketch.py](reference/api_sketch.py) gives every signature.

```python
import queryearth as qe
from queryearth import space as sp

index = qe.Index("demo", axes=[qe.Axis("resolution", "km", "horizontal grid spacing")])
index.load_pack("packs/demo")  # GeoJSON rules, plus products cru_ts and era5_land

# One lake, two products. Each request has its own variables and support, and
# with no time given, each takes its own product's coverage (listed in assumed).
lake = sp.polygon(lake_geojson)  # the caller's outline, never lake.buffer(0.5)
found = index.query(
    space=lake,
    requests=[qe.Request("CRUTS", ("pre",)), qe.Request("era5_land", ("tas",))],
    label="lake 1234",
)
for f in found:  # every finding names its product and how much of the request it covers
    print(f.product, f.code, f.kind, f.severity.name, f.area_fraction)

# Resolution only is a complete query; conditional findings name what is missing.
only_res = index.query(axes={"resolution": 8.0}, include_conditional=True)

# An Arctic model domain: recommendations carry structured suggestions.
ring = sp.from_grid(qlon, qlat)  # cell corners; a ring around the pole is closed
arctic = index.query(
    space=ring,
    axes={"resolution": sp.resolution_of(qlon, qlat)},
    facets={"model": "mom6"},
)
todo = [s for f in arctic if f.kind == "recommendation" for s in f.suggestions]

# Inverse query: products ordered by their known concerns, never by "quality".
ranked = index.suitable(qe.Query(space=lake), variable="pre")

# Findings are data; emit() turns them into warnings, log lines or one exception.
qe.emit(found)  # caveats warn as "[CODE] ..."; recommendations are logged at INFO
```

## 1. Problem and scope

A **rule** is a statement with a scope: where, when and to what it applies. It produces a **caveat** ("these values are climatology, not observations"), a **recommendation** ("consider an active sea-ice component") or a **coverage** finding ("this product does not reach part of your request"). A query returns **findings**: structured objects that a program can log, raise, store or act on. Section 4 defines every term exactly.

### 1.1 Three motivating examples

**A caveat: CRU TS precipitation over Africa (CRU001, and the computed rule CRU002).** CRU TS is a gridded monthly climate dataset interpolated from weather stations. Where no station lies within the correlation-decay distance (450 km for precipitation), CRU TS writes the 1961-1990 climatology for that cell and month and records a station count `stn` of 0. The design research computed this from GLHE's public copy of CRU TS 4.07: over the eight IPCC AR6 African land regions (reference regions of the Intergovernmental Panel on Climate Change's Sixth Assessment Report), the share of land cells with `stn = 0` rose from 6.8% in 1973 to 34% in 2022. So the faithful check is computed from `stn` for the cells and months actually used (CRU002), and the static record CRU001 is the coarse fallback. The author's original example, South Africa, turned out to be gradual station thinning rather than climatology fill, so severity must be graded (section 12.4; full numbers in [reference/background.md](reference/background.md#cru-ts-station-counts)).

**A recommendation: an Arctic CrocoDash domain (CROC101 and CROC104).** CrocoDash sets up regional ocean model cases for MOM6, the ocean model of CESM (the Community Earth System Model). For an Arctic domain the rule should say "set parameter X to Y", not only "beware". The expert-interview knowledge base behind the Regional Ocean Debugger (a CROCODILE project tool for diagnosing regional MOM6 runs) gives two pieces of advice that fit: the time step has to be set from the smallest grid cells in the domain, and at high latitudes a polar projection usually makes more sense; and a domain that extends far north brings sea ice into play. So a computed rule, CROC104, scoped to the latitude band 66.5N to 90N and to the facet `model = mom6`, returns the suggestion `{"target": "MOM_input", "key": "DT", "value": <seconds>}`, computed from the finest grid spacing, and a record, CROC101, with the same scope suggests an active sea-ice component and a polar-stereographic grid. The DT formula and the setting names are illustrative (section 16). The space handling must be right for polar-stereographic grids whose boundary encloses the North Pole without reaching it, and for domains that cross the antimeridian.

**A rule with no area or time (CROC102).** The same knowledge base, paraphrased, says that a grid spacing of about 1/10 degree is generally considered eddy-resolving, and that finer grids may conflict with parameterizations designed for coarser resolutions. The rule "below 10 km grid spacing, revisit coarse-grid parameterizations" depends only on resolution, so a query that gives nothing but `resolution = 8 km` must be complete and must return it. Rules like this are common: of the 31 known issues that ECMWF (the European Centre for Medium-Range Weather Forecasts) lists for ERA5, its global atmospheric reanalysis, about 13 have no area or time scope at all (tally made during the design research). The 66.5N and 10 km thresholds are author choices.

### 1.2 Who it is for

- **Tool builders** write software that chooses, fetches or configures data, such as data-access layers, model setup tools and analysis pipelines. They call queryearth before or while using a product.
- **Rule authors** know where and when a dataset or a configuration has problems and want that knowledge checked automatically rather than left on documentation pages. They write rules as data (GeoJSON) or as short Python classes.

Neither group needs to be an earth scientist. The engine knows about longitude, latitude, calendars and areas; it knows nothing about precipitation or ocean models.

| First consumer | What it needs to know | Query shape | Where the check runs |
|---|---|---|---|
| GLHE (Global Lake Hydrology Explorer) | Whether a product can serve a lake, which months are weak, and which product to use. Its `Products.md` roadmap already asks for "Uncertainty and Cautionary Flags" and a "Global Product API". | One lake polygon per run from HydroLAKES, a global database of lake outlines (1,427,688 lakes, median about 24 vertices); products CRU TS, ERA5-Land (a land reanalysis driven by ERA5), NWM (the National Water Model; contiguous US only) and DAHITI (lake levels from satellite altimetry; see the [glossary](reference/glossary.md)). No time range: GLHE reads each product's whole record. All products are checked in one query, with one request each. | A coverage check before any download, and the computed `stn` rule inside the CRU TS accessor |
| CrocoDash | Whether the forcing products cover the domain and period, which caveats apply, and which model settings the domain calls for | One regional domain per case (rotated, polar, antimeridian-crossing or periodic in longitude), dates at day resolution, one to six products, checked in one query with one request each | Once per case, when forcings are configured; findings go into the case's `config.json` |

The engine is domain-neutral: facets and axes are names that an Index declares, and the engine never interprets suggestion targets. Drone geozones (as encoded in the EUROCAE ED-318 format), sampling-bias caveats on species-occurrence data, and disease-surveillance reporting gaps fit the same model, and the example pack encodes one of each (section 16). The design research found no consumer outside earth-system modelling, so the general-purpose claim is still untested (Q52).

### 1.3 What queryearth is, and is not

queryearth is an engine. It provides a scope and outcome model in which every dimension is optional; a correctness layer for the antimeridian, the poles, cell edges and calendars, with a fixture suite; a query contract based on the support; one `Finding` type for rule records, computed rules and product coverage; an emission policy; a JSON Schema and a loader for rule packs; and an inverse query that ranks products by their known concerns. It is not:

- **a content source.** It ships no rules and no product declarations; users bring their own packs (the author's decision). The only built-in rules are the coverage checks QE001 and QE002, which run on products that users declare. The example pack is test and documentation data, not shipped content.
- **a quality judge.** A query with no findings means only that no registered rule matched. It does not mean the data are good.
- **a data-access or catalogue tool.** It downloads nothing and searches no archives. NASA's CMR, STAC APIs and ERDDAP already answer availability across archives.
- **a model configurator.** It returns suggestions; consumers decide whether to apply them.
- **a user interface or a server** in v1 (section 17).

To be plain about it: does this shape overlap that one, and does this interval overlap that one? Several tools already answer that, and about 60 lines of standard-library Python would too. queryearth's contribution is the scope and outcome model, the correctness layer, the support-based query contract and the emission policy. For any one user, most of the practical value will still come from the rules they write, and writing rules is labour, not software.

## 2. Prior art and what we borrow

The design research surveyed generic matchers that find records by space and time, caveat and errata services that hold real content but no geometry, and standards whose vocabulary fits. In short: the matcher exists many times over, and caveat content exists without geometry, but no tool combines them. The closest structural analogue is OSV, a format for software vulnerability advisories. The table is condensed; [reference/background.md](reference/background.md#prior-art-in-full) gives the full survey with sizes and timings.

| Prior art | What it is | What queryearth takes, or why it is not the core |
|---|---|---|
| geostructures | A library of time-bounded shapes with a linear-scan intersection filter | Nothing. The author prefers not to depend on or contribute to it, and queryearth is written without consulting its source. |
| cql2-rs (Python package `cql2`) | Evaluates CQL2 (OGC Common Query Language) expressions against one JSON record at a time | A predicate evaluator, not a registry; a good optional input adapter later (section 17) |
| rustac with stac-geoparquet, geopandas, pygeofilter | Search through DuckDB, a spatial index plus a time mask, and a CQL2 parser with several backends | Tens of megabytes of wheels or hundreds of milliseconds of import time, no outcome model, and no seam or pole handling |
| IVOA MOC 2.0 and ST-MOC | Sky and space-time coverages stored as ranges of HEALPix cells, an equal-area division of the sphere | Coverages carry no metadata and time has no civil calendars; the cell-index idea is the upgrade path for very large derived layers (section 17) |
| ESGF errata for CMIP6 (468 issues), ISIMIP caveats (76), ECMWF's ERA5 known issues (31), the NCAR Climate Data Guide (about 230 pages), NASA CMR known issues | Real caveat content with severity, status, action, affected product and version, and citations | The field vocabulary. None has geometry or data time. |
| OSV (Open Source Vulnerability format) | Software vulnerability advisories | Version ranges (`introduced`, `fixed`, `last_affected`, `versions`), `withdrawn`, `aliases`, typed references, and reviewed records kept in separate repositories |
| CAP 1.2 (Common Alerting Protocol) | Public warnings | Severity kept separate from certainty (`confidence`); headline, description and instruction (`title`, `message`, `instruction`); `region_ref`; `supersedes` |
| EUROCAE ED-318 | Drone geozones in GeoJSON | A collection metadata header; no time means always; lists of periods or areas are unions |
| OGC JSON-FG 1.0 and CQL2 1.0 | GeoJSON with time; a query language | The `time` member, `coordRefSys` and a null `place`; space-intersects and time-intersects semantics with closed intervals, but not the syntax |
| ISO 19157 and RFC 7946 (GeoJSON) | Data quality; geographic features in JSON | A quality statement scoped by an extent, with evidence as method, measure and result; CRS84, straight edges, antimeridian cuts, counterclockwise exteriors, null geometry |
| xclim and smaller borrowings | Climate indices; several Python libraries | One switch between log, warn, raise and ignore (xclim); prefixed codes filterable with `python -W` (ruff, pylint); an explicit registry with an application default (pint); named containment modes (H3); `time_start` and `time_end` fields (GDAL 3.12); `__init_subclass__` registration with duplicates made an error (CrocoDash) |

Speed does not separate the matchers at realistic sizes: with 10,000 rules, a pure-Python linear scan answers a point, lake or continent query in 0.49 to 10 ms, and a shapely STRtree (a spatial index that finds the shapes whose envelopes, their bounding boxes, meet a query) in 0.06 to 4.5 ms (design research; section 13). The caveat services teach two lessons: most of OSV's value lies in its maintained database, not its schema code, and GeoViQua, an EU project (2011 to 2014), built quality-aware catalogue search that faded once funding ended. Content should live apart from the engine, and an engine without maintained content does not get adopted; since queryearth ships no content, its usefulness depends on someone writing and maintaining rules. Because packs are plain GeoJSON with the JSON-FG `time` member, GDAL 3.12 reads them as JSON-FG, so QGIS (a desktop geographic information system) and geopandas can display packs without queryearth.

**Why a small matcher of our own.** queryearth needs behaviour no single tool provides: conditional matches when a query omits a dimension a rule constrains; closed-set boundaries, so grid points on a region's edge match; seam and pole normalisation enforced at load; overlap measures in area, time and on each axis; civil-date keys that work across calendars; and hard errors for unknown names. Wrapping a generic matcher would still mean writing all of this; the design research estimated the whole package at 1,000 to 2,000 lines, most of it outside the matcher. The core depends only on shapely and numpy, which both first consumers already install, and speed does not argue for reuse, because a plain list or a shapely STRtree is fast enough (section 13). The author also prefers not to depend on or contribute to geostructures, so queryearth is written clean-room: that library's source is not read, copied or paraphrased, and it is cited here only as prior art.

## 3. Requirements

The author set six requirements (R1 to R6), added two after the first review (R7 and R8) and one more on 2026-10-12 (R17). The design research surfaced eight (R9 to R16). This table is also the requirement half of the checklist: it says where each requirement is met and how that was checked, as section 19 does for the author's decisions. "Review" means the row was checked by reading the cited sections against the approved plan. [reference/background.md](reference/background.md#requirements-with-their-evidence) gives the full evidence for each requirement.

| # | Requirement | Verdict | Key evidence | Met in | How checked |
|---|---|---|---|---|---|
| R1 | Point and polygon queries | Sound, but incomplete | Cyclic domains have no bounding box, polar domains enclose a pole their boundary never reaches, NWM lakes are known by id, and a model grid is weighted cell centres. Most of all, a query must describe the support: under cell-centre masking a lake of about 150 km² selects no CRU TS cell. | 4.4, 4.12, 6, 8 | Review; fixtures 2 to 10 and 25 state the expected answers |
| R2 | Minimal dependencies, standard library wherever possible | Sound for loading, time and emission; too strict for geometry | shapely 2.1 or later and numpy are required (author decision). Python 3.11 or later with no upper limit (author decision): the floor is set by CrocoDash, which pins Python below 3.12, and nothing in the design needs a ceiling. | 2, 4.11, 12.1, 13 | [reference/api_sketch.py](reference/api_sketch.py) imports nothing beyond the standard library, numpy and shapely, and runs on Python 3.11.16 |
| R3 | Very fast querying | Premature for single queries; real for bulk grids and loading | 10 ms or less per query at 10,000 rules; a million grid points against 10,000 rules take about 80 s in pure Python (extrapolated) and 2.5 s with shapely. Both workloads are in v1 (author decision). | 9, 13 | Prototype and design-research measurements cited in sections 9 and 13 and in [reference/background.md](reference/background.md#engine-measurements) |
| R4 | An easy interface layer | Sound; this is where the value lies | The consumers log and print rather than warn, the default warning filter hides repeats, and `warnings.catch_warnings` is not thread-safe before Python 3.14. Findings must be the API. | 4.9, 4.11, 11 | Review |
| R5 | Rule objects that are quick to write | Sound | Data-only packs for people who do not program, Python rules for programmers, CrocoDash's `__init_subclass__` pattern with three fixes | 5, 12, 16 | Review; 14 records and three computed rules written in the example pack |
| R6 | A user interface layer | Premature | The JSON Schema, geojson.io for drawing and GDAL or QGIS for viewing cover v1 | 17 | Review |
| R7 | Extra dimensions such as resolution (added) | Sound and essential | Of ERA5's 31 known issues, about 6 name a region and a period, 5 only a region or terrain, 7 are global and time-limited, and 13 have neither. Every dimension is optional on both sides. | 4.2, 4.3, 4.6, 4.7, 8.3 | Fixtures 17 to 19 |
| R8 | Recommendation outcomes (added) | Sound | A rule must be able to say "consider setting X". Suggestions are structured and never interpreted by the engine. | 4.9, 5.2, 11.1, 11.3, 15.1, 16 (CROC101 to CROC104), [reference/schema.json](reference/schema.json) | The schema rejects a recommendation without suggestions (broken variant) |
| R9 | Provenance and versioning | Surfaced by research | Product versions are often not PEP 440 versions, Python's version-number standard (`ERA5T`, ERA5's preliminary stream; `GEBCO_2024`, a release of the GEBCO ocean-depth grid), and change meaning; unknown product names must be errors | 4.7, 4.8, 5.2, 12.3 | Fixture 21 |
| R10 | Overlap measures | Surfaced | A large domain that clips a regional caveat differs from a lake inside it | 4.3, 4.4, 4.6, 6.3, 7.2 | Fixtures 9, 11, 13, 17 and 22; the area code in [reference/geometry.py](reference/geometry.py) run on the caps and bands of fixture 22 |
| R11 | Computed rules | Surfaced | Object predicates and raster-derived rules, with graded severity, no silent skips and a recorded time-aggregation rule | 4.10, 4.11, 12.2, 12.4 | Fixture 19 |
| R12 | Coverage, and the inverse query built on it | Surfaced; inverse query in v1 by author decision | Footprints are the commonest concern, and coverage has the opposite polarity to a caveat | 4.9, 10, 16.1 | Review |
| R13 | Two time axes | Surfaced | Data time (which years are affected) differs from record time (when the rule was written or withdrawn) | 5.2, 7.2 | Review |
| R14 | Calendars and long time ranges | Surfaced | numpy `datetime64[ns]` wraps silently, cftime raises across calendars, and `datetime` covers years 1 to 9999 only | 7, 8.3 | Fixtures 11 and 13 to 16 |
| R15 | Warning fatigue | Surfaced | A "request smaller than a product cell" rule fires for nearly every lake; a trial against real lakes and domains is an acceptance test | 11.1, 11.3, 15.3 (the trial); Q11 and Q12 in [reference/decisions.md](reference/decisions.md#matching-and-scope) | The trial of section 15.3 is an acceptance test; it has not been run |
| R16 | A shared correctness fixture suite | Surfaced | The dangerous failures pass validity checks (section 6.1); every implementation and adapter must pass the suite | 14, [reference/fixtures.md](reference/fixtures.md) | Review; 28 fixtures |
| R17 | Every part easily extensible, including complex matching in dimensions other than space and time (added) | Sound | A user with a basin hierarchy, a taxonomy or a network should declare it once and reuse it across rules, packs and queries, not write it into every rule's `check()` | 4.13, 11.1, 12.5 | The Pfafstetter dimension of section 4.13 was run against the API sketch; fixtures 27 and 28 |

## 4. Concepts and data model

This section sets the vocabulary and the contracts that the rest of the document follows. Sections 6 to 8 give the geometry, time and query semantics, [reference/decisions.md](reference/decisions.md#detailed-contracts) lists every field, and [reference/api_sketch.py](reference/api_sketch.py) gives the API.

### 4.1 Terms

| Term | Meaning |
|---|---|
| Rule | A statement that applies within a scope and produces findings. A rule is either a record (data: one GeoJSON Feature in a pack) or code (a computed rule written in Python). |
| Scope | Where, when and to what a rule applies: a conjunction ("and") over four kinds of dimension, namely space, time, axes and facets. |
| Dimension | One independent part of a scope or a query. Every dimension is optional on both sides. Space and time are built in; every other kind, including axes and facets, is a `Dimension` plugin declared on the Index (section 4.13). |
| Axis | A named, ordered, numeric dimension declared on an Index with one unit, such as `resolution` in km. |
| Facet | A named categorical dimension declared on an Index, such as `product`, `variable` or `version`. |
| Query | A description of what the caller is about to use: an area, a period, values on axes and facet values. Any subset may be given. A query may also carry requests, one per product. |
| Request | One product as the caller uses it within a query: the product, the variables read from it, and optionally its version, time and support. The engine evaluates each request as its own sub-query, and rules that concern no product once on the base query (section 4.12). |
| Support | The cells and time steps that a product actually contributes to the caller's request, as opposed to the caller's own geometry. For a lake inside one 0.5 degree grid cell, the support is that cell, not the lake outline. |
| Finding | The result of one rule matching one query. Findings are the API; warnings and log lines are optional outputs built from them. |
| Conditional finding | A finding for a rule that the engine could not decide: the rule constrains a dimension that the query omitted, that the query gave in a form not comparable with the rule's (object ids against a polygon), or that needs a `Query.context` key the caller did not pass. The rule might apply; the undecided dimensions are named in `conditional_on`. |
| Product | A dataset that queries can name, such as CRU TS, ERA5 or GLORYS (a global ocean reanalysis), with a canonical name, aliases, coverage, resolution, calendar and the version in use. [reference/glossary.md](reference/glossary.md) describes each product the document names. |
| Pack | A versioned set of rule records and product declarations: a `pack.toml` file plus GeoJSON FeatureCollection files. |
| Index | The object that holds the declared axes and facets, products, named regions and rules, and answers queries. There is no hidden global registry; `Index.default()` exists for convenience. |

### 4.2 The scope model

A rule's scope is a conjunction: the rule applies only where all of its constrained dimensions apply, and a dimension that the rule leaves out matches anything. A query has the same four kinds of dimension, each optional.

| Dimension | What a rule can state | What a query can give | Left out of a rule means |
|---|---|---|---|
| Space | A polygon or multipolygon; a longitude-arc box; a latitude band; named regions (`region_ref`); a set of object ids | A point, polygon, box, latitude band, the outline of a 2D grid, weighted points, object ids, or the product cells a region uses | Global |
| Time | A union of closed intervals, optionally limited to some calendar months of every year | A union of intervals, normally the bounds of the time steps used | Always |
| Axes | An interval on each named axis declared on the Index, for example `resolution` below 10 km | A value or a closed range on each axis | Any value |
| Facets | Allowed (and optionally excluded) values for declared facets; OSV-style ranges for `version` | One or more values per facet; products, with their variables, as requests (section 4.12) | Any value |
| Other plugin dimensions | Whatever the plugin parses from the record's `dimensions` block, such as basins in a hierarchy | Whatever the plugin parses from `Query.dims` | Any value |

Every dimension must be optional because real rules rarely use all four (the ERA5 tally under R7), and some, such as CROC102, have neither area nor time. Four rules are used as running examples; CROC101 and CROC102 draw on the ocean debugger's expert-interview knowledge base (section 1.1), and the model parameters named in their suggestions are illustrative.

| Rule | Space | Time | Axes | Facets |
|---|---|---|---|---|
| CRU001: CRU TS precipitation falls back to climatology over much of Africa | Eight IPCC AR6 African land regions (`region_ref`) | 2000 onward | none | product `cru_ts`, variable `pre`, version 4.07 |
| ERA5-001: lower-stratosphere cold bias, rerun as ERA5.1 | none (global) | 2000 to 2006 | none | product `era5`, version `ERA5` |
| CROC101: Arctic domain, consider active sea ice | Latitude band 66.5N to 90N | none (always) | none | model `mom6` |
| CROC102: eddy-resolving grid, revisit coarse-grid parameterizations | none (global) | none (always) | `resolution` below 10 km | none |

### 4.3 Matching when a dimension is missing

For each dimension, the engine asks two questions: does the rule constrain it, and does the query supply it?

| Rule constrains the dimension | Query supplies it | Result for this dimension |
|---|---|---|
| No | No | Passes. |
| No | Yes | Passes. For space, `area_fraction` is 1.0; for time, `time_overlap` is the query's own period. |
| Yes | Yes, in a comparable form | Evaluated. If the two do not overlap, the rule produces no finding at all, not even a conditional one. If they overlap, the overlap is recorded on the finding. |
| Yes | Yes, but not comparable with the rule's form | Undecided, as in the next row. The one case in v1 is space given as object ids against a rule with a geometry, or the reverse, when the Index holds no geometry for that id namespace (section 4.4). |
| Yes | No | Undecided. The dimension's name is added to `conditional_on`, and the finding reports the rule's own extent for it. |

A computed rule that needs a `Query.context` key the caller did not pass is undecided in the same way, on `"context:<key>"`. A rule therefore produces a finding exactly when no dimension fails. If `conditional_on` is empty the finding is **definite**; otherwise it is **conditional**. `Index.query` returns conditional findings only when called with `include_conditional=True`, and `emit()` never emits them, because they describe what might apply rather than what does. A month recurrence counts as a time constraint even when the rule's `time` member is null. In a conditional finding, measures of the decided dimensions are filled exactly as for a definite finding, and measures of the undecided ones report the rule's own extent or nothing: an undecided space leaves `area_fraction` and `overlap_km2` None; an undecided time leaves `time_fraction` None and lists the rule's own periods in `time_overlap`; an undecided axis reports the rule's own interval; and a computed rule's `check()` does not run. The names in `conditional_on` (`"space"`, `"time"`, axis names, facet names, `"context:<key>"`) are listed in a fixed order, and axis and facet names may not be `space` or `time`, so they are never ambiguous. [reference/decisions.md](reference/decisions.md#conditional-findings-in-full) gives the full rules.

How the running examples respond to three queries:

| Query | CRU001 | ERA5-001 | CROC101 | CROC102 |
|---|---|---|---|---|
| Resolution 8 km and nothing else | Conditional on space, time, product, variable, version | Conditional on time, product, version | Conditional on space, model | Definite |
| Arctic MOM6 domain outline, 2020, resolution 8 to 12 km, model `mom6` | No finding (no spatial overlap) | No finding (2020 is outside 2000 to 2006) | Definite; `area_fraction` is the share of the domain north of 66.5N | Definite; `axes` records the overlap [8, 10) |
| Congo-basin lake outline, 1991 to 2020, product `CRUTS` (an alias), variable `pre` | Definite; the support (the CRU TS cells the lake touches, from the product's grid) and version 4.07 assumed from the product; `time_overlap` 2000-01-01 to 2020-12-31 | No finding (product differs) | No finding (no spatial overlap) | Conditional on resolution |

So "resolution only" is a complete query: it returns the rules that depend only on resolution as definite findings and, with `include_conditional=True`, lists everything that would apply once the caller says where, when and with which product.

**Defaults supplied by the product.** A query names its products through requests, one per product (section 4.12), and the engine evaluates each request as its own sub-query. In each sub-query, two omitted dimensions are filled from that request's product instead of becoming conditional: `version` from `Product.version` (the version this application uses), and `time` from the product's temporal coverage. A coverage with no time fills an interval open at both ends, and an open-ended coverage fills an open-ended interval; in both cases `time_fraction` is None, because the query's duration is unbounded. That is the correct support for a caller that reads a product's whole record, which is what GLHE does today, so GLHE's findings are resolved in time without it passing a period. A filled dimension is listed in the finding's `assumed` field when the rule constrains it, so a reader can see that version 4.07 was assumed rather than stated.

**Without a product, nothing is filled.** When the query names no product, or for a rule evaluated on the base query of section 4.12, an omitted time stays omitted: a time-scoped rule gives a finding conditional on `"time"`, and the finding still reports the rule's own periods in `time_overlap`. The author confirmed this behaviour (section 18.1); section 7.3 gives examples.

### 4.4 Space

Coordinates are float64 longitude and latitude in degrees on WGS84, longitude first (CRS84, as in RFC 7946). Edges are straight lines in longitude-latitude space ("planar" edges), which matches product grid cells and latitude-longitude boxes exactly. Every geometry is normalised once, when a record is loaded or a query is built (section 6).

A rule states its space in one of five forms: a GeoJSON polygon or multipolygon, holes allowed; a `box` `{west, width, south, north}`, which is a longitude arc that may cross the antimeridian, and a latitude band when its width is 360; named regions (`region_ref`, resolved at load through regions registered on the Index); a set of object ids (Python only); or nothing, which means global.

A query builds its space with the helpers in `queryearth.space`, imported as `sp`. `point`, `polygon`, `box` and `box_arc` build ordinary shapes. `lat_band` describes a domain periodic in longitude, and `from_grid` the outline of a 2D grid of cell corners. `weighted_points` takes model cell centres, and `features` object ids. `cells` and `cell_mask` give the product cells a region uses (section 8.2), and `nowhere` is the empty space. `resolution_of` is not a space: it returns a grid's (finest, coarsest) spacing for the `resolution` axis. [reference/decisions.md](reference/decisions.md#space-forms-in-full) tables every form.

**Predicate.** Space overlaps when the closed sets intersect, so a query that only touches a rule's boundary matches, and points on a rule's edge, on the split at plus or minus 180, or at a pole are inside. This deliberately over-warns at boundaries rather than missing them (section 6.3). Every finding carries `area_fraction`, defined by the kind of query space, and `overlap_km2`, the absolute overlapping area:

| Query space | `area_fraction` |
|---|---|
| None | None |
| Point | 1.0 (a point that is not covered produces no finding) |
| Polygon, box, band, grid outline or cells | Spherical area of the intersection divided by the spherical area of the query (section 6.3) |
| Weighted points | Sum of the weights of covered points divided by the sum of all weights (equal weights if none are given) |
| Object ids against object ids in the same namespace | Shared ids divided by query ids |
| Object ids against a geometry, or a geometry against object ids | Not comparable, so the finding is conditional on `"space"` (section 4.3), unless the Index has geometry for that namespace from `add_regions` |

When the rule is global and the query gives a space, `area_fraction` is 1.0. For coverage findings, `area_fraction` is the fraction of the query that lies outside the product's coverage. The engine reports every overlap, however small: a rule's `min_overlap` (default 0) only stops `emit()` from emitting findings whose `area_fraction` is below it, so a large domain that clips the edge of a regional caveat is still visible as data without raising a warning. A finding whose `area_fraction` is None is never dropped by this threshold, in `emit()` or in `default_score` (section 10.2).

### 4.5 Time

Records, packs and `Finding.to_dict()` use the `time` member of OGC JSON-FG 1.0 for data time: `{"date": "2020-01-09"}` is that whole day, `{"timestamp": "2020-01-09T06:00:00Z"}` that second, `{"interval": [start, end]}` a closed interval whose ends are dates, timestamps or `".."` for an open end, and `null` or absent, which JSON-FG defines as no temporal information, means always in queryearth. Interval ends are inclusive at their stated precision, so `["2000-01-01", "2006-12-31"]` includes all of 31 December 2006. A rule that applies in several separate periods lists them in `properties.periods`, inside the `time` member, which gives their overall extent. `properties.recurrence = {"months": [...]}` limits a rule to those calendar months in every year of its periods, or in every year if it has no time. If an editor drops the JSON-FG member, the loader accepts `properties.time_start` and `properties.time_end`, the field names GDAL uses for JSON-FG. Inside the code, each instant becomes a calendar-free integer key packed from the civil date and time, intervals are half-open, and every time specification carries a calendar name used for validation and durations but never for ordering (Q60). Section 7 specifies the key, calendars, recurrence and the measures `time_overlap` and `time_fraction`.

### 4.6 Axes

An axis is a named, ordered, numeric dimension that an Index declares with exactly one unit, for example `Axis("resolution", "km", "horizontal grid spacing")`; other examples are `depth` in metres and `vertical_levels` as a count. A rule states an interval with any of `gt`, `ge`, `lt` and `le` (never both `gt` and `ge`, or both `lt` and `le`) and an optional `unit` that must equal the declared one. A query gives a number or a closed range `(lo, hi)`; for a curvilinear grid it passes `(finest, coarsest)` from `resolution_of()`. The axis matches when the two intervals intersect, and `Finding.axes` records the intersection, so a reader can see that only the finest part of a grid (8 to 10 km of an 8 to 12 km grid) falls under a "below 10 km" rule. An undeclared axis name raises `UnknownNameError` in records and queries alike, because a misspelled axis would otherwise look like "no issues". The core does no unit conversion; conversions between km and degrees exist only in helpers that know a latitude, such as `resolution_of()`.

### 4.7 Facets

A facet is a categorical name declared on the Index. The default set is `product`, `variable`, `version`, `model` and `component`; an Index can replace or extend it, and an undeclared facet name in a record or a query is an error.

- **Rule side.** A list of patterns (shorthand for `any_of`) or `{"any_of": [...], "none_of": [...]}`; in Python a bare string is a one-item list. Patterns use case-sensitive `fnmatch` glob syntax. A value matches when it matches some `any_of` pattern (or `any_of` is absent) and no `none_of` pattern. The `version` facet uses version ranges instead (section 4.8).
- **Query side.** One string or a tuple of strings. The facet matches when at least one query value matches, and `Finding.matched_facets` records which values did.
- **Product names.** Product values on both sides are resolved through the aliases products declare, exactly and ignoring case, so `CRUTS`, `CRU TS` and `cru_ts` name the same product. An unknown product name is an error, because a misspelled product would otherwise look like "no known issues". For the same reason, product patterns such as `["era5*"]` match canonical names after alias resolution, and a pattern that matches no declared product is a load error (Q3).

| Rule states | Query gives the facet | Query omits the facet |
|---|---|---|
| Nothing for this facet | Passes | Passes |
| `["*"]` | Passes for any value | Conditional on the facet |
| `["era5*"]` | Passes if some value starts with `era5` | Conditional on the facet |
| `{"none_of": ["tp"]}` | Passes unless every query value is `tp` | Conditional on the facet |

`["*"]` is therefore not the same as leaving the facet out: it says the rule concerns some value of the facet, so it is undecided until the query names one. Matching is done facet by facet, so a query that gives variables `{pre, tas}` would match a rule for `pre` even if the caller reads `pre` from only one of its products. Products and their variables are therefore given as requests, one per product (section 4.12).

### 4.8 Version ranges

The `version` facet uses OSV-style ranges: `introduced` (inclusive), `fixed` (exclusive) or `last_affected` (inclusive, never with `fixed`), and exact `versions`; a list of ranges is a union. Bounds compare as dotted integers padded with zeros, so `"4.10"` is later than `"4.9"` and `"4.07"` equals `"4.7"`. Versions that are not dotted integers, such as `ERA5`, `ERA5T` or `GEBCO_2024`, can only be listed in `versions`, where they match literally. PEP 440 is not used: it needs the third-party `packaging` library, and most product versions are not PEP 440 versions. An omitted `version` is filled from the product (section 4.3). [reference/decisions.md](reference/decisions.md#version-ranges-in-full) gives the full grammar and examples.

### 4.9 Outcomes

Every match produces the same `Finding` type, and its `kind` says what sort of statement it is:

| Kind | Produced by | Fires when | Default severity | Carries |
|---|---|---|---|---|
| `caveat` | Records and computed rules | The query overlaps the scope | `WARNING` | `action`, `confidence`, `instruction` |
| `coverage` | The built-in coverage rule, from `Product.coverage` | Part of the query lies outside the product's coverage | `SEVERE` | `area_fraction` and `time_overlap` of the part outside |
| `recommendation` | Records and computed rules | The query overlaps the scope | `INFO` | `suggestions` |

**Coverage** is declared on products, not written as records, because its polarity is the opposite of a caveat's: being outside produces the finding. It may be static, or a callable evaluated per query for availability known only at run time. One built-in rule per code evaluates the product of every request (section 4.12) against that request's space and time: `QE001` for outside the spatial coverage and `QE002` for outside the temporal coverage (the prefix `QE` is reserved). Its action is `do_not_use` when the request is entirely outside and `use_with_caution` when it is partly outside, and it always names the product. A callable coverage returns `sp.nowhere()` to say that a request is not served at all (Q7). A coverage given as object ids, queried with a geometry, raises an error that names the namespace mismatch instead of becoming conditional, because a silent conditional would hide a pre-flight check (Q6). [reference/decisions.md](reference/decisions.md#coverage-findings-qe001-and-qe002) tables the two codes.

**Severity** is a three-level `IntEnum` whose values equal the `logging` levels: `INFO = 20`, `WARNING = 30`, `SEVERE = 40` (the number of `logging.ERROR`), so a logger can use `logger.log(finding.severity, ...)` directly. A source's own wording, such as "critical" in the ESGF errata service or "Extreme" in CAP, is kept verbatim in `source_severity`. "Outside coverage" is a kind, not a fourth severity, so how bad something is stays separate from whether the product can serve the request at all. **Confidence** says how sure the source is (`observed`, `likely`, `possible` or `unknown`, four of CAP 1.2's five certainty values). **Action** says what to do with the data, following ISIMIP: `can_be_used`, `use_with_caution`, `do_not_use` or `replaced`; recommendations normally leave it unset. **Suggestions** make a recommendation something a program can act on: each is `{target, key, value, rationale}`, where `target` names where the change goes (`MOM_input`, `compset`, `user_nl_cice`), `key` what to change, and `value` any JSON value. The engine never interprets `target` or `key`; CrocoDash may log a MOM6 suggestion, record it in the case's `config.json`, or apply it. `{"target": "MOM_input", "key": "DT", "value": 240.0}` is the suggestion CROC104 computes for an Arctic domain whose finest cells are 8 km (section 16.2).

**No known concerns is not good data.** A query that returns no findings means that no registered rule matched, nothing more. `suitable()` ranks products by their known concerns and says so, and no part of the API reports "good" or "suitable" as a quality judgement. `Index.query` returns findings sorted by severity (highest first), then kind (coverage, caveat, recommendation), then code, then part: the base query first, then the requests in order (section 4.12).

### 4.10 Rule kinds

All rule kinds implement one protocol, `evaluate(query) -> Sequence[Finding]`, and all go through the same scope matching, so section 4.3 applies to every kind. A **static record** is a GeoJSON Feature in a pack, or a `Rule(...)` or record mapping passed to `Index.add` (CRU001, ERA5-001, CROC101, CROC102). A **computed rule** (object predicate) is a `ComputedRule` subclass or an `@index.rule(...)` function: GEN001 fires when the caller's region is much smaller than the support (section 12.2), and CROC104 sets an Arctic domain's time step from its finest cells (section 16.2). A **raster-derived rule** is a computed rule that reads data the caller already holds, passed in `Query.context`, such as CRU002 on the CRU TS cell-months with `stn = 0` in the cells used (section 12.4); in v1 it is evaluated live, inside the consumer's adapter, and a missing context key makes it conditional on `"context:<key>"` rather than silently skipped. **Coverage** is built in, from `Product.coverage` (QE001, QE002). A third-party rule kind may also define `outcomes(query, match)`; the Index then does its scope matching and calls `outcomes()` only for the rules that survive (Q5).

### 4.11 Core objects

All core objects are frozen dataclasses. Everything except `Query.context` and the shapely and numpy members of `Space` is JSON-serialisable through `to_dict()` and `Rule.from_feature()`. Python 3.11 or later is supported, with no upper limit, and shapely 2.1 or later and numpy are the only third-party dependencies at run time; cftime, pandas and numpy date values are accepted by duck typing, not imported (section 7.1). Objects that hold mappings compare by value but are not hashable. [reference/decisions.md](reference/decisions.md#core-objects-in-full) gives every field, the hashing rules and the error classes; the tables below are the short form.

**Product**, with `Coverage(space=None, time=None)`, where None means global or all time:

| Field | Meaning |
|---|---|
| `name`, `aliases` | Canonical lowercase slug, such as `cru_ts`, and other names matched exactly ignoring case, such as `CRUTS` |
| `variables` | Variables the product offers, in the pack's own vocabulary; used by `suitable()` |
| `coverage` | A `Coverage`, or a callable `(Query) -> Coverage` for availability known only at run time |
| `resolution`, `calendar` | Native grid spacing in degrees or km (used by ranking), and the calendar of the time axis |
| `version` | The version this application uses; fills an omitted `version` facet |
| `grid` | The product's cells: rectilinear edges `(lon_edges, lat_edges)` or a callable `(Space) -> Space`. If declared, the engine derives a request's support from the caller's region (section 4.12). |

**Query** has `space` and `time` (the support: the cells and areas actually used, and the bounds of the time steps used); `axes` (a value or a closed range per axis); `facets` (values per facet, where `product` with `variable` and `version` is shorthand for requests); `dims` (values for other plugin dimensions, section 4.13); `requests` (one `Request(product, variables=(), version=None, time=None, support=None)` per product the caller uses, section 4.12); `context` (data for computed rules, such as station counts already loaded, not serialised); and `label` (the caller's name for the query, such as "lake 1234" or a case name, used in messages and de-duplication).

**Finding** is the rule's outcome plus how its scope met the query:

| Fields | Meaning |
|---|---|
| `code`, `kind`, `title`, `message`, `instruction`, `severity`, `source_severity`, `confidence`, `action`, `status`, `suggestions` | What the rule says, possibly overridden by a computed rule |
| `product`, `request` | The request's canonical product and its position; None for findings from the base query |
| `area_fraction`, `overlap_km2`, `time_overlap`, `time_fraction` | Spatial and temporal overlap (sections 4.4 and 7.2) |
| `axes`, `matched_facets`, `dims` | The intersection on each constrained axis, as an `AxisOverlap` that keeps open ends; the query values that matched each facet; and, for every other plugin dimension the rule constrains, its `DimMatch` (overlap and, if measurable, fraction) |
| `conditional_on`, `assumed` | Undecided dimensions (empty means definite), and the dimensions the rule constrains that were filled from the request's product (`space`, `time`, `version`) |
| `min_overlap`, `references`, `evidence`, `details`, `source`, `query_label` | Copied from the rule; rule-specific numbers; pack name, `computed` or `builtin`; the query's label |

**ComputedRule.** A subclass declares its code and scope with class keyword arguments (`code`, `index`, `abstract`, `kind`, `severity`, `title`, `facets`, `axes`, `space`, `time`, `requires`, `suggestions`), and defining the subclass registers one instance; a reused code raises `DuplicateCodeError`. Only if the match is definite does the engine call `check(query, match)`, which returns `True` for one finding with the declared defaults, `False` or `None` for none, a mapping of Finding fields to override, or several such mappings. An optional `mask(lon, lat, query)` hook serves the bulk path. `@index.rule(code, ...)` wraps a plain function the same way. A subclass of an `abstract=True` base inherits the base's keywords, merged, with its own winning, so a family of rules states its shared index and scope once (Q9).

**Index.** `Index(name, axes=..., facets=..., dimensions=...)` declares axes, facets and any other plugin dimensions, and `add_dimension` adds one before the first rule; `add_product`, `add_regions`, `add(rule)` and `load_pack(path)` fill it; `rule(code, ...)` is the decorator for function rules; `query(...)` answers one query with any number of requests (section 9.1); `expand(query)` shows the base query and sub-queries the engine will run (section 4.12); `query_points(lon, lat, ...)` is the bulk path (section 9.3); `suitable(query, variable, ...)` is the inverse query (section 10); `products` is a read-only mapping of the declared products, which computed rules can read (Q4); `rule_counts()` reports how many rules concern each product (Q35); and `Index.default()` is the application default, created on first use.

### 4.12 Several products in one query: requests

Both first consumers use several products for one request: GLHE reads CRU TS, ERA5-Land and NWM for one lake, and CrocoDash forces one domain with several products. Facet-by-facet matching cannot say which variable belongs to which product (section 4.7), and one product's default time cannot serve another. So a query names its products through **requests**, and the engine evaluates each request as its own sub-query. The author decided this design (section 18.1).

A `Request` has five fields: `product` (a canonical name or an alias), `variables` (the variables the caller reads from that product), and `version`, `time` and `support`, each optional. The engine splits a query with requests into a base query and one sub-query per request:

| Part | Rules it evaluates | Space | Time | Facets |
|---|---|---|---|---|
| Base query | Rules that constrain none of `product`, `variable` and `version`, such as CROC101 and CROC102 | The query's own space | The query's own time. If the query has none, a time-scoped rule is conditional on `"time"`. | The query's other facets, such as `model` |
| One sub-query per request | Rules that constrain `product`, `variable` or `version`, and the coverage rule for the request's product | The request's `support`; otherwise the support derived from `Product.grid`; otherwise the query's space | The request's `time`; otherwise the query's time; otherwise the product's temporal coverage | `product` is the request's product; `variable` its variables (omitted if it has none); `version` its version, otherwise `Product.version`; plus the query's other facets |

Axes, `context` and `label` are shared by every part. Each rule is evaluated either on the base query or on every request, never on both. A query without requests is just the base query, and every rule is evaluated on it, so a product-scoped rule is conditional on `"product"`. In the query of section 0.1, a rule about ERA5-Land precipitation gives no finding, because the second request reads `tas` only.

**Derived support.** A product may declare its cells as `Product.grid`: the edges `(lon_edges, lat_edges)` of a rectilinear grid, or a callable that takes a region and returns the cells it uses. When a request gives no support, the query's space is a point or an area, and the product declares a grid, the engine derives that product's support itself, with the semantics of `cells(grid, region, mode="overlap")` (section 8.2): every cell whose intersection with the region has positive area. So a caller can pass one lake polygon and have each gridded product judged on the cells it actually contributes. Object ids and weighted points are used as given. A derived support is listed in `assumed` as `"space"`, next to `"time"` and `"version"`, so a reader can see that `area_fraction` is relative to the product's cells, not to the caller's outline. An explicit `Request.support` always wins, for a caller whose extraction differs from the overlap cells.

**Findings name their product.** Every finding from a sub-query carries `product`, the request's canonical product name, and `request`, the position of its request; findings from the base query carry None for both. Overlap fractions, time overlaps and coverage findings are therefore per product, and when a query gives no time, each request's time is its own product's temporal coverage, listed in `assumed`.

**The facet shorthand.** `facets={"product": [...], "variable": [...]}` is still accepted, and the engine expands it into requests by this rule, never by guessing:

1. one request per listed product, in the order given, after alias resolution, with duplicates merged;
2. every request gets every listed variable, so the shorthand checks each listed variable against each listed product;
3. a `version` facet is allowed only with exactly one product, and becomes that request's version;
4. the query's time applies to every request, as it does to explicit requests.

Without a `product` facet there are no requests, and `variable` and `version` stay ordinary facets of the base query. A query that gives requests together with any of the facets `product`, `variable` or `version` raises `ValueError`. `Index.expand(query)` returns the base query and the sub-queries the engine will run, so a caller can inspect exactly which combinations are checked. Requests are the recommended form whenever products and variables come in pairs (fixture 23 in [reference/fixtures.md](reference/fixtures.md)).

`suitable()` builds one request per candidate product and runs this same machinery before ranking (section 10), and `query_points()` accepts requests too and keys its masks and fractions by `(product, code)` (section 9.3). Two details of this design were chosen while drafting and adopted by the author (Q59).

### 4.13 Dimensions are plugins

Space and time are built in, because the correctness layer of sections 6 and 7 lives there. Every other kind of scope is a `Dimension` plugin. Axes (`Axis`, numeric ranges), facets (`Labels`, glob patterns) and versions (`Versions`, OSV-style ranges) are the three built-in plugins, and a user adds a new kind of matching by writing one more. A plugin has four required members:

| Member | Used | Does |
|---|---|---|
| `name` | Everywhere | The key in records (`properties.dimensions`), queries (`Query.dims`), findings (`Finding.dims`) and `conditional_on` |
| `schema` | At load | A JSON Schema for the rule-side value; the loader validates every record's value against it |
| `parse_rule(value)`, `parse_query(value)` | At load, and at query time | Turn wire or Python values into the plugin's own form, raising `ValueError` on bad input |
| `match(rule, query)` | For each candidate rule | `None` when the two values do not overlap, otherwise a `DimMatch(overlap, fraction)` |

Four members are optional. `comparable(rule, query)` returning False makes the finding conditional on the dimension, as object ids against a polygon do for space. `build(values)` returns a prefilter whose `candidates(query)` narrows the rules before `match()` runs, so a plugin can bring its own index. `to_json(overlap)` serialises the overlap for `Finding.to_dict()`. `late = True` runs an expensive plugin after the exact spatial test rather than before it.

A plugin decides only whether one rule value meets one query value. The engine does everything else, the same way for every dimension: the conditional logic of section 4.3 (a rule that constrains `basin`, against a query that gives none, is conditional on `"basin"`), unknown-name errors, record validation, the base query and requests of section 4.12, sorting, emission, and the bulk path, where a plugin dimension is evaluated once per rule because it does not vary from point to point. Any name except `space`, `time` and `product` may be taken by a plugin: a pack whose variables follow a hierarchy of CF standard names, for example, can declare its own `variable` dimension, and requests still fill it.

**Example: a basin hierarchy.** HydroBASINS numbers river basins with Pfafstetter codes, in which each extra digit nests a basin inside the one before, so basin 1423 lies inside basin 14. A rule about a basin applies to every lake in it, however finely the caller codes its own basin:

```python
from dataclasses import dataclass
from typing import Any

import queryearth as qe


@dataclass(frozen=True)
class Pfafstetter:
    """HydroBASINS basin codes: basin 1423 lies inside basin 14."""

    name: str = "basin"
    schema = {"type": "array", "items": {"type": "string", "pattern": "^[1-9]+$"}}

    def parse_rule(self, value: Any) -> tuple[str, ...]:
        return tuple(str(v) for v in value)  # the basins the rule concerns

    def parse_query(self, value: Any) -> str:
        code = str(value)
        if not code.isdigit() or "0" in code:
            raise ValueError(f"not a Pfafstetter code: {value!r}")
        return code  # the caller's basin, at any level

    def match(self, rule: tuple[str, ...], query: str) -> qe.DimMatch | None:
        hits = [b for b in rule if query.startswith(b) or b.startswith(query)]
        if not hits:
            return None
        inside = any(query.startswith(b) for b in hits)  # query nested in a rule basin
        return qe.DimMatch(overlap=tuple(hits), fraction=1.0 if inside else None)


index = qe.Index("glhe", dimensions=[Pfafstetter()])
```

A rule with `"dimensions": {"basin": ["14"]}` matches `index.query(space=lake, dims={"basin": "1423"})` with fraction 1.0. It also matches a query for the whole of basin 1, with fraction None, because it covers only part of that basin and the plugin cannot say how much. A query for basin 31 gets no finding, and one that gives no basin gets a finding conditional on `"basin"`. Fixture 27 tests these cases, and the code above was run against the API sketch. The same pattern serves a taxonomy (a species inside a genus) or a river network (everything upstream of a gauge, with a prefilter built from the network).

## 5. Record format

### 5.1 A rule is a GeoJSON Feature

A static rule is one GeoJSON Feature (RFC 7946) with the JSON-FG `time` member for data time and queryearth properties. The Feature has `geometry` (Polygon, MultiPolygon or null), the `time` member, an optional informational `id`, `place` (null or omitted) and `coordRefSys` (only on the root object, a pack or a rule stored as its own file; if present, `http://www.opengis.net/def/crs/OGC/0/CRS84`, which is also the default; it never applies to `geometry`). A pack's root object also carries JSON-FG's `conformsTo` with the core conformance class. queryearth is a profile of JSON-FG 1.0: it allows one time member only, where JSON-FG allows consistent combinations, and it accepts signed or five-digit years and 30 February for paleoclimate and `360_day` data, so records that use those are not valid JSON-FG. The code in `properties` is authoritative, because some tools move or drop the top-level `id`. Its vocabulary borrows from public standards (section 2): severity separate from certainty, and headline, description and instruction, from CAP 1.2; action and status from ISIMIP; evidence from ISO 19157; withdrawal, aliases and version ranges from OSV. [reference/schema.json](reference/schema.json) is the full JSON Schema.

### 5.2 Record properties

| Group | Properties |
|---|---|
| Identity and outcome (required) | `code` (a prefix plus three or four digits, such as `CRU001` or `ERA5-014`; a hyphen is required after a prefix that ends in a digit, so every code parses one way), `kind` (`caveat` or `recommendation`; coverage is declared on products), `title`, `message`, `severity` (`info`, `warning` or `severe`) |
| Advice | `instruction`, `confidence`, `action`, `source_severity`, and `suggestions` (at least one, required for recommendations) |
| Scope | `facets`, `axes`, `dimensions` (values for other plugin dimensions, each checked against that plugin's schema), `region_ref` or `box` (geometry must then be null), `periods`, `recurrence`, `calendar`, and the fallback `time_start` and `time_end` |
| Emission | `min_overlap`, a threshold on `area_fraction` from 0 to 1 (default 0) |
| Provenance | `evidence` (ISO 19157-style `{method, measure, result, script, notes}`), `references`, `aliases` |
| Lifecycle (record time, never data time) | `status` (`draft`, `reviewed` or `deprecated`), `created`, `updated`, `withdrawn`, `supersedes` |
| Extensions | `x_*` fields, kept and ignored by the engine |

[reference/decisions.md](reference/decisions.md#record-properties-in-full) describes each property.

### 5.3 Loader checks

The JSON Schema covers structure; the loader checks what a schema cannot express and reports every error with the file, the feature's position and its code. Codes are unique in the Index; each pack's codes belong to a prefix it owns, and no two packs claim the same prefix (`QE` is reserved); rules added from Python may use any prefix except `QE`; `periods` lie inside `time` and dates are valid in their calendar; a box has `south` below `north`; every axis, facet, dimension, product and region name is declared and units match; every plugin dimension's value passes that plugin's schema and `parse_rule`; version-range bounds are dotted integers; both ends of an interval have the same precision, dates or timestamps, as JSON-FG requires; every product pattern matches a declared product (Q3); the axes, facets and dimensions a pack declares agree with the Index (Q13); and a `reviewed` record cites at least one reference (Q54). [reference/decisions.md](reference/decisions.md#loader-checks-in-full) gives the exact rules.

### 5.4 Packs

A pack is a directory with a `pack.toml` (read with the standard library's `tomllib`) and one or more FeatureCollection files. The toml declares the pack's name, version, owned code prefixes, licence and files; the axes, facets and plugin dimensions its records use, under `[axes.<name>]`, `[facets]` and `[dimensions]`, which must agree with the Index it is loaded into (Q13); its products under `[products.<slug>]` (aliases, variables, resolution, calendar, version, coverage as a time range plus an optional `box` or `region_ref`, and, for a regular grid, `grid` as first edge, last edge and step in degrees); and its named regions under `[regions.<namespace>]`. A FeatureCollection may also carry a `metadata` header in the style of EUROCAE ED-318, which must agree with `pack.toml`. [reference/examples/pack.toml](reference/examples/pack.toml) is a complete example. An irregular grid or a callable coverage is declared in Python. Loading a pack never runs code, so packs from untrusted sources are safe to load.

### 5.5 Example record

CRU001, the running example. Its region list, start date, `min_overlap` and draft status are author choices, and the evidence numbers come from the design research.

```json
{
  "type": "Feature",
  "id": "CRU001",
  "geometry": null,
  "time": {"interval": ["2000-01-01", ".."]},
  "properties": {
    "code": "CRU001",
    "kind": "caveat",
    "title": "CRU TS precipitation falls back to climatology over much of Africa",
    "message": "Where no station lies within the correlation-decay distance (450 km for precipitation), CRU TS sets the monthly value to the 1961-1990 climatology and records stn = 0. Over the eight IPCC AR6 African land regions, the share of land cells with stn = 0 rose from 6.8% in 1973 to 34% in 2022. In those cells, year-to-year variability and trends are not observed.",
    "instruction": "Read the stn variable for the cells and months you use. Treat months with stn = 0 as climatology, not observations, and report how many such months your result depends on.",
    "severity": "warning",
    "confidence": "observed",
    "action": "use_with_caution",
    "facets": {"product": ["cru_ts"], "variable": ["pre"], "version": {"versions": ["4.07"]}},
    "region_ref": ["ar6:SAH", "ar6:WAF", "ar6:CAF", "ar6:NEAF", "ar6:SEAF", "ar6:WSAF", "ar6:ESAF", "ar6:MDG"],
    "calendar": "standard",
    "min_overlap": 0.1,
    "evidence": [{"method": "derived", "measure": "Share of land cells with stn = 0 (annual mean, not area-weighted), CRU TS 4.07 precipitation, eight IPCC AR6 African land regions", "result": {"1973": 0.068, "2020": 0.41, "2022": 0.34}, "notes": "Computed from GLHE's public CRUTS.zarr during the queryearth design research. The share varies from year to year, so this record is provisional; the computed rule CRU002 checks stn per cell and month."}],
    "references": [{"type": "article", "citation": "Harris, I., Osborn, T. J., Jones, P. and Lister, D. (2020). Version 4 of the CRU TS monthly high-resolution gridded multivariate climate dataset. Scientific Data 7, 109.", "doi": "10.1038/s41597-020-0453-3"}],
    "status": "draft",
    "created": "2026-10-09T00:00:00Z",
    "updated": "2026-10-09T00:00:00Z"
  }
}
```

## 6. Geometry semantics

This section fixes what a shape means, so that every implementation and every consumer adapter gives the same answer at the antimeridian, at the poles and on cell edges. The failures it prevents are silent: the wrong shapes pass validity checks.

### 6.1 Motivating failures

Each case was reproduced in memory during the design research and again while drafting ([reference/background.md](reference/background.md#geometry-evidence) has the full table). A **box over Fiji written naively** as the ring (170, -20), (-170, -20), (-170, -10), (170, -10) is valid to shapely but covers the other 340 degrees of longitude, and regionmask (a Python package that masks gridded data by region) selects 13,600 cells of a 0.5 degree grid instead of 800. A **polar-stereographic domain**, a ±1,500 km square in EPSG:3995 (the Arctic polar stereographic projection), has vertex latitudes of only 70.65 to 76.26 degrees; its naive longitude-latitude polygon intersects itself, and nothing in the vertex bounds says it covers the North Pole. A **region crossing 180** loses half its 800 cells in regionmask under either longitude convention, without an error. And with **edge meaning left undeclared**, the box from -179 to 179 in longitude and -80 to 80 in latitude is almost the whole globe to shapely but 0.55% of the Earth to the geodesic area of pyproj, the Python interface to the PROJ projection library.

### 6.2 Canonical representation and normalisation

Coordinates are float64 (longitude, latitude) in degrees on WGS84. Stored longitudes lie in [-180, 180] and latitudes in [-90, 90]; a latitude outside that range by more than 1e-9 degrees is an error, and a smaller excursion is clamped. Edges are straight lines in longitude-latitude ("planar" edges), as RFC 7946 and GeoParquet's default `edges="planar"` declare them, so an edge written along 60N stays on 60N. Shapes are shapely Polygons or MultiPolygons in which no part crosses plus or minus 180, exteriors run counterclockwise and holes clockwise, and a third coordinate (altitude) is dropped.

Every record geometry, query polygon and grid outline is normalised once, when it is loaded or built. The steps run in this order because pole detection needs the ring before it is cut, and the cut needs a valid polygon:

1. **Wrap** every longitude exactly into [-180, 180]. The common formula `((x + 180) % 360) - 180` rounds, so 179.99999999999997 becomes -180.0; `wrap_lon` uses `math.fmod`, which is exact, and keeps both 180 and -180.
2. **Unwrap and count turns.** Take every step between consecutive vertices the short way, so the ring becomes continuous in longitude; a step of exactly 180 degrees and a full-turn step of exactly 360 degrees keep their written direction. The steps of a closed ring sum to 360 times the winding number: 0 for an ordinary ring, plus or minus 1 for a ring that goes once around a pole, anything else an error. This is the winding-sum idea of mom6_forge's `_encircles_globe` helper, written fresh; vertex latitudes and thresholds are not used.
3. **Close pole rings** along latitude 90 or -90. `polygon(pole="auto")` picks the pole on the side of the ring's mean latitude, records the choice on the `Space` and logs it at debug level (Q14), and `from_grid()` keeps the candidate that covers the grid's middle node.
4. **Repair** with shapely `make_valid`, keep the polygon parts (two levels deep) and union them. A shape left empty is a load error, never a rule that silently matches nothing, and `buffer(0)` is never used.
5. **Split** at plus and minus 180 by intersecting with 360 degree strips and shifting each piece by whole turns, which is exact.
6. **Orient** with shapely `orient_polygons`.

Holes are normalised as separate rings, so a hole may itself enclose a pole. Boxes, longitude arcs and latitude bands are built as polygons directly and never pass through ring normalisation. Reading every edge the short way is a deliberate departure from RFC 7946 for edges longer than 180 degrees (Q60), and it is what makes the naive Fiji ring the intended 20 degree box. [reference/geometry.py](reference/geometry.py) is the reference code for these steps and for the area below, and [reference/decisions.md](reference/decisions.md#normalisation-steps-in-full) states each step in full.

### 6.3 Boxes, closed sets and areas

A box is a longitude arc plus latitude limits, `(west, width, south, north)`, with `west` in [-180, 180) and `width` in (0, 360]. A query uses `box_arc(west, width, south, north)` or `box(west, south, east, north)`, where `east < west` crosses the antimeridian and `east == west` is an error (`lat_band()` gives the full circle). Only `west` is wrapped and `width` is kept: wrapping the two ends separately is the bug CrocoDash fixed in #283. A longitude x lies on the arc when `(x - west) mod 360 <= width` ([reference/decisions.md](reference/decisions.md#boxes-in-full)).

Predicates use closed sets: a point query uses prepared `covers`, a polygon, box, band, grid outline or cells uses prepared `intersects`, and the bulk path uses `shapely.intersects_xy`, never `contains_xy`. (A prepared geometry is one that shapely has preprocessed so that repeated tests against it run fast.) In longitude-latitude a pole is a line, so a point at latitude 90 or -90 is tested with `intersects` against the whole pole edge (that latitude at every longitude); otherwise a sector box from 0E to 90E reaching 90N would miss the point (123, 90). Closed sets matter because real grid points sit on rule edges: of the 1,681 ERA5 0.25 degree points in the closed square [0, 10] by [0, 10], `contains_xy` finds 1,521 and `intersects_xy` all 1,681 (measured while drafting). The cost is deliberate over-warning: a query polygon that only shares an edge with a rule matches with `area_fraction` 0.0, and the rule's `min_overlap` decides whether `emit()` shows it ([reference/decisions.md](reference/decisions.md#closed-set-predicates)).

`overlap_km2` is the area of the intersection of the rule shape and the query shape, and `area_fraction` divides it by the area of the query shape. shapely computes the intersection in longitude-latitude, which is exact under planar edges. Areas use a closed form that needs only `math`: by Green's theorem the spherical area is a sum over edges of an exact per-edge integral, `dlon * sin(mean latitude) * sin(dlat / 2) / (dlat / 2)` in radians, and an edge along a pole gives a pole cap its area. It matched pyproj's spherical geodesic area on densified polygons to within 2e-10 to 5e-9 relative error in the design research. Square degrees are not areas: the box [0, 10] by [40, 45] is half of [0, 10] by [40, 50] in square degrees, but 0.5218 of its area.

### 6.4 Not supported

Great-circle edges (densify such sources first); edges longer than 180 degrees of longitude other than full-turn edges (write a box, or add vertices); a ring read as "the larger side", since queryearth never chooses a ring's side by size or orientation and regions larger than a hemisphere are written as pole caps, boxes and bands; shapes containing both poles, and rings that wind more than once; coordinate systems other than CRS84; and rule geometries other than polygons, multipolygons and null. [reference/decisions.md](reference/decisions.md#normalisation-steps-in-full) explains each.

## 7. Time semantics

These rules make time comparisons independent of calendars, safe for any year, and exact at interval ends.

### 7.1 The civil-date key and its wire format

The usual time types fail in ways that matter for climate and model data: numpy `datetime64[ns]` wraps silently outside 1677-09-22 to 2262-04-11, Python `datetime` covers years 1 to 9999 in one calendar, cftime raises `TypeError` when comparing two calendars, and numeric offsets mean different dates in different calendars ([reference/background.md](reference/background.md#time-evidence)). queryearth compares civil dates instead: the labels (year, month, day, hour, minute, second) as written. Each instant becomes one integer:

```python
key = ((((year * 13 + month) * 32 + day) * 24 + hour) * 60 + minute) * 60 + second
```

This mixed-radix number sorts exactly like the tuple, including negative years, and ordering needs no calendar: 30 February in a `360_day` calendar sorts between 29 February and 1 March. `interval()` and `from_bounds()` accept wire strings, `datetime` values, cftime objects, numpy `datetime64` values in any unit and pandas `Timestamp` values, recognised by duck typing without importing those libraries. All keys are UTC civil time, and second 60 is rejected.

On the wire, an end is inclusive at its stated precision: `"2006-12-31"` includes that whole day and `"2006-12-31T23:59:59Z"` that second. Version 1 has only these two precisions; a month is written as its first and last day, and the schema rejects `"2020-01"`. Wire dates, `datetime.date` values and `datetime64` values in days are day precision, and every datetime-like value is second precision, even at midnight: `interval(Timestamp("2020-01-01"), Timestamp("2020-01-09"))` ends with the first second of 9 January, while `from_bounds` reads the same pair as the days 1 to 8 January (section 8.3). Years with a sign or more than four digits (`"-5000-06-01"`, `"12000-01-01"`) are accepted for paleoclimate products, a documented extension beyond RFC 3339 and JSON-FG 1.0, so records that use them are not valid JSON-FG. Years are astronomical: year 0 is 1 BC, and a cftime object without a year zero is converted accordingly. [reference/decisions.md](reference/decisions.md#time-conversion-in-full) gives the conversion rules.

### 7.2 Intervals, recurrence and calendars

Inside the code every interval is half-open, [start, end), with `None` for an open end, so a closed wire end `"2020-01-09"` becomes key(2020, 1, 9) + 86,400. Adding a day never needs month lengths: past the last day of a month the sum lands on "day 0" of the next month, a slot no real instant uses, so overlap tests are exact without a calendar. Two intervals [a, b) and [c, d) overlap when a < d and c < b, and half-open intervals stop a boundary day from matching twice. A finding writes `time_overlap` back in closed wire form, and `time_fraction` is the overlap's length in days divided by the query's length in days, measured in the query's calendar; it is None when the query has an open end, and for a `standard` or `gregorian` query that starts before 15 October 1582, where proleptic Gregorian durations would be wrong (Q19); `julian` has its own day table (Q20) ([reference/decisions.md](reference/decisions.md#intervals-in-full)).

`properties.recurrence = {"months": [12, 1, 2]}` limits a rule to those calendar months; because the months are a set, a season that wraps the year end needs no special case. The rule's periods are intersected with the query, cut into calendar months by key arithmetic, and runs that touch are merged, so December joins the following January; December to February over CRU TS's record from 1901 to 2022 gives 123 runs. Against an open-ended query every month occurs, the rule matches, and `time_overlap` reports the intersection without expansion. Seasonal windows at day precision are not in version 1.

Every time specification carries a calendar name from the CF (Climate and Forecast) metadata conventions, such as `noleap` or `360_day`, by default `proleptic_gregorian`. The calendar validates dates (29 February in `noleap` is a load error), names the last day of a month and measures durations; it never orders them. When a rule and a query use different calendars, their dates are compared as civil labels: a `360_day` rule for 1 to 30 February 2000 matches a Gregorian query for 29 February 2000, with no `TypeError`. Physical time can then differ by a few days, which is acceptable for advisories and is documented. `standard` is treated as proleptic Gregorian for durations and validation, which is wrong only before 15 October 1582 ([reference/decisions.md](reference/decisions.md#calendars-in-full)). `time`, `periods` and `recurrence` are **data time**: when the data are affected. `created`, `updated` and `withdrawn` are **record time**: the lifecycle of the record itself. Query times are compared only with data time, and a withdrawn record never matches, whatever the query's time. "As of" queries against the records that existed at some past moment are not in version 1 (section 17).

### 7.3 Answers when the query has no time

A rule without time always passes. For a rule with time, each request takes its time from its own product's temporal coverage, lists `"time"` in `assumed` and gets a definite finding with `time_overlap` clipped to that coverage, so two products with different records give two findings with different overlaps (fixture 24). A query that names no product, and any rule evaluated on the base query of section 4.12, gets a finding conditional on `"time"` whose `time_overlap` lists the rule's own periods. The author confirmed this behaviour (section 18.1). GLHE reads each product's whole record and passes no time. Its query for CRU TS (coverage 1901-01-01 to 2022-12-31) returns CRU001 as definite, with `time_overlap` from 2000-01-01 to 2022-12-31 and `time_fraction` 0.189. A computed rule can return a finer `time_overlap`: CRU002 lists the flagged years, which is the "which months are weak" answer GLHE needs rather than a yes or no.

## 8. Query contract: query with the support

### 8.1 The contract

A query describes what the caller is about to use, not what the caller has in mind. A product's support is the set of cells and time steps that it actually contributes to the request. The adapter that reads the product knows the support and passes it, either as the query's space or as `Request.support`, or the product declares its grid and the engine derives the support from the caller's region (section 4.12). The core never buffers, never pads and never guesses a footprint: the only support it builds itself comes from a grid the product declares. Three problems show why ([reference/decisions.md](reference/decisions.md#why-the-support)):

- **Buffers distort.** GLHE retries an empty extraction with `polygon.buffer(0.5)`, but a buffer in degrees is anisotropic (at 70N, 0.5 degree of longitude is about 19 km and of latitude about 56 km), and the buffered outline is neither the lake nor the cells whose values are used.
- **Small regions vanish.** A 0.15 by 0.15 degree lake inside one 0.5 degree cell, but not over its centre, selects no cell under centre masking, and a rule over the western 40% of that cell does not touch the lake, yet affects the value the lake receives; `cells(..., mode="overlap")` selects the cell, and the rule matches with `area_fraction` 0.4.
- **Time stamps mislead.** A monthly value stamped 2020-01-16 stands for all of January, so a rule for 20 to 25 January, compared with the stamp, misses it, while the bounds [2020-01-01, 2020-02-01) overlap it.

### 8.2 Choosing a space and selecting product cells

A gridded product read for a region uses `cells()`; a model domain on a 2D grid uses `from_grid()` on its cell corners; a domain periodic in longitude (a Southern Ocean channel) uses `lat_band()`, because it has no bounding box or closed outline, and `from_grid()` detects such a grid (winding number 0 across 360 degrees) and raises an error pointing to `lat_band()` (Q15); objects known by id, such as the 5,782 lakes in the National Water Model retrospective v3.0 lake output, use `features()`. With `weighted_points()`, zero weights on land cells make `area_fraction` an ocean-only fraction. Any longitude convention is accepted: a lake from 350.0E to 350.15E and the same lake from -10.0 to -9.85 give the same findings. `cells(grid, region, mode)` takes a rectilinear grid as `(lon_edges, lat_edges)`, in any longitude convention, and returns the union of the selected cells as one space:

| Mode | Selects |
|---|---|
| `"centre"` | Cells whose centre the region covers. Can select nothing for a region smaller than a cell. |
| `"overlap"` (default) | Cells whose intersection with the region has positive area; for a region without area, such as a point, every cell that covers it. Never drops a small lake, and a region whose edge lies on a grid line does not pull in the neighbouring cell. |
| `"full"` | Cells the region covers completely |

The resulting `area_fraction` is relative to the support; a caller who also wants to know whether a rule touches the lake itself runs a second query with the lake polygon and a different `label`. A product that declares `Product.grid` gets this selection, in `"overlap"` mode, from the engine itself, and `cell_mask()` returns the same selection as a boolean array, so an adapter can read the product's data for exactly those cells.

### 8.3 Time, axes and facets

`from_bounds(starts, ends)` builds the query time from the bounds of the time steps used: the CF `time_bnds` variable, or bounds inferred from the step frequency. Each pair is read as CF defines it, start inclusive and end exclusive, so monthly bounds from 2020-01-01T00:00Z to 2020-02-01T00:00Z become the closed wire interval 2020-01-01 to 2020-01-31, which does not touch a rule that starts on 1 February. Bounds at midnight give day precision, and consecutive steps merge into one interval. A caller with a range of days uses `interval(start, end)` with dates, whose ends are inclusive; a caller whose end is exclusive, such as CrocoDash, whose run from `date_range[0]` to `date_range[1]` lasts `(end - start).days` days, passes the pair to `from_bounds([start], [end])` instead (section 15.1).

Axis values are given in the axis's declared unit, as a number or a closed range; a grid has a range of spacings, so pass the range. `resolution_of(lon2d, lat2d, unit="km")` returns (finest, coarsest): the shortest and longest cell edge, each measured as a great-circle length on a sphere of radius 6,371.0088 km. A 1/4 degree latitude-longitude grid from 60N to 70N gives (9.51, 27.80) km, because its east-west edges shrink with latitude. Pass cell corners, not a MOM6 supergrid, whose nodes are half a cell apart and give (4.75, 13.90); pass `x[::2, ::2]` and `y[::2, ::2]` instead. Facets are strings or tuples of strings, product names may be aliases, and an unknown name is an error.

Adapters should pass every dimension they know, including the variables of each request. An adapter that forgets `resolution` turns CROC102 into a conditional finding, so its message silently disappears from the log; one that sends a request without variables does the same to every rule that constrains `variable`, such as GLORYS001. Test adapters with `include_conditional=True`: every conditional finding there names a dimension the adapter could have supplied.

## 9. Matching engine and bulk path

Two entry points share one engine: `Index.query` answers one query, with any number of requests, and `Index.query_points` answers the same question for up to millions of points. The reference semantics are those of `RuleKind.evaluate(query)` and section 4.3; the Index's vectorised stages are only an optimisation of calling `evaluate` on every rule, and a property test must check that both give the same findings for random queries. For a rule kind it does not know, the Index uses the rule's `scope` as a prefilter and then calls the rule's own `evaluate(query)`, whose answer is final. Numbers labelled "this document's benchmark" were measured for this document, in memory, with Python 3.11.16, shapely 2.1.2 and numpy 2.4.6 on one core, against synthetic star-shaped rule polygons rather than real packs ([reference/background.md](reference/background.md#engine-measurements)).

### 9.1 The pipeline of `Index.query`

> **As built (2026-10-13):** the vectorised tables described below were implemented, then removed to keep the code small. `Index.query` now calls `evaluate()` on every active rule of each part, after any plugin prefilters (a `Dimension`'s optional `build()`), and each rule runs stages 1 to 7 for itself. At realistic pack sizes, tens to hundreds of rules, a query still takes milliseconds; the 10,000-rule targets of section 13 assume the tables. Section 17 lists the upgrade path.

For each declared facet the Index keeps a map from literal values (aliases resolved) to rule positions, a short list of rules with glob patterns, and parsed version ranges; for each axis, float64 arrays of bounds; for time, int64 arrays of each rule's civil-key envelope; for space, the envelope of every normalised part, a shapely STRtree over those envelopes and a cache of prepared geometries. Computed rules are stored in the same arrays, and withdrawn or superseded rules never enter them. The STRtree cannot be changed once built, so every `add` marks it stale and the next query rebuilds it, which took 3.3 ms over 10,000 polygons (this document's benchmark; [reference/decisions.md](reference/decisions.md#index-internals) tables every structure).

Stage 0 splits the query into its base query and one sub-query per request (section 4.12), and stages 1 to 8 run for each part. Each stage gives every surviving rule one of three states for its dimension, following section 4.3: it fails and is dropped, it passes, or it is undecided, which sets one bit in a small per-rule bit set. When `include_conditional` is False, any rule with a bit set is dropped at once, so a query that names no product drops every product-scoped rule at stage 1, before any geometry is touched.

0. **Prepare.** Normalise the query space once, resolve aliases, reject undeclared names, expand the facet shorthand and split the query. For every request, evaluate its product's coverage once, for QE001 and QE002 and to fill the request's time; fill its version; derive its support from `Product.grid` when the request gives none.
1. **Facets**, by set operations on literal values, `fnmatch` for patterns and integer tuples for versions.
2. **Axes and other plugin dimensions**, one vectorised interval test per axis the query gives; for each other plugin dimension, its prefilter if it has one, then `match()` on the surviving rules. Plugins marked `late` run after stage 5.
3. **Time**, an envelope test on the int64 key arrays, then the exact interval union and month recurrence for the survivors only.
4. **Spatial candidates**, from the STRtree with each normalised query part; object-id rules by set intersection.
5. **Exact test**, `shapely.intersects` against the prepared rule geometry, or `intersects_xy` for a point; both are closed-set tests.
6. **Measures**: area overlap (with shortcuts when one shape covers the other), time overlap and fraction, axis intersections and matched facet values. This stage dominates large queries.
7. **Findings.** A record builds a `Finding` from its outcome plus the match. A computed rule has its `requires` keys checked, and `check(query, match)` runs only when the match is definite. The coverage rule measures what lies outside each request's product coverage.
8. **Sort** by severity, kind, code and part.

The cheap, vectorised, non-spatial stages come first because most real rules are scoped by product, variable or time rather than by area; about 80% of ERA5's known issues need no polygon at all. No stage is worse than linear in the number of rules. A continent-sized query against 10,000 rules with no facet pruning took 47 to 57 ms, nearly all in polygon intersections, and 4.7 ms when product facets pruned most rules (this document's benchmark; [reference/decisions.md](reference/decisions.md#query-pipeline-in-full) states each stage in full).

### 9.2 Loading packs

Loading matters more than query speed for short-lived processes, such as stateless servers that reload on every call. Parsing dominates large packs and building geometries most of the rest, so the loader defers geometry: it validates properties and fills the facet, axis and time arrays at once, so every naming, schema and calendar error surfaces at load; it computes each ring's envelope and longitude-step sum in one pure-Python pass, normalising at load only the rings that cross the seam, enclose a pole or use longitudes from 0 to 360; and it builds, normalises and prepares a shapely geometry the first time its rule becomes a spatial candidate. A pack of 10,000 rules loaded in 0.67 s lazily and 1.21 s eagerly (this document's benchmark). The trade-off is that a self-intersecting polygon is repaired at first use rather than at load, so a pack linter in continuous integration should build every geometry eagerly.

### 9.3 The bulk path: `query_points`

GLHE wants a global per-cell map and CrocoDash wants masks over a model's cell centres: up to about a million points. `query_points(lon, lat, weights=None, time=..., axes=..., facets=..., requests=..., include_conditional=False)` returns a `PointResult` whose masks, weighted fractions and skipped rules are keyed by `(product, code)`, with product None for rules evaluated on the base query. Requests are expanded as in section 4.12, so each request gets its own default time and version, but the points themselves are the support of every request: `Request.support` must be None and `Product.grid` is not used. Points with a NaN coordinate are inside no rule. There is no `context`, so a computed rule needs a `mask()` hook to take part and is otherwise listed in `skipped`; conditional findings get no mask.

The points are bucketed into 64 × 64 tiles with a second STRtree over the tile boxes, and each candidate rule queries that tree twice, once with `covers` (tiles entirely inside, which need no point tests) and once with `intersects`, so only points near a rule's boundary are tested with `intersects_xy`. Points at latitude 90 or -90 are tested once per rule against the whole pole edge, so the bulk path agrees with the single-query path at the poles (fixture 5). Each rule with at least one point inside gets a boolean mask and its weighted fraction as `area_fraction`, and `PointResult.any(min_severity)` combines the masks of definite findings. A rule's `min_overlap` is never applied on the bulk path, because a bulk fraction is a share of the whole point set, not of one request.

With 10⁶ points and 300 rules, the tile path took 0.32 s for a global grid and 1.7 s for a regional grid that every rule overlaps, against 0.25 s and 8.0 s for the plain bounding-box approach (this document's benchmark); outlines that zigzag across a wide band remain slow. Masks are full boolean arrays, about 1 MB per matching rule per million points, so callers with more points should call `query_points` on chunks. `STRtree.query(points, predicate=...)` must not be used, because it prepares the points rather than the polygons. [reference/decisions.md](reference/decisions.md#bulk-path-in-full) gives the steps and a pseudo-code sketch, and [reference/background.md](reference/background.md#engine-measurements) the benchmark tables.

## 10. Inverse query: which products suit this request

The inverse query turns the question around. A caller describes where, when and which variable, and `suitable(query, variable, *, products=None, score=None, include_dropped=False)` returns a ranked `list[Suitability]` of the products that can serve the request, ordered by how many known concerns they carry. GLHE's roadmap asks for this as its "Global Product API"; CrocoDash mostly needs the coverage filter.

### 10.1 Contract

1. **Candidates.** By default, all products whose `variables` include `variable`, in name order. Named `products` go through alias resolution; an unknown name raises `UnknownNameError`, and a named product that does not offer the variable raises `ValueError`.
2. **One request per product.** For each candidate P, the engine adds `Request(P, variables=(variable,))` to the caller's query, which must carry no requests and no `product`, `variable` or `version` facet of its own, and runs the request machinery of section 4.12. P's omitted time and version come from P, and a P that declares a grid is judged on the cells the caller's region uses. Only definite findings of P's sub-query are used.
3. **Coverage filter.** P is dropped when QE001 or QE002 has action `do_not_use`, meaning the request lies entirely outside P's spatial or temporal coverage. A product only partly outside stays, and its SEVERE coverage finding counts against it.
4. **Score.** `score(P, q_P, findings)` returns a tuple of floats, where `q_P` is the caller's query with the single request for P; lower means fewer known concerns. The default is `default_score`.
5. **Order.** Sort by score, then product name, and return `Suitability(product, score, findings)`, with P's findings sorted as in `Index.query`.
6. **Dropped products.** With `include_dropped=True`, the products the coverage filter dropped are listed last, with their QE001 or QE002 findings, so an explanation can show them (Q33).

Callers pass their own region, such as the lake outline, not a support. If the query has no time, each product is judged over its own whole record, so products are compared over different periods; pass a time range to compare like with like. [reference/decisions.md](reference/decisions.md#inverse-query-in-full) gives each step in full.

### 10.2 The default score

The default score is a tuple of three terms, compared in order:

| Term | Definition | Why |
|---|---|---|
| `worst` | The highest severity value (20, 30 or 40) among the counted findings, or 0 | One severe concern outranks any number of minor ones |
| `burden` | The sum over counted findings of weight × area part × time part. Weights are 1 for INFO, 2 for WARNING and 4 for SEVERE; the area and time parts are `area_fraction` and `time_fraction`, each 1.0 when None. Rounded to 0.001. | How much of the request is flagged, and how badly. It is a weighted sum, not a fraction: one SEVERE finding over the whole request scores 4. |
| `misfit` | `max(0, log2(cell size / query size))`. Cell size is `Product.resolution` in km (a size in degrees is converted at the query's centroid latitude as the side of an equal-area square); query size is the square root of the query's area. 0 when the query has no area or the product declares no resolution. | How many halvings coarser a product cell is than the request; products at least as fine tie |

Counted findings are definite caveat and coverage findings whose `area_fraction` is not below the rule's `min_overlap`, the threshold `emit()` uses; a finding whose `area_fraction` is None always counts. Recommendations are advice about what to do, not concerns about the data, so they are not counted. The weights and the rounding are starting values to be tuned on GLHE lakes. Any function with the `ScoreFn` signature can replace the default; it is called once per product that passed the coverage filter, must have no side effects, and must return tuples of the same length for every product. `Suitability.score` is for ordering only and should not be shown as a quality number. The explanation is the attached findings, shown together with the products the coverage filter dropped. An empty findings list means only that no registered rule matched; consumers should word it as "no registered rule matched this request", and the documentation of `suitable()` describes its order as "fewest known concerns first". The documentation must also state the bias plainly: a product with fewer registered rules ranks higher simply because less has been written about it, and `Index.rule_counts()` lets a consumer show how many rules each product has (Q35).

### 10.3 Worked example: a lake with CRU TS, ERA5-Land and NWM

The pack is illustrative. It declares three products that all offer `pre`, with resolutions and periods from the design research: CRU TS 4.07 (0.5 degree, 1901 to 2022, global land), ERA5-Land (0.1 degree, 1950 onward, global land) and NWM retrospective v3.0 (about 1 km; coverage simplified here to the contiguous United States from February 1979). It holds CRU001 and CRU002, no rule for ERA5-Land precipitation, and no grids. The request is a hypothetical lake of about 150 km² near the equator in the Congo basin, inside the AR6 Central Africa region (CAF), for 1991 to 2020.

- **NWM** is dropped: QE001 reports the whole request outside its coverage with action `do_not_use`, before any download.
- **CRU TS** gets CRU001, with version 4.07 assumed, `area_fraction` 1.0 and `time_fraction` 7,671 / 10,958 = 0.700. CRU002 needs `cru_ts.stn`, which an inverse query normally lacks, so it is conditional and not counted. A 0.5 degree cell near the equator is about 55.6 km across and the lake about 12.2 km, so `misfit` is log2(4.54), about 2.18, and the score is (30, 1.4, 2.18).
- **ERA5-Land** has no findings, and its 0.1 degree cell (about 11.1 km) is finer than the lake, so its score is (0, 0, 0).

The result lists ERA5-Land, then CRU TS. ERA5-Land ranks first partly because this pack holds no rule about it, although ECMWF does publish ERA5-Land known issues. If GLHE passes the station counts, CRU002 becomes definite, and SEVERE where whole years are climatology, which pushes CRU TS further down. [reference/decisions.md](reference/decisions.md#inverse-query-in-full) has the full walk-through.

## 11. Emission and policy

Findings are the API. `Index.query` has no side effects: it returns a sorted list of `Finding` objects that a caller can filter, store with `to_dict()`, show in a dashboard or assert on in a test. `emit()` is an optional adapter that turns findings into log records, warnings or an exception, under a policy the caller controls. Warnings cannot be the API: Python's default filter shows an identical message only once per call site, so a loop over lakes hides repeats; `warnings.catch_warnings` changes process-wide state and is not thread-safe in Python 3.11 to 3.13; and server and web interfaces never see warnings at all ([reference/background.md](reference/background.md#emission-evidence)).

### 11.1 Modes and policy

The switch between logging, warning and raising follows xclim.

| Mode | What `emit()` does with each finding it keeps |
|---|---|
| `"warn"` (default) | `warnings.warn(text, category)`, where the category is `InfoAdvisory`, `WarningAdvisory` or `SevereAdvisory` by severity, all subclasses of `AdvisoryWarning(UserWarning)`. The warning instance carries the finding as `.finding`. |
| `"log"` | `logging.getLogger("queryearth").log(finding.severity, text, extra={"finding": finding})`. Severity values equal logging levels, so no custom level is registered; a `SEVERE` finding shows as `ERROR`. |
| `"raise"` | Raises one `AdvisoryError` whose `.findings` holds every kept caveat and coverage finding. If none is kept, nothing is raised and `emit()` returns normally. |
| `"ignore"` | Nothing; returns an empty list, so consumers can call `emit()` unconditionally |
| A sink: any function `(finding, text)` | Calls the function with each kept finding, recommendations included, and its message text, instead of logging or warning. `raise_at` still applies. GLHE can pass a function that publishes to its event bus. |

**Recommendations are logged at INFO.** In the log, warn and raise modes, every recommendation that survives the filters goes to the `queryearth` logger at `INFO`, whatever `min_severity` and `raise_at` say; a recommendation is never warned and never raised. This is the approved plan's rule: recommendations are emitted at info level by default and are also returned as data. `Policy(show_recommendations=False)` turns this off, and queryearth adds no logging handler. `emit()` drops conditional findings; caveats and coverage findings below `min_severity` (default `WARNING`); findings whose `area_fraction` is below the rule's `min_overlap`; codes or prefixes in `ignore`; drafts when `include_drafts` is False; and a second finding with the same code, query label and product in the same call. `raise_at` works with the log and warn modes: findings below it are reported first, then every one at or above it is raised together in one `AdvisoryError`, so every blocking problem shows at once. `emit()` returns the findings it logged or warned ([reference/decisions.md](reference/decisions.md#emission-in-full)).

The active `Policy` is held in a `contextvars.ContextVar`. `policy(**changes)` installs a modified copy for the duration of a `with` block and restores the previous one, even after an exception, and keyword arguments to `emit()` override it for one call. Each thread has its own context, and each asyncio task runs in a copy of the context that created it, so a policy set while serving one dashboard session or MCP request never changes another. In Python 3.11 to 3.13 a new thread starts with an empty context; to carry the policy into a new thread, submit `contextvars.copy_context().run`.

### 11.2 Message text

Every message starts with the code in brackets, then the title, the query label, the spatial overlap, the overlapping periods, and `draft` for draft rules:

```text
[CRU001] CRU TS precipitation falls back to climatology over much of Africa (lake 1234; area 100%; 2000-01-01..2022-12-31; draft)
```

The label makes messages for different requests differ, so the once-per-call-site filter never hides one lake behind another. The leading code lets users filter messages without changing code:

```bash
python -W "ignore:[CRU001]" run.py                   # hide one rule
python -W "ignore:[CRU" run.py                       # hide every code starting with CRU
python -W "error::queryearth.SevereAdvisory" run.py  # turn SEVERE findings into exceptions
```

`PYTHONWARNINGS` and pytest's `filterwarnings` accept the same strings, so the warning classes are exported at the package top level. A warning should name the user's line, so `emit()` walks outward to the first frame outside queryearth and `Policy.skip_packages` and passes that depth to `warnings.warn` and to logging, as pandas does; Python 3.11 has no `skip_file_prefixes`.

### 11.3 Warning fatigue and recommendations

A rule that fires on almost every request teaches people to ignore all advisories. GEN001 (section 12.2) fires for nearly every HydroLAKES lake against a 0.5 degree product, so it has severity `INFO`: at the default floor it is not emitted, but it stays in the findings. The defences, in order of preference: authors give an honest severity; a rule's `min_overlap` keeps a domain that only clips a regional caveat from warning; conditional findings are never emitted; repeats are dropped, and consumers make one query per case or lake, with one request per product, rather than one per chunk of work (section 15.1); and users silence codes or prefixes with `Policy.ignore` or `-W`. Recommendations are meant to be used as data: a consumer reads `finding.suggestions` and applies or records them, and `emit()` never applies a suggestion. [reference/usage.py](reference/usage.py) shows `emit()` under a policy that raises on SEVERE findings.

## 12. Authoring rules and the registry

Rules come from three authoring paths, and all three produce `RuleKind` objects that go through the same scope matching (section 4.3). A **data-only pack** is written by anyone, in a text editor, geojson.io or QGIS, runs no code when loaded, and suits documented issues with a fixed area, period, product, version or resolution (CRU001, ERA5-001, CROC101, CROC102). A **`ComputedRule` subclass** is written by Python developers, runs on import, and suits rules computed from the request or from data the caller holds, with tunable thresholds; an **`@index.rule` function** does the same for one short rule. Pick the simplest path that can express the rule.

### 12.1 Data-only packs

Section 5 defines the record and the pack, and [reference/examples/](reference/examples/README.md) gives a complete pack of 14 records. `index.load_pack(path)` validates each file against the JSON Schema with a small standard-library validator that implements exactly the keywords the schema uses ([reference/decisions.md](reference/decisions.md#schema-validator)), runs the loader checks of section 5.3, and returns the codes it loaded. The jsonschema package and pyproj are test extras, never run-time dependencies, and a test checks that the standard-library validator agrees with jsonschema on the example records and on broken variants. Not every editor keeps the JSON-FG `time` member (whether geojson.io does is unverified, and QGIS moves the top-level `id` into the properties), which is why the code in `properties` is authoritative and `time_start` and `time_end` are accepted as a fallback.

### 12.2 Computed rules

A computed rule is a `ComputedRule` subclass whose class keyword arguments give its code and scope (section 4.11), or a plain function wrapped by `@index.rule(code, ...)`, which takes the same keywords and its title from the docstring. Thresholds are class attributes, documented next to their source, so a reader can find and change them in one place. A rule that needs data the caller holds names the `Query.context` keys in `requires`; if a key is missing, the finding is conditional on `context:<key>` rather than silently dropped, and `check()` does not run. A rule without a `mask()` hook cannot run on the bulk path and is listed in `PointResult.skipped`. Section 16.2 shows CROC104 as a function rule, and section 12.4 describes CRU002.

GEN001, "the request is much smaller than the product cells that represent it", compares the caller's own area, passed in the context as `request_km2`, with the area of the support the query describes, and fires when the ratio is below 0.1 (an author choice); a rule cannot compare the support itself with one product cell, because the support is never smaller than a cell. GEN001 concerns whichever product supplies the support, so it declares the facet `product = ["*"]`: it is evaluated once per request, on that request's support (section 4.12), and it is conditional on `"product"` when the query names none. In the research prototype, a 6.7 km² lake was compared with a CRU TS cell of about 2,786 km² at 25.7S, a ratio of about 0.0024. Its code is in [reference/examples/README.md](reference/examples/README.md#gen001).

### 12.3 The Index, codes and lifecycle

Rules, products, regions, axes and facets live on an explicit `Index`; there is no hidden global registry. `Index.default()` is an application default created on first use, following pint's application registry, for scripts and notebooks. A library such as CrocoDash or GLHE keeps its own Index, so two consumers in one process never see each other's rules. Registering a code the Index already holds raises `DuplicateCodeError`, whether the rule comes from a pack, a class or a function, with one exception: redefining a rule with the same code and the same qualified name (module plus class or function), as re-running a notebook cell does, replaces it (Q10). This is a lesson from CrocoDash's `ProductRegistry`, whose class-level dictionary silently replaces a duplicate product, whose `loaded` flag never changes, and whose class-level state every caller in a process shares; queryearth keeps the automatic registration and fixes all three ([reference/decisions.md](reference/decisions.md#registry-lessons)).

A code is a prefix plus three or four digits, in the style of ruff and pylint (`CRU001`, `ERA5-014`), with a hyphen required after a prefix that ends in a digit (Q8). Prefixes are exclusive between packs, open to rules added from Python, and `QE` is reserved (section 5.3); they let users silence a family of rules (`ignore={"CRU"}`, or `-W "ignore:[CRU"`). A code is never reused for a different issue; a retired rule is withdrawn instead. Each product has a canonical lowercase slug and aliases, declared in `pack.toml` or with `Index.add_product`, which is needed when the coverage or the grid is a callable. The two consumers already name products differently (GLHE writes `CRUTS`, CrocoDash lower-cases names such as `glorys`), and aliases make both resolve to the same product. Versions use the ranges of section 4.8. `status` is `draft` (the default), `reviewed` or `deprecated`; every finding carries it, and `Policy(include_drafts=False)` keeps drafts out of emission. `created` and `updated` record when the record itself changed. A `withdrawn` rule is kept for history but never matches; withdraw a rule instead of deleting it or reusing its code. `supersedes` lists codes that stop matching while this rule is loaded, and `aliases` holds the source's own identifiers for the issue, such as an ECMWF known-issue number ([reference/decisions.md](reference/decisions.md#codes-versions-and-lifecycle)).

### 12.4 Raster-derived rules: CRU002

Some rules are best computed from a quality field the product itself ships. CRU TS ships `stn`, the number of stations within the correlation-decay distance behind each monthly value, capped at 8; `stn = 0` means the value is the 1961-1990 climatology (Harris et al. 2020). In v1 such rules run live in the consumer's adapter, which passes the data it already holds in `Query.context`. Two findings from the data (design research, on GLHE's public `CRUTS.zarr`) shape the rule:

- **Graded severity.** Climatology fill and station thinning are different problems. In a box over South Africa, the mean station count fell from 8.0 (1930s to 1990s) to about 3.5 (2010s) while the share of cells with `stn = 0` stayed at 2 to 10%. CRU002 reports `SEVERE` for years of climatology and `WARNING` for years with two stations or fewer on average.
- **Hysteresis.** Raw monthly flags flicker: from 1901 to 2022 there are 936,068 runs of `stn = 0`, with a median length of one month. Flagging a year only when at least 6 of its 12 months have `stn = 0` reduced this to 78,068 (cell, year range) runs. CRU002 also uses a lower threshold for leaving the flagged state (3 months, an author choice not yet tested on the data), and flags for the latest years are provisional because recent years are back-filled in later releases.

CRU002 returns a single finding with the worst grade and puts the years of each grade in `details`, which keeps one finding per rule per request. The graded code is in [reference/examples/README.md](reference/examples/README.md#cru002-graded-form), and the simple form (any `stn = 0` month is SEVERE) is in [reference/usage.py](reference/usage.py). When a consumer does not hold the data, or a bulk query needs the rule everywhere, the same rule can later be compiled offline into cell sets on the product's own grid, about 78,000 rows for all of CRU TS precipitation (design research; section 17; [reference/background.md](reference/background.md#cru-ts-station-counts)).

### 12.5 Extension points

Every part of queryearth that varies between users takes user code through a small, documented interface, so extending it never means forking the package. Plugins are passed explicitly to the Index or to a call; discovering them through entry points is a non-goal for v1 (section 17).

| To add | Write | Example |
|---|---|---|
| A new kind of scope: a hierarchy, a taxonomy, a network, any matching other than space and time | A `Dimension` plugin (section 4.13), passed to `Index(dimensions=...)` | Pfafstetter basins |
| A rule computed from the request or from data the caller holds | A `ComputedRule` subclass or an `@index.rule` function (section 12.2) | CRU002, GEN001, CROC104 |
| A computed rule on the bulk path | A `mask(lon, lat, query)` method on that rule (section 9.3) | A per-point station-count mask |
| A new kind of rule altogether | Any object with `code`, `scope` and `evaluate(query)` (the `RuleKind` protocol), passed to `Index.add` | A rule backed by a database lookup |
| Rules from another format | Build records and pass them to `Index.add`, or `Rule.from_feature` per feature | CAP alerts, a spreadsheet |
| Availability known only at run time | A callable `Product.coverage` | NWM's lakes (section 15.2) |
| An irregular product grid | A callable `Product.grid` | A curvilinear ocean model grid |
| Named regions | `Index.add_regions(namespace, regions)` | IPCC AR6 regions, countries |
| A ranking for the inverse query | A `ScoreFn`, passed as `suitable(score=...)` | A GLHE-specific skill measure |
| A destination for findings | A sink function as the `emit()` mode (section 11.1) | GLHE's event bus |

Two things are deliberately not pluggable: the geometry semantics of section 6 (straight longitude-latitude edges, closed sets, normalisation at load) and the civil-date time key of section 7. Every fixture and both consumers rely on them, and two meanings of "overlaps" in one Index would make findings incomparable; a different geometry or time model would be a new built-in, not a plugin.

## 13. Performance targets

Speed is not the binding constraint, except on the bulk path. At realistic pack sizes every per-request operation finishes in milliseconds, and import and load time matter more for short-lived processes, such as stateless MCP servers that reload a pack on every tool call and aim for about 100 ms per call. Targets are for a warm file cache on one core; cold starts on GLADE, NCAR's shared file system, were not measured. "Prototype" means the in-memory pipeline sketch of section 9 (numpy masks, an STRtree, prepared tests, vectorised spherical areas, frozen `Finding` objects), without property validation or computed rules; the targets leave headroom for both. The targets are checked by a benchmark script, not by unit tests, because timings on shared continuous-integration runners vary too much for pass or fail thresholds.

| Operation | Target | Measured basis |
|---|---|---|
| `import queryearth`, including interpreter start | ≤ 100 ms | Interpreter 22 ms; numpy, shapely and the standard-library modules used, 74 ms together (best of 5, this document). geopandas took 255 ms and xarray 314 ms in the design research, which is why the core does not import them. |
| Load a pack of 100 rules × 500 vertices | ≤ 20 ms | Lazy 9.0 ms, eager 43 ms (section 9.2); the design research measured 46 ms eager |
| Load a pack of 10,000 rules, about 1 million vertices | ≤ 1 s (provisional) | Lazy 0.67 s, of which 0.60 s is `json.loads`; eager 1.21 s. Property validation is not yet measured ([Q45](reference/decisions.md#engine-and-performance)), so the target is provisional and leaves little headroom. Past about 50,000 rules, the SQLite upgrade (section 17) opened and queried in 1.06 ms. |
| Point query, 10,000 rules | ≤ 1 ms | 0.021 ms in the prototype, including findings; 0.061 ms with the STRtree in the design research |
| Lake query (500-vertex outline), 10,000 rules | ≤ 5 ms | 2.2 ms for 7 findings with no facet pruning |
| Continent query (30 degree radius), 10,000 rules | ≤ 100 ms | 47 to 57 ms for about 240 findings with no facet pruning; 4.7 ms when product facets prune most rules |
| Resolution-only query, 10,000 rules | ≤ 2 ms | 0.79 ms for 396 definite findings, mostly building `Finding` objects |
| `query_points`, 10⁶ points × 300 rules | ≤ 3 s | Tile path 0.32 to 1.7 s, including the case where every rule overlaps the domain (section 9.3); the plain bounding-box path took 8 to 11 s there |
| `suitable()` over 10 products, lake-sized query, 10,000 rules | ≤ 50 ms | Ten one-product lake queries took 3.0 ms in the prototype |

## 14. Correctness fixture suite

Every implementation must pass the 28 fixtures in [reference/fixtures.md](reference/fixtures.md), and every consumer adapter must also pass the ones marked "adapter", building the query with its own code. Each fixture is data (records, a query and the expected findings), so other implementations can reuse it, and every expected number was computed while drafting or revising. They cover the exact longitude wrap and the antimeridian (fixtures 1 and 2); pole caps, polar domains and pole points (3 to 5 and 22); closed edges, holes, repair and polar bands (6 to 8); spherical area and the small-lake support problem (9 and 10); time bounds, untimed rules, open ends, recurrence, calendars and unusual years (11 to 16); resolution-only and conditional queries (17 to 19); aliases, wildcards and version ranges (20 and 21); requests, per-product default time and per-product support (23 to 25); the emission of recommendations (26); and the extension points, a plugin dimension and an emission sink (27 and 28).

## 15. Consumer integration

GLHE and CrocoDash are the first two consumers. The integrations below are **acceptance tests for the design**: if the API cannot express them simply, the design is wrong. They are not changes to make now; each would become its own pull request in the consumer's repository after a prototype exists. [reference/consumers.md](reference/consumers.md) gives each integration in full, with line references (CrocoDash `main` at 507f2d6b, GLHE `main` at e26898d), complete sketches, and the changes each consumer needs outside queryearth. `sp` is `queryearth.space`, and `ADVISORIES` and `INDEX` are each consumer's own Index.

### 15.1 CrocoDash

**In short.** CrocoDash needs queryearth to check one model domain, one date range and several forcing products in a single call, to return model-parameter recommendations for the domain, and to stop case setup before anything is written when a product cannot cover the request.

The hook goes in `Case.configure_forcings`, directly after `config |= self.fcr.run_configurators(None)` (`CrocoDash/case.py:642`), because the CICE, WW3, runoff and chlorophyll products are only chosen inside the configurators, and because a coverage error raised there comes before stale outputs are deleted and `config.json` is written. The adapter makes one query per case: the space `sp.from_grid(grid.qlon, grid.qlat)` from the grid's cell corners (`sp.lat_band(...)` for cyclic domains); the date range through `qe.from_bounds([start], [end])`, because CrocoDash's end date is exclusive; `resolution` from `sp.resolution_of(...)`; the facet `model = "mom6"`; one `qe.Request(product, variables=...)` per forcing product, with the variables CrocoDash reads from it; and the case name as label. Model-level rules such as CROC101, CROC102 and CROC104 are evaluated once, on the domain; product rules and coverage once per request. The adapter then emits caveats and recommendations, emits coverage findings last in raise mode, and stores every finding's `to_dict()` in `config.json`.

Coverage findings raise `AdvisoryError`, so `configure_forcings` fails before writing anything; with `strict=False`, a new keyword, they warn instead (Q47). Caveats warn, recommendations are logged at `INFO` and recorded in `config.json` under `"advisories"` (Q48), and suggestions are not applied in v1. **Acceptance criteria**, in full in [reference/consumers.md](reference/consumers.md#crocodash):

1. An Arctic domain (EPSG:3995, 25 km) yields CROC101 and CROC104 as definite recommendations; CROC104 suggests the MOM_input parameter `DT` from the domain's finest spacing, and both suggestions are logged at `INFO` and recorded in `config.json`.
2. A 1/12 degree Gulf of Mexico domain yields CROC102 as a definite finding with its `axes` overlap.
3. A Pacific domain that crosses the antimeridian and a cyclic Southern Ocean channel produce no findings from rules on the far side of the globe.
4. A date range outside a product's coverage produces QE002, and `configure_forcings` raises and leaves the case as it was; with `strict=False` it warns.
5. `process_forcings`, the recipe code and the bundle code still read a `config.json` that contains `"advisories"`.
6. A date range outside the coverage of two products produces two QE002 findings, and the `AdvisoryError` holds both.
7. A GLORYS-forced case starting in 1995 yields GLORYS001 as a definite caveat, because the request carries the variables CrocoDash reads.

### 15.2 GLHE

**In short.** GLHE needs queryearth to check one lake against several products in a single call, before anything is downloaded, and to turn the CRU TS station counts it already reads into graded, per-year caveats.

GLHE processes one HydroLAKES polygon per run and passes no time range. The **pre-flight**, in `CLAY_driver.main` before the product loop, makes one query with the lake outline and one request per product, and skips products that cannot serve the lake. Gridded products such as CRU TS and ERA5-Land are judged on the cells the lake touches, derived from their grids; NWM, which serves 5,782 lakes rather than an area, gets a callable coverage that tests whether one of its lakes lies inside the polygon. Each request takes its time and version from its own product. Today NWM fails late, inside its accessor; with queryearth a QE001 finding with action `do_not_use` turns NWM off before any download and records why. The **accessor rule** runs in the CRU TS accessor once the data are known: it selects the overlap cells with `cell_mask()`, which replaces the `polygon.buffer(0.5)` fallback, passes their `stn` values and the lake's own area in the context, and gets CRU002 and GEN001 alongside CRU001 (Q46). Findings travel as `to_dict()` payloads on GLHE's event bus, into the README, a `<lake>_advisories.json` file and the dashboard. **Acceptance criteria**, in full in [reference/consumers.md](reference/consumers.md#glhe):

1. For a lake outside NWM's domain, the pre-flight produces QE001 with action `do_not_use` for the NWM request; NWM is skipped, the README says why, and no exception from the NWM accessor is logged.
2. For a lake smaller than one CRU TS cell, the support is one cell and no fallback runs; GEN001 is in the findings at `INFO` and is not emitted.
3. For a Congo-basin lake, CRU002 is `SEVERE` with the climatology years in `time_overlap`, and CRU001 is definite with `space`, `time` and `version` in `assumed`.
4. For a South African lake, CRU002 grades rather than flags: `WARNING` for thin years, or nothing if its cells keep more than two stations.
5. `INDEX.suitable(qe.Query(space=lake), variable="pre")` ranks the products that offer precipitation for the lake, each gridded product judged on its own cells, without describing any of them as good.
6. The pre-flight's single query returns findings that each name their product, measured on that product's cells and over its own coverage.

### 15.3 Warning-fatigue trial

Requirement R15 asks whether a draft pack warns so often that people stop reading. Before 1.0, a draft pack is run, at the default policy, against 1,000 HydroLAKES lakes spread across size classes and regions and about 10 CrocoDash domains (regional, rotated, polar, antimeridian-crossing and cyclic). For each query the trial records how many findings are returned, how many `emit()` shows, and how many are conditional. Every code that `emit()` shows for more than half of the queries is reviewed: its severity is lowered, its `min_overlap` raised, or its scope narrowed. The one-half threshold is an author choice. The trial also settles Q11 and Q12 ([reference/decisions.md](reference/decisions.md#matching-and-scope)). It is an acceptance test of the design and has not been run.

## 16. Worked examples

These examples check that the data model can express real rules. "Illustrative" marks content not checked against a source, "fictional" marks invented places, feeds or authorities, and "author choice" marks a threshold or boundary a reviewer should question.

### 16.1 The example pack and its rules

The example pack encodes 14 rule records in one FeatureCollection, [reference/examples/rules.geojson](reference/examples/rules.geojson), with its products and regions in [reference/examples/pack.toml](reference/examples/pack.toml), and registers three computed rules and one product coverage in Python. [reference/examples/README.md](reference/examples/README.md) explains every rule, says which content is grounded and which is illustrative, and gives the setup code and the full expected findings of the five queries below. All 14 records validate against [reference/schema.json](reference/schema.json), one at a time and as a FeatureCollection, and deliberately broken variants are all rejected. The pack lives only under the package's `tests/` and `docs/` directories, is excluded from the wheel, and carries the header line "Worked examples for the design document, not a curated pack", so it never ships as content (section 1.3).

The pack covers CRU TS precipitation (CRU001 to CRU004, with a withdrawn record and its replacement), four ERA5 known issues, GLORYS before the Argo float array (GLORYS001), four CrocoDash recommendations (CROC101 to CROC104), a predicate on the request itself (GEN001), NWM's lake coverage as a set of object ids, and three examples from outside earth science (BIO001, UAS001 and EPI001); the README describes each. Only CRU TS declares a grid, so the examples show both a derived support and a product judged on the caller's own geometry. The model parameters in CROC101 to CROC104 are illustrative; their messages are grounded in the ocean debugger knowledge base (paraphrased), and the `crs` suggestion in mom6_forge.

### 16.2 CROC104: a computed recommendation

CROC104 is the parameter-style answer to the Arctic example of section 1.1, registered on the example Index with the extra axis and facets ([reference/examples/README.md](reference/examples/README.md#index-setup-and-the-nwm-coverage) gives the full setup):

```python
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

Its scope is CROC101's, plus the axis bound `resolution > 0`, which every real spacing meets but which makes the rule conditional on `resolution` when a query leaves the spacing out, so `check()` never runs without it. For a domain whose finest cells are 8 km it suggests `{"target": "MOM_input", "key": "DT", "value": 240.0}`. The coefficient of 30 seconds per km is an illustrative author choice; a real rule would compute the time step from the model's stability limit for its fastest waves.

### 16.3 Five example queries

| Query | Expected findings | Notable absences |
|---|---|---|
| 1. Lake Kariba (GLHE): the outline, 2013 to 2022, one request for `CRUTS` with `pre`, station counts in the context | CRU002 (SEVERE); CRU001 (WARNING) with `assumed=("space", "version")`, `area_fraction` 1.0 and `time_fraction` 1.0; GEN001 (INFO) only if the lake covers less than a tenth of its support. Every finding has `product` `cru_ts` and `request` 0. | CRU004 (Kariba lies north of the box), CRU003 (withdrawn), QE001 and QE002; CROC102 is conditional on `resolution` and hidden |
| 2. An Arctic MOM6 domain (CrocoDash): a ±1,500 km polar stereographic square, 2020, resolution 8 to 12 km, model `mom6`, requests `glorys` (`thetao`, `so`) and `era5` (`t2m`, `skt`) | Base query: CROC101; CROC104 with `DT = 240.0` seconds; CROC102 with `axes` [8, 10). Request 1: ERA5-024, with `time_overlap` 2020-01-01 to 2020-02-29 and 2020-12-01 to 2020-12-31. GEN001 is conditional on `context:request_km2` for each request. | ERA5-001 and GLORYS001 (outside their periods), CROC103, QE001 and QE002 |
| 3. Resolution 8 km and nothing else, with `include_conditional=True` | CROC102, with `axes` [8, 8] | CROC103 (not at or above 25 km), CRU003 (withdrawn), QE001 and QE002 (no product); every other rule is conditional and names what it needs |
| 4. Bulk: every 0.5 degree cell centre (259,200 points), cosine-weighted, shorthand product `CRUTS` and variable `pre` | CRU001 and CRU004 masks, keyed `("cru_ts", code)`, with `assumed=("time", "version")` | CRU002 and GEN001 are in `skipped`, because they have no `mask()` hook |
| 5. `suitable()` for precipitation at Lake Kariba, 2013 to 2022 | `era5` first, with no findings; `cru_ts` second, with worst severity 40 from CRU002 | `glorys`, `gbif`, `demo_ili` and `nwm_retro` are not ranked, because they do not offer `pre` |

## 17. Non-goals for v1 and upgrade paths

Each non-goal is a deliberate deferral, not a rejection. The design keeps a path open for each, and the last column says what evidence should reopen it.

| Non-goal | Why not now | Upgrade path | Trigger to revisit |
|---|---|---|---|
| Curated content (rule packs, product declarations) | The author decided on an engine only. Curation is ongoing labour that needs review and citations, and source licences (CRU and CEDA, ECMWF's pages, the Climate Data Guide) were not checked. | Separate, versioned data repositories of reviewed packs, each owning its code prefixes; CC-BY-4.0, with references only where a source's licence is unclear. This follows OSV and timezonefinder's separate data package. | Two consumers need the same rules and someone commits to maintaining them |
| A user interface | The JSON Schema, geojson.io and GDAL or QGIS cover writing and reviewing packs | A separate package: a static Leaflet page running Pyodide (which ships shapely, according to its documentation), an ipyleaflet widget, and Panel components for GLHE's dashboard | People who do not program write rules regularly, or reviewers need to see scopes on a map |
| An MCP server | No v1 consumer needs one | A thin, stateless FastMCP server over `Index.query` and `Index.suitable` that loads data-only packs, never code packs from untrusted sources | An agent workflow (the CrocoDash MCP server or the ocean debugger) needs findings during a session |
| Vectorised prefilter tables (section 9.1) | Built and then removed on 2026-10-13 to keep the code small; a plain loop over `evaluate()` gives identical findings and takes milliseconds at hundreds of rules | Restore per-dimension tables before `evaluate()`: literal facet maps, axis bound arrays, int64 time envelopes and an STRtree over rule envelopes with seam and pole flags (commit f9a247b has the implementation and a property test against the plain loop) | A pack grows to thousands of rules, or per-query time matters to a consumer |
| An SQLite R*Tree backend | At 10,000 rules every method answers in about 10 ms or less; an index pays off only past about 50,000 to 200,000 rules | A backend protocol (candidate ids by box and time, then an exact check) over a three-dimensional R*Tree on longitude, latitude and time, with seam boxes split into rows and float32 bounds used only as a prefilter. At 1,000,000 rules it measured 4.7 ms per point query against 190 ms for a linear scan. | An Index grows past about 50,000 rules, or loading becomes too slow for stateless servers (parsing a 10,000-polygon GeoJSON took 0.82 s, against about 1 ms to open and query an equivalent SQLite file) |
| A HEALPix or MOC cell store | Too much machinery for 10 to 1,000 rules; needs compiled backends (healpix-geo, or mocpy with astropy); the research's pure-Python HEALPix code was never checked against healpy; MOC time has no civil calendars | Compile spatial scopes into ranges of equal-area cells, and export MOC 2.0 for interoperability | Derived layers dominate the content, or Indexes reach millions of cell flags |
| CQL2 as a query input | v1 adopts CQL2's semantics, not its syntax; parsing adds dependencies | An optional extra that translates CQL2-JSON into a `Query` with cql2-rs | A consumer already holds CQL2 filters, for example from a STAC or OGC API Records client |
| A unit-conversion library | Each axis declares one unit and a mismatch is a load error; km to degrees needs a latitude, so it lives in helpers such as `resolution_of()` | Optional conversion with pint at load and query time, into the axis's declared unit | Packs from different authors use different units for the same axis |
| Discovering packs through entry points | An explicit `load_pack(path)` keeps provenance visible, and code packs run arbitrary Python when loaded | A lazily scanned entry-point group, `queryearth.packs`, loading data-only packs by default (the first scan cost 240.8 ms over 305 distributions, a cached scan 5.4 ms, design research) | Packs are published as installable distributions |
| Subscriptions ("which past requests does a new rule affect?") | They need stored queries and a persistent store | Store past queries as records in the same schema and run new rules against them; the matcher works in both directions | Users want old CrocoDash cases or GLHE runs re-checked when a pack changes |
| Compiled raster-derived layers | v1 evaluates raster rules live in the consumer's adapter; compiling raises licensing and staleness questions and needs xarray or zarr | An offline compiler, shipped as an extra, writing cell sets on the product's own grid (section 12.4) | A consumer needs a raster rule for data it does not load itself |
| "As of" (bitemporal) queries | Data time plus the record lifecycle fields are enough for v1 | An `as_of` query field that filters rules by `created`, `updated` and `withdrawn` | Someone must reproduce which rules applied to a past run, or ERA5T-style revisions start to matter |
| Great-circle edges | v1 declares straight longitude-latitude edges, which match grid cells and boxes exactly | Densify sources that declare great-circle edges when they are loaded | A source supplies long great-circle edges |

## 18. Decisions and outstanding work

### 18.1 Decisions

**Taken by the author.**

- **Omitted time (confirmed).** When a query or a request names a product and omits time, the time defaults to that product's temporal coverage and the version to `Product.version`, and both are recorded in `Finding.assumed`. Without a product, time-scoped rules are conditional on `"time"` and still report their periods (sections 4.3 and 7.3). This settles the former Q1.
- **Several products in one query (decided).** Multi-product queries are first-class. A query carries `requests=[Request(product, variables=(...), version=None, time=None, support=None), ...]`, and the engine splits it into one sub-query per request, each with its own variables, default time and version (recorded in `Finding.assumed`) and support. A product may declare `Product.grid`, from which the engine derives that product's support for the caller's geometry with overlap semantics; otherwise the caller's geometry or the request's explicit support is used. Every finding names its product and request. The facet shorthand is still accepted and is expanded into requests by a documented rule (every listed variable goes to every listed product, as `Index.expand()` shows). `suitable()` is the same machinery plus ranking, and `query_points()` accepts requests and keys its results by `(product, code)` (section 4.12). This replaces the earlier advice to query one product at a time, and settles the former Q2 (splitting multi-valued facet queries) and Q34 (a per-product support for `suitable()`).
- **No upper limit on the Python version (decided 2026-10-12).** Python 3.11 or later; the floor comes from CrocoDash, and continuous integration tests every release from 3.11 to the newest.
- **Every part extensible (decided 2026-10-12, R17).** Each kind of scope other than space and time is a `Dimension` plugin, so complex matching in any other dimension is declared once and reused (section 4.13); `emit()` accepts a sink function (section 11.1); section 12.5 lists every extension point.
- **Every recommended default adopted (decided 2026-10-12).** The author accepted the recommended default of every numbered question. These were the ones to settle before the prototype:
  - **Q3.** Product patterns such as `["era5*"]` match canonical product names after alias resolution, and a pattern that matches no declared product is a load error, because it would otherwise look like "no known issues" (section 4.7).
  - **Q6.** A product whose coverage is a set of object ids, queried with a geometry, raises an error that names the namespace mismatch instead of quietly becoming conditional; callers use a callable coverage (section 15.2) or query with ids (section 4.9).
  - **Q7.** A callable coverage says "not served" by returning `sp.nowhere()`, which yields `area_fraction` 1.0 and action `do_not_use` (section 4.9).
  - **Q13.** `pack.toml` declares the axes, facets and plugin dimensions its records use, which must agree with the Index, and a product may give its coverage as a `box` or `region_ref`; irregular and callable grids stay in Python (section 5.4).
  - **Q47.** CrocoDash raises only on coverage findings and warns otherwise, with `strict=False` to opt out (section 15.1).
  - **Q48.** CrocoDash records findings in `config.json` under `"advisories"` (section 15.1).
  - **Q59.** Rules that constrain `product`, `variable` or `version` run once per request and all other rules once on the base query, and a support derived from `Product.grid` is listed in `assumed` as `"space"` (section 4.12).
  - **Q60.** The calendar is used for durations as well as validation, and an edge longer than 180 degrees of longitude, other than a full-turn edge, is read the short way (sections 7.2 and 6.2).

  Every other numbered question, with its decision and reason, is in [reference/decisions.md](reference/decisions.md#questions-decided-by-adopting-their-defaults). The decisions that change a contract are written into the sections they concern, the API sketch and the schema.

**Taken while drafting.** The section drafts and two reviews disagreed in places. How each disagreement was settled is listed in [reference/decisions.md](reference/decisions.md#choices-made-while-drafting); the author adopted those choices with the defaults.

### 18.2 Outstanding work

These are actions, not choices. Q1, Q2 and Q34 were retired earlier, and the other question numbers are kept so that references stay stable.

**For the author.**

- **Q55.** Sections 1.1 and 16 and the CROC records paraphrase a private expert-interview knowledge base, without quoting it; that knowledge base must not be made public without authorisation. Confirm the paraphrased sentences are acceptable before this document is shared beyond the team.

**Checks done on 2026-10-12.**

- **Q56.** Citations spot-checked against Crossref and the publishers: Harris et al. 2020 (CRU TS v4, DOI 10.1038/s41597-020-0453-3) and Lellouche et al. 2021 (GLORYS12, DOI 10.3389/feart.2021.698876) are correct as written, and the GLORYS001 error figures (0.75 °C and 0.2 psu in 1993-2002, 0.45 °C and 0.1 psu in the Argo era) match the paper's text. Beck et al. 2014 is correct but is the biodiversity source behind BIO001, not a precipitation source; its DOI (10.1016/j.ecoinf.2013.11.002) was added, with Kadmon et al. 2004 (DOI 10.1890/02-5364) for BIO001's roadside-bias wording. `ar6:MDG` (Madagascar) is confirmed as the eighth African land region in the IPCC AR6 reference regions (Iturbide et al. 2020); the Mediterranean region MED, labelled Europe-Africa, lies outside the eight.
- **Q24.** JSON-FG details checked against the published standard, OGC 21-045r1 version 1.0.0: `time` and `place` are optional on a feature; `conformsTo` is required on the root object only and must list `http://www.opengis.net/spec/json-fg-1/1.0/conf/core`; `coordRefSys` too belongs only on the root object, CRS84 is written `http://www.opengis.net/def/crs/OGC/0/CRS84`, and it is the default when absent. The schema now enforces this, the example pack declares `conformsTo`, and section 5.1 says how queryearth departs from JSON-FG: one time member only, signed or five-digit years, and 30 February.
- **Q57.** UAS001's fictional zone has moved from a real location in western Scotland to Null Island (0N, 0E), the point in the Gulf of Guinea that geographic examples conventionally use, so no reader can mistake it for a real restriction.

**For the prototype and the consumers.**

- **Q49.** CRU002's exit threshold (3 months) and thin threshold (2.0 stations) are untested, and are applied to the support mean while the research measured per cell. Compute them from `stn` before writing tests, and mark the latest years as provisional in `details`.
- **Q45.** Measure the cost of property validation at load against the targets of section 13; the 10,000-rule target stays provisional until then.
- **Q37.** Tune the default score's weights, rounding and misfit term on GLHE lakes before 1.0.
- **Q46.** Switch GLHE's CRU TS extraction to the overlap cells, which the engine derives from CRU TS's `Product.grid`, as section 15.2 assumes; until that GLHE change lands, GLHE passes the padded box it actually averages as `Request.support`.
- **Q52.** Find one real user outside earth-system modelling before 1.0. The example pack encodes three non-earth-science examples against the schema, needing only two extra facets and one extra axis, but the general-purpose claim is untested.

## 19. Requirement and decision checklist

Requirements R1 to R16 are checked in the table of section 3; this table covers the author's decisions and the other commitments of the approved plan. "Review" means the row was checked by reading the cited sections against the approved plan. Automated checks were run with Python 3.11.16, shapely 2.1.2, numpy 2.4.6, jsonschema 4.26.0 and black 26.3.1 while revising and restructuring this document.

| Requirement or decision | Where it is met | How checked |
|---|---|---|
| Name `queryearth`, plain | Title, 0 | Review |
| Engine only; no curated packs shipped; the example pack is test and documentation data, excluded from the wheel | 1.3, 16.1, 17 | Review |
| Inverse query in v1 | 10, 16.3 (query 5) | Review |
| Per-request and bulk (about 10⁶ points) workloads | 9.1, 9.3, 13 | Measurements cited in sections 9.3 and 13 |
| Own thin matcher on shapely, written clean-room; the prior-art library is named only as prior art | 2 | A text search of every file finds the library's name only in section 2, and none of its identifiers anywhere |
| The generic matcher is called a commodity, plainly | 0, 1.3, 2 | Review |
| Python 3.11 or later, no upper limit, with no 3.12-only syntax; frozen dataclasses | 3 (R2), 4.11, 18.1, [reference/api_sketch.py](reference/api_sketch.py) | Every Python code block and file parses with `ast.parse(..., feature_version=(3, 11))` and `black --check` leaves it unchanged; the API sketch imports and runs |
| Scope beyond area and time; rules and queries may omit area and time | 4.2, 4.3, 4.6, 8.3 | Fixtures 12, 17 and 19 |
| Conditional findings, hidden by default and shown with `include_conditional=True` | 4.3, 9.1 | Fixture 19 |
| Axis values derived from a grid (`resolution_of`) | 8.3 | Fixture 18 |
| **Query by resolution only** | 0.1, 4.3 (first query row), 14 (fixture 17), 16.3 (query 3) | Fixture 17 |
| **Arctic domain yields a parameter recommendation** | 1.1, 16.2 (CROC104 computes the MOM_input `DT`), 16.3 (query 2), 15.1 (criterion 1) | The ocean debugger knowledge base was queried again while revising: it advises setting the time step from the smallest cells and a polar projection at high latitudes; the DT coefficient is labelled illustrative |
| Outcomes beyond warnings; severity equal to the logging levels, with confidence and action kept separate | 4.9, 12 | Review; the sketch's `Severity` values are 20, 30 and 40 |
| Recommendations emitted at INFO by default and also returned as data | 11.1, 11.3, `Policy.show_recommendations` in [reference/api_sketch.py](reference/api_sketch.py) | Fixture 26 |
| Record format: GeoJSON Feature with the JSON-FG `time` member, a JSON Schema and a standard-library validator | 5, 12.1, [reference/schema.json](reference/schema.json) | The schema passes `check_schema` for JSON Schema 2020-12; the 14 example records and the CRU001 block of section 5.5 validate; 14 broken variants are all rejected; the validator's keyword list was derived from the schema |
| Explicit `Index`, duplicate codes are errors, `__init_subclass__` registration and the `@index.rule` decorator | 4.11, 12.2, 12.3 | The sketch registers a `ComputedRule` and rejects a reused and a missing code |
| Non-goals for v1 (curated content, user interface, MCP server, SQLite and HEALPix backends, CQL2, unit conversion) | 17 | Review |
| Omitted time, confirmed by the author: with a product, time from its coverage and version from `Product.version`, both in `assumed`; without one, conditional on time with the rule's periods reported | 4.3, 4.12, 7.3, 18.1 | Fixtures 12, 21 and 24 |
| Several products in one query, decided by the author: `requests`, per-request defaults and support, `Product.grid`, findings that name their product, the expanded facet shorthand, `suitable()` and `query_points()` on the same machinery | 0.1, 4.11, 4.12, 9.1, 9.3, 10.1, 15.1, 15.2, 16.3, 18.1, [reference/api_sketch.py](reference/api_sketch.py) | Fixtures 23 to 25; the sketch constructs a query with two requests and a product with a grid |
| Query with the support, never a buffered geometry | 4.12, 8 | Fixtures 10 and 25 |
| Antimeridian, poles, edges and calendars handled once, at load | 6, 7, 14 | [reference/geometry.py](reference/geometry.py), run as written, reproduces fixtures 1 to 3, 7 and 22 and loses no polygon area on 3,000 random rings |
| Consumer integrations as acceptance tests (CrocoDash `case.py:642`, GLHE `CLAY_driver.py:140-162` and `CRUTS.py:119-125`) | 15, [reference/consumers.md](reference/consumers.md) | Review; CrocoDash line numbers were checked by the second reviewer at 507f2d6b; GLHE's were not checked locally |
| About 15 example rules, including three outside earth science, validate against the schema | 16, [reference/examples/README.md](reference/examples/README.md) | jsonschema 4.26.0, one at a time and as a FeatureCollection, against [reference/schema.json](reference/schema.json) |
| Model-parameter examples grounded or labelled illustrative | 1.1, 4.2, 16.1, 16.2, [reference/examples/README.md](reference/examples/README.md#grounding-of-the-model-parameter-examples) | Review against the knowledge base queries |
| Every part extensible: plugin dimensions for complex matching beyond space and time, emission sinks, and a list of every extension point | 4.13, 11.1, 12.5, [reference/api_sketch.py](reference/api_sketch.py) | The Pfafstetter plugin was run against the API sketch (nested, partial, disjoint and invalid codes); the schema accepts a `dimensions` block and rejects malformed names; fixtures 27 and 28 |
| Every recommended default adopted (2026-10-12), with the contract changes written in | 4.7, 4.9, 4.10, 4.11, 5.2 to 5.4, 6.2, 7.2, 8.2, 10.1, 10.2, 12.3, 18, [reference/decisions.md](reference/decisions.md#questions-decided-by-adopting-their-defaults), [reference/api_sketch.py](reference/api_sketch.py), [reference/schema.json](reference/schema.json) | The schema accepts `CRU001`, `ERA5-014` and `GLORYS001`, rejects `QE001`, `cru001` and `ABC12001`, and rejects a `reviewed` record without references; the example pack still validates; the API sketch imports with `Index.products`, `rule_counts()` and `include_dropped` |
| Restructured for reading: a main document with the narrative, decisions and contracts, and reference files for the detail | This file and every reference file | Every link resolves; every Python file and block parses and is black-clean; the examples validate against the schema file; the TOML parses |
