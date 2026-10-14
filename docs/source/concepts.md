# Concepts

## Rules and their scope

A **rule** has a code, a title, a message and a level, and may list changes. Its scope says where, when and for what it applies. Rules are written in Python or as records in GeoJSON rule files, and both are added to a {class}`~queryearth.Registry`, the object you query (see [Writing rules](rules.md)). A scope is given on [dimensions](#dimensions), such as space, time and grid resolution.

A rule without changes is a warning or a note, such as "these values are climatology, not observations". A rule with changes suggests what to do: each change is a {class}`~queryearth.Change` with a `target`, a `key`, a `value` and an optional `rationale`, such as `qe.Change("MOM_input", "DT", 900.0)`. queryearth never interprets changes; your code applies them, for example to a model's settings.

The **level** is a standard `logging` level, or its name: `"info"`, `"warning"` or `"error"`. It defaults to `logging.WARNING` (30) for a rule without changes and `logging.INFO` (20) for a rule with changes.

A **code** is a prefix plus three or four digits, such as `CRU001`, or `ERA5-014` (a prefix that ends in a digit needs the hyphen).

## Dimensions

Everything a rule can be scoped by is a dimension. Each dimension has a set of values: a rule's scope picks some of them, a query picks some of them, and the two meet where they overlap. There are six kinds:

| Kind | Values | A rule gives | A query gives | Declare it with |
|---|---|---|---|---|
| Space (built in) | points on the sphere | a polygon or box | a point or polygon | — |
| Time (built in) | the time line | intervals, optionally some months each year | an interval | — |
| Axis | numbers, with a unit | a range: `{"lt": 10}`, with any of `gt`, `ge`, `lt`, `le` (and optionally the declared `"unit"`) | a number or a range, such as `8` or `(5, 10)` | `qe.Axis("resolution", "km")` |
| Labels | names | names, with `*` and `?` wildcards: `["glorys", "era5*"]`; or `{"any_of": [...], "none_of": [...]}` | one or more names, such as `"era5"` | `qe.Labels("product")` |
| Versions | versions, such as `4.07` or `ERA5T` | ranges or exact versions: `{"introduced": "4.00", "fixed": "4.09"}`, `{"versions": ["ERA5T"]}`, or a list of them | one or more versions, such as `"4.07"` | `qe.Versions("version")` |
| Your own | anything | anything | anything | a class with `name`, `parse_rule`, `parse_query` and `match` |

A rule's values are written the same way in Python (`Scope(dimensions=...)`) and in a rule file (the record's `"dimensions"` member).

A scope picks values on some dimensions and leaves the rest open: a dimension the rule leaves out matches anything. A rule applies when its scope and the query overlap on every dimension. A query that leaves out a dimension the rule constrains gets a [conditional finding](#conditional-findings).

Space and time are built into every Registry. Every other dimension is declared, in one list, when you make the Registry, and its name is the key that rules and queries use:

```python
registry = qe.Registry(
    "mine",
    dimensions=[
        qe.Axis("resolution", "km"),
        qe.Labels("product"),
        qe.Labels("variable"),
        qe.Versions("version"),
    ],
)
```

Scopes and queries give space and time as `space=` and `time=`, and the other dimensions in one mapping, such as `dimensions={"resolution": 8, "product": "era5"}`. A name the Registry has not declared raises `UnknownNameError`, so a misspelt name never looks like "no rule applies". [Extending queryearth](extending.md#dimension-plugins) shows how to write your own kind.

## Queries and findings

A {class}`~queryearth.Query` gives values on any subset of the dimensions. "Resolution 8 km" on its own is a complete query. {meth}`Registry.query() <queryearth.Registry.query>` takes a `Query` or its fields as keywords, and returns a sorted list of {class}`~queryearth.Finding` objects: highest level first, then those without changes before those with changes, then by code.

A finding carries the rule's `code`, `title`, `message`, `level` and `changes`, plus how it matched:

- `area_fraction` and `overlap_km2` give how much of the query's area the rule covers;
- `time_overlap` and `time_fraction` give the overlapping periods and their share of the query's time;
- `dimensions` holds, for each other dimension, a {class}`~queryearth.DimMatch` with its `overlap` and, where it can be measured, its `fraction` of the query's values.

`Finding.to_dict()` gives a JSON-ready dictionary.

## Conditional findings

When a query leaves out a dimension that a rule constrains, the rule can neither match nor fail. Its finding is **conditional**: `conditional_on` names what is missing, for example `("space", "model")`. Conditional findings are hidden unless you pass `include_conditional=True`, which is a quick way to see every rule that might apply:

```python
registry.query(dimensions={"resolution": 8}, include_conditional=True)
```

## Products

`product` is an ordinary label dimension, matched like `variable`: exact, case-sensitive names or glob patterns. Coverage limits and other per-product facts are ordinary rules scoped by it, and you query once per product you use. In the [toy example](example.md), TOY004 is an ERROR for `toy_coastal` before 2010:

```python
registry.query(time=("2005-01-01", "2005-12-31"), dimensions={"product": ["toy_coastal"]})
# [TOY004] toy_coastal starts in 2010 (2005-01-01..2005-12-31; draft)
```

## Query with what you use

Pass the space and time a product actually contributes: the cells and time steps you read, not a buffered shape. For a model grid, {func}`queryearth.converters.grid_outline` gives its outline from the corners of its cells, such as mom6_forge's `grid.qlon` and `grid.qlat`:

```python
domain = qe.converters.grid_outline(grid.qlon.values, grid.qlat.values)
registry.query(space=domain, time=("2000-01-01", "2000-12-31"))
```

A grid that contains a pole becomes the whole polar cap beyond its outline, since queryearth does not take a ring around a pole: no rule that touches the grid is missed, but area fractions are measured against the cap.

## Space

Coordinates are longitude and latitude in degrees, and edges are straight lines in longitude and latitude, as in GeoJSON. Helpers in `queryearth.space`:

- `point(lon, lat)`;
- `box(west, south, east, north)`, where `west > east` crosses the antimeridian;
- `polygon(shape)` for a GeoJSON mapping, a shapely geometry or a coordinate list.

Shapes are normalised once: longitudes from 0 to 360 are wrapped, rings that cross ±180 are split there, and invalid rings are repaired. A ring that goes all the way around a pole raises an error: close it along latitude 90 or -90 first. Matching uses closed sets, so a point on an edge is inside. Area fractions use spherical areas.

## Time

queryearth uses one calendar, the proleptic Gregorian. A time is an ISO 8601 date or timestamp string, a `datetime.date` or `datetime.datetime`, a numpy `datetime64`, or any object with `year`, `month` and `day` attributes (so cftime and pandas values work). `".."` is an open end. An end date covers its whole day, so `qe.interval("2020-01-01", "2020-01-31")` is all of January.

Model calendars such as `noleap` work unchanged, because every noleap date is a valid Gregorian date. A date that does not exist in the Gregorian calendar, such as 30 February in a 360-day calendar, raises an error.
