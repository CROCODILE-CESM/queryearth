# queryearth

queryearth answers one question: given where (a point or a polygon, such as a lake outline or a model domain), when (a time range) and anything else that matters (grid resolution, product, variable and so on), which registered rules apply, how much of the request does each one cover, and what does it say to watch out for or to do?

Rules are GeoJSON features or short Python classes. A query returns findings of three kinds: caveats ("these values are climatology, not observations"), coverage gaps ("this product does not reach part of your request") and recommendations ("set this model parameter"). queryearth ships no rules of its own; you bring yours.

**Documentation:** https://crocodile-cesm.github.io/queryearth/

**Status:** pre-alpha. To try it, run [examples/toy/play.py](examples/toy/play.py), which loads a small made-up pack and walks through queries, coverage gaps, Python rules, `emit()`, `suitable()` and `query_points()`.

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
