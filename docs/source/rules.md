# Writing rules

There are three ways to write a rule: a {class}`~queryearth.Rule` built in Python, a computed rule whose outcome depends on the query, or a record in a GeoJSON **rule file** or a **pack**, a folder with a file per rule. All three end up on a {class}`~queryearth.Registry`, the rules in memory that you query, loaded from any number of rule files and packs.

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

A {class}`~queryearth.Scope` takes `space`, `time` and, in `dimensions`, a value for each other [dimension](concepts.md#dimensions) the rule constrains, by its declared name; `edge=True` makes it an [edge rule](concepts.md#space). `changes` lists {class}`~queryearth.Change` objects, or mappings with the same fields. `level` takes a `logging` level or its name, such as `"error"`, in place of [the default](concepts.md#rules-and-their-scope). Adding a code that is already on the Registry raises `DuplicateCodeError`.

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

A rule file is a GeoJSON file holding a FeatureCollection of records, or a single record. Besides `features`, a FeatureCollection can have three top-level members:

- `queryearth`: the release whose file format the file uses, such as `"0.6"`. A file that needs a later release than the one installed is refused, with a message that says so; a file without it is read as it is.
- `categories`: the [categories](concepts.md#rules-and-their-scope) of its rules, each code prefix with its title, or with its title and parent for a subcategory (files from before 0.6 call this member `groups`, and are read as they are): `{"DOMAIN": "Domain design", "OBC": {"title": "Open boundaries", "parent": "DOMAIN"}}`.
- `dimensions`: the [dimensions](concepts.md#dimensions) its rules use, such as `[{"name": "resolution", "kind": "axis", "unit": "km"}, {"name": "product", "kind": "labels"}]`. Each has a `name`, a `kind` (`axis`, `labels` or `versions`), a `unit` for an axis, and optionally a `description`.

{meth}`Registry.from_file() <queryearth.Registry.from_file>` makes a Registry with those categories and dimensions and loads the rules:

```python
registry = qe.Registry.from_file("examples/toy/rules.geojson")
```

It takes several files too, and a file can be an http(s) URL, such as a raw link to a file in a GitHub repository or gist. The Registry then holds every file's categories and dimensions, which must agree where two files share a name, and a code must be unique across the files. Each finding's `source` names the file its rule came from, so rules kept in separate files, such as one file per author, stay told apart:

```python
registry = qe.Registry.from_file(
    "my_rules.geojson",
    "https://raw.githubusercontent.com/me/rules/main/more_rules.geojson",
)
```

Loading a URL needs the network when it runs, so pin the link to a commit when results must be reproducible.

{meth}`Registry.load() <queryearth.Registry.load>` adds a file's rules, from a path or a URL, to a Registry you already have, and returns their codes. That Registry must declare every dimension the records use; a file that declares its dimensions must declare them as the Registry does, and its categories must be declared on the Registry:

```python
codes = registry.load("mine.geojson")
```

Loading never runs code. Every problem is reported at once in a `LoadError` that names the file, the feature's position and its code, and the Registry is left unchanged. Products need no declaration of their own: records name them as values of a `product` label dimension. A finding from a loaded rule has the file name as its `source`. A Feature or FeatureCollection mapping can also be added directly with `Registry.add(mapping)`.

### Records

Each rule is one GeoJSON Feature. Its `geometry` is a Polygon, a MultiPolygon or null (null means everywhere). Its time goes in the top-level JSON-FG `time` member: `{"interval": ["2000-01-01", "2003-12-31"]}`, `{"date": ...}`, `{"timestamp": ...}` or null. The rest is in `properties`:

| Topic | Properties |
|---|---|
| Identity and outcome | `code`, `title` and `message`, all required; `level` (`info`, `warning` or `error`; optional, with [a default](concepts.md#rules-and-their-scope)) |
| Advice | `instruction`, `confidence`, `action`, and `changes` (a list of `{target, key, value, rationale}` objects) |
| Scope | `dimensions` (the value on each other dimension, by name), `box` (`{west, width, south, north}`, a shorthand for a polygon; geometry must then be null), `edge` (`true` for an [edge rule](concepts.md#space)), `periods` (intervals inside `time`), `recurrence` (`{"months": [12, 1, 2]}`), and the fallback `time_start` and `time_end` |
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

{meth}`Rule.to_feature() <queryearth.Rule.to_feature>` turns a rule back into a record, leaving out the fields at their defaults and writing the scope's `dimensions` as given, so that `Rule.from_feature(rule.to_feature())` gives the same rule. A `box` is written as its polygon, split at ±180, and time as the `time` member plus `periods` and `recurrence` where needed. A rule whose space is a point, or whose level is not info, warning or error, has no record form and raises `ValueError`. A computed rule is code, so it has no record form either.

{meth}`Registry.to_file() <queryearth.Registry.to_file>` writes a Registry's rule file: the `queryearth` release of its format, its categories and dimensions, and a record for each rule, in the order they were added. Computed rules are left out. {meth}`Registry.to_collection() <queryearth.Registry.to_collection>` gives the same FeatureCollection as a dict.

```python
registry.to_file("mine.geojson")
again = qe.Registry.from_file("mine.geojson")
```

## Packs

A large ruleset is easier to keep as a **pack**: a folder that holds the same rules as a rule file, laid out by category, with one file per rule.

```
crocodash_rules/
  pack.json            {"queryearth": "0.6", "dimensions": [...]}
  DOMAIN/
    category.json      {"title": "Domain design"}
    OBC/
      category.json    {"title": "Open boundaries"}
      OBC001.geojson   one rule: a GeoJSON Feature
      OBC002.geojson
  REGION/
    ITF/ …
```

- `pack.json` holds the pack's `queryearth` release and its `dimensions`, as a rule file's top-level members do.
- Each category is a folder named by its prefix, with a `category.json` holding its title; a subcategory's folder sits inside its parent's. The folders are the category tree, so a pack needs no `parent` fields.
- Each rule is a file named by its code, holding one Feature, in its category's folder.
- Other files, such as a README or images, are left alone.

{meth}`Registry.from_file() <queryearth.Registry.from_file>` and {meth}`Registry.load() <queryearth.Registry.load>` read a pack from its folder, alongside rule files; a finding's `source` is the folder's name. {meth}`Registry.to_pack() <queryearth.Registry.to_pack>` writes one, and updates a pack that is already there: it removes the rule files and categories that are gone and keeps everything else, so a pack in git shows each change as a change to one rule's file. A rule file and a pack hold the same rules, so either converts to the other:

```python
qe.Registry.from_file("crocodash_rules/").to_file("crocodash_rules.geojson")  # to share or link
qe.Registry.from_file("crocodash_rules.geojson").to_pack("crocodash_rules/")  # to organize
```

A web link points at one file, so share a ruleset as a rule file; a pack is read from disk. Loading a pack checks its layout: a rule file whose name is not its code, a rule in another category's folder, or a folder of rules without a `category.json` is reported with the rest of the load's problems.
