# Writing rules

There are three ways to write a rule: a {class}`~queryearth.Rule` built in Python, a computed rule whose outcome depends on the query, or a record in a GeoJSON **rule file**. All three end up on a {class}`~queryearth.Registry`, the object you query.

## Rules in Python

```python
import queryearth as qe
from queryearth import space as sp

registry = qe.Registry(
    "mine",
    dimensions=[
        qe.Axis("resolution", "km"),
        qe.Labels("product"),
        qe.Labels("variable"),
        qe.Labels("model"),
    ],
)
rule = qe.Rule(
    code="MINE001",
    title="Coastal values are interpolated",
    message="Within this box, values near the coast come from interpolation.",
    action="use_with_caution",
    scope=qe.Scope(
        space=sp.box(-98, 18, -80, 31),
        dimensions={"variable": ["thetao", "so"]},
    ),
)
registry.add(rule)
```

A {class}`~queryearth.Scope` takes `space`, `time` and, in `dimensions`, a value for each other [dimension](concepts.md#dimensions) the rule constrains, by its declared name. `changes` lists {class}`~queryearth.Change` objects, or mappings with the same fields. `level` takes a `logging` level or its name, such as `"error"`, in place of [the default](concepts.md#rules-and-their-scope). Adding a code that is already on the Registry raises `DuplicateCodeError`.

## Computed rules

A computed rule decides its outcome from the query, or from data the caller passes in `Query.context`. Register a function with `@registry.rule`; its docstring is the title:

```python
@registry.rule("MINE102", dimensions={"resolution": {"gt": 0}})
def time_step(query, match):
    """Set the time step from the finest cells"""
    finest_km = match.dimensions["resolution"].overlap[0].lo
    return {"changes": [qe.Change("settings", "dt", 30.0 * finest_km)]}
```

The function runs only when the scope matches definitely. It returns `True` (one finding with the declared outcome), `False` or `None` (no finding), a mapping of `Finding` fields to override, or several such mappings. Like any rule, its findings default to INFO when they carry changes, unless the rule declares a `level`. For a class-based rule, subclass {class}`~queryearth.ComputedRule` with the same keywords and define `check(self, query, match)`. `requires=["key"]` names `Query.context` keys the rule needs: without them, the finding is conditional. A `mask(lon, lat, query)` method lets the rule take part in {meth}`~queryearth.Registry.query_points`.

## Rule files

A rule file is a GeoJSON file holding a FeatureCollection of records, or a single record. A FeatureCollection can declare the [dimensions](concepts.md#dimensions) its rules use in a top-level `dimensions` member, such as `[{"name": "resolution", "kind": "axis", "unit": "km"}, {"name": "product", "kind": "labels"}]`: each has a `name`, a `kind` (`axis`, `labels` or `versions`), a `unit` for an axis, and optionally a `description`. {meth}`Registry.from_file() <queryearth.Registry.from_file>` then makes a Registry with those dimensions and loads the rules:

```python
registry = qe.Registry.from_file("examples/toy/rules.geojson")
```

{meth}`Registry.load() <queryearth.Registry.load>` adds a file's rules to a Registry you already have, and returns their codes. That Registry must declare every dimension the records use, and a file that declares its dimensions must declare them as the Registry does:

```python
codes = registry.load("mine.geojson")
```

Loading never runs code. Every problem is reported at once in a `LoadError` that names the file, the feature's position and its code, and the Registry is left unchanged. Products need no declaration of their own: records name them as values of a `product` label dimension. A finding from a loaded rule has the file name as its `source`. A Feature or FeatureCollection mapping can also be added directly with `Registry.add(mapping)`.

### Records

Each rule is one GeoJSON Feature. Its `geometry` is a Polygon, a MultiPolygon or null (null means everywhere). Its time goes in the top-level JSON-FG `time` member: `{"interval": ["2000-01-01", "2003-12-31"]}`, `{"date": ...}`, `{"timestamp": ...}` or null. The rest is in `properties`:

| Group | Properties |
|---|---|
| Identity and outcome | `code`, `title` and `message`, all required; `level` (`info`, `warning` or `error`; optional, with [a default](concepts.md#rules-and-their-scope)) |
| Advice | `instruction`, `confidence`, `action`, and `changes` (a list of `{target, key, value, rationale}` objects) |
| Scope | `dimensions` (the value on each other dimension, by name), `box` (`{west, width, south, north}`, a shorthand for a polygon; geometry must then be null), `periods` (intervals inside `time`), `recurrence` (`{"months": [12, 1, 2]}`), and the fallback `time_start` and `time_end` |
| Overlap | `min_overlap`, an area fraction from 0 to 1 below which the finding is too small to count, which you can filter on |
| Provenance | `evidence`, `references`, `aliases` |
| Lifecycle | `status` (`draft`, `reviewed` or `deprecated`; a reviewed record cites a reference), `created`, `updated`, `withdrawn` (kept for history, never matched), `supersedes` |
| Extensions | `x_*` fields, kept and ignored |

A record from the toy rule file:

```json
{
  "type": "Feature",
  "id": "TOY002",
  "geometry": {
    "type": "Polygon",
    "coordinates": [[[165, 52], [-160, 52], [-160, 66], [165, 66], [165, 52]]]
  },
  "time": null,
  "properties": {
    "code": "TOY002",
    "title": "toy_ocean is too warm in the Bering Sea in winter",
    "message": "From December to March, toy_ocean sea temperature in the Bering Sea runs about 1 K too warm.",
    "dimensions": {"product": ["toy_ocean"], "variable": ["thetao"]},
    "recurrence": {"months": [12, 1, 2, 3]},
    "status": "draft"
  }
}
```

Its ring crosses the antimeridian the way most tools write it, from 165 to -160, and queryearth splits it at ±180.

The values in `dimensions` take the forms in the [table of dimensions](concepts.md#dimensions).

### Writing records

{meth}`Rule.to_feature() <queryearth.Rule.to_feature>` turns a rule back into a record, leaving out the fields at their defaults and writing the scope's `dimensions` as given, so that `Rule.from_feature(rule.to_feature())` gives the same rule. A `box` is written as its polygon, split at ±180, and time as the `time` member plus `periods` and `recurrence` where needed. A rule whose space is a point, or whose level is not info, warning or error, has no record form and raises `ValueError`. A computed rule is code, so it has no record form either. To write rules to a file:

```python
import json

collection = {
    "type": "FeatureCollection",
    "dimensions": registry.describe()["dimensions"],  # so from_file() can read it
    "features": [rule.to_feature()],
}
with open("mine.geojson", "w") as f:
    json.dump(collection, f, indent=2)
```
