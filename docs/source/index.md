# queryearth

queryearth answers one question: given where (a point or a polygon), when (a time range) and anything else that matters (grid resolution, product, variable, model and so on), which registered rules apply, how much of the query does each one cover, and what does it say to watch out for or to do? Each of these is a [dimension](concepts.md#dimensions).

Rules are short Python objects or GeoJSON records. A query returns **findings**, one for each rule that applies. Each has a `logging` level and says what to watch out for, such as "these values are climatology, not observations" or "this product does not reach part of your area"; some also list **changes** for your code to make, such as "set this model parameter".

queryearth is an engine only: it ships no rules of its own. You bring yours.

## Install

```bash
pip install queryearth
```

queryearth needs Python 3.11 or later, numpy, and shapely 2.1 or later. It is pre-alpha: the API may change before version 0.1.

## A first query

```python
import logging

import queryearth as qe
from queryearth import space as sp

registry = qe.Registry("demo", dimensions=[qe.Axis("resolution", "km")])
registry.add(
    qe.Rule(
        code="DEMO001",
        title="Sparse observations south of 50S before 2004",
        message="Few observations constrain this period, so values drift.",
        scope=qe.Scope(
            space=sp.box(-180, -90, 180, -50),
            time=qe.interval("1993-01-01", "2003-12-31"),
        ),
    )
)
registry.add(
    qe.Rule(
        code="DEMO101",
        title="Fine grid: turn off the coarse-grid scheme",
        message="Below 10 km the model resolves this process itself.",
        scope=qe.Scope(dimensions={"resolution": {"lt": 10}}),
        changes=[qe.Change("settings", "coarse_scheme", False)],
    )
)

for f in registry.query(
    space=sp.box(-60, -70, -20, -40),  # west, south, east, north
    time=qe.interval("2000-01-01", "2005-12-31"),
    dimensions={"resolution": 8},
):
    level = logging.getLevelName(f.level)
    print(f.code, level, f"area {f.area_fraction:.0%}", f"time {f.time_fraction:.0%}")
```

This prints DEMO001 first, at WARNING, because findings come highest [level](concepts.md#rules-and-their-scope) first. DEMO001 covers 58% of the box's area and 67% of its period. Then it prints DEMO101, at INFO, which applies to the whole query at 8 km.

```{toctree}
:maxdepth: 2

concepts
rules
results
extending
example
api
```
