# Dimensions

Everything a rule can be scoped by is a **dimension**: space, time, grid resolution, forcing product, and any you define. Each dimension has a name, which is its key in rules, queries and rule files, and decides for itself what its values look like and when two of them match.

## What comes with queryearth

| Dimension | A rule gives | A query gives | In a rule file |
|---|---|---|---|
| space | a polygon: `sp.box(west, south, east, north)` or `sp.polygon(geojson)` | a point or a polygon | the Feature's `geometry` |
| time | `qe.interval(start, end)` | `qe.interval(start, end)` | the Feature's `time`: `{"interval": [start, end]}` |
| `qe.Axis(name, unit)` | a range with any of `gt`, `ge`, `lt`, `le`: `{"lt": 8}` | a number, or a range `(lo, hi)` | `"dimensions": {name: {"lt": 8, "unit": "km"}}` |
| `qe.Labels(name)` | a name or names, with `*` and `?` wildcards: `["jra", "era5*"]` | a name or names | `"dimensions": {name: ["jra", "era5*"]}` |

Space, time and axes are the base dimensions, and labels the extension that comes with them. Every Registry has space and time; declare the others when you make it:

```python
registry = qe.Registry([qe.Axis("resolution", "km"), qe.Labels("product")])
```

[Rules and queries](concepts.md#space) has the details of space and time.

**Rules are data; code lives in dimensions.**

- A new kind of value, or a new way to compare values, is a new dimension.
- A value derived from your case is computed when you build the query, and given to an `Axis` or your own dimension: CrocoDash computes `cell_size_ratio = largest / smallest` from its grid's cells and queries an Axis with it.
- Advice is a rule: plain data in a rule file, which never runs code.

## The contract

A dimension subclasses {class}`~queryearth.Dimension`, sets `name`, and implements three methods. Python refuses to create one that leaves any out.

| Method | Does |
|---|---|
| `parse_rule(value)` | checks a rule's value, given in Python or read from a rule file's JSON, and returns it in the form `matches` takes; raises `ValueError` for a bad one |
| `parse_query(value)` | the same for a query's value |
| `matches(rule, query)` | says whether the two share at least one value, such as a point, an instant, a number or a name |

That is all a dimension does. The Registry does the rest, the same way for every dimension, built in or yours:

- `Registry.add` calls `parse_rule` on each value in a rule's scope, and refuses a name the Registry has not declared.
- `Registry.query` calls `parse_query` on each value in the query, and refuses an undeclared name, so a misspelt one never looks like "no rule applies".
- A rule applies when, on **every** dimension it constrains, the query gives a value and `matches` is true: the two share at least one value. A dimension the rule leaves out matches anything. A dimension the rule constrains and the query leaves out does not match, since the query gives no value to share.
- A rule keeps each value as it was given, and a rule file holds it that way, under the rule's `"dimensions"` property; `Registry.from_file` parses it with `parse_rule` when it adds the rule. So writing a rule needs no dimension, and a value given in Python is plain JSON, apart from space and time, whose `Space` and `Interval` objects write themselves.

Space and time are written on the same class, in `queryearth/dimensions.py`, and differ in one place only: in a rule file their values go in the Feature's `geometry` and `time` members, where GeoJSON and JSON-FG put them, so that other tools can read them.

## A worked example: Labels

`Labels` matches names, such as a forcing product or a compset's ice component, with wildcards. This is its whole source:

```{literalinclude} ../../queryearth/dimensions.py
:language: python
:pyobject: Labels
```

- It is a frozen dataclass, so `Labels("product")` sets `name`.
- `parse_rule` takes one name or a list, and checks that each is a non-empty string. It returns a tuple, which is what `matches` takes.
- A query gives names in the same form, so `parse_query` is `parse_rule`.
- `matches` is true when some query name matches some rule pattern, by `fnmatch`'s case-sensitive globs: the rule `["jra", "era5*"]` matches the query `"era5_land"`, not `"ERA5"`.

## Writing your own

Write the three methods for whatever your values are. A value can be any JSON value the dimension knows how to parse: a number, a range, a shape, or a mapping of several fields. A dimension sees only its own value, so inputs it needs together go in that one value, or you combine them when you build the query, as CrocoDash does with `cell_size_ratio`.

This dimension describes the sea floor under a model, by its depth and its slope, in one value. A rule bounds either field, using an `Axis` for each:

```python
class Bathymetry(qe.Dimension):
    name = "bathymetry"
    fields = {"depth": qe.Axis("depth", "m"), "slope": qe.Axis("slope", "degree")}

    def parse_rule(self, value):  # a range on either field: {"slope": {"gt": 5}}
        if not isinstance(value, dict) or not value or set(value) - set(self.fields):
            raise ValueError(f"a bathymetry rule bounds depth or slope, not {value!r}")
        return {k: self.fields[k].parse_rule(v) for k, v in value.items()}

    def parse_query(self, value):  # both fields: {"depth": 4000, "slope": 8}
        if not isinstance(value, dict) or set(value) != set(self.fields):
            raise ValueError(f"bathymetry gives depth and slope, not {value!r}")
        return {k: self.fields[k].parse_query(v) for k, v in value.items()}

    def matches(self, rule, query):
        return all(self.fields[k].matches(r, query[k]) for k, r in rule.items())


registry = qe.Registry([Bathymetry()])
registry.add(
    qe.Rule(
        "TOPO001",
        "Steep slopes",
        "Pressure-gradient errors grow over steep bathymetry.",
        scope={"bathymetry": {"slope": {"gt": 5}}},
    )
)
registry.query(bathymetry={"depth": 4000, "slope": 8})  # [TOPO001]
```

A rule file holds the rule as `"dimensions": {"bathymetry": {"slope": {"gt": 5}}}`, as given. To read it, declare the dimension again: `qe.Registry.from_file("bathymetry.geojson", dimensions=[Bathymetry()])`. A file that names a dimension the Registry has not declared is refused, naming the file, the rule and the dimension: the file holds values, and the code that knows what they mean is yours.
