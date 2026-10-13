# The toy example

The repository's `examples/toy/` holds a small, made-up pack (nine rules) and a script that walks through queries, conditional findings, coverage rules, rules written in Python, logging the findings, a query per product and `query_points()`. Everything in it is invented: the products, the rules and the parameter names.

Run it as a script, or cell by cell in an editor that understands `# %%` cells:

```bash
python examples/toy/play.py
```

## play.py

```{literalinclude} ../../examples/toy/play.py
:language: python
```

## rules.geojson

```{literalinclude} ../../examples/toy/rules.geojson
:language: json
```
