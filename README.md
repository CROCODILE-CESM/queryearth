# queryearth

queryearth matches rules to a query. A rule says something worth knowing, such as "tidal mixing dominates here, so force tides", and is scoped by **dimensions**: where (space), when (time), and anything else that matters, such as grid resolution or forcing product. A query gives values on any of the dimensions and gets back the rules that apply. Rules live in GeoJSON files, so any GIS tool can show where they apply.

Space, time and numeric axes are the base dimensions, and labels come with them. **Defining your own dimension is a few lines of Python**, written on the same three-method class the built-in ones use.

**Documentation:** https://crocodile-cesm.github.io/queryearth/

## A first query

```python
import queryearth as qe
from queryearth import space as sp

registry = qe.Registry([qe.Axis("resolution", "km"), qe.Labels("product")])
registry.add(
    qe.Rule(
        code="GULF001",
        title="glorys is too fresh off the Mississippi",
        message="Near the delta, glorys surface salinity runs low.",
        scope={"space": sp.box(-92, 27, -87, 30.5), "product": "glorys"},
    )
)
registry.add(
    qe.Rule(
        code="GRID001",
        title="Turn off GM at high resolution",
        message="Below 8 km eddies are partly resolved: set THICKNESSDIFFUSE = False.",
        level="info",
        scope={"resolution": {"lt": 8}},
    )
)

findings = registry.query(
    space=sp.box(-98, 18, -80, 31),  # west, south, east, north
    time=qe.interval("2020-01-01", "2020-12-31"),
    resolution=(5, 9),  # the grid's smallest and largest cells, in km
    product="glorys",
)
print([rule.code for rule in findings])  # ['GULF001', 'GRID001'], warnings first
print(findings[0].to_feature())  # a finding, as the GeoJSON Feature of its rule
```

A rule applies when, on every dimension it constrains, the query gives a value and the two overlap. A dimension the rule leaves out matches anything; a dimension the rule constrains and the query leaves out does not match.

## Define your own dimension

A dimension subclasses `qe.Dimension`, sets its `name` and implements three methods:

| Method | Does |
|---|---|
| `parse_rule(value)` | checks a rule's value, from Python or from a rule file's JSON, and returns it in the form `matches` takes |
| `parse_query(value)` | the same for a query's value |
| `matches(rule, query)` | says whether the two share at least one value |

A value can be anything the dimension knows how to parse from JSON: a number, a range, a shape, or a mapping of several fields, such as `{"depth": 4000, "slope": 8}`. A dimension sees only its own value, so inputs it needs together go in that one value. A rule keeps each value as you gave it, and a rule file holds it that way, so a value you give in Python is plain JSON, apart from space and time.

Space, time and `Axis` are written this way, and so is `Labels`, which comes with queryearth as the worked example:

```python
@dataclass(frozen=True)
class Labels(Dimension):
    """Names, such as a forcing product or a model option.

    A rule gives a name or a list of names, which may use the wildcards * and
    ? (case-sensitive), such as ["jra", "era5*"]; a query gives a name or a
    list of names. They match when a query name matches one of the rule's.
    """

    name: str

    def parse_rule(self, value: Any) -> tuple[str, ...]:
        names = [value] if isinstance(value, str) else value
        if not isinstance(names, (list, tuple)) or not names:
            raise ValueError(f"labels {self.name!r} takes a name or a list of names")
        if not all(isinstance(n, str) and n for n in names):
            raise ValueError(f"labels {self.name!r} takes names, not {value!r}")
        return tuple(names)

    parse_query = parse_rule

    def matches(self, rule: tuple[str, ...], query: tuple[str, ...]) -> bool:
        return any(fnmatchcase(name, pattern) for pattern in rule for name in query)
```

**Rules are data; code lives in dimensions.**

- A new kind of value, or a new way to compare values, is a new dimension.
- A value derived from your case is computed when you build the query, and given to an `Axis` or your own dimension: CrocoDash computes `cell_size_ratio = largest / smallest` from its grid's cells and queries an Axis with it.
- Advice is a rule: plain data in a rule file, which never runs code.

Declare a dimension when you make the Registry, `qe.Registry([qe.Labels("product")])`; its name is its key in rules, queries and rule files. [Dimensions](https://crocodile-cesm.github.io/queryearth/dimensions.html) walks through it.

## Rule files

A rule file is a GeoJSON FeatureCollection with one Feature per rule. Its geometry is the rule's space, its JSON-FG `time` member the rule's time, and its properties hold the code, title, message, level, the value on each other dimension under `"dimensions"`, as the rule gives it, and anything else, such as an instruction or references, which queryearth keeps unchanged. `Rule.from_feature()` reads one Feature and `rule.to_feature()` writes it; `Registry.from_file()` and `registry.to_file()` read and write a whole file.

A code may be a path, such as `REGION/ITF/ITF001`: its category, `rule.category`, is the path before the last slash. To keep the findings in one category, filter on the code: `[r for r in findings if r.code.startswith("REGION/")]`.

```python
registry.to_file("rules.geojson")
dimensions = [qe.Axis("resolution", "km"), qe.Labels("product")]
registry = qe.Registry.from_file("rules.geojson", "more.geojson", dimensions=dimensions)
```

## Install

```bash
pip install queryearth
```

queryearth needs Python 3.11 or later, numpy and shapely 2.1 or later.

## The growth path

This is the core of queryearth, cut back from 0.6.0 to what is realistic to review. [docs/growth.md](docs/growth.md) lists what 0.6.0 had beyond it, kept at the tag v0.6.0: what has come back into the core since (categories, version enforcement), then what is planned, parked and dropped.

## Development

```bash
pip install -e ".[test]"
pytest
black .
```

Versions come from git tags through setuptools-scm. Every push to `main` builds the package, and every GitHub release tagged `vX.Y.Z` publishes version X.Y.Z to PyPI.

## Licence

Apache-2.0.
