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

## Choosing a product: suitable()

{meth}`Registry.suitable() <queryearth.Registry.suitable>` takes a query and a variable, and ranks the products that offer that variable:

```python
for s in registry.suitable(qe.Query(space=gulf, time=year_2000), "so"):
    print(s.product.name, s.score, [f.code for f in s.findings])
```

Products entirely outside their coverage are dropped, or listed last with `include_dropped=True`. The rest are ordered by the worst level among their warning and coverage findings, then by those levels weighted by area and time fractions (INFO 1, WARNING 2, ERROR 4), then by how well the product's resolution fits the query.

The score is not a quality ranking. A product with no findings only has no rule written about it; `registry.rule_counts()` shows how many rules concern each product. Pass `score=` to rank by your own function.

## Many points at once: query_points()

{meth}`Registry.query_points() <queryearth.Registry.query_points>` evaluates every rule over many points, such as every cell centre of a grid:

```python
result = registry.query_points(
    lon, lat, weights=cell_area, time=january, requests=[qe.Request("toy_ocean", "thetao")]
)
mask = result.masks[("toy_ocean", "TOY002")]  # shaped like lon
share = result.fractions[("toy_ocean", "TOY002")]  # weighted share of the points
flagged = result.any()  # points inside a definite finding at WARNING or above
```

Results are keyed by `(product, code)`, with product `None` for rules matched on the base query. NaN points are inside no rule. A computed rule takes part only through its `mask()` method; otherwise it is listed in `result.skipped`.
