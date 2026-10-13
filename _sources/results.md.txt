# Using findings

## Reporting them: emit()

Findings are data. {func}`~queryearth.emit` turns them into Python warnings, log lines, an exception, or calls to a function of yours:

```python
qe.emit(findings)  # default: warnings for caveats and coverage, log lines for advice
qe.emit(findings, mode="log")
qe.emit(findings, mode="raise")  # raises AdvisoryError listing the findings
qe.emit(findings, mode=lambda finding, text: print(text))  # a sink
```

Every message starts with the code in brackets, such as `[TOY002]`, so warnings can be filtered with `-W` or `warnings.filterwarnings`. The warning classes are `InfoAdvisory`, `WarningAdvisory` and `SevereAdvisory`, all subclasses of `AdvisoryWarning`.

`emit()` drops:

- conditional findings;
- caveats and coverage findings below `min_severity` (default `WARNING`);
- findings whose area fraction is below the rule's `min_overlap`;
- codes or prefixes listed in `ignore`;
- repeats.

Recommendations are logged at INFO, never warned or raised.

The settings live in a {class}`~queryearth.Policy`. Change them for one block of code with {func}`~queryearth.policy`:

```python
with qe.policy(mode="log", raise_at=qe.Severity.SEVERE, ignore={"TOY002"}):
    qe.emit(findings)
```

## Choosing a product: suitable()

{meth}`Index.suitable() <queryearth.Index.suitable>` takes a query and a variable, and ranks the products that offer that variable:

```python
for s in index.suitable(qe.Query(space=gulf, time=year_2000), "so"):
    print(s.product.name, s.score, [f.code for f in s.findings])
```

Products entirely outside their coverage are dropped, or listed last with `include_dropped=True`. The rest are ordered by their worst severity, then by severity weighted by area and time fractions, then by how well the product's resolution fits the query.

The score is not a quality ranking. A product with no findings only has no rule written about it; `index.rule_counts()` shows how many rules concern each product. Pass `score=` to rank by your own function.

## Many points at once: query_points()

{meth}`Index.query_points() <queryearth.Index.query_points>` evaluates every rule over many points, such as every cell centre of a grid:

```python
result = index.query_points(
    lon, lat, weights=cell_area, time=january, requests=[qe.Request("toy_ocean", "thetao")]
)
mask = result.masks[("toy_ocean", "TOY002")]  # shaped like lon
share = result.fractions[("toy_ocean", "TOY002")]  # weighted share of the points
flagged = result.any(qe.Severity.WARNING)  # points inside any definite finding
```

Results are keyed by `(product, code)`, with product `None` for rules matched on the base query. NaN points are inside no rule. A computed rule takes part only through its `mask()` method; otherwise it is listed in `result.skipped`.
