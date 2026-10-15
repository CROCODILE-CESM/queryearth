# CLAUDE.md

Guidance for Claude Code (and anyone else) working in this repository.

## What queryearth is

A small engine that matches rules to a query. A rule is scoped by any mix of dimensions: space and time, which are built in, and the ones a Registry declares, such as an `Axis` (grid resolution), `Labels` (product, variable, model), `Versions` or a plugin. A query gives values on any subset of those and gets back findings, one per rule that applies. A rule has a code, a title, a message and a level, and may list changes, structured actions that callers such as CrocoDash apply. A product's coverage limits are ordinary warnings scoped by a `product` label dimension. Each finding has a standard `logging` level, and callers log findings with `logging` themselves. It is general-purpose, not tied to earth system modelling. Its first consumers are CrocoDash (one query per forcing product, in `Case.configure_forcings`) and GLHE (lake polygons against data products).

It is an engine only: the package ships no curated rules. Rule files belong to their users. The example in `examples/toy/` is made up.

## Rules

- **Clean room: geostructures.** Never read, copy, paraphrase or search for code from the `geostructures` project, and do not depend on it or contribute to it. More generally, avoid dependencies on projects run by military contractors.
- **Dependencies.** Runtime imports are the standard library, numpy and shapely (2.1 or later) only. Anything else goes in an optional extra, and test-only packages go in the `test` extra.
- **Python.** 3.11 or later with no upper cap. Write nothing newer than the 3.11 grammar. Add each new Python release to the CI matrix in `.github/workflows/tests.yml`.
- **Keep it small.** The author cares about code size. Prefer the simplest implementation that passes the tests: no speculative options, no extra layers, no single-use helpers. Features cut before 2026-10-13 are listed in section 17 of the frozen `docs/design.md`, each with its upgrade path; packs (`pack.toml`), named regions (`region_ref`) and the plugin-schema checker were removed after it froze. Re-add a feature only when its trigger happens.
- **Keep the extension hooks.** Everything that varies between users plugs in through a small interface (design.md section 12.5), and these hooks stay even where nothing uses them yet:
  - plugin `Dimension`s, with their optional `build`, `comparable`, `late`, `to_json` and `extent`;
  - third-party rule kinds (`RuleKind`, `outcomes()`);
  - `ComputedRule` and `@registry.rule`, with `mask()` for the bulk path.

  Geometry and time semantics are deliberately not pluggable.
- **Codes.** A code is a prefix plus three or four digits (`CRU001`, `ERA5-014`). A hyphen is required after a prefix that ends in a digit.
- **Git.** Ask before committing or pushing. Never add a `Co-Authored-By` line. Never @-mention people on GitHub. Branch names are plain and descriptive, with no personal names. The author does releases.
- **Public.** The repository, the user docs site and the PyPI package are all public. Parts of the frozen design docs paraphrase expert interviews, which the author has agreed to publish. `MANIFEST.in` prunes `docs/` from the source distribution; keep it that way.

## Layout

| Path | What it holds |
|---|---|
| `queryearth/space.py` | `Space` (point or polygon) and its helpers `point`, `box`, `polygon`. Antimeridian splitting, closed-set `meets`, `measure` (area fraction and km²), spherical `area_km2`, the points mask for the bulk path |
| `queryearth/converters.py` | Turn other descriptions of a place into a `Space`: `grid_outline(lon, lat)` from a curvilinear grid's cell corners (a pole-containing grid becomes the polar cap). Numpy only; never import a model package here |
| `queryearth/time.py` | `Interval`, `TimeSpec`, `interval()`, `parse_time()` for records, `overlap`, `time_fraction`, month recurrence. One calendar: proleptic Gregorian |
| `queryearth/objects.py` | Frozen dataclasses: `Change`, `Outcome`, `Match`, `Finding` (whose `str()` is the message to log), `Scope`, `Query`; and the error classes `DuplicateCodeError`, `UnknownNameError` and `LoadError` |
| `queryearth/dimensions.py` | The `Dimension` protocol and `DimMatch`; `SpaceDimension` and `TimeDimension`, built into every Registry and not replaceable; the built-in plugins `Axis` (with `AxisOverlap`), `Labels` and `Versions` |
| `queryearth/rules.py` | Codes (`check_code`, `split_code`, `make_code`), `Rule` (a static record, read with `from_feature`, which does the record checks by hand, and written with `to_feature`), `ComputedRule`, `match_scope` (one scope against one query part) and building findings |
| `queryearth/registry.py` | `FORMAT`; `Registry`: declarations (dimensions and categories), `add`, `load` (one rule file, all or nothing), `from_file` (a Registry for one or more files, at paths or http(s) URLs, that declare their dimensions and categories), `next_code`, `values`, `describe`, `to_collection`/`to_file`, `query`, `query_points`, `PointResult` |
| `tests/` | One file per module, plus `test_queries.py` (bulk path) and `test_records.py` (rule files, the loader checks and `to_feature` round trips) |
| `examples/toy/` | A made-up rule file, `rules.geojson`, and `play.py`, a walkthrough to run cell by cell |
| `docs/source/` | The public user docs (Sphinx with MyST Markdown), built and deployed to GitHub Pages by `.github/workflows/docs.yml`: one folder per release (`vX.Y.Z/`) plus `dev/` for `main`, with a version menu; `.github/docs_versions.py` keeps the version list and the root redirect. |
| `docs/design.md` | Frozen: the design and the spec as they stood at commit e5e9d0e, with "As built" notes where the code then differed |
| `docs/reference/` | Frozen: `fixtures.md` (correctness fixtures), `decisions.md` (the Q-numbered decisions and detailed contracts), `usage.py` (a usage example), and background, consumer and glossary notes |

