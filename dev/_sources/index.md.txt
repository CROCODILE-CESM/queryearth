# queryearth

queryearth answers one question: given where (a point or a polygon), when (a time range) and anything else that matters (grid resolution, product, variable, model and so on), which registered rules apply, how much of the request does each one cover, and what does it say to watch out for or to do?

Rules are short Python objects or GeoJSON records. A query returns **findings** of three kinds:

- **caveats**, such as "these values are climatology, not observations";
- **coverage gaps**, such as "this product does not reach part of your request";
- **recommendations** with structured suggestions, such as "set this model parameter".

queryearth is an engine only: it ships no rules of its own. You bring yours.

## Install

```bash
pip install queryearth
```

queryearth needs Python 3.11 or later, numpy, and shapely 2.1 or later. It is pre-alpha: the API may change before version 0.1.

## A first query

```python
import queryearth as qe
from queryearth import space as sp

registry = qe.Registry("demo", axes=[qe.Axis("resolution", "km")])
registry.add(
    qe.Rule(
        code="DEMO001",
        kind="caveat",
        title="Sparse observations south of 50S before 2004",
        message="Few observations constrain this period, so values drift.",
        severity=qe.Severity.WARNING,
        scope=qe.Scope(
            space=sp.box(-180, -90, 180, -50),
            time=qe.interval("1993-01-01", "2003-12-31"),
        ),
    )
)
registry.add(
    qe.Rule(
        code="DEMO101",
        kind="recommendation",
        title="Fine grid: turn off the coarse-grid scheme",
        message="Below 10 km the model resolves this process itself.",
        severity=qe.Severity.INFO,
        scope=qe.Scope(axes={"resolution": {"lt": 10}}),
        suggestions=[qe.Suggestion("settings", "coarse_scheme", False)],
    )
)

for f in registry.query(
    space=sp.box(-60, -70, -20, -40),  # west, south, east, north
    time=qe.interval("2000-01-01", "2005-12-31"),
    axes={"resolution": 8},
):
    print(f.code, f.kind, f"area {f.area_fraction:.0%}", f"time {f.time_fraction:.0%}")
```

This prints DEMO001 first, because it is more severe: it covers 58% of the box's area and 67% of its period. Then it prints DEMO101, which applies to the whole request at 8 km.

```{toctree}
:maxdepth: 2

concepts
rules
results
extending
example
api
```
