# Concepts

## Rules and their scope

A **rule** has a code, an outcome (what it says) and a scope (where, when and for what it applies). A scope is a conjunction over dimensions, and a dimension the rule leaves out matches anything:

| Dimension | Rule side | Query side |
|---|---|---|
| `space` | a polygon, or a named region | a point or a polygon |
| `time` | intervals, optionally limited to some months of the year | an interval |
| axes, such as `resolution` | a range: `{"gt", "ge", "lt", "le"}` in the axis's unit | a number or a range `(lo, hi)` |
| facets: `product`, `variable`, `version`, `model`, `component` | values or glob patterns; versions as ranges | values |
| plugin dimensions | whatever the plugin parses | whatever the plugin parses |

Axes are declared on the {class}`~queryearth.Registry` with one unit each, for example `qe.Axis("resolution", "km")`. The default facets can be replaced or extended with `Registry(facets=...)`.

A **code** is a prefix plus three or four digits, such as `CRU001`, or `ERA5-014` (a prefix that ends in a digit needs the hyphen). The prefix `QE` is reserved for the built-in coverage findings.

## Queries and findings

A {class}`~queryearth.Query` gives any subset of the same dimensions. "Resolution 8 km" on its own is a complete query. {meth}`Registry.query() <queryearth.Registry.query>` takes a `Query` or its fields as keywords, and returns a sorted list of {class}`~queryearth.Finding` objects: most severe first, then by kind and code.

A finding is the rule's outcome plus how it matched:

- `kind` is `caveat`, `coverage` or `recommendation`;
- `severity` is `INFO`, `WARNING` or `SEVERE`, with the values of the matching `logging` levels (20, 30, 40);
- `area_fraction` and `overlap_km2` give how much of the query's area the rule covers;
- `time_overlap` and `time_fraction` give the overlapping periods and their share of the query's time;
- `axes`, `matched_facets` and `dims` hold the overlap on each other dimension;
- `suggestions` holds structured actions (`target`, `key`, `value`, `rationale`) for a recommendation. queryearth never interprets them; your code applies them.

`Finding.to_dict()` gives a JSON-ready dictionary.

## Conditional findings

When a query leaves out a dimension that a rule constrains, the rule can neither match nor fail. Its finding is **conditional**: `conditional_on` names what is missing, for example `("space", "model")`. Conditional findings are hidden unless you pass `include_conditional=True`, which is a quick way to see every rule that might apply:

```python
registry.query(axes={"resolution": 8}, include_conditional=True)
```

## Several products in one query: requests

A query can name the products it uses, each with its own variables, version, time and support. With the products of the [toy pack](example.md):

```python
registry.query(
    space=domain,
    time=qe.interval("2020-01-01", "2020-12-31"),
    requests=[
        qe.Request("toy_ocean", variables=("thetao", "so")),
        qe.Request("toy_atmos", variables=("t2m",)),
    ],
)
```

Each request runs as its own sub-query, and every finding names its `product` and `request`. When the query gives no time, a request takes its product's coverage time. When a request gives no version, it takes the product's version. Either way, `Finding.assumed` lists what was filled in. `facets={"product": [...], "variable": [...]}` is shorthand for one request per product.

Products are declared with {meth}`Registry.add_product() <queryearth.Registry.add_product>` or in a pack. A product's **coverage** (a time range and optionally an area) produces two built-in findings: **QE001** when part of the request lies outside its area, and **QE002** when part lies outside its time.

## Query with what you use

Pass the space and time a product actually contributes: the cells and time steps you read, not a buffered shape. A model grid is converted to a polygon by the caller, for example its outline.

## Space

Coordinates are longitude and latitude in degrees, and edges are straight lines in longitude and latitude, as in GeoJSON. Helpers in `queryearth.space`:

- `point(lon, lat)`;
- `box(west, south, east, north)`, where `west > east` crosses the antimeridian;
- `polygon(shape)` for a GeoJSON mapping, a shapely geometry or a coordinate list.

Shapes are normalised once: longitudes from 0 to 360 are wrapped, rings that cross ±180 are split there, and invalid rings are repaired. A ring that goes all the way around a pole raises an error: close it along latitude 90 or -90 first. Matching uses closed sets, so a point on an edge is inside. Area fractions use spherical areas.

## Time

queryearth uses one calendar, the proleptic Gregorian. A time is an ISO 8601 date or timestamp string, a `datetime.date` or `datetime.datetime`, a numpy `datetime64`, or any object with `year`, `month` and `day` attributes (so cftime and pandas values work). `".."` is an open end. An end date covers its whole day, so `qe.interval("2020-01-01", "2020-01-31")` is all of January.

Model calendars such as `noleap` work unchanged, because every noleap date is a valid Gregorian date. A date that does not exist in the Gregorian calendar, such as 30 February in a 360-day calendar, raises an error.
