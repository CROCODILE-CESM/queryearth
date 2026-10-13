# Extending queryearth

Everything that varies between users plugs in through a small interface, so extending queryearth never means forking it. Plugins are passed explicitly to the Registry or to a call.

| To add | Write |
|---|---|
| A new kind of scope: a hierarchy, a taxonomy, a network | A `Dimension` plugin, passed to `Registry(dimensions=...)` |
| A rule computed from the request or from data you hold | A `ComputedRule` subclass or an `@registry.rule` function |
| A computed rule on the bulk path | A `mask(lon, lat, query)` method on that rule |
| A new kind of rule altogether | Any object with `code`, `scope` and `evaluate(query)` (the `RuleKind` protocol), passed to `Registry.add` |
| Rules from another format | Build records and pass them to `Registry.add`, or `Rule.from_feature` per feature |
| Availability known only at run time | A callable `Product.coverage`, which takes the request's sub-query and returns a `Coverage` |
| Named regions | `Registry.add_regions(namespace, regions)` |
| A ranking of products | A score function, passed as `suitable(score=...)` |

Geometry and time semantics are not pluggable. Space and time are dimensions inside the engine, but `SpaceDimension` and `TimeDimension` are built into every Registry and cannot be replaced, so "overlaps" means the same thing for every rule.

## Dimension plugins

A dimension has a `name`, a `schema` (JSON Schema for the value in records), and three methods:

- `parse_rule(value)` checks and parses a rule's value when the rule is added;
- `parse_query(value)` does the same for a query's value;
- `match(rule, query)` returns a `DimMatch(overlap, fraction)` when they meet, or `None` when they do not.

The Registry does everything else: conditional findings, unknown names, requests and sorting. This plugin matches HydroBASINS Pfafstetter basin codes, where basin 1423 lies inside basin 14:

```python
class Pfafstetter:
    name = "basin"
    schema = {"type": "array", "items": {"type": "string", "pattern": "^[1-9]+$"}}

    def parse_rule(self, value):
        return tuple(str(v) for v in value)

    def parse_query(self, value):
        code = str(value)
        if not code.isdigit() or "0" in code:
            raise ValueError(f"not a Pfafstetter code: {value!r}")
        return code

    def match(self, rule, query):
        hits = [b for b in rule if query.startswith(b) or b.startswith(query)]
        if not hits:
            return None
        inside = any(query.startswith(b) for b in hits)
        return qe.DimMatch(overlap=tuple(hits), fraction=1.0 if inside else None)


registry = qe.Registry("basins", dimensions=[Pfafstetter()])
registry.add(
    qe.Rule(
        code="BAS001",
        kind="warning",
        title="Gauges sparse in basins 14 and 62",
        message="Few gauges report in these basins.",
        scope=qe.Scope(dims={"basin": ["14", "62"]}),
    )
)
registry.query(dims={"basin": "1423"})  # BAS001, overlap ("14",), fraction 1.0
```

A dimension may also define these optional members:

| Member | Effect |
|---|---|
| `comparable(rule, query)` | Returning False makes the finding conditional on the dimension instead of a non-match |
| `build(pairs)` | Takes the `(position, rule value)` pairs of the rules that constrain the dimension and returns a prefilter whose `candidates(query)` gives the positions to keep, so a plugin can bring its own index |
| `late = True` | Runs the dimension after the others; space sets it, so the costly spatial test runs last |
| `always = True` | Calls `match(None, query)` when a rule leaves the dimension out, so the query is still measured |
| `extent(rule)` | What a finding reports when the query leaves the dimension out |
| `to_json(overlap)` | Serialises the overlap for `Finding.to_dict()` |
