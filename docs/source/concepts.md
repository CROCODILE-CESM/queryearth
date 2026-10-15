# Rules and queries

## Rules

A {class}`~queryearth.Rule` has:

- a `code`, unique on its Registry, which may be a path such as `REGION/ITF/ITF004`: its [category](#categories) is the path before the last slash;
- a `title` and a `message`;
- a `level`: `"info"`, `"warning"` (the default) or `"error"`;
- a `scope`, mapping each [dimension](dimensions.md) the rule constrains to its value;
- `properties`, anything else the rule carries, such as an instruction, references or evidence. queryearth never reads them; it keeps them as given and writes them back to a rule file unchanged.

```python
registry = qe.Registry([qe.Axis("resolution", "km")])
rule = qe.Rule(
    code="REGION/ITF/ITF004",
    title="Lombok Strait spans only a few cells",
    message="Lombok Strait spans only a few cells even at 5 km.",
    scope={"space": sp.box(115.4, -9, 116.1, -8), "resolution": {"gt": 2}},
    properties={"instruction": "Count the cells across the strait."},
)
registry.add(rule)
```

{meth}`Registry.add() <queryearth.Registry.add>` checks each scope value with its dimension. A code already on the Registry raises `DuplicateCodeError`. `Registry.rules` lists every rule, in the order added.

## Categories

A code may be a path; its category is the path before the last slash. `REGION/ITF/ITF004` is in category `REGION/ITF`, which sits in `REGION`, so categories need no declaring. `rule.category` gives a rule's category, or None for a code without a slash. Codes are unique as whole paths, so `REGION/ITF/001` and `DOMAIN/OBC/001` can both exist. Moving a rule to another category changes its code.

A query is about dimensions only. To keep the findings in one category and those below it, filter on the code:

```python
findings = registry.query(resolution=(9.1, 9.3))
in_region = [rule for rule in findings if rule.code.startswith("REGION/")]
```

## Queries

{meth}`Registry.query() <queryearth.Registry.query>` takes the query's value on any of the dimensions, by name, and returns the rules that apply, highest level first, then by code:

```python
domain = sp.box(105, -15, 145, 10)  # the Indonesian seas
registry.query(space=domain, resolution=(9.1, 9.3))  # [the ITF004 rule]
```

A rule applies when, on every dimension it constrains, the query gives a value and the two share at least one value: the query's box meets the rule's polygon, its interval meets the rule's, its range of numbers meets the rule's range, or one of its names matches. Within a rule, all its dimensions must hold, so "or" across dimensions, such as "the Arctic in northern winter, or the Antarctic in southern winter", is two rules.

A dimension the rule leaves out matches anything. A dimension the rule constrains and the query leaves out does **not** match: the query gives no value to share, so a rule about one product says nothing until the query names a product. Passing `None` leaves a dimension out, which helps when you build a query from a dict. To see every rule regardless of a query, use `registry.rules`.

## Findings

What a query returns are the {class}`~queryearth.Rule` objects that apply. To print or save one, use its GeoJSON Feature, as a rule file holds it:

```python
import json

for rule in registry.query(space=domain, resolution=(9.1, 9.3)):
    print(json.dumps(registry.to_feature(rule), indent=2))
```

## Space

Coordinates are longitude and latitude in degrees, and edges are straight lines in longitude and latitude, as in GeoJSON. Make spaces with `queryearth.space`:

- `sp.point(lon, lat)`, for queries;
- `sp.box(west, south, east, north)`, where `west > east` crosses the antimeridian and `-180` to `180` is a full band of latitude;
- `sp.polygon(shape)`, from a GeoJSON Polygon or MultiPolygon, a shapely geometry, or a list of `(lon, lat)` positions.

Shapes are normalised once: longitudes in any convention are wrapped, rings that cross ±180 are split there, and invalid rings are repaired. Matching uses closed sets, so a point on an edge is inside, and shapes that touch across ±180 meet. A box to latitude 90 or -90 covers the polar region beyond its southern or northern edge, such as `sp.box(-180, 66.5, 180, 90)` for the Arctic; a ring that goes all the way around a pole is refused, so write a polar region as a box.

## Time

A time is an interval, made with `qe.interval(start, end)`. Its ends are ISO 8601 dates or timestamps, `datetime.date` or `datetime.datetime` values, numpy `datetime64` values, or anything with `year`, `month` and `day` attributes, so cftime and pandas values work; `".."` or `None` is an open end. Both ends are inclusive: an end date covers its whole day, so `qe.interval("2020-01-01", "2020-01-31")` is all of January. queryearth uses one calendar, the proleptic Gregorian; model calendars such as `noleap` work unchanged, and a date that does not exist, such as 30 February, raises an error.
