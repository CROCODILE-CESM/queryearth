# CLAUDE.md

Guidance for Claude Code (and anyone else) working in this repository.

## What queryearth is

A small engine that matches rules to a query. A rule has a code, a title, a message, a level (`info`, `warning` or `error`, default `warning`) and a scope: a value on each dimension it constrains. Space and time are on every Registry; `Axis` (numbers in a unit) and `Labels` (names with wildcards) are declared on it, and so is any dimension a user writes. A query gives values on any of the dimensions and gets back the rules that apply. Rules are data, kept in GeoJSON rule files; code lives in dimensions. It is general-purpose, not tied to earth system modelling. Its first consumer is CrocoDash, which queries once in `Case()` and once in `configure_forcings()`.

It is an engine only: the package ships no curated rules. Rule files belong to their users.

This is the core, cut back from 0.6.0 to what is realistic to review. `docs/growth.md` lists what 0.6.0 had beyond it, kept at the tag v0.6.0: planned (categories first), parked and dropped. Re-add a feature only when the author asks for it, and move its entry.

## Rules

- **Clean room: geostructures.** Never read, copy, paraphrase or search for code from the `geostructures` project, and do not depend on it or contribute to it. More generally, avoid dependencies on projects run by military contractors.
- **Dependencies.** Runtime imports are the standard library, numpy and shapely (2.1 or later) only. Anything else goes in an optional extra, and test-only packages go in the `test` extra.
- **Python.** 3.11 or later with no upper cap. Write nothing newer than the 3.11 grammar. Add each new Python release to the CI matrix in `.github/workflows/tests.yml`.
- **Keep it small.** The author cares about code size and reviewability. Prefer the simplest implementation that passes the tests: no speculative options, no extra layers, no single-use helpers. When unsure whether something belongs in the core, leave it out and list it in `docs/growth.md`.
- **Rules are data; code lives in dimensions.** A new kind of value or comparison is a new `Dimension`; a value derived from the caller's case is computed when the query is built; advice is a rule. There are no computed rules or rule kinds.
- **One extension point.** A dimension subclasses `Dimension` and implements `parse_rule`, `parse_query`, `matches` and `to_json`. Space, time, `Axis` and `Labels` use exactly that contract, with no private hooks; space and time differ only in where their values sit in a Feature (`geometry` and `time`).
- **Git.** Ask before committing or pushing. Never add a `Co-Authored-By` line. Never @-mention people on GitHub. Branch names are plain and descriptive, with no personal names. The author does releases.
- **Public.** The repository, the user docs site and the PyPI package are all public. `MANIFEST.in` prunes `docs/` from the source distribution; keep it that way.

## Layout

| Path | What it holds |
|---|---|
| `queryearth/space.py` | `Space` (point or polygon) and `point`, `box`, `polygon`: longitudes wrapped, rings cut at ±180, invalid rings repaired, a ring around a pole refused; `meets`, closed-set and across the seam |
| `queryearth/time.py` | `Interval` (half-open integer-second keys, day or second precision) and `interval()`; one calendar, proleptic Gregorian |
| `queryearth/dimensions.py` | `Dimension` (the four-method contract), `applies()` (the matching rule, in one place), `SpaceDimension`, `TimeDimension`, `Axis`, `Labels` |
| `queryearth/rules.py` | `Rule`, a frozen dataclass: code, title, message, level, scope, properties |
| `queryearth/registry.py` | `Registry`: `add`, `query`, `rules`, `to_feature`, `to_file`, `from_file`; the rule file format (`FORMAT`, the Feature reader); `DuplicateCodeError` |
| `tests/` | `test_space.py`, `test_dimensions.py`, `test_queries.py`, `test_files.py`, and `test_docs.py`, which runs `docs/source/llms.txt` and checks the README's copy of `Labels` |
| `docs/source/` | The public user docs (Sphinx with MyST Markdown): index, dimensions, concepts, rule files, API, and `llms.txt`. Built and deployed to GitHub Pages by `.github/workflows/docs.yml`, one folder per release (`vX.Y.Z/`) plus `dev/` for `main`; `.github/docs_versions.py` keeps the version list |
| `docs/growth.md` | The growth path: what 0.6.0 had beyond the core, where it lives at the tag, and how it would plug in |

## Concepts worth knowing before changing the engine

- A rule applies when, on every dimension its scope constrains, the query gives a value and the dimension's `matches()` is true: they share at least one value. A dimension the rule leaves out matches anything. A dimension the rule constrains and the query leaves out does not match. There are no conditional findings.
- `Registry.add` parses each scope value with its dimension and refuses an undeclared name, as `Registry.query` does for the query's values. Findings are the `Rule` objects that apply, sorted by level (error first), then code. They print as GeoJSON with `Registry.to_feature`.
- A rule file is one FeatureCollection. A rule's space is the Feature's `geometry`, its time the JSON-FG `time` member (`{"interval": [start, end]}`), and every other dimension's value is in `properties.dimensions`, as that dimension's `to_json()` writes it (an axis range carries its unit). Every other property passes through unread and is written back unchanged, except `box`, `edge`, `periods`, `recurrence`, `time_start`, `time_end`, `withdrawn` and `supersedes`, which changed which rules apply in 0.6 and are refused.
- Files never declare dimensions: the caller passes them to `Registry.from_file(*paths, dimensions=[...])`, and a rule that names an undeclared one is refused. A file is read whole or not at all.
- `to_file` writes `FORMAT`, the release that last changed the rule file format, in the `queryearth` member, and `from_file` refuses a file that names a later one. When a change alters the file format, set `FORMAT` to the release that will ship it.
- Rings are normalised once, when a space is made. Matching uses closed sets, so a point on an edge is inside. On the wire, time intervals are closed, and an end date covers its whole day.
- Callers query with the support they actually use (the cells and time steps), never a buffered shape.

## Development

```bash
pip install -e ".[test]"
pytest
black .            # target py311, configured in pyproject.toml
pip install -e ".[docs]" && sphinx-build -W -b html docs/source docs/_build
```

- **CI.** It runs pytest on Python 3.11 to 3.14 on every push to every branch and on pull requests. Black is checked on pull requests.
- **Versions** come from git tags through setuptools-scm.
- **Builds and releases.** Every push to `main` builds the package. A GitHub release tagged `vX.Y.Z` publishes to PyPI through trusted publishing; there is no TestPyPI job.
- **Style.** Match the existing code: frozen dataclasses, error messages that name the rule code, short comments only where the reason is not obvious.
- **Behaviour changes.** Update the tests, and `docs/source/`, `README.md`, `docs/growth.md` and this file as needed.
- **NCAR GLADE.** The `dev_cd` conda env has numpy and shapely, so you can run against the checkout without installing: `PYTHONPATH=$PWD conda run -n dev_cd python -c "import queryearth"`.
- **For AI agents.** `docs/source/llms.txt` is a one-page guide for language models, served at the docs root. `tests/test_docs.py` runs its rule file and Python as written, so keep it exact when the API changes.
