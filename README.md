# queryearth

queryearth answers one question: given where (a point or a polygon, such as a lake outline or a model domain), when (a time range) and anything else that matters (grid resolution, product, variable and so on), which registered rules apply, how much of the query does each one cover, and what does it say to watch out for or to do?

Rules are GeoJSON features or short Python classes. A query returns findings of two kinds: warnings ("these values are climatology, not observations", or "this product does not reach part of your area") and suggestions ("set this model parameter"). Each finding has a standard `logging` level, so you log findings with the `logging` module. queryearth ships no rules of its own; you bring yours.

**Documentation:** https://crocodile-cesm.github.io/queryearth/

**Status:** pre-alpha. To try it, run [examples/toy/play.py](examples/toy/play.py), which loads a small made-up rule file and walks through queries, coverage limits written as rules, Python rules, logging the findings and `query_points()`.

## Install

```bash
pip install queryearth
```

queryearth needs Python 3.11 or later, numpy and shapely 2.1 or later.

## Development

```bash
pip install -e ".[test]"
pytest
black .
```

Versions come from git tags through setuptools-scm. Every push to `main` builds the package, and every GitHub release tagged `vX.Y.Z` publishes version X.Y.Z to PyPI.

## Licence

Apache-2.0.
