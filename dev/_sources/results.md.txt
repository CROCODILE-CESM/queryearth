# Using findings

## Reporting findings

Findings are data: queryearth never warns, logs or raises for them. A finding's `level` is a `logging` level, and `str(finding)` is a one-line message that starts with its code, such as `[TOY002] toy_ocean is too warm in the Bering Sea in winter (area 83%; 2000-12-01..2001-03-31; draft)`. So log them with the `logging` module:

```python
import logging

log = logging.getLogger("myapp")
for f in findings:
    log.log(f.level, f)
```

Filter or raise in your own loop. For example, to skip findings that only clip a rule's area, then stop on anything at ERROR or above:

```python
kept = [
    f for f in findings if f.area_fraction is None or f.area_fraction >= f.min_overlap
]
errors = [f for f in kept if f.level >= logging.ERROR]
if errors:
    raise RuntimeError("\n".join(map(str, errors)))
```

## Many points at once: query_points()

{meth}`Registry.query_points() <queryearth.Registry.query_points>` evaluates every rule over many points, such as every cell centre of a grid:

```python
ocean = {"product": ["toy_ocean"], "variable": ["thetao"]}
result = registry.query_points(lon, lat, weights=cell_area, time=january, facets=ocean)
mask = result.masks["TOY002"]  # shaped like lon
share = result.fractions["TOY002"]  # weighted share of the points
flagged = result.any()  # points inside a definite finding at WARNING or above
```

Results are keyed by rule code. NaN points are inside no rule. A computed rule takes part only through its `mask()` method; otherwise it is listed in `result.skipped`.