## Docs: maintained and frozen

- **Maintained:** `docs/source/` (the public docs), `README.md` and this file. They describe the current package, and every future change updates them, and only them, as needed.
- **Frozen:** everything else under `docs/`: `docs/design.md` and all of `docs/reference/`. They were frozen on 2026-10-13 at commit e5e9d0e, carry a banner saying so, and record the design as it stood then. Do not update them, apart from turning a link into plain text when its target is deleted. Design section numbers cited in docstrings refer to them.

## Concepts worth knowing before changing the engine

- There are **rules**, **rule files** and the **Registry**. A rule is a static `Rule` (built in Python, or read from a GeoJSON record with `Rule.from_feature`), a computed rule, or a third-party rule kind; every rule carries its own geometry. A rule file is one GeoJSON file of records, a FeatureCollection or a single Feature. The Registry is the in-memory object you add rules to and query: `Registry.add` takes a rule or a record mapping, and `Registry.load(path)` adds one file's records, all or nothing. `Rule.to_feature()` writes a static rule back as a record; computed rules are code and have none.
- Every dimension but space and time is declared on the Registry: in Python, in one list (`Registry(name, dimensions=[...])`), or by a rule file's top-level `dimensions` member (`[{"name", "kind", "unit"}]`, read by `Registry.from_file`; `describe()["dimensions"]` gives it back). A file that declares dimensions must agree with the Registry it is loaded into. Scopes, queries and computed rules give their values in one `dimensions` mapping, records in one `dimensions` member, and `Match.dimensions` holds a `DimMatch` for each. A dimension checks its own values in `parse_rule`, for records too. `docs/source/concepts.md` has the one table that explains the kinds; the other pages link to it.
- A rule's scope is a conjunction: a dimension the rule leaves out matches anything. Space and time are dimensions too. `match_scope` runs one loop over every dimension of the Registry, and the `late` ones (space) run last. An edge rule (`Scope(edge=True)`, `"edge": true` in a record) is compiled to an `Edge` space, which `SpaceDimension.match` tests with `space.edge_meets`.
- A code's prefix is its category. A Registry may declare categories (prefix to title, or to {"title", "parent"} for a subcategory, parent first), before any rule; then every code must use one. `category_path(prefix)` gives the chain of categories, outermost first. `next_code(prefix)` hands out numbers, one past the highest in use, so numbers are never reused.
- Rule files are read by `_open`, from a path or an http(s) URL (urllib, no new dependency). `from_file(*sources)` merges files: their dimensions and categories must agree where they share a name, and codes must be unique; a finding's `source` is its file's name or URL.
- `Registry.to_file` writes the `queryearth` member as `FORMAT`, the release that last changed the rule file format, and loading refuses a file whose `queryearth` is a later release. When a change alters the file format, set `FORMAT` to the release that will ship it.
- What a rule says is an `Outcome`; its `changes` are `Change(target, key, value, rationale)` objects. `level` defaults to WARNING without changes and INFO with them; for a computed rule that declares no level, each finding takes the default for the changes `check()` returns. Findings sort by level (highest first), then those without changes, then code.
- When a query omits a dimension that a rule constrains, the finding is **conditional** (`conditional_on` names what is missing). Conditional findings are hidden unless `include_conditional=True`.
- `product` is a plain label dimension, like `variable`. A caller makes one query per product, and nothing fills an omitted time or version.
- `Registry.query` calls `evaluate()` on every active rule, after any plugin prefilters. There are no vectorised tables (design.md section 9.1).
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
- **Behaviour changes.** Update the tests, and `docs/source/`, `README.md` and this file as needed. The frozen docs are not updated.
- **NCAR GLADE.** The `dev_cd` conda env has numpy and shapely, so you can run against the checkout without installing: `PYTHONPATH=$PWD conda run -n dev_cd python examples/toy/play.py`.
- **For AI agents.** `docs/source/llms.txt` is a one-page guide for language models, served at the docs root. `tests/test_llms_txt.py` runs its rule file and Python as written, so keep it exact when the API changes.
