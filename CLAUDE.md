# CLAUDE.md

Guidance for Claude Code (and anyone else) working in this repository.

## What queryearth is

A small engine that matches rules to a request. A rule is scoped by any mix of space, time, numeric axes (such as grid resolution), labels (product, variable, model) and plugin dimensions. A query gives any subset of those and gets back findings of three kinds: caveats, coverage gaps (built-in codes QE001 for space and QE002 for time) and recommendations with structured suggestions. It is general-purpose, not tied to earth system modelling. Its first consumers are CrocoDash (one query per case, in `Case.configure_forcings`) and GLHE (lake polygons against data products).

It is an engine only: the package ships no curated rules. Rule packs belong to their users. The examples in `examples/` and `docs/reference/examples/` are illustrations, marked as made up or illustrative.

## Rules

- **Clean room: geostructures.** Never read, copy, paraphrase or search for code from the `geostructures` project, and do not depend on it or contribute to it. More generally, avoid dependencies on projects run by military contractors.
- **Dependencies.** Runtime imports are the standard library, numpy and shapely (2.1 or later) only. Anything else goes in an optional extra, and test-only packages go in the `test` extra.
- **Python.** 3.11 or later with no upper cap. Write nothing newer than the 3.11 grammar. Add each new Python release to the CI matrix in `.github/workflows/tests.yml`.
- **Keep it small.** The author cares about code size. Prefer the simplest implementation that passes the fixtures: no speculative options, no extra layers, no single-use helpers. Features cut to keep v0.0.1 small are listed in `docs/design.md` section 17, each with its upgrade path. Re-add one only when its trigger happens, and update that row when you do.
- **Keep the extension hooks.** Everything that varies between users plugs in through a small interface (design.md section 12.5), and these hooks stay even where nothing uses them yet:
  - plugin `Dimension`s, with their optional `build`, `comparable`, `late`, `to_json` and `extent`;
  - third-party rule kinds (`RuleKind`, `outcomes()`);
  - `ComputedRule` and `@registry.rule`, with `mask()` for the bulk path;
  - a callable `Product.coverage`;
  - a `ScoreFn` for `suitable()`;
  - `emit()` sinks;
  - named regions.

  Geometry and time semantics are deliberately not pluggable.
- **Codes.** A code is a prefix plus three or four digits (`CRU001`, `ERA5-014`). A hyphen is required after a prefix that ends in a digit. The prefix `QE` is reserved for built-in findings.
- **Git.** Ask before committing or pushing. Never add a `Co-Authored-By` line. Never @-mention people on GitHub. Branch names are plain and descriptive, with no personal names. The author does releases.
- **Privacy.** The repository is private, but the user docs site and the PyPI package are public. Parts of `docs/` paraphrase a private knowledge base of expert interviews, so do not make the repository or the docs public without the author's agreement. `MANIFEST.in` prunes `docs/` from the source distribution; keep it that way.

## Layout

| Path | What it holds |
|---|---|
| `queryearth/space.py` | `Space` (point or polygon) and its helpers `point`, `box`, `polygon`. Antimeridian splitting, closed-set `meets`, `measure` (area fraction and km²), spherical `area_km2`, the points mask for the bulk path |
| `queryearth/time.py` | `Interval`, `TimeSpec`, `interval()`, `parse_time()` for records, `overlap`, `time_fraction`, month recurrence. One calendar: proleptic Gregorian |
| `queryearth/objects.py` | Frozen dataclasses: `Severity`, `Suggestion`, `Outcome`, `Match`, `Finding`, `Scope`, `Coverage`, `Product`, `Request`, `Query` |
| `queryearth/dimensions.py` | The `Dimension` protocol; `SpaceDimension` and `TimeDimension`, built into every Registry and not replaceable; the built-in plugins `Axis`, `Labels` and `Versions` |
| `queryearth/rules.py` | `Rule` (a static record), `ComputedRule`, `match_scope` (one scope against one query part) and building findings |
| `queryearth/registry.py` | `Registry`: declarations, `query`, requests, coverage findings, `suitable`, `query_points`, `PointResult` |
| `queryearth/packs.py` | Loading a pack (`pack.toml` plus GeoJSON FeatureCollections), with the loader checks done by hand |
| `queryearth/emit.py` | `emit()`, `Policy`, `policy()`, the warning classes and `AdvisoryError` |
| `tests/` | One file per module, plus `test_queries.py` (bulk path, `suitable`) and `test_packs.py` |
| `examples/toy/` | A made-up pack and `play.py`, a walkthrough to run cell by cell |
| `docs/source/` | The public user docs (Sphinx with MyST Markdown), built and deployed to GitHub Pages by `.github/workflows/docs.yml`. Nothing derived from the private interviews goes here |
| `docs/design.md` | The design and the spec. "As built" notes mark where the code differs from it |
| `docs/reference/` | `fixtures.md` (correctness fixtures, each with a test unless marked dropped), `schema.json` (record schema), `decisions.md` (the Q-numbered decisions and detailed contracts), the example pack, `usage.py` (a usage example), and background, consumer and glossary notes |

## Concepts worth knowing before changing the engine

- A **pack** is a file format: a directory with `pack.toml` (identity, owned code prefixes, products, axes, facets, regions) and GeoJSON rule records. A **Registry** is the in-memory object that packs and Python rules are loaded into, and the thing you query. One Registry can hold several packs.
- A rule's scope is a conjunction: a dimension the rule leaves out matches anything. Space and time are dimensions too. `match_scope` runs one loop over every dimension of the Registry, and the `late` ones (space) run last.
- When a query omits a dimension that a rule constrains, the finding is **conditional** (`conditional_on` names what is missing). Conditional findings are hidden unless `include_conditional=True`.
- A query can hold several **requests** (one per product). Each runs as its own sub-query. It takes its product's coverage time and version when the query gives none, and lists them in `Finding.assumed`.
- `Registry.query` calls `evaluate()` on every active rule of each part, after any plugin prefilters. There are no vectorised tables (design.md section 9.1).
- Rings are normalised once, at load: longitudes wrapped, rings split at ±180, `make_valid`, oriented. Matching uses closed sets, so a point on an edge is inside.
- On the wire, time intervals are closed, and an end date covers its whole day.
- Callers query with the support they actually use (the cells and time steps), never a buffered shape.

## Development

```bash
pip install -e ".[test]"
pytest
black .            # target py311, configured in pyproject.toml
python examples/toy/play.py
pip install -e ".[docs]" && sphinx-build -W -b html docs/source docs/_build
```

- **CI.** It runs pytest on Python 3.11 to 3.14 on every push to every branch and on pull requests. Black is checked on pull requests.
- **Versions** come from git tags through setuptools-scm.
- **Builds and releases.** Every push to `main` builds the package. A GitHub release tagged `vX.Y.Z` publishes to PyPI through trusted publishing; there is no TestPyPI job.
- **Style.** Match the existing code: frozen dataclasses, error messages that name the rule code, short comments only where the reason is not obvious, and docstrings that cite the design section.
- **Fixtures.** When behaviour changes, update the fixture in `docs/reference/fixtures.md` and its test together. If it changes `docs/design.md`, add or update its "As built" note or section 17 row.
- **NCAR GLADE.** The `dev_cd` conda env has numpy and shapely, so you can run against the checkout without installing: `PYTHONPATH=$PWD conda run -n dev_cd python examples/toy/play.py`.
