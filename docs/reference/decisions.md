# Decisions and detailed contracts

This file holds what [design.md](../design.md) condenses: the choices made while drafting, the numbered design questions with their decisions, and the detailed contracts behind the main document's sections. Section numbers refer to design.md. The author's decisions, including the adoption of every recommended default on 2026-10-12, are in its [section 18.1](../design.md#181-decisions), and the work still outstanding is in its [section 18.2](../design.md#182-outstanding-work).

## Choices made while drafting

**Taken while assembling and reviewing this draft.** The section drafts and the two reviews disagreed in places. These were settled as follows and are listed so they can be reviewed:

- Within the requests design: rules that constrain `product`, `variable` or `version` are evaluated once per request, and all other rules once on the base query, so model-level rules such as CROC101 appear once; GEN001 declares `product = ["*"]` so that it runs per request; a derived support is listed in `assumed` as `"space"`; `Index.expand()` shows the expansion; the shorthand gives every listed variable to every listed product.
- `emit()` logs recommendations at `INFO` in every mode except `"ignore"`, whatever `min_severity` says, with `Policy.show_recommendations` to turn this off. This follows the approved plan; the first draft had dropped them at the default floor.
- The calendar name is used for durations and for naming the last day of a month, not only for validation as the plan said (section [4.5](../design.md#45-time)).
- A full-turn edge of exactly 360 degrees keeps its direction, so planar caps and bands written as RFC 7946 polygons work, and edges longer than 180 degrees are otherwise read the short way, a deliberate departure from RFC 7946 (section [6.2](../design.md#62-canonical-representation-and-normalisation)).
- Findings carry `product`, `request` and `source_severity`, and axis overlaps are `AxisOverlap` values that keep open ends.
- Datetime-like values are second precision and dates are day precision; CrocoDash passes its exclusive end through `from_bounds` (sections [7.1](../design.md#71-the-civil-date-key-and-its-wire-format) and [8.3](../design.md#83-time-axes-and-facets)).
- `check()` runs only for definite matches; the bulk path applies the pole-edge test and never applies `min_overlap`.
- `Finding.assumed` lists only the product-filled dimensions that the rule constrains, in the order of `conditional_on`, so a time-only rule gets `("time",)`.
- `emit()` de-duplicates by code, query label and product, not by code and label alone, so two products partly outside coverage give two QE001 messages.
- Rules added from Python may use a code prefix that a loaded pack owns; prefixes are exclusive only between packs, and a duplicate code is always an error.
- `Policy.skip_packages` and `default_score` were added to the API sketch, because sections [10](../design.md#10-inverse-query-which-products-suit-this-request) and [15](../design.md#15-consumer-integration) use them.
- In Python, a bare string is shorthand for a one-item facet pattern list (the usage sketch relies on it); computed rules default to kind `caveat` and severity `WARNING`; `@index.rule` takes its title from the docstring.
- `cells(mode="overlap")` selects cells whose intersection with the region has positive area, so a grid-aligned region does not pull in its neighbours.
- Normalisation runs wrap, unwrap and count turns, close pole rings, repair, split, orient (section [6.2](../design.md#62-canonical-representation-and-normalisation)), the same steps as first proposed in a different order.
- Versions compare as dotted integers padded with zeros, in ranges and in `versions` lists, and a query version that is not a dotted integer never falls inside a range.
- A callable coverage is evaluated once per request, and its result serves both the request's time default and QE001 and QE002.
- `suitable()` is called with the caller's own geometry; products that declare a grid are judged on the cells that geometry uses (section [10.1](../design.md#101-contract)). The usage sketch passes cell corners, not a MOM6 supergrid, to `resolution_of()`.
- The computed-rule example "the support is smaller than one product cell" can never fire, because a support is at least one cell; it became GEN001, which compares the caller's own area with the support.

Two parts of the first choice, which rules run once per request and the `"space"` that a derived support adds to `assumed`, became Q59, and the calendar and full-turn-edge choices Q60; the author adopted both with the other defaults (section [18.1](../design.md#181-decisions)). The shorthand rule in the first choice is part of the author's decision on requests. The other choices above stand as drafted; several of them interpret the author's decisions: which dimensions `Finding.assumed` lists, GEN001's `product = ["*"]`, a callable coverage evaluated once per request, and `suitable()` taking the caller's own geometry.

## Questions decided by adopting their defaults

On 2026-10-12 the author accepted the recommended default of every numbered question. Each question below keeps its number from earlier drafts, so that references stay stable, with its decision and a one-line reason. The questions that were settled before the prototype (Q3, Q6, Q7, Q13, Q47, Q48, Q59 and Q60), the author's action Q55, and the remaining work (Q24, Q37, Q45, Q49, Q56 and Q57) are in design.md, sections [18.1](../design.md#181-decisions) and [18.2](../design.md#182-outstanding-work).

Decisions that change a contract are written into design.md, [api_sketch.py](api_sketch.py) and [schema.json](schema.json): `Index.products` (Q4), the optional `outcomes()` hook (Q5), a hyphen after a prefix ending in a digit (Q8), keywords inherited from an abstract base (Q9), replacing a rule that is redefined by the same function or class (Q10), the pole recorded on a `Space` (Q14), periodic grids refused by `from_grid` (Q15), the 1582 limit for `standard` durations (Q19), a day table for `julian` (Q20), `suitable(include_dropped=True)` (Q33), `Index.rule_counts()` (Q35) and a reference required for `reviewed` records (Q54). The others keep the draft as it was, or are plans for the prototype.

### Matching and scope

- **Q4.** `Match` now carries the resolved product name and the request position (section [4.11](../design.md#411-core-objects)). Should computed rules also reach the matched `Product` itself (its resolution, calendar or grid)? *Decided:* yes, through a read-only `products` mapping on the Index. *Why:* `Match` already carries the product's name, and a read-only mapping lets a rule read the product's resolution, calendar or grid without changing the Index.
- **Q5.** Should `RuleKind` gain an optional `outcomes(query, match)` method, so the vectorised Index need not repeat scope work for third-party rule kinds? *Decided:* yes, optional. *Why:* the Index could then do the scope work once for third-party rule kinds instead of each kind repeating it in `evaluate()`.
- **Q8.** The code pattern lets `ERA5001` parse as `ERA` plus 5001 or `ERA5` plus 001. *Decided:* require the hyphen when a prefix ends in a digit (`ERA5-001`). *Why:* prefix ownership depends on where the prefix ends, so a code must parse one way only.
- **Q9.** Should a `ComputedRule` subclass inherit class keywords (`index`, `facets`) from an `abstract=True` base? *Decided:* yes, merged, with the subclass's keywords winning. *Why:* a family of rules then states its shared index and scope once.
- **Q10.** Re-running a notebook cell that defines a rule raises `DuplicateCodeError`. *Decided:* allow replacement when the code and the qualified name (module plus class or function) both match; any other reuse stays an error. *Why:* re-running a cell is not a conflict, but any other reuse of a code is.
- **Q11.** `min_overlap` applies only to area. Add a time threshold? *Decided:* not in v1; `time_fraction` is always reported. Revisit after the warning-fatigue trial (section [15.3](../design.md#153-warning-fatigue-trial)). *Why:* there is no evidence yet that time overlap needs a threshold, and the trial will show whether it does.
- **Q12.** A polygon that only touches a rule matches with `area_fraction` 0.0 and is emitted under the default `min_overlap` of 0, so a grid-aligned domain next to a regional rule warns. *Decided:* keep this deliberate over-warning in v1 and revisit with the warning-fatigue trial (section [15.3](../design.md#153-warning-fatigue-trial)). *Why:* missing a boundary is worse than over-warning at it, and the trial will measure the cost.

### Geometry and time

- **Q14.** `polygon(pole="auto")` picks the pole on the side of the ring's mean latitude, a heuristic. *Decided:* keep it, record the chosen pole on the `Space` and log it at debug level; model domains use `from_grid()`. *Why:* the heuristic is right for ordinary polar rings, and recording the choice makes a wrong guess visible.
- **Q15.** Should `from_grid` accept grids periodic in longitude? *Decided:* not in v1; detect the case (winding 0, spanning 360 degrees) and raise with a pointer to `lat_band()`. *Why:* a periodic domain has no closed outline, and `lat_band()` already describes it.
- **Q16.** Is 1e-9 degrees the right tolerance for clamping latitudes just beyond plus or minus 90? *Decided:* yes. *Why:* it absorbs projection round-off and still rejects real errors.
- **Q17.** Should `cells()` accept curvilinear product grids? *Decided:* rectilinear only in v1. *Why:* a product with a curvilinear grid can declare a callable `Product.grid` instead.
- **Q18.** `resolution_of` reports the shortest and longest cell edge, so a 1/4 degree grid reaches "below 10 km" north of about 69N and fires CROC102. *Decided:* keep (finest, coarsest) as the default and add a nominal-spacing option if rule authors need it. *Why:* the exact range lets `Finding.axes` show which part of a grid a rule concerns.
- **Q19.** Durations treat `standard` and `gregorian` as proleptic Gregorian, wrong before 1582-10-15. *Decided:* return `time_fraction = None` for those calendars when the query starts earlier. *Why:* a missing fraction is better than a wrong one.
- **Q20.** Should `julian` get a day table for `time_fraction`? *Decided:* yes; its leap rule is one line. *Why:* with a day table, `time_fraction` need not be None for `julian`.
- **Q21.** Accept year-only or year-month dates on the wire (`"1990"`, `"1990-06"`)? *Decided:* not in v1, although it would be cheap: the key layout already leaves the slots (the end of month m is key(y, m, 32)). *Why:* dates and timestamps express every example, and the key layout keeps the option open.
- **Q22.** Recurrence holds months only. Add day-precision seasons (15 June to 15 September) or ED-318-style weekday and hour windows with a time zone? *Decided:* not in v1. *Why:* months cover every example except UAS001's weekday and hour windows.
- **Q23.** Signed and five-digit years go beyond RFC 3339. *Decided:* keep the extension, documented; writers use the standard form whenever the year fits. *Why:* paleoclimate products need such years, and the standard form keeps other tools working.
- **Q25.** Should a product be able to declare an ordered list of non-dotted versions (`GEBCO_2024`, `ERA5T`) so ranges work for them? *Decided:* not in v1. *Why:* exact `versions` lists cover the non-dotted versions in every example.
- **Q26.** ERA5-001 constrains no variable and so over-warns, and no vertical dimension is designed. *Decided:* real packs list variables; an Index that needs it declares a `pressure_level` or `depth` axis. *Why:* the scope model already offers both tools; the example over-warns only because it is an example.

### Outcomes, emission and the inverse query

- **Q27.** Should a product be able to declare a softer coverage severity? *Decided:* no; consumers adjust through `Policy` (ignore `QE002`, or set `raise_at=None`). *Why:* "outside coverage" should mean the same for every product, and tolerance belongs to the consumer.
- **Q28.** Should draft rules count by default, in emission and in `suitable()`? *Decided:* yes; v1 packs are written by their own users, and every finding shows its `status`. *Why:* in v1 the people who write a pack are the people who use it.
- **Q29.** Is `"warn"` the right default mode? *Decided:* yes, for scripts and notebooks; consumer libraries set `mode="log"` in their adapters. *Why:* a person running a script or notebook sees warnings without configuring logging, while libraries control their own output.
- **Q30.** Should `emit()` de-duplicate across calls within one context? *Decided:* not in v1. *Why:* cross-call de-duplication needs state that outlives a call, and query labels already keep messages for different requests apart.
- **Q31.** `check()` may return several findings, which `emit()` then collapses by key. *Decided:* document one finding per rule per request, as CRU002 does, rather than widen the key. *Why:* one finding per rule per request keeps the de-duplication key simple.
- **Q32.** Keep `Policy.skip_packages` (section [11.2](../design.md#112-message-text))? *Decided:* yes; Python 3.11 has no `skip_file_prefixes`. *Why:* without it, warnings point inside the consumer rather than at the user's line.
- **Q33.** Should `suitable()` return the products its coverage filter drops? *Decided:* yes, behind `include_dropped=True`, listed last with their QE001 or QE002 findings. *Why:* section [10.2](../design.md#102-the-default-score) says the explanation shows the dropped products too.
- **Q35.** Should the Index report how many rules exist per product, to expose rankings driven by missing rules (ERA5-Land in section [10.3](../design.md#103-worked-example-a-lake-with-cru-ts-era5-land-and-nwm))? *Decided:* yes; it is cheap. *Why:* rankings driven by missing rules are otherwise invisible.
- **Q36.** Variable names differ between products (`pre` in CRU TS, `tp` in ERA5). *Decided:* a pack uses one vocabulary in `Product.variables` and the `variable` facet; add per-product variable aliases if packs need them. *Why:* `suitable(variable=...)` matches names literally.
- **Q37.** The default score's weights (1, 2, 4), rounding, ordering and coarseness-only misfit are author choices, and point queries get no resolution term. *Decided:* tune on GLHE lakes before 1.0. *Why:* they are author choices with no data behind them yet.
- **Q38.** Without a time, `suitable()` compares products over different records. *Decided:* keep and document; pass a time range to compare like with like. *Why:* it follows from the confirmed omitted-time behaviour (section [7.3](../design.md#73-answers-when-the-query-has-no-time)).
- **Q39.** Should a generic predicate such as GEN001 ship as a built-in `QE` rule? *Decided:* not in v1; the engine stays content-free apart from coverage. *Why:* the author decided that the engine ships no content.
- **Q40.** The `action` vocabulary describes data use and does not fit rules such as a drone zone. *Decided:* leave `action` unset for such rules. *Why:* the action vocabulary describes data use.

### Engine and performance

- **Q41.** Bulk masks cost about 1 MB per matching rule per million points. *Decided:* full arrays and chunking advice in v1; add a fractions-only mode or packed masks if memory bites. *Why:* chunking bounds the memory without new API.
- **Q42.** Outlines that zigzag across a wide band defeat the tile shortcut (52 s in the pathological case). *Decided:* accept it. *Why:* it is a pathological case, not a target (section [9.3](../design.md#93-the-bulk-path-query_points)).
- **Q43.** Lazy geometry decoding defers repair to first use. *Decided:* a pack linter in CI that builds every geometry, rather than a strict load mode. *Why:* loads stay fast, and bad geometry is still caught before a pack is released.
- **Q44.** Should the tile count adapt to the number of points and the domain shape? *Decided:* fixed 64 × 64 in v1. *Why:* the fixed tiling met the bulk target in every benchmark case except the pathological one.
- **Q45.** Property-validation cost at load is unmeasured. *Decided:* measure it in the prototype against the load targets in section [13](../design.md#13-performance-targets) (20 ms or less for 100 rules of 500 vertices; 1 s or less for 10,000 rules). *Why:* the 10,000-rule load target stays provisional until then.

### Consumers

- **Q50.** Who builds the crosswalk from HydroLAKES ids to NWM lakes needed by id-based coverage? *Decided:* nobody in v1; GLHE uses the callable coverage of section [15.2](../design.md#152-glhe). *Why:* the callable coverage runs the same test without a crosswalk.
- **Q51.** Should ERA5-024 become a raster-derived rule on ERA5's own sea-ice mask? *Decided:* later, in a real pack. *Why:* real content belongs in packs, not in the engine or its examples.

### Project and content

- **Q53.** Who reviews curated packs, and where do they live, once someone publishes content? *Decided:* not needed for v1 (section [17](../design.md#17-non-goals-for-v1-and-upgrade-paths)); later, separate repositories reviewed through pull requests. *Why:* v1 ships no content.
- **Q54.** Should status `reviewed` require at least one reference? *Decided:* yes, enforced by the loader. *Why:* a reviewed rule should cite what it was reviewed against.
- **Q58.** The example records' lifecycle dates are placeholders. *Decided:* replace them when a real pack is made. *Why:* the example records are not content.

### Retired questions

- **Q1.** Omitted time: decided by the author (section [18.1](../design.md#181-decisions)).
- **Q2.** Splitting multi-valued facet queries: decided by the author through requests (sections [4.12](../design.md#412-several-products-in-one-query-requests) and [18.1](../design.md#181-decisions)).
- **Q34.** A per-product support for `suitable()`: decided by the author through `Product.grid` and requests (sections [4.12](../design.md#412-several-products-in-one-query-requests) and [18.1](../design.md#181-decisions)).

## Detailed contracts

Each subsection below gives the full text of a contract that design.md states in short form, under the section that states it.

### Conditional findings in full

Section [4.3](../design.md#43-matching-when-a-dimension-is-missing).

A computed rule that needs a `Query.context` key the caller did not pass is undecided in the same way, on `"context:<key>"`. So `conditional_on` names every dimension the engine could not decide: omitted by the query, not comparable with the rule's form, or a missing context key.

A rule therefore produces a finding exactly when no dimension fails. If `conditional_on` is empty the finding is **definite**; otherwise it is **conditional**. `Index.query` returns conditional findings only when called with `include_conditional=True`, and `emit()` never emits them, because they describe what might apply rather than what does. A month recurrence counts as a time constraint even when the rule's `time` member is null.

The fields of a conditional finding follow one principle: measures of the decided dimensions are filled exactly as for a definite finding, and measures of the undecided ones report the rule's own extent or nothing.

- Space undecided: `area_fraction` and `overlap_km2` are None.
- Time undecided: `time_fraction` is None, and `time_overlap` lists the rule's own periods. For a rule limited only by a month recurrence, `time_overlap` is empty and the months are given in `details["recurrence_months"]`.
- Axis undecided: `axes` holds the rule's own interval for that axis.
- Facet undecided: `matched_facets` leaves that facet out.
- A computed rule's `check()` does not run. The finding carries the rule's declared outcome (kind, severity, title, message, suggestions) and empty `details`, apart from `recurrence_months`.
- On the bulk path (section [9.3](../design.md#93-the-bulk-path-query_points)), a conditional finding has no mask and no weighted fraction.

The names in `conditional_on` are `"space"`, `"time"`, an axis name such as `"resolution"`, a facet name such as `"product"`, and `"context:<key>"` when a computed rule needs data the caller did not pass in `Query.context`. Axis and facet names share one namespace on the Index and may not be `space` or `time`, so the names are never ambiguous. They are listed in a fixed order: space, time, axes in declaration order, facets in declaration order, then context keys. `assumed` (section [4.3](../design.md#43-matching-when-a-dimension-is-missing)) uses the same order.

### Space forms in full

Section [4.4](../design.md#44-space).

Coordinates are float64 longitude and latitude in degrees on WGS84, longitude first (CRS84, as in RFC 7946). Edges are straight lines in longitude-latitude space ("planar" edges), which matches product grid cells and latitude-longitude boxes exactly. Every geometry is normalised once, when a record is loaded or a query is built: longitudes are wrapped exactly, rings that wind around a pole are closed along it, invalid polygons are repaired, shapes are split at plus and minus 180 and rings are oriented. Section [6](../design.md#6-geometry-semantics) specifies all of this.

**Rule space forms.**

| Form | How a record states it | Notes |
|---|---|---|
| Global | `geometry` is null, with no `box` and no `region_ref` | Matches any query space |
| Polygon or multipolygon | GeoJSON `geometry` | Holes are allowed |
| Box | `properties.box` = `{west, width, south, north}` | A longitude arc: west 170 with width 20 covers 170E to 170W; width 360 is a latitude band. Use a box for anything that crosses the antimeridian. |
| Named regions | `properties.region_ref`: one `namespace:id` string, or a list (a union) | Resolved at load time through regions registered on the Index (`Index.add_regions` or a pack's `[regions]` table). An unresolved reference is a load error. |
| Object ids | Python only: `sp.features(ids, namespace)` | A set of ids in a namespace, such as National Water Model lake feature ids |

**Query space forms**, built with helpers in `queryearth.space` (imported as `sp`):

| Helper | Builds | Typical use |
|---|---|---|
| `point(lon, lat)` | A point | A station or one grid cell centre |
| `polygon(shape, pole="auto")` | A normalised polygon from shapely, GeoJSON or a coordinate list | A lake outline or a drawn region |
| `box(west, south, east, north)`, `box_arc(west, width, south, north)` | A longitude-arc box; `east < west` crosses the antimeridian | A request bounding box |
| `lat_band(south, north)` | A full circle of latitude | Domains periodic in longitude, which have no bounding box |
| `from_grid(lon2d, lat2d)` | The traced outline of a 2D grid of cell corners, with pole detection | A rotated, polar or seam-crossing model domain |
| `weighted_points(lon, lat, weights)` | A point set with weights such as cell areas | Model cell centres |
| `features(ids, namespace)` | A set of object ids | Rivers or lakes identified by id |
| `cells(grid, region, mode)` | The union of the cells of `grid = (lon_edges, lat_edges)` that `region` uses (section [8.2](../design.md#82-choosing-a-space-and-selecting-product-cells)) | The support of a gridded product for a lake or a domain |
| `cell_mask(grid, region, mode)` | The same selection as a boolean (latitude, longitude) array on `grid` | Selecting the product's data for exactly the support cells |
| `nowhere()` | The empty space | A callable coverage that does not serve a query (section [15.2](../design.md#152-glhe)) |
| `resolution_of(lon2d, lat2d, unit)` | Not a space: the (finest, coarsest) cell spacing in km or degrees (section [8.3](../design.md#83-time-axes-and-facets)) | The value for the `resolution` axis |

**Predicate.** Space overlaps when the closed sets intersect, so a query that only touches a rule's boundary matches, and points on a rule's edge, on the split at plus or minus 180, or at a pole are inside. This deliberately over-warns at boundaries rather than missing them (section [6.3](../design.md#63-boxes-closed-sets-and-areas)).

**Overlap measure.** Every finding carries `area_fraction`, defined by the kind of query space, and `overlap_km2`, the absolute overlapping area:

| Query space | `area_fraction` |
|---|---|
| None | None |
| Point | 1.0 (a point that is not covered produces no finding) |
| Polygon, box, band, grid outline or cells | Spherical area of the intersection divided by the spherical area of the query (section [6.3](../design.md#63-boxes-closed-sets-and-areas)) |
| Weighted points | Sum of the weights of covered points divided by the sum of all weights (equal weights if none are given) |
| Object ids against object ids in the same namespace | Shared ids divided by query ids |
| Object ids against a geometry, or a geometry against object ids | Not comparable, so the finding is conditional on `"space"` (section [4.3](../design.md#43-matching-when-a-dimension-is-missing)), unless the Index has geometry for that namespace from `add_regions` |

When the rule is global and the query gives a space, `area_fraction` is 1.0. For coverage findings, `area_fraction` is the fraction of the query that lies outside the product's coverage.

**Minimum overlap.** The engine reports every overlap, however small. A rule's `min_overlap` (default 0) only stops `emit()` from emitting findings whose `area_fraction` is below it, so a large domain that clips the edge of a regional caveat is still visible as data without raising a warning. A finding whose `area_fraction` is None (the query gave no space, or space is undecided) is never dropped by this threshold, in `emit()` or in `default_score` (section [10.2](../design.md#102-the-default-score)).

### Time, axes and facets in full

Sections [4.5](../design.md#45-time), [4.6](../design.md#46-axes) and [4.7](../design.md#47-facets).

Records, packs and `Finding.to_dict()` use the `time` member of OGC JSON-FG 1.0 for data time:

| Form | Meaning |
|---|---|
| `{"date": "2020-01-09"}` | That whole day |
| `{"timestamp": "2020-01-09T06:00:00Z"}` | That second |
| `{"interval": [start, end]}` | A closed interval; each end is a date, a timestamp, or `".."` for an open end |
| `null` or absent | Always |

Interval ends are inclusive at their stated precision, so `["2000-01-01", "2006-12-31"]` includes all of 31 December 2006. JSON-FG allows one `time` member per feature, so a rule that applies in several separate periods lists them in `properties.periods`, a union of closed intervals inside the `time` member, which then gives their overall extent. `properties.recurrence = {"months": [...]}` limits a rule to those calendar months in every year of its periods, or in every year if it has no time. If an editor drops the JSON-FG member, the loader accepts `properties.time_start` and `properties.time_end` instead, the field names GDAL uses for JSON-FG.

Inside the code, each instant becomes a calendar-free integer key packed from the civil date and time, intervals are half-open, and every time specification carries a calendar name used for validation and durations but never for ordering (the plan said "validation only"; durations were added, section [18.1](../design.md#181-decisions)). Section [7](../design.md#7-time-semantics) specifies the key, calendars, recurrence and the measures `time_overlap` and `time_fraction`.

An axis is a named, ordered, numeric dimension that an Index declares with exactly one unit, for example `Axis("resolution", "km", "horizontal grid spacing")`. Other examples are `depth` in metres and `vertical_levels` as a count.

| Side | Form | Rules |
|---|---|---|
| Rule | `{"gt": x, "ge": x, "lt": x, "le": x, "unit": u}`: any subset with at least one bound, never both `gt` and `ge` or both `lt` and `le` | A missing bound is open. If `unit` is given it must equal the declared unit; a mismatch is a load error. The core does no unit conversion. |
| Query | A number `v` (treated as `[v, v]`) or a closed range `(lo, hi)` | For a curvilinear grid, pass `(finest, coarsest)` from `resolution_of()` |

The axis matches when the rule's interval and the query's range intersect, and `Finding.axes` records the intersection, so a reader can see that only the finest part of a grid (8 to 10 km of an 8 to 12 km grid) falls under a "below 10 km" rule. An axis name the Index has not declared raises `UnknownNameError` in records and queries alike, because a misspelled axis would otherwise look like "no issues". Conversions between km and degrees exist only in helpers that know a latitude, such as `resolution_of()`.

A facet is a categorical name declared on the Index. The default set is `product`, `variable`, `version`, `model` and `component`; an Index can replace or extend it. An undeclared facet name in a record or a query is an error.

- **Rule side.** A list of patterns (shorthand for `any_of`) or an object `{"any_of": [...], "none_of": [...]}`. In Python, a bare string is shorthand for a one-item list. Patterns use case-sensitive `fnmatch` glob syntax. A value matches when it matches some `any_of` pattern (or `any_of` is absent) and no `none_of` pattern. The `version` facet uses version ranges instead (section [4.8](../design.md#48-version-ranges)).
- **Query side.** One string or a tuple of strings. The facet matches when at least one query value matches, and `Finding.matched_facets` records which values did.
- **Product names.** Before matching, product values on both sides are resolved through the aliases products declare. Alias matching is exact and ignores case, so `CRUTS`, `CRU TS` and `cru_ts` name the same product. An unknown product name in a record or a query is an error, because a misspelled product would otherwise look like "no known issues".

These cases are easy to confuse, so they are stated exactly:

| Rule states | Query gives the facet | Query omits the facet |
|---|---|---|
| Nothing for this facet | Passes | Passes |
| `["*"]` | Passes for any value | Conditional on the facet |
| `["era5*"]` | Passes if some value starts with `era5` | Conditional on the facet |
| `{"none_of": ["tp"]}` | Passes unless every query value is `tp` | Conditional on the facet |

`["*"]` is therefore not the same as leaving the facet out: it says the rule concerns some value of the facet, so it is undecided until the query names one. Within one query, matching is done facet by facet: a query that gives variables `{pre, tas}` matches a rule for `pre` even if the caller reads `pre` from only one of its products. Products and their variables are therefore given as requests, one per product (section [4.12](../design.md#412-several-products-in-one-query-requests)), so that `cru_ts` with `pre` and `era5_land` with `tas` never match a rule for `era5_land` with `pre`. A `product` facet in a query is shorthand that the engine expands into requests by a documented rule (section [4.12](../design.md#412-several-products-in-one-query-requests)).

### Version ranges in full

Sections [4.8](../design.md#48-version-ranges) and [12.3](../design.md#123-the-index-codes-and-lifecycle).

The `version` facet uses ranges in the style of OSV:

| Field | Meaning |
|---|---|
| `introduced` | First affected version, inclusive. If absent, the range starts at the first version. |
| `fixed` | First version no longer affected, exclusive |
| `last_affected` | Last affected version, inclusive; used when no fix is known, never together with `fixed` |
| `versions` | Exact versions. Two dotted-integer strings compare as numbers, so `"4.7"` matches `"4.07"`; any other string is compared literally. |

A range with neither `fixed` nor `last_affected` is open-ended, and a list of range objects is a union. `{"introduced": "4.00", "fixed": "4.09"}` matches 4.07 and 4.08 but not 4.09. Bounds compare as dotted integers, padded with zeros to equal length: `"4.10"` is later than `"4.9"`, and `"4.07"` equals `"4.7"` and `"4.7.0"`. The same comparison applies to `versions` entries, so a product version written `"4.7"` matches CRU001's `{"versions": ["4.07"]}` as it would match an equivalent range. Versions that are not dotted integers, such as `ERA5`, `ERA5T`, `ERA5.1` or `GEBCO_2024`, can only be listed in `versions`, where they match literally; a range bound that is not a dotted integer is a load error, and a query version that is not one never falls inside a range. PEP 440 is not used: it needs the third-party `packaging` library, and most product versions are not PEP 440 versions. An omitted `version` is filled from the product as described in section [4.3](../design.md#43-matching-when-a-dimension-is-missing).

**Versions** use OSV-style ranges (section [4.8](../design.md#48-version-ranges)):

| Situation | `facets.version` |
|---|---|
| Found in CRU TS 4.07 only | `{"versions": ["4.07"]}` |
| Present from 4.00, fixed in 4.09 | `{"introduced": "4.00", "fixed": "4.09"}` |
| Present from 4.08, no fix known | `{"introduced": "4.08"}` |
| ERA5 2000-2006 stratospheric cold bias, rerun as ERA5.1 | `{"versions": ["ERA5"]}` |
| Affects the preliminary near-real-time stream too | `{"versions": ["ERA5", "ERA5T"]}` |

### Outcomes in full

Section [4.9](../design.md#49-outcomes).

Every match produces the same `Finding` type, and its `kind` says what sort of statement it is:

| Kind | Produced by | Fires when | Default severity | Carries |
|---|---|---|---|---|
| `caveat` | Records and computed rules | The query overlaps the scope | `WARNING` | `action`, `confidence`, `instruction` |
| `coverage` | The built-in coverage rule, from `Product.coverage` | Part of the query lies outside the product's coverage | `SEVERE` | `area_fraction` and `time_overlap` of the part outside |
| `recommendation` | Records and computed rules | The query overlaps the scope | `INFO` | `suggestions` |

#### Coverage findings QE001 and QE002

**Coverage** is declared on products, not written as records, because its polarity is the opposite of a caveat's: being outside produces the finding. It may be static, or a callable evaluated per query for availability known only at run time. One built-in rule per code evaluates the product of every request (section [4.12](../design.md#412-several-products-in-one-query-requests)), against that request's space and time: `QE001` for outside the spatial coverage and `QE002` for outside the temporal coverage (the prefix `QE` is reserved). Its action is `do_not_use` when the request is entirely outside and `use_with_caution` when it is partly outside. A coverage finding always carries the product's canonical name in `product`.

| | QE001: outside the spatial coverage | QE002: outside the temporal coverage |
|---|---|---|
| Fires when | Part of the query's space lies outside `Coverage.space` | Part of the query's time lies outside `Coverage.time` |
| `area_fraction` | The share of the query's space outside the coverage | None |
| `time_overlap`, `time_fraction` | Empty and None | The parts of the query outside the coverage, and their share of the query's duration (None if the query has an open end) |
| Coverage dimension is None | Never fires (global coverage) | Never fires (coverage at all times) |
| Query and request omit the dimension | Conditional on `"space"` | Never fires, because the request's time is filled from that coverage (section [4.3](../design.md#43-matching-when-a-dimension-is-missing)) |

#### Severity, confidence, action and suggestions

**Severity** is a three-level `IntEnum` whose values equal the `logging` levels: `INFO = 20`, `WARNING = 30`, `SEVERE = 40` (the number of `logging.ERROR`), so a logger can use `logger.log(finding.severity, ...)` directly. A source's own wording, such as "critical" in the ESGF errata service or "Extreme" in CAP, is kept verbatim in `source_severity`. "Outside coverage" is a kind, not a fourth severity, so how bad something is stays separate from whether the product can serve the request at all.

**Confidence** says how sure the source is, separately from how bad the problem is. It takes four of CAP 1.2's five certainty values: `observed`, `likely`, `possible` or `unknown` (the default).

**Action** says what to do with the data, following the ISIMIP caveat messages: `can_be_used`, `use_with_caution`, `do_not_use` or `replaced`. It is optional, and recommendations normally leave it unset.

**Suggestions** make a recommendation something a program can act on:

| Field | Meaning |
|---|---|
| `target` | Where the change goes, named by the consumer, for example `MOM_input`, `compset` or `user_nl_cice` |
| `key` | What to change within the target |
| `value` | Any JSON value |
| `rationale` | One sentence of explanation |

The engine never interprets `target` or `key`. CrocoDash may log a MOM6 suggestion, record it in the case's `config.json`, or apply it. `{"target": "MOM_input", "key": "DT", "value": 240.0}` is the suggestion CROC104 computes for an Arctic domain whose finest cells are 8 km (section [16.2](../design.md#162-croc104-a-computed-recommendation)), and `{"target": "MOM_input", "key": "THICKNESSDIFFUSE", "value": false}` is an illustrative suggestion for CROC102.

**No known concerns is not good data.** A query that returns no findings means that no registered rule matched, nothing more. `suitable()` ranks products by their known concerns and says so, and no part of the API reports "good" or "suitable" as a quality judgement.

**Order.** `Index.query` returns findings sorted by severity (highest first), then kind (coverage, caveat, recommendation), then code, then part: the base query first, then the requests in order (section [4.12](../design.md#412-several-products-in-one-query-requests)).

### Requests: an example

Section [4.12](../design.md#412-several-products-in-one-query-requests).

```python
lake = sp.polygon(lake_geojson)  # one outline for every product
found = index.query(
    space=lake,
    requests=[
        qe.Request("cru_ts", variables=("pre",)),  # support: the CRU TS cells used
        qe.Request("era5_land", variables=("tas",)),  # time: ERA5-Land's whole record
    ],
    label="lake 1234",
)
```

Here a rule about ERA5-Land precipitation gives no finding, because the second request reads `tas` only. No time is given, so each request's time is its product's temporal coverage, and its findings list `"time"` in `assumed`.

### Rule kinds in full

Section [4.10](../design.md#410-rule-kinds).

All rule kinds implement one protocol, `evaluate(query) -> Sequence[Finding]`, and all go through the same scope matching, so section [4.3](../design.md#43-matching-when-a-dimension-is-missing) applies to every kind.

| Kind | Written as | Example |
|---|---|---|
| Static record | A GeoJSON Feature in a pack, or a `Rule(...)` or record mapping passed to `Index.add` | CRU001, ERA5-001, CROC101, CROC102 |
| Computed (object predicate) | A `ComputedRule` subclass or an `@index.rule(...)` function | GEN001: the caller's region is much smaller than the support (section [12.2](../design.md#122-computed-rules)); CROC104: an Arctic domain's time step from its finest cells (section [16.2](../design.md#162-croc104-a-computed-recommendation)) |
| Raster-derived | A computed rule that reads data the caller already holds, passed in `Query.context` | CRU002: CRU TS cell-months with `stn = 0` in the cells used (section [12.4](../design.md#124-raster-derived-rules-cru002)) |
| Coverage | Built in, from `Product.coverage` | QE001, QE002 |

Raster-derived rules are evaluated live in v1, inside the consumer's adapter, on data it has already loaded; GLHE already reads CRU TS from a zarr store that contains `stn`. If a required context key is missing, the rule is conditional on `"context:<key>"` rather than silently skipped.

### Core objects in full

Section [4.11](../design.md#411-core-objects).

All core objects are frozen dataclasses ([api_sketch.py](api_sketch.py)). Everything except `Query.context` and the shapely and numpy members of `Space` is JSON-serialisable through `to_dict()` and `Rule.from_feature()`. The record properties (section [5.2](../design.md#52-record-properties)) map onto the fields of a static `Rule` and its `Rule.scope`: `box`, `periods`, `recurrence` and `calendar` become the scope's space and time, and `x_*` extension fields are kept on the side. Python 3.11 or later is supported, with no upper limit, and shapely 2.1 or later and numpy are the only third-party dependencies at run time; cftime, pandas and numpy date values are accepted by duck typing, not imported (section [7.1](../design.md#71-the-civil-date-key-and-its-wire-format)).

Objects that hold only scalars and tuples (`Interval`, `TimeSpec`, `Axis`, `Suggestion`, `AxisOverlap`) are hashable, and so is `Request`, whose `support` hashes by identity. `Space` and `PointResult` compare and hash by identity. Objects that hold mappings (`Scope`, `Query`, `Match`, `Finding`, `Rule`) compare by value, which the tests that compare the single and vectorised paths need, but they are not hashable: Python raises `TypeError` if one is used in a set or as a dictionary key. Key findings by `(code, query_label, product)` instead, as `emit()` does.

**Axis** has `name` (lowercase, unique among axes and facets, not `space` or `time`), `unit` (the only unit records and queries may use) and `description`.

**Product** and **Coverage**:

| Field | Type | Meaning |
|---|---|---|
| `name` | str | Canonical lowercase slug, for example `cru_ts` |
| `aliases` | tuple[str, ...] | Other names, matched exactly ignoring case, for example `CRUTS`, `CRU TS` |
| `variables` | tuple[str, ...] | Variables the product offers, under the pack's own variable names; used by `suitable()` |
| `coverage` | Coverage, or a callable `(Query) -> Coverage` | `Coverage(space=None, time=None)`; None means global or all time |
| `resolution` | (float, "deg" or "km"), or None | Native grid spacing; used by ranking (section [10](../design.md#10-inverse-query-which-products-suit-this-request)) |
| `calendar` | str | Calendar of the product's time axis |
| `version` | str or None | The version this application uses; fills an omitted `version` facet |
| `grid` | `(lon_edges, lat_edges)`, a callable `(Space) -> Space`, or None | The product's cells: the edges of a rectilinear grid, or a function that returns the cells a region uses. If declared, the engine derives a request's support from the caller's region (section [4.12](../design.md#412-several-products-in-one-query-requests)). |

Product names are global within one Index. Two packs that declare the same product name are a load error, unless the second declaration only adds aliases.

**ComputedRule.** A subclass declares its identity and scope with class keyword arguments, and defining the subclass registers one instance (examples in section [12.4](../design.md#124-raster-derived-rules-cru002) and [api_sketch.py](api_sketch.py)):

| Class keyword | Meaning |
|---|---|
| `code` | Required unless `abstract=True`. A reused code raises `DuplicateCodeError`. |
| `index` | The Index to register on; defaults to `Index.default()` |
| `abstract` | `True` for an intermediate base class that should not register |
| `kind`, `severity`, `title` | As for records; defaults `caveat` and `WARNING`. `title` defaults to the first line of the docstring. |
| `facets`, `axes`, `space`, `time` | The scope, in the same forms as a record; `space` also accepts a `Space` from `queryearth.space`, and `time` a `TimeSpec`. The Index checks every name. |
| `requires` | `Query.context` keys the rule reads. A missing key makes the finding conditional on `context:<key>`. |
| `suggestions` | Default suggestions for a recommendation; `check()` may replace them |

`evaluate()` matches the declared scope exactly as for a record. Only if the match is definite (`conditional_on` is empty) does it call `check(query, match)`; a conditional match yields a conditional finding with the declared defaults and empty `details`, and `check()` never runs with a context key missing. `check` returns `True` for one finding with the declared defaults, `False` or `None` for none, a mapping of Finding fields to override (`severity`, `message`, `area_fraction`, `time_overlap`, `suggestions`, `details`), or an iterable of such mappings. When `check()` overrides `time_overlap`, the engine recomputes `time_fraction` from it, so the two stay consistent. An optional `mask(lon, lat, query)` hook serves the bulk path; a rule without one is listed in `PointResult.skipped` rather than silently left out. `@index.rule(code, **same_keywords)` wraps a plain function `(query, match) -> CheckResult` the same way, taking its title from the function's docstring. This is the `__init_subclass__` registration pattern CrocoDash already uses, with three fixes (section [12.3](../design.md#123-the-index-codes-and-lifecycle)).

**Query**:

| Field | Type | Meaning |
|---|---|---|
| `space` | Space or None | The support: cells and areas actually used |
| `time` | TimeSpec or None | The bounds of the time steps used |
| `axes` | mapping of name to (lo, hi) | A plain number is accepted and becomes `(v, v)` |
| `facets` | mapping of name to tuple of values | A plain string is accepted. `product` (with `variable` and `version`) here is shorthand for requests. |
| `requests` | tuple of `Request` | One per product the caller uses: `Request(product, variables=(), version=None, time=None, support=None)` (section [4.12](../design.md#412-several-products-in-one-query-requests)). A plain string for `variables` means one variable, and a plain product name means a request with no variables. |
| `context` | mapping | Data for computed rules, such as station counts already loaded; not serialised |
| `label` | str | The caller's name for the query ("lake 1234", a case name), used in messages and de-duplication |

`Index.query(space=..., time=..., axes=..., facets=..., requests=..., context=..., label=..., include_conditional=False)` builds the Query itself and accepts shorthands: a pair of strings for `time`, and plain values for axes and facets.

**Finding** is the rule's outcome plus how its scope met the query (the `Outcome` and `Match` dataclasses in [api_sketch.py](api_sketch.py)):

| Field | Meaning |
|---|---|
| `code`, `kind`, `title`, `message`, `instruction` | From the rule, possibly overridden by a computed rule |
| `severity`, `confidence`, `action`, `status` | As defined in section [4.9](../design.md#49-outcomes) and section [5.2](../design.md#52-record-properties) |
| `source_severity` | The source's own severity wording, verbatim (for example `REQ_AUTHORIZATION` for UAS001), or None |
| `suggestions` | For recommendations |
| `product` | The canonical name of the request's product, for every finding from a request, coverage findings included; None for findings from the base query (rules that concern no product, such as CROC101) |
| `request` | The position of the finding's request in the query's requests after shorthand expansion (section [4.12](../design.md#412-several-products-in-one-query-requests)); None for the base query |
| `area_fraction`, `overlap_km2` | Spatial overlap (section [4.4](../design.md#44-space)) |
| `time_overlap`, `time_fraction` | Overlapping periods as closed wire-form intervals, and their share of the query's duration (section [7.2](../design.md#72-intervals-recurrence-and-calendars)) |
| `axes` | The intersection on each axis the rule constrains, as an `AxisOverlap(lo, hi, lo_closed, hi_closed)`, so `[8, 10)` keeps its open end |
| `matched_facets` | The query values that matched each constrained facet |
| `conditional_on` | Dimensions the engine could not decide: omitted by the query, not comparable with the rule's form, or a missing context key (section [4.3](../design.md#43-matching-when-a-dimension-is-missing)); empty means definite |
| `assumed` | Dimensions the rule constrains that were filled from the request's product: `space` (a support derived from `Product.grid`), `time` and `version` |
| `min_overlap`, `references`, `evidence` | Copied from the rule |
| `details` | Rule-specific numbers, for example `{"stn0_fraction": 0.41}` |
| `source`, `query_label` | Pack name, `computed` or `builtin`; the query's label |

`Finding.to_dict()` writes severity as its lowercase name and intervals in wire form, so findings can go into a case's `config.json`, a README or a web page unchanged.

**Index**:

| Method | Purpose |
|---|---|
| `Index(name, axes=..., facets=...)` | Declare axes (with units) and facet names |
| `add_product`, `add_regions` | Declare products and named regions |
| `add(rule)` | Add a `Rule`, a record mapping or any `RuleKind`; raises `DuplicateCodeError` on a reused code |
| `load_pack(path)` | Load a data-only pack; returns the codes loaded |
| `rule(code, ...)` | Decorator for function rules |
| `query(...)` | One query, with any number of requests; returns a sorted `list[Finding]` (section [9.1](../design.md#91-the-pipeline-of-indexquery)) |
| `expand(query)` | The base query and one sub-query per request, after shorthand expansion and product defaults, so a caller can see which combinations are checked (section [4.12](../design.md#412-several-products-in-one-query-requests)) |
| `query_points(lon, lat, weights=None, time=..., axes=..., facets=..., requests=..., include_conditional=False)` | The bulk path; returns masks, weighted fractions and findings keyed by `(product, code)` as a `PointResult` (section [9.3](../design.md#93-the-bulk-path-query_points)) |
| `suitable(query, variable, *, products=None, score=None)` | The inverse query: coverage filter, then a ranked `list[Suitability]` (section [10](../design.md#10-inverse-query-which-products-suit-this-request)) |
| `Index.default()` | The application default Index, created on first use |

### Error classes

These are the errors the design names, gathered in one place; [api_sketch.py](api_sketch.py) declares the classes. Where the design says only that something "is an error", the class is left to the prototype.

| Error | Raised when | Where specified |
|---|---|---|
| `UnknownNameError(KeyError)` | An undeclared axis, facet or product name appears in a record or a query; an unknown name is passed to `suitable(products=...)` | Sections [4.6](../design.md#46-axes), [4.7](../design.md#47-facets) and [10.1](../design.md#101-contract) |
| `DuplicateCodeError(ValueError)` | A code the Index already holds is registered again, from a pack, a `ComputedRule` subclass or an `@index.rule` function | Sections [4.11](../design.md#411-core-objects) and [12.3](../design.md#123-the-index-codes-and-lifecycle) |
| `AdvisoryError(Exception)` | `emit()` runs in `"raise"` mode and keeps at least one caveat or coverage finding, or runs with `raise_at` and keeps one at or above that severity; `.findings` holds them all | Section [11.1](../design.md#111-modes-and-policy) |
| `ValueError` | A query gives requests together with a `product`, `variable` or `version` facet; `suitable()` is asked for a named product that does not offer the variable; a ring winds around the globe more than once, or encloses no area after repair | Sections [4.12](../design.md#412-several-products-in-one-query-requests), [10.1](../design.md#101-contract) and [6.2](../design.md#62-canonical-representation-and-normalisation) |
| `TypeError` | A `ComputedRule` subclass has no `code` and is not `abstract=True`; an object that holds mappings (`Scope`, `Query`, `Match`, `Finding`, `Rule`) is put in a set or used as a dictionary key | Section [4.11](../design.md#411-core-objects) and [api_sketch.py](api_sketch.py) |
| Load error, reported with the file, the feature's position and its code | A schema violation; a duplicate code; a code outside the pack's prefixes, a prefix claimed by two packs, or the reserved prefix `QE`; `periods` outside `time`; a date invalid in its calendar; a box with `south` not below `north`; an undeclared name or a unit that does not match its axis; a version-range bound that is not a dotted integer; an unresolved `region_ref`; a latitude beyond plus or minus 90 by more than 1e-9 degrees; a ring that encloses no area; two packs declaring one product name beyond adding aliases; a collection header that disagrees with `pack.toml` | Sections [4.4](../design.md#44-space), [4.6](../design.md#46-axes), [4.8](../design.md#48-version-ranges), [4.11](../design.md#411-core-objects), [5.3](../design.md#53-loader-checks), [5.4](../design.md#54-packs) and [6.2](../design.md#62-canonical-representation-and-normalisation) |
| Other errors the design names without a class | `box()` with `east == west`; `polygon(pole="auto")` on a ring whose mean latitude is exactly 0; second 60 in a time; a `version` facet in the shorthand together with more than one product; `Request.support` given to `query_points()` | Sections [6.3](../design.md#63-boxes-closed-sets-and-areas), [6.2](../design.md#62-canonical-representation-and-normalisation), [7.1](../design.md#71-the-civil-date-key-and-its-wire-format), [4.12](../design.md#412-several-products-in-one-query-requests) and [9.3](../design.md#93-the-bulk-path-query_points) |

Warnings are not errors: `emit()` warns with `AdvisoryWarning(UserWarning)` subclasses `InfoAdvisory`, `WarningAdvisory` and `SevereAdvisory`, one per severity (section [11.1](../design.md#111-modes-and-policy)).

### Record properties in full

Section [5.2](../design.md#52-record-properties).

| Property | Required | Meaning |
|---|---|---|
| `code` | yes | Unique identifier: a prefix plus three or four digits, optionally hyphenated (`CRU001`, `ERA5-014`). Messages start with `[CODE]`. |
| `kind` | yes | `caveat` or `recommendation` (coverage is declared on products) |
| `title` | yes | One-line headline (CAP headline) |
| `message` | yes | What applies and why (CAP description) |
| `instruction` | no | What the reader should do (CAP instruction) |
| `severity` | yes | `info`, `warning` or `severe` |
| `source_severity` | no | The source's own severity wording, verbatim |
| `confidence` | no | `observed`, `likely`, `possible` or `unknown` (default) |
| `action` | no | `can_be_used`, `use_with_caution`, `do_not_use` or `replaced` |
| `suggestions` | for recommendations | At least one `{target, key, value, rationale}` |
| `facets` | no | Facet name to patterns, or `version` to ranges |
| `axes` | no | Axis name to `{gt, ge, lt, le, unit}` |
| `region_ref` | no | `namespace:id` or a list of them (a union); geometry must then be null |
| `box` | no | `{west, width, south, north}`; geometry must then be null |
| `periods` | no | Closed intervals inside the `time` member (a union) |
| `recurrence` | no | `{"months": [1, 2, 12]}` |
| `calendar` | no | Calendar of the dates in this record |
| `time_start`, `time_end` | no | Fallback for editors that drop the JSON-FG member; never together with a non-null `time` |
| `min_overlap` | no | Emission threshold on `area_fraction`, 0 to 1 (default 0) |
| `evidence` | no | ISO 19157-style `{method, measure, result, script, notes}`; method is `documented`, `derived`, `measured` or `expert` |
| `references` | no | `{type, citation, url, doi, retrieved}`, with at least one of citation, url or doi |
| `status` | no | `draft` (default), `reviewed` or `deprecated`. Every finding carries it. |
| `created`, `updated` | no | Timestamps of the record itself: its lifecycle time, never the data time |
| `withdrawn` | no | Timestamp. A withdrawn rule is kept for history but never matches. |
| `supersedes` | no | Codes this rule replaces; they stop matching while this rule is loaded |
| `aliases` | no | Other identifiers for the same issue, such as the source's own issue number |
| `x_*` | no | Extension fields, kept and ignored by the engine |

### Loader checks in full

Section [5.3](../design.md#53-loader-checks).

The JSON Schema covers structure. The loader also checks, and reports every error with the file, the feature's position and its code:

- codes are unique in the Index;
- each pack's codes belong to a prefix it owns: a code's prefix is the part before the optional hyphen and the final three or four digits, and it must equal an owned prefix exactly (so a pack owning `CRU` does not own `CRUX001`);
- no two packs claim the same prefix, and `QE` is reserved. Rules added from Python (`Index.add`, `ComputedRule`, `@index.rule`) may use any prefix except `QE`, including one a loaded pack owns; only a duplicate code is an error;
- `periods` lie inside `time`, and dates are valid in the stated calendar;
- a `box` has `south` below `north`;
- axis, facet, product and region names are declared, and `unit` matches the axis;
- version-range bounds are dotted integers.

### Packs in full

Section [5.4](../design.md#54-packs).

A pack is a directory with a `pack.toml` (read with the standard library's `tomllib`) and one or more FeatureCollection files. A FeatureCollection may also carry a `metadata` header with `pack`, `version`, `code_prefix`, `license`, `issued` and `technical_limitations`, in the style of EUROCAE ED-318. The header is required when the file is loaded on its own; otherwise it must agree with `pack.toml` (the header's `pack` is the toml's `[pack] name`).

```toml
[pack]
name = "demo"
version = "0.1.0"
code_prefix = ["CRU", "CROC"]
license = "CC-BY-4.0"
files = ["rules/*.geojson"]

[products.cru_ts]
aliases = ["CRUTS", "CRU TS"]
variables = ["pre", "tmp"]
resolution = [0.5, "deg"]
calendar = "standard"
version = "4.07"
coverage = { time = ["1901-01-01", "2022-12-31"] }
grid = { lon = [-180.0, 180.0, 0.5], lat = [-90.0, 90.0, 0.5] }  # cell edges: first, last, step

[regions.ar6]
file = "regions/ar6_land.geojson"  # FeatureCollection of named regions
id_property = "abbrev"             # property that holds each region's id
```

A product's `grid` in `pack.toml` gives the edges of a regular grid as first edge, last edge and step, in degrees; an irregular grid or a callable is declared in Python (section [4.12](../design.md#412-several-products-in-one-query-requests)). Loading a pack never runs code, so packs from untrusted sources are safe to load.

### Normalisation steps in full

Sections [6.2](../design.md#62-canonical-representation-and-normalisation) and [6.4](../design.md#64-not-supported); the code is in [geometry.py](geometry.py).

- **Coordinates** are float64 (longitude, latitude) in degrees on WGS84, longitude first. Stored longitudes lie in [-180, 180] and latitudes in [-90, 90]. A latitude outside that range by more than 1e-9 degrees is an error; a smaller excursion, such as projection round-off, is clamped.
- **Edges** are straight lines in longitude-latitude ("planar" edges), declared as RFC 7946 and GeoParquet's default `edges="planar"` declare them. Product grid cells and latitude-longitude boxes have exactly these edges, so an edge written along 60N stays on 60N; read as a great circle, the edge from (-60, 60) to (60, 60) would peak at 73.9N. The two readings also give different areas: pyproj's geodesic area of a raw longitude-latitude box differs from its planar-edge area by -38% (120 by 20 degrees, 40N to 60N) to +10.8% (90 by 45 degrees, equator to 45N). One departure from RFC 7946 is deliberate: an edge that spans more than 180 degrees of longitude, other than a full-turn edge of exactly 360 degrees, is read the short way (section [6.2](../design.md#62-canonical-representation-and-normalisation), step 2). Under RFC 7946 the naive Fiji ring of section [6.1](../design.md#61-motivating-failures) really is the 340 degree shape; queryearth reads it as the intended 20 degree box.
- **Shapes** are shapely Polygons or MultiPolygons. No part crosses plus or minus 180, exteriors run counterclockwise and holes clockwise, and a third coordinate (altitude) is dropped.

Every record geometry, query polygon and grid outline is normalised once, when it is loaded or built. The steps run in this order because pole detection needs the ring before it is cut, and the cut needs a valid polygon.

1. **Wrap** every longitude exactly into [-180, 180] (section [6.2](../design.md#62-canonical-representation-and-normalisation)).
2. **Unwrap and count turns.** Walk each ring and take every step between consecutive vertices the short way, so the ring becomes continuous in longitude (a ring that crosses the antimeridian runs, say, from 170 to 190). Two kinds of step keep the direction in which they were written, computed from the raw input: a step of exactly 180 degrees, and a full-turn step of exactly 360 degrees, which RFC 7946 reads as an edge along the whole parallel. The full-turn rule is what makes a planar polar cap, such as ERA5-024's ring from (-180, 66.5) to (180, 66.5) to (180, 90) to (-180, 90), come out as the cap rather than as four copies of one point. The steps of a closed ring sum to 360 times a whole number, the winding number: 0 for an ordinary ring, plus or minus 1 for a ring that goes once around a pole, and anything else is an error. This is the winding-sum idea of the `_encircles_globe` helper in mom6_forge (a CROCODILE grid-generation package), written fresh; it gives exactly one turn for the polar-stereographic square of section [6.1](../design.md#61-motivating-failures) (fixture 4). Vertex latitudes and thresholds such as "spans 350 degrees" are not used. A ring that goes around a pole lists the seam longitude once: a ring at 70N written from -180 to 179 and closed has winding number 1, but the same ring listing both -180 and 180 gains a full-turn closing edge back, has winding number 0 and encloses nothing, which step 4 reports as an error.
3. **Close pole rings.** A ring with winding number plus or minus 1 is closed along latitude 90 or -90: after its last vertex, the path continues to the copy of the first vertex one turn away, rises to the pole, runs along it back to the first vertex's longitude and comes down. `polygon(pole="auto")` picks the pole on the side of the ring's mean latitude and requires `pole=` when that mean is exactly 0. `from_grid()` keeps the north candidate if it covers the grid's middle node, and otherwise uses the south one.
4. **Repair** with shapely `make_valid`, keep only the polygon parts and union them, so overlapping parts of a multipolygon are not counted twice. `make_valid` can return a GeometryCollection that holds a MultiPolygon, so the parts are taken two levels deep; one level silently drops the MultiPolygon. A shape left empty is a load error ("the ring encloses no area"), never a rule that silently matches nothing. `buffer(0)` is never used: for the bow-tie ring (0, 0), (2, 2), (2, 0), (0, 2), `make_valid` keeps both triangles (area 2.0) while `buffer(0)` keeps one (area 1.0). The reason from `is_valid_reason` goes into the load report.
5. **Split.** Intersect the shape with each 360 degree strip [360k - 180, 360k + 180] it reaches, shift each piece by -360k, and union the pieces. The clip places new vertices exactly on the strip edge (all 8,259 seam vertices from 3,000 random seam-crossing quadrilaterals landed exactly on plus or minus 180), and a whole-turn shift is exact, so the halves meet exactly. An index stores each part's bounds separately, because the overall bounds of a split shape span the globe.
6. **Orient** with shapely `orient_polygons`.

Holes are normalised as separate rings and subtracted from the exterior, so a hole may itself enclose a pole: a band from 66.5N to 85N can be written as a ring at 66.5N with a hole ring at 85N. After step 2 the Fiji ring becomes the intended 20 degree box, and the same box written in 0 to 360 longitudes normalises to the same two parts. Boxes, longitude arcs and latitude bands (`box`, `box_arc`, `lat_band` and records' `box`) are built as polygons directly (section [6.3](../design.md#63-boxes-closed-sets-and-areas)) and never pass through ring normalisation. The code in [geometry.py](geometry.py) was run while revising this document on the Fiji ring in both longitude conventions, the polar-stereographic square, rings around 70N written with the seam once and twice, the planar caps and band of fixture 22, the bow-tie with and without a spike (fixture 7), and 3,000 random rings with small integer coordinates, of which none lost polygon area in the repair.

The common formula `((x + 180) % 360) - 180` rounds when it adds 180, so 179.99999999999997 becomes -180.0. During the design research it changed 488 of 2,000 samples taken within 5e-12 degrees of the seam; on the east edge of a box, such an error turns a sliver into nearly the whole globe. `wrap_lon` uses `math.fmod`, which is exact, and corrects by 360 only when the remainder lies beyond 180 in size; that correction is exact because the two numbers are within a factor of two of each other (Sterbenz's lemma). Both 180 and -180 are kept, since a split shape uses both.

- **Great-circle edges.** A source whose edges are great circles must be densified first, for example with pyproj `Geod.npts`.
- **Edges longer than 180 degrees of longitude**, other than full-turn edges of exactly 360 degrees. They are read the short way (step 2), a deliberate departure from RFC 7946; write a box, or add vertices.
- **A ring read as "the larger side".** A ring with winding number 0 always encloses the side that contains no pole, and one with winding number plus or minus 1 is closed toward one pole. Spherical engines such as S2 choose a ring's side by size or orientation; queryearth never does. Regions larger than a hemisphere are written as pole caps, boxes and bands, with holes where needed. A shape containing both poles, or a ring that winds more than once, cannot be written as one ring.
- **Coordinate systems other than CRS84**, and rule geometries other than polygons, multipolygons and null.

### Boxes in full

Section [6.3](../design.md#63-boxes-closed-sets-and-areas).

A box is a longitude arc plus latitude limits, `(west, width, south, north)`, with `west` in [-180, 180) and `width` in (0, 360]. A rule writes it as `properties.box`. A query uses `box_arc(west, width, south, north)` or `box(west, south, east, north)`, where the width is `east - west` if `east` is greater than `west` and `east - west + 360` otherwise. `east == west` is an error (`lat_band()` gives the full circle), and -90 <= south < north <= 90. A `west` that wraps to 180 is stored as -180, so stored values stay in [-180, 180).

Only `west` is wrapped; `width` is kept. Wrapping the two ends separately is the bug CrocoDash fixed in #283: before the fix, 7 of 14 combinations of box and longitude convention selected too little. A longitude x lies on the arc when `(x - west) mod 360 <= width`, the test CrocoDash's `bbox_mask` uses. For matching, a box becomes one polygon, or two when `west + width > 180`.

### Closed-set predicates

Section [6.3](../design.md#63-boxes-closed-sets-and-areas).

| Query space | Test against a rule shape |
|---|---|
| Point | Prepared `covers` |
| Point at latitude 90 or -90 | `intersects` with the whole pole edge (that latitude at every longitude), so a pole point matches every rule that reaches that pole. In longitude-latitude the pole is a line, and a sector box from 0E to 90E reaching 90N would otherwise miss the point (123, 90). |
| Polygon, box, band, grid outline or cells | Prepared `intersects` |
| Weighted points (bulk path) | `shapely.intersects_xy`, never `contains_xy`; points at latitude 90 or -90 use the pole-edge test above, once per rule (section [9.3](../design.md#93-the-bulk-path-query_points)) |

Closed sets matter because real grid points sit on rule edges. ERA5's 0.25 degree grid has 2,401 points in [-1, 11] by [-1, 11], and 1,681 of them lie in the closed square [0, 10] by [0, 10]. `contains_xy` finds 1,521 (it drops all 160 edge points), even-odd ray casting finds 1,600 (it drops the right and top edges), and `intersects_xy` finds all 1,681 (measured while drafting). The cost is deliberate over-warning: a query polygon that only shares an edge with a rule matches with `area_fraction` 0.0, and the rule's `min_overlap` decides whether `emit()` shows it.

### Area in full

Section [6.3](../design.md#63-boxes-closed-sets-and-areas); the code is in [geometry.py](geometry.py).

`overlap_km2` is the area of the intersection of the rule shape and the query shape, and `area_fraction` divides it by the area of the query shape. shapely computes the intersection in longitude-latitude, which is exact under planar edges.

Areas use a closed form that needs only `math`. On a sphere of radius R, the area of a region is R² times the integral of cos(latitude) over latitude and longitude. Green's theorem turns this into -R² times the sum, over the boundary's edges, of the integral of sin(latitude) with respect to longitude. Along a planar edge, longitude changes linearly with latitude, so each edge's integral has an exact form, `dlon * sin(mean latitude) * sin(dlat / 2) / (dlat / 2)` in radians, where the last factor is 1 when `dlat` is 0. This form avoids the cancellation in cos(lat1) - cos(lat2) on nearly east-west edges, and an edge along a pole contributes -dlon, which is how a pole cap gets its area.

A polygon's area is its exterior's minus its holes'; a multipolygon's is the sum over its parts. During the design research this formula matched pyproj's spherical geodesic area on densified polygons (shapely `segmentize` at 0.01 degrees) to within 2e-10 to 5e-9 relative error, for shapes from a 10 hectare lake to a polar cap; checks while drafting gave 1e-9 to 5e-9 on six shapes, and better than 1e-12 against the exact formulas for a box and a cap. Absolute areas differ from ellipsoidal ones by up to about 0.3%, which does not affect fractions. Square degrees are not areas: the box [0, 10] by [40, 45] is half of [0, 10] by [40, 50] in square degrees, but 0.5218 of its area.

### Time conversion in full

Section [7.1](../design.md#71-the-civil-date-key-and-its-wire-format).

queryearth compares civil dates instead: the labels (year, month, day, hour, minute, second) as written. Each instant becomes one integer:

`interval()` and `from_bounds()` accept wire strings; `datetime.date` and `datetime.datetime` (aware values converted to UTC, naive values treated as UTC); cftime objects (their fields and calendar); numpy `datetime64` values in any unit, converted in their own unit and never through `datetime64[ns]`; and pandas `Timestamp` values, through their fields. None of these libraries is imported: cftime, pandas and numpy date values are recognised by duck typing, through their fields and attributes. All keys are UTC civil time. Second 60 is rejected, because no CF calendar has leap seconds.

Precision follows the type of the value. Wire dates, `datetime.date` values and numpy `datetime64` values in days are day precision. Wire timestamps, `datetime.datetime`, cftime objects, `Timestamp` values and `datetime64` values in finer units are second precision, even at midnight. So `interval(Timestamp("2020-01-01"), Timestamp("2020-01-09"))` ends with the first second of 9 January, while `from_bounds` reads the same pair as the days 1 to 8 January (section [8.3](../design.md#83-time-axes-and-facets), fixture 11). An interval whose two ends differ in precision is written back with timestamps at both ends (section [7.2](../design.md#72-intervals-recurrence-and-calendars)).

Years are astronomical (section [7.1](../design.md#71-the-civil-date-key-and-its-wire-format)). A cftime object whose calendar has no year zero (`has_year_zero=False`, cftime's default for `standard`, `gregorian` and `julian`) counts 1 BC as year -1, so the conversion adds 1 to years at or below 0; an object with `has_year_zero=True` is taken as written (fixture 16).

The wire format is the JSON-FG `time` member (section [4.5](../design.md#45-time)). An end is inclusive at its stated precision: `"2006-12-31"` includes that whole day and `"2006-12-31T23:59:59Z"` that second. Version 1 has only these two precisions; a month is written as its first and last day, and the schema rejects `"2020-01"` (section [18](../design.md#18-decisions-and-outstanding-work)). Years with a sign or more than four digits (`"-5000-06-01"`, `"12000-01-01"`) are accepted for paleoclimate products, a documented extension beyond RFC 3339 and JSON-FG 1.0 (records that use them are not valid JSON-FG). Years are astronomical, as in ISO 8601's expanded years: year 0 is 1 BC and year -1 is 2 BC.

### Intervals in full

Section [7.2](../design.md#72-intervals-recurrence-and-calendars).

Inside the code every interval is half-open, [start, end), with `None` for an open end:

| Wire | Internal |
|---|---|
| Start `"2020-01-09"` | key(2020, 1, 9) |
| End `"2020-01-09"` | key(2020, 1, 9) + 86,400, which equals key(2020, 1, 10) |
| End `"2020-01-31"` | key(2020, 1, 31) + 86,400, which equals key(2020, 1, 32) and key(2020, 2, 0) |
| End `"2020-12-31"` | key(2020, 12, 31) + 86,400, which equals key(2021, 0, 0) |
| End `"2020-01-09T06:00:00Z"` | key(2020, 1, 9, 6) + 1 |
| `".."` | `None` |

Adding a day never needs month lengths. Past the last day of a month, the sum lands on "day 0" of the next month or "month 0" of the next year; no real instant uses those slots, so the sum comes after every second of the day and before the next real day, and overlap tests are exact without a calendar. Two intervals [a, b) and [c, d) overlap when a < d and c < b; unions and intersections are computed by sorting and sweeping. Half-open intervals also stop a boundary day from matching twice.

When a finding writes `time_overlap`, each [start, end) goes back to closed wire form: the start's date, and the day before the end, with the calendar naming the last day of the previous month when the end falls on day 0 or day 1. The output is at day precision unless either side used timestamps. `time_fraction` is the overlap's length in days divided by the query's length in days, measured in the query's calendar. It is None when the query has an open end, and for `julian`.

### Month recurrence in full

Section [7.2](../design.md#72-intervals-recurrence-and-calendars).

`properties.recurrence = {"months": [12, 1, 2]}` limits a rule to those calendar months. Because the months are a set, a season that wraps the year end needs no special case. To evaluate it, intersect the rule's periods with the query to get B, then cut B into calendar months; month m of year y is [key(y, m, 1), key of the first day of the next month), which needs no month lengths, and runs that touch are merged so that December joins the following January. Adding the months of one year is plain integer arithmetic on keys, with no month lengths involved.

If B has an open end (an open-ended query), every month occurs in it, the rule matches, and `time_overlap` reports B without expansion. December to February over CRU TS's record from 1901 to 2022 gives 123 runs. Seasonal windows at day precision, such as 15 June to 15 September, are not in version 1.

### Calendars in full

Section [7.2](../design.md#72-intervals-recurrence-and-calendars).

Every time specification carries a CF calendar name, by default `proleptic_gregorian`. The calendar validates dates, names the last day of a month and measures durations. It never orders them.

| Calendar | 29 February | 30 February | 31st day |
|---|---|---|---|
| `standard`, `gregorian`, `proleptic_gregorian` | Gregorian leap years | Error | In months that have one |
| `julian` | Every fourth year | Error | In months that have one |
| `noleap`, `365_day` | Error | Error | In months that have one |
| `all_leap`, `366_day` | Every year | Error | In months that have one |
| `360_day` | Every year | Every year | Error |

When a rule and a query use different calendars, their dates are compared as civil labels: a `360_day` rule for 1 to 30 February 2000 matches a Gregorian query for 29 February 2000, with no `TypeError`. Between `360_day` and Gregorian dates, physical time can differ by a few days, which is acceptable for advisories and is documented. `standard` is treated as proleptic Gregorian for durations and validation, which is wrong only before 15 October 1582 (the two calendars put 1500-03-01 ten days apart, and cftime rejects 1582-10-10 in `standard`).

`time`, `periods` and `recurrence` are **data time**: when the data are affected. `created`, `updated` and `withdrawn` are **record time**: the lifecycle of the record itself. Query times are compared only with data time, and a withdrawn record never matches, whatever the query's time. Evaluating a past run against the records that existed then ("as of" time) is not in version 1 (section [17](../design.md#17-non-goals-for-v1-and-upgrade-paths)).

### Why the support

Section [8.1](../design.md#81-the-contract).

| Problem | What happens | With the support |
|---|---|---|
| Buffering a small shape | GLHE retries an empty extraction with `polygon.buffer(0.5)` (`CRUTS.py`, lines 119 to 125). A buffer in degrees is anisotropic: at 70N, 0.5 degree of longitude is about 19 km and of latitude about 56 km. The buffered outline is neither the lake nor the cells whose values are used. | The cells that supply the value are the query |
| Small shapes and cell centres | A 0.15 by 0.15 degree lake (about 280 km² near the equator) inside one 0.5 degree cell, but not over its centre, selects no cell under centre masking (regionmask's default, and H3's classic polygon fill). A rule over the western 40% of that cell does not touch the lake, yet it affects the value the lake receives. | `cells(..., mode="overlap")` selects the cell, and the rule matches with `area_fraction` 0.4 |
| Mid-month time stamps | A monthly value stamped 2020-01-16 stands for all of January; a rule for 20 to 25 January, compared with the stamp, misses it | The bounds [2020-01-01, 2020-02-01) overlap the rule |

### Query spaces and product cells in full

Section [8.2](../design.md#82-choosing-a-space-and-selecting-product-cells).

Section [4.4](../design.md#44-space) lists the helpers. A gridded product read for a region uses `cells()`; a model domain on a 2D grid uses `from_grid()` on its cell corners; a domain periodic in longitude (a Southern Ocean channel) uses `lat_band()`, because it has no bounding box or closed outline; objects known by id, such as the 5,782 lakes in the National Water Model retrospective v3.0 lake output, use `features()`. With `weighted_points()`, zero weights on land cells make `area_fraction` an ocean-only fraction. Any longitude convention is accepted: a lake from 350.0E to 350.15E and the same lake from -10.0 to -9.85 give the same findings, and a CrocoDash grid stored continuously from 170 to 200 normalises to two parts.

`cells(grid, region, mode)` takes a rectilinear grid as `(lon_edges, lat_edges)`, in any longitude convention, and returns the union of the selected cells as one space; each cell is a box, normalised like any other.

| Mode | Selects |
|---|---|
| `"centre"` | Cells whose centre the region covers. Can select nothing for a region smaller than a cell. |
| `"overlap"` (default) | Cells whose intersection with the region has positive area; for a region without area, such as a point, every cell that covers it. Never drops a small lake, and a region whose edge lies on a grid line does not pull in the neighbouring cell. |
| `"full"` | Cells the region covers completely |

The resulting `area_fraction` is relative to the support. A caller who also wants to know whether a rule touches the lake itself runs a second query with the lake polygon and a different `label`.

A product that declares `Product.grid` gets this selection, in `"overlap"` mode, from the engine itself: a request for that product without an explicit support is judged on the cells the caller's region uses (section [4.12](../design.md#412-several-products-in-one-query-requests)). `cell_mask()` returns the same selection as a boolean array, so an adapter can read the product's data for exactly those cells.

### Time bounds, axes and facets in full

Section [8.3](../design.md#83-time-axes-and-facets).

`from_bounds(starts, ends)` builds the query time from the bounds of the time steps used: the CF `time_bnds` variable, or bounds inferred from the step frequency. Each pair is read as CF defines it, start inclusive and end exclusive, so monthly bounds from 2020-01-01T00:00Z to 2020-02-01T00:00Z become the closed wire interval 2020-01-01 to 2020-01-31, which does not touch a rule that starts on 1 February. Bounds at midnight give day precision, and consecutive steps merge into one interval. A caller with a range of days uses `interval(start, end)` with dates, whose ends are inclusive. A caller whose end is exclusive, such as CrocoDash, where a run from `date_range[0]` to `date_range[1]` lasts `(end - start).days` days, passes the pair to `from_bounds([start], [end])` instead (section [15.1](../design.md#151-crocodash)).

Axis values are given in the axis's declared unit, as a number or a closed range. A grid has a range of spacings, so pass the range. `resolution_of(lon2d, lat2d, unit="km")` returns (finest, coarsest): the shortest and longest cell edge, each measured as a great-circle length on a sphere of radius 6,371.0088 km (with `unit="deg"`, as central angles). A 1/4 degree latitude-longitude grid from 60N to 70N gives (9.51, 27.80) km, because its east-west edges shrink with latitude. Pass cell corners, not a MOM6 supergrid, whose nodes are half a cell apart: the supergrid of the same grid gives (4.75, 13.90); pass `x[::2, ::2]` and `y[::2, ::2]` instead. Other axes come from the configuration, for example `vertical_levels` from the length of the vertical grid.

Facets are strings or tuples of strings, product names may be aliases, and an unknown name is an error. Give products and their variables as requests (section [4.12](../design.md#412-several-products-in-one-query-requests)).

Adapters should pass every dimension they know, including the variables of each request. An adapter that forgets `resolution` turns CROC102 into a conditional finding, so its message silently disappears from the log; one that sends a request without variables does the same to every rule that constrains `variable`, such as GLORYS001. Test adapters with `include_conditional=True`: every conditional finding there names a dimension the adapter could have supplied.

### Query pipeline in full

Sections [9](../design.md#9-matching-engine-and-bulk-path) and [9.1](../design.md#91-the-pipeline-of-indexquery).

Two entry points share one engine: `Index.query` answers one query, with any number of requests, and `Index.query_points` answers the same question for up to millions of points. The matching itself is ordinary, so this part of the file fixes the order of the stages (below), the data an Index keeps ([Index internals](#index-internals)), how packs load quickly ([Lazy loading in full](#lazy-loading-in-full)) and how the bulk path stays fast ([Bulk path in full](#bulk-path-in-full)).

The reference semantics are those of `RuleKind.evaluate(query)` and the matching table in section [4.3](../design.md#43-matching-when-a-dimension-is-missing). The Index's vectorised stages are only an optimisation of calling `evaluate` on every rule, and a property test must check that both give the same findings for random queries. The Index matches records and `ComputedRule` subclasses itself; for any other `RuleKind` it uses the rule's `scope` as a prefilter and then calls the rule's own `evaluate(query)`, whose answer is final.

Stage 0 splits the query into its base query and one sub-query per request (section [4.12](../design.md#412-several-products-in-one-query-requests)), and stages 1 to 8 run for each part over the rules that part evaluates. Each stage gives every surviving rule one of three states for its dimension, following section [4.3](../design.md#43-matching-when-a-dimension-is-missing): it fails and is dropped, it passes, or it is undecided (omitted by the query, not comparable with the rule's form, or a missing context key). An undecided dimension sets one bit in a small per-rule bit set, in the fixed order of `conditional_on`. When `include_conditional` is False, any rule with a bit set is dropped at once. That is the main pruning in practice: a query that names no product drops every product-scoped rule at stage 1, before any geometry is touched.

| Stage | Work |
|---|---|
| 0. Prepare the query | Normalise the query space once (section [6.2](../design.md#62-canonical-representation-and-normalisation)). Resolve product aliases. Reject undeclared axis, facet and product names with `UnknownNameError`. Expand the facet shorthand into requests and split the query (section [4.12](../design.md#412-several-products-in-one-query-requests)). For every request, evaluate its product's coverage once (calling it if it is a callable) and use the result both for QE001 and QE002 and to fill the request's time; fill its version from the product; derive its support from `Product.grid` when the request gives none. |
| 1. Facets | For each facet the query gives, combine the rules listed under its values, the glob-pattern rules `fnmatch` accepts, and the rules that do not constrain the facet; compare version ranges as integer tuples. For each facet the query omits, mark the rules that constrain it as undecided. Numpy masks: microseconds. |
| 2. Axes | One vectorised interval test per axis the query gives, honouring open and closed ends; an omitted axis makes the rules that constrain it undecided. |
| 3. Time | An envelope test on the int64 key arrays (6 µs at 10,000 rules, design research), then the exact interval union and month recurrence for the survivors only. |
| 4. Spatial candidates | Rules without a space pass. If the query has no space, rules with one become undecided. Otherwise query the STRtree with each normalised query part, without a predicate, map hit parts to rules and merge duplicates. Object-id rules match by set intersection. |
| 5. Exact test | `shapely.intersects` against the prepared rule geometry, or `shapely.intersects_xy` for a point query; both are closed-set tests. |
| 6. Measures | If the rule `covers` the query, `area_fraction` is 1.0 and `overlap_km2` the query's area; if the query covers the rule, the overlap is the rule's cached area; otherwise intersect the two and take the spherical area. Also the time overlap and fraction, axis intersections and matched facet values. This stage dominates large queries. |
| 7. Findings | A record builds a `Finding` from its outcome plus the match (about 2 µs each), with the part's `product` and `request`. A computed rule first has its `requires` keys checked against `Query.context` (a missing key adds `context:<key>`); `check(query, match)` runs only when the match is definite, and a conditional match yields the declared defaults with empty `details` (section [4.11](../design.md#411-core-objects)). The coverage rule measures the part of each request's space and time that lies outside its product's coverage. |
| 8. Sort | By severity, then kind, then code, then part: the base query first, then the requests in order. Several findings from one computed rule are kept. |

The cheap, vectorised, non-spatial stages come first because most real rules are scoped by product, variable or time rather than by area; about 80% of ERA5's known issues need no polygon at all.

With N rules, stages 1 to 3 are O(N) numpy operations plus one `fnmatch` call per glob-pattern rule; stage 4 costs O(log P + c) for P normalised parts and c candidates; stage 6 is proportional to the vertex counts of each hit that neither shortcut resolves; no stage is worse than linear in N. A continent-sized query (a 30 degree radius star) against 10,000 rules with no facet pruning gave about 240 hits and took 51 to 57 ms, nearly all in polygon intersections; the "query covers rule" shortcut cut this to 47 ms with identical fractions. With 90% of rules scoped to one of ten products and the query naming none, it took 4.7 ms (this document's benchmark). An index beyond the STRtree pays off only past about 50,000 rules (section [17](../design.md#17-non-goals-for-v1-and-upgrade-paths)).

### Index internals

Section [9.1](../design.md#91-the-pipeline-of-indexquery).

| Structure | Contents | Built |
|---|---|---|
| Rule list | Every rule in load order and a map from code to position. Withdrawn rules and superseded codes go to a separate history map and never enter the arrays below. | On `add` and `load_pack` |
| Facet table | For each declared facet: which rules constrain it; a map from literal values (aliases resolved) to rule positions; a short list of rules with glob patterns or `none_of`, checked with `fnmatch`; version ranges parsed into integer tuples | On `add` |
| Axis table | For each axis: float64 arrays of lower and upper bounds (infinite when open), flags for closed ends, and a "constrains" array | On `add` |
| Time table | int64 arrays holding the civil-key envelope of each rule's periods; the exact interval union and month set stay on the rule | On `add` |
| Space table | Each rule's space kind; the envelope of every normalised part, with a part-to-rule array; a shapely STRtree over those envelopes; a cache of built, normalised and prepared geometries; for object-id rules, a map from namespace and id to rules | Envelopes on `add`; the tree on the first query after a change; geometries on first use |
| Regions | Namespace and id to geometry, and the union for each `region_ref` list | Names checked on `add`; unions built on first use |
| Products | Canonical name to `Product`, and case-folded alias to canonical name | On `add_product` |

Computed rules are stored in the same arrays, so the Index filters them exactly like records before `check()` runs. A shapely STRtree cannot be changed once built, so every `add` marks it stale and the next query rebuilds it; rebuilding over 10,000 polygons took 3.3 ms (this document's benchmark).

### Lazy loading in full

Section [9.2](../design.md#92-loading-packs); the load measurements are in [background.md](background.md#engine-measurements).

1. Parse with the standard `json` module; this dominates large packs.
2. Validate properties and fill the facet, axis and time arrays at once, so every naming, schema and calendar error surfaces at load.
3. Make one pure-Python pass over each ring to compute its envelope and longitude-step sum. A ring with no step over 180 degrees, no longitude outside [-180, 180] and a zero step sum needs no splitting or pole closure, and its raw envelope is already that of its normalised form, so its envelope goes straight into the tree.
4. Normalise every other ring at load (seam crossers, pole rings, longitudes written from 0 to 360), so its envelopes are right.
5. Build, normalise and prepare the shapely geometry the first time the rule becomes a spatial candidate, then cache it.

### Bulk path in full

Section [9.3](../design.md#93-the-bulk-path-query_points); the benchmark tables are in [background.md](background.md#engine-measurements).

GLHE wants a global per-cell map and CrocoDash wants masks over a model's cell centres: up to about a million points. `query_points(lon, lat, weights=None, time=..., axes=..., facets=..., requests=..., include_conditional=False)` returns a `PointResult` whose masks, fractions and skipped rules are keyed by `(product, code)`, with product None for rules evaluated on the base query:

1. Convert `lon`, `lat` and `weights` to flat float64 arrays (weights default to 1) and wrap longitudes exactly. Points with a NaN coordinate (land on many model grids) are inside no rule: they are left out of every mask and of the weight total.
2. Expand the requests as in section [4.12](../design.md#412-several-products-in-one-query-requests) and run stages 0 to 3 once for the base query and once per request, so each request gets its own default time and version. Space counts as given: the points are the support of every request, so `Request.support` must be None and `Product.grid` is not used. Object-id rules are conditional on `space` unless their namespace has region geometry. There is no `context`, so a computed rule needs a `mask()` hook to take part. Conditional findings get no mask (section [4.3](../design.md#43-matching-when-a-dimension-is-missing)).
3. Give every rule without a space a mask of every valid point and a fraction of 1.0.
4. Bucket the points into 64 × 64 tiles over their envelope and sort them by tile once. Give each tile the tight envelope of its own points, widened by 1e-9 degrees, and build a second STRtree over the tile boxes. Empty tiles are dropped, so a point set that straddles the antimeridian keeps its locality.
5. For each rule still alive whose envelope meets the points', query the tile tree with the rule's prepared geometry twice: with predicate `covers` (tiles entirely inside) and `intersects` (tiles touched). Points in covered tiles are inside without a test; points in touched but not covered tiles are tested with `shapely.intersects_xy`.
6. Points at latitude 90 or -90 are tested once per candidate rule against the whole pole edge (section [6.3](../design.md#63-boxes-closed-sets-and-areas)), and the result is broadcast to all of them, so the bulk path agrees with the single-query path at the poles. Plain `intersects_xy` would miss them: on a 0.25 degree global grid that includes both poles, a sector box from 0E to 90E and 80N to 90N holds 15,880 points with the pole-edge test and 14,801 without it (fixture 5).
7. For each rule with at least one point inside, store a boolean mask shaped like `lon` and the weighted fraction, and emit one finding with that fraction as `area_fraction` (`overlap_km2` is None, because the weights' units are unknown).
8. Computed rules run their `mask(lon, lat, query)` hook or are listed in `skipped`. The coverage rule's mask marks points outside each request's product coverage.
9. `PointResult.any(min_severity)` combines, with a logical or, the masks of the definite findings at or above that severity.

A rule's `min_overlap` is never applied on the bulk path. A bulk finding's `area_fraction` is a share of the whole point set, not of one request: over a global grid, CRU001's African regions hold about 6% of the cosine-weighted points (an estimate from the design review), below the rule's `min_overlap` of 0.1, which would hide the rule. Bulk findings are meant for maps and masks, not for `emit()`, and `PointResult.any()` ignores `min_overlap`.

The core of steps 4 to 7 for one part (the base query or one request) is sketched below. It is internal pseudo-code; the public API is in [api_sketch.py](api_sketch.py).

```python
def _bulk_masks(index, part, lon, lat, weights=None):
    """Masks and weighted fractions for one part of a bulk query (pseudo-code)."""
    weights = np.ones_like(lon) if weights is None else weights
    valid = np.flatnonzero(~(np.isnan(lon) | np.isnan(lat)))  # NaN: inside no rule
    total = weights[valid].sum()
    poles = {cap: valid[lat[valid] == cap] for cap in (90.0, -90.0)}
    tiles = Tiles(lon[valid], lat[valid], n=64)  # sort by tile; STRtree of tile boxes
    masks, fractions = {}, {}
    for rid in index.spatial_candidates(part, tiles.envelope):  # stages 0 to 4
        geom = index.prepared(rid)  # built and prepared on first use
        inside = tiles.tree.query(geom, predicate="covers")  # whole tiles inside
        touched = tiles.tree.query(geom, predicate="intersects")
        mask = np.zeros(lon.shape, dtype=bool)
        mask[valid[tiles.points_of(inside)]] = True  # no point tests for these
        edge = valid[tiles.points_of(np.setdiff1d(touched, inside))]
        mask[edge] = shapely.intersects_xy(geom, lon[edge], lat[edge])
        for cap, rows in poles.items():  # one pole-edge test per rule (section 6.3)
            mask[rows] = shapely.intersects(geom, POLE_EDGE[cap])
        if mask.any():
            masks[index.code(rid)] = mask
            fractions[index.code(rid)] = weights[mask].sum() / total
    return masks, fractions
```

`POLE_EDGE` holds the lines along latitude 90 and -90 from -180 to 180, and `Tiles` is the tile index of step 4. **Edges.** `intersects_xy` is closed, so a point exactly on a rule's edge is inside; `contains_xy` would put it outside, which matters on real grids where ERA5's 0.25 degree points sit on integer-degree edges (section [6.3](../design.md#63-boxes-closed-sets-and-areas)). The `covers` tile shortcut is closed as well.

### Inverse query in full

Section [10](../design.md#10-inverse-query-which-products-suit-this-request).

The inverse query turns the question around. A caller describes where, when and which variable, and `suitable()` returns the products that can serve the request, ordered by how many known concerns they carry. GLHE's roadmap asks for this as its "Global Product API"; CrocoDash mostly needs the coverage filter.

```python
def suitable(
    self,
    query: Query,
    variable: str,
    *,
    products: Sequence[str] | None = None,
    score: ScoreFn | None = None,
) -> list[Suitability]: ...
```

1. **Candidates.** By default, all products whose `variables` include `variable`, in name order. Names in `products` go through alias resolution; an unknown name raises `UnknownNameError`, and a named product that does not offer the variable raises `ValueError`.
2. **One request per product.** For each candidate P, the engine adds the request `Request(P, variables=(variable,))` to the caller's query, which must carry no requests and no `product`, `variable` or `version` facet of its own, and runs the request machinery of section [4.12](../design.md#412-several-products-in-one-query-requests). P's omitted `time` and `version` come from P, and if P declares a grid, P is judged on the cells the caller's region uses. Only definite findings of P's sub-query are used. Findings of the base query (rules that concern no product) are the same for every product, so they do not affect the order and are not attached.
3. **Coverage filter.** P is dropped when a coverage finding (QE001 or QE002) has action `do_not_use`, meaning the request lies entirely outside P's spatial or temporal coverage. A product that is only partly outside stays, and its SEVERE coverage finding counts against it.
4. **Score.** `score(P, q_P, findings)` returns a tuple of floats, where `q_P` is the caller's query with the single request for P, so its space is the caller's own region and the misfit term compares P's cells with the request, not with P's support; lower means fewer known concerns. The default is `default_score`.
5. **Order.** Sort by score, then product name, and return `Suitability(product, score, findings)`, with P's findings sorted as in `Index.query`, recommendations included.

Two consequences follow. Callers pass their own region, such as the lake outline: a product that declares a grid is judged on the cells that region uses, and a product without one on the region itself. For a small lake the difference matters (section [8.1](../design.md#81-the-contract)), so gridded products should declare their grids. And if the query has no time, each product is judged over its own whole record, so products are compared over different periods; pass a time range to compare like with like.

The default score is a tuple of three terms, compared in order:

| Term | Definition | Why |
|---|---|---|
| `worst` | The highest severity value (20, 30 or 40) among the counted findings, or 0 | One severe concern outranks any number of minor ones |
| `burden` | The sum over counted findings of weight × area part × time part. Weights are 1 for INFO, 2 for WARNING and 4 for SEVERE; the area and time parts are `area_fraction` and `time_fraction`, each 1.0 when None. Rounded to 0.001. | How much of the request is flagged, and how badly. It is a weighted sum, not a fraction: one SEVERE finding over the whole request scores 4. |
| `misfit` | `max(0, log2(cell size / query size))`. Cell size is `Product.resolution` in km (a size in degrees is converted at the query's centroid latitude as the side of an equal-area square); query size is the square root of the query's area. 0 when the query has no area or the product declares no resolution. | How many halvings coarser a product cell is than the request; products at least as fine tie |

Counted findings are definite findings of kind `caveat` or `coverage` whose `area_fraction` is not below the rule's `min_overlap`, the same threshold `emit()` uses; a finding whose `area_fraction` is None always counts. Recommendations are advice about what to do, not concerns about the data, so they are not counted, and conditional findings never count. The weights and the rounding are starting values to be tuned on GLHE lakes. `default_score` is public ([api_sketch.py](api_sketch.py)), so a custom score can build on it.

Any function with the `ScoreFn` signature can replace it. It is called once per product that passed the coverage filter, must have no side effects, and must return tuples of the same length for every product:

```python
def resolution_first(product, query, findings):
    worst, burden, misfit = qe.default_score(product, query, findings)
    return (misfit, worst, burden)


request = qe.Query(space=lake, time=y1991_2020)  # the lake outline, not CRU cells
ranked = index.suitable(request, "pre", score=resolution_first)
```

`Suitability.score` is for ordering only and should not be shown as a quality number. The explanation is the attached findings, each naming a rule, its message and how much of the request it covers, shown together with the products the coverage filter dropped. An empty findings list means only that no registered rule matched; consumers should word it as "no registered rule matched this request", and the documentation of `suitable()` describes its order as "fewest known concerns first". The documentation must also state the bias plainly: a product with fewer registered rules ranks higher simply because less has been written about it.

The pack is illustrative. It declares three products that all offer a variable named `pre`, with resolutions and periods from the design research: CRU TS 4.07 (0.5 degree, 1901 to 2022, global land), ERA5-Land (0.1 degree, 1950 onward, global land) and NWM retrospective v3.0 (about 1 km; coverage simplified here to the contiguous United States from February 1979). It holds CRU001 and CRU002, and no rule for ERA5-Land precipitation. It declares no grids, so all three products are judged on the lake outline; if it declared CRU TS's grid, CRU TS would be judged on the cells the lake touches, with the same result as long as those cells also lie inside CAF. The request is a hypothetical lake of about 150 km² near the equator in the Congo basin, inside the AR6 Central Africa region (CAF), for 1991 to 2020: `index.suitable(qe.Query(space=lake, time=y1991_2020), "pre")`.

- **NWM** is dropped: the lake lies outside the contiguous United States, so QE001 reports the whole request outside with action `do_not_use`. GLHE meets this today as a late failure inside its NWM accessor; here it is known before any download.
- **CRU TS** gets CRU001, with version 4.07 assumed. The lake lies wholly inside CAF, so `area_fraction` is 1.0, above the rule's `min_overlap` of 0.1; `time_overlap` runs from 2000-01-01 to 2020-12-31, so `time_fraction` is 7,671 / 10,958 = 0.700. CRU002 needs `cru_ts.stn`, which an inverse query normally lacks, so it is conditional and not counted. A 0.5 degree cell near the equator is about 55.6 km across and the lake about 12.2 km, so `misfit` is log2(4.54), about 2.18. The score is (30, 1.4, 2.18).
- **ERA5-Land** has no findings, and its 0.1 degree cell (about 11.1 km) is finer than the lake, so its score is (0, 0, 0).

The result lists ERA5-Land, then CRU TS; NWM is not listed. A consumer should display it along these lines: "ERA5-Land: no registered rule matched this request." "CRU TS 4.07: [CRU001] precipitation falls back to climatology over much of Africa, covering 70% of the period." "NWM: outside coverage (QE001)." ERA5-Land ranks first partly because this pack holds no rule about it, although ECMWF does publish ERA5-Land known issues. If GLHE passes the station counts for the CRU cells, CRU002 becomes definite, and SEVERE where whole years are climatology (section [12.4](../design.md#124-raster-derived-rules-cru002)), which pushes CRU TS further down.

### Emission in full

Section [11](../design.md#11-emission-and-policy); the evidence is in [background.md](background.md#emission-evidence).

The switch between logging, warning and raising follows xclim.

| Mode | What `emit()` does with each finding it keeps |
|---|---|
| `"warn"` (default) | `warnings.warn(text, category)`, where the category is `InfoAdvisory`, `WarningAdvisory` or `SevereAdvisory` by severity, all subclasses of `AdvisoryWarning(UserWarning)`. The warning instance carries the finding as `.finding`. |
| `"log"` | `logging.getLogger("queryearth").log(finding.severity, text, extra={"finding": finding})`. Severity values equal logging levels, so no custom level is registered; a `SEVERE` finding shows as `ERROR`. |
| `"raise"` | Raises one `AdvisoryError` whose `.findings` holds every kept caveat and coverage finding. If none is kept, nothing is raised and `emit()` returns normally. |
| `"ignore"` | Nothing; returns an empty list, so consumers can call `emit()` unconditionally |

**Recommendations are logged at INFO.** In the log, warn and raise modes, every recommendation that survives the filters below goes to the `queryearth` logger at `INFO`, whatever `min_severity` and `raise_at` say; a recommendation is never warned and never raised. This is the approved plan's rule: recommendations are emitted at info level by default and are also returned as data. Whether the line appears depends on the application's logging configuration, as for any `INFO` record; queryearth adds no handler. `Policy(show_recommendations=False)` turns this off, and the `"ignore"` mode emits nothing at all.

`emit()` drops, before reporting: conditional findings; caveats and coverage findings below `min_severity` (default `WARNING`); findings whose `area_fraction` is below the rule's `min_overlap` (a None `area_fraction` is never dropped); codes in `ignore`, matched exactly or as a prefix such as `"QE"` or `"CRU"`; drafts when `include_drafts` is False; recommendations when `show_recommendations` is False; and a second finding with the same code, query label and product in the same call. The product is part of that key because one query can carry requests for two products that are both partly outside coverage, giving two QE001 findings.

`raise_at` works with the log and warn modes: caveats and coverage findings below it are logged or warned first, then every one at or above it is raised together in one `AdvisoryError`. Collecting before raising, as pandera's lazy validation does, shows every blocking problem at once. `emit()` returns the findings it logged or warned, so a caller can record what the user was shown.

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

The active `Policy` is held in a `contextvars.ContextVar`. `policy(**changes)` installs a modified copy for the duration of a `with` block and restores the previous one, even after an exception. Keyword arguments to `emit()` override the active policy for that one call.

Each thread has its own context, and each asyncio task runs in a copy of the context that created it, so a policy set while serving one dashboard session or MCP request never changes another. In Python 3.11 to 3.13 a new thread starts with an empty context; to carry the policy into a worker, submit `contextvars.copy_context().run`.

A rule that fires on almost every request teaches people to ignore all advisories. GEN001 (section [12.2](../design.md#122-computed-rules)), "the request is much smaller than the product cells that represent it", fires for nearly every HydroLAKES lake against a 0.5 degree product, so it has severity `INFO`: at the default floor it is not emitted, but it stays in the findings. The defences, in order of preference: authors give an honest severity; a rule's `min_overlap` keeps a domain that only clips a regional caveat from warning; conditional findings are never emitted; repeats are dropped, and consumers make one query per case or lake, with one request per product, rather than one per chunk of work (section [15.1](../design.md#151-crocodash)); and users silence codes or prefixes with `Policy.ignore` or `-W`.

Recommendations have severity `INFO` by default and are meant to be used as data: a consumer reads `finding.suggestions` and applies or records them. `emit()` also logs them at `INFO` in every mode except `"ignore"` (section [11.1](../design.md#111-modes-and-policy)), so a person running the code can see what was suggested without the consumer lowering `min_severity`, and a recommendation never turns into a warning. `emit()` never applies a suggestion.

```python
shown = qe.emit(found, mode="log")  # caveats from WARNING up; recommendations at INFO

with qe.policy(raise_at=qe.Severity.SEVERE, ignore=frozenset({"GEN001"})):
    try:
        qe.emit(found)  # warns for caveats, then raises once for SEVERE findings
    except qe.AdvisoryError as err:
        blocked = [f.code for f in err.findings]
```

### Schema validator

Section [12.1](../design.md#121-data-only-packs).

```text
packs/croc/
  pack.toml                 # name, version, owned code prefixes, licence, products, regions
  rules/arctic.geojson      # a FeatureCollection with one Feature per rule
  regions/ar6_land.geojson  # optional named regions for region_ref
```

Section [5](../design.md#5-record-format) defines the record and the pack, and section [16](../design.md#16-worked-examples) gives a complete pack of 14 records. `index.load_pack("packs/croc")` validates each file against the JSON Schema with a small standard-library validator, runs the loader checks of section [5.3](../design.md#53-loader-checks), and returns the codes it loaded. The validator implements exactly the keywords [schema.json](schema.json) uses: `$ref` and `$defs`; `type`, `enum` and `const`; `properties`, `required`, `additionalProperties`, `patternProperties`, `propertyNames`, `minProperties` and `maxProperties`; `items`, `prefixItems`, `minItems`, `maxItems` and `uniqueItems`; `pattern`, `minLength` and `maxLength`; `minimum`, `maximum`, `exclusiveMinimum` and `exclusiveMaximum`; `oneOf`, `anyOf`, `allOf`, `not`, `if` and `then`. `format` is treated as an annotation, as JSON Schema 2020-12 does by default, and `title`, `description`, `$schema` and `$id` carry no rules. The third-party jsonschema package and pyproj are test extras, never run-time dependencies, and a test checks that the standard-library validator agrees with jsonschema on the 14 example records and on the broken variants listed in [examples/README.md](examples/README.md#how-the-examples-were-checked). During the design research, GDAL 3.12.4 (through pyogrio 0.13.0) recognised a pack file as JSON-FG automatically and exposed `time_start` and `time_end` columns. Not every editor keeps the `time` member (whether geojson.io does is unverified, and QGIS moves the top-level `id` into the properties), which is why the code in `properties` is authoritative and `time_start`/`time_end` are accepted as a fallback. Load times are in sections [9.2](../design.md#92-loading-packs) and [13](../design.md#13-performance-targets).

### Authoring paths

Section [12](../design.md#12-authoring-rules-and-the-registry).

Rules come from three authoring paths. All three produce `RuleKind` objects and go through the same scope matching (section [4.3](../design.md#43-matching-when-a-dimension-is-missing)). Pick the simplest path that can express the rule.

| Path | Written by | Runs code when loaded | Best for |
|---|---|---|---|
| Data-only pack | Anyone, in a text editor, geojson.io or QGIS | No | Documented issues with a fixed area, period, product, version or resolution (CRU001, ERA5-001, CROC101, CROC102) |
| `ComputedRule` subclass | Python developers | Yes, on import | Rules computed from the request or from data the caller holds; tunable thresholds |
| `@index.rule` function | Python developers | Yes, on import | One short computed rule |

### Computed rules in full

Section [12.2](../design.md#122-computed-rules); the code of GEN001 is in [examples/README.md](examples/README.md#gen001).

A computed rule is a class whose class keyword arguments give its code and scope (section [4.11](../design.md#411-core-objects)). Thresholds are class attributes, documented next to their source, so a reader can find and change them in one place. A rule that needs data the caller holds names the `Query.context` keys in `requires`; if a key is missing, the finding is conditional on `context:<key>` rather than silently dropped, and `check()` does not run, since it runs only for a definite match. A rule without a `mask()` hook cannot run on the bulk path and is listed in `PointResult.skipped`. CRU002 (section [12.4](../design.md#124-raster-derived-rules-cru002)) is the worked example.

A single short rule can be a function; the decorator takes the same keywords as the class, and the title comes from the docstring. GEN001 compares the caller's own area, passed in the context, with the support the query describes. A rule cannot compare the support itself with one product cell, because the support is never smaller than a cell. GEN001 concerns whichever product supplies the support, so it declares the facet `product = ["*"]`: it is evaluated once per request, on that request's support (section [4.12](../design.md#412-several-products-in-one-query-requests)), and it is conditional on `"product"` when the query names none.

In the research prototype, a 6.7 km² lake was compared with a CRU TS cell of about 2,786 km² at 25.7S, a ratio of about 0.0024.

### Registry lessons

Section [12.3](../design.md#123-the-index-codes-and-lifecycle).

Rules, products, regions, axes and facets live on an explicit `Index`; there is no hidden global registry. `Index.default()` is an application default created on first use, following pint's application registry, for scripts and notebooks. A library such as CrocoDash or GLHE keeps its own Index, so two consumers in one process never see each other's rules.

Registering a code the Index already holds raises `DuplicateCodeError`, whether the rule comes from a pack, a class or a function. This is a lesson from CrocoDash's `ProductRegistry`: `register` (`raw_data_access/registry.py:15`) assigns into a class-level dictionary, so a second product with the same name silently replaces the first; `load()` assigns a local variable (`registry.py:78`), so the class-level `loaded` flag never changes; and class-level state means every caller in a process shares one registry, the shape of the known `CASEROOT` singleton bug. queryearth keeps the automatic registration and fixes all three.

### Codes, versions and lifecycle

Section [12.3](../design.md#123-the-index-codes-and-lifecycle).

**Codes.** A code is a prefix plus three or four digits, in the style of ruff and pylint (`CRU001`, `ERA5-014`). Prefix ownership is defined in section [5.3](../design.md#53-loader-checks): exclusive between packs, open to rules added from Python, and `QE` reserved. Prefixes let users silence a family of rules (`ignore={"CRU"}`, or `-W "ignore:[CRU"`). A code is never reused for a different issue; a retired rule is withdrawn instead.

**Products.** Each product has a canonical lowercase slug and aliases, declared in `pack.toml` under `[products.<slug>]` or in Python with `Index.add_product`; Python is needed when the coverage or the grid is a callable. The two consumers already name products differently (GLHE writes `CRUTS`, CrocoDash lower-cases names such as `glorys`), and aliases make both resolve to the same product.

| Field | Use |
|---|---|
| `status` | `draft` (the default), `reviewed` or `deprecated`. Every finding carries it, and `Policy(include_drafts=False)` keeps drafts out of emission. |
| `created`, `updated` | When the record itself changed; never the data time |
| `withdrawn` | The rule is kept for history but never matches. Use it instead of deleting a rule or reusing its code. |
| `supersedes` | Codes that stop matching while this rule is loaded, for example a reviewed rule that replaces a provisional one |
| `aliases` | The source's own identifiers for the issue, such as an ECMWF known-issue number or an ESGF errata id |
