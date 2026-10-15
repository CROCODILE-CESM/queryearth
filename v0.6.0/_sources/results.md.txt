# Using findings

## Reporting findings

Findings are data: queryearth never prints, warns, logs or raises for them. To show them to people, print {func}`~queryearth.report`, which gives each finding's level and one-line text, then its message and changes, or `""` when there are none:

```python
print(qe.report(findings))
```

```text
WARNING [TOY002] toy_ocean is too warm in the Bering Sea in winter (area 83%; 2000-12-01..2001-03-31; draft)
    From December to March, toy_ocean sea temperature in the Bering Sea runs about 1 K too warm.
INFO [TOY102] Fine grid: turn off the coarse-grid eddy scheme (area 100%; 2000-11-01..2001-03-31; draft)
    Below 10 km the model starts to resolve eddies itself.
    Change: MOM_input TOY_EDDY_SCHEME = False (Made-up parameter name.)
```

The first line of each is `str(finding)`: the code, the title, the share of the query's area, the periods it applies to, and "draft" for a rule not yet reviewed. A finding's `level` is a `logging` level, so to log findings instead, log that line at its level:

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
result = registry.query_points(
    lon, lat, weights=cell_area, time=january, dimensions=ocean
)
mask = result.masks["TOY002"]  # shaped like lon
share = result.fractions["TOY002"]  # weighted share of the points
flagged = result.any()  # points inside a definite finding at WARNING or above
```

Results are keyed by rule code. NaN points are inside no rule. A computed rule takes part only through its `mask()` method; otherwise it is listed in `result.skipped`.
