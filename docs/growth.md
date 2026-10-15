# The growth path

This core is queryearth cut back to what is realistic to review: rules scoped by space, time, axes and labels, one matching rule, and GeoJSON rule files. Everything else queryearth 0.6.0 had is kept at the tag [v0.6.0](https://github.com/CROCODILE-CESM/queryearth/tree/v0.6.0) and listed here: what has come back into the core since, then what is planned, parked and dropped. Paths are at v0.6.0 unless they say "core". The full 0.6.0 design, its decisions and its correctness fixtures are `docs/design.md` and `docs/reference/` at the tag, and `examples/toy/` there exercises most of the features.

The core grows in three places: a new `Dimension` subclass (its four methods), the `Registry` (adding, querying, reading and writing), and `Rule.properties`, which already carries anything else a rule says, unread. Rules stay data; code lives in dimensions.

## Now in the core

### Categories

A code may be a path, such as `REGION/ITF/ITF001`; its category, `rule.category`, is the path before the last slash. Categories need no declaring: the path is the hierarchy. Codes are unique as whole paths, so two categories can each have a rule named `001`. A `category` property is refused, so it can never disagree with the code. A query is about dimensions only; keeping the findings in one category is one line on the results, `[r for r in found if r.code.startswith("REGION/")]`. A `category` filter on `query()` and a `categories` listing are easy to add if a user interface needs them.

The trade-off: moving a rule to another category changes its code, and aliases, which kept a rule's old codes in 0.6.0, are parked.

At v0.6.0 a category was the code's prefix (ITF001 in ITF), declared on the Registry with a title and a parent, and `next_code()` numbered rules within it: `queryearth/registry.py`: `add_category`, `categories`, `category_path`, `next_code`; `queryearth/rules.py`: `check_code`, `split_code`, `make_code`. Titles and `next_code()` stay at the tag.

### Version enforcement

`to_file` writes the format's release in the `queryearth` member, and `from_file` refuses a file that needs a later queryearth, saying to upgrade. Reading pre-0.6 files' `groups` member as `categories` stays at the tag: `queryearth/registry.py`, `_categories_member`.

## Planned

### Recurring time

**What.** A rule's time as several intervals (`periods`) and as some months of every year (`recurrence`, such as `{"months": [12, 1, 2]}`, wrapping the year end). The core's time is one interval.

**At v0.6.0.** `queryearth/time.py`: `TimeSpec`, `parse_time`, and `overlap`, which cuts an overlap into calendar months.

**Plugs in.** `TimeDimension.parse_rule` and `to_json` take and write a list of intervals and a set of months, and `matches` checks whether the query's interval meets any interval in one of the months (the month cutting in `overlap`). The file form is the 0.6.0 one: `periods` and `recurrence` beside the `time` member, which the core refuses today so that an old record is never read as applying all year. Alternatively, months alone can be a dimension of its own, such as `Months("season")`, with no core change.

### report()

**What.** `report(findings)` printed each finding as text: its level, `[CODE] title`, then its message, instruction and changes, indented. The core prints findings as their GeoJSON Features.

**At v0.6.0.** `queryearth/objects.py`: `report`, `Finding.__str__`.

**Plugs in.** A function over the rules a query returns, in `queryearth/rules.py`, reading `rule.properties` for an instruction. About ten lines.

*Optional: why a rule did not apply.* For one rule and one query, name the dimension that failed or that the query left out. Not in 0.6.0; it came out of the z3 study. A sibling of `applies()` in the core's `queryearth/dimensions.py`, about eight lines.

### Sharing: rule files at URLs

**What.** `from_file` read a rule file at an http(s) URL, such as a raw link to a file in a GitHub repository or gist, with urllib and no new dependency.

**At v0.6.0.** `queryearth/registry.py`: `_open`, `Registry.from_file`, `Registry.load`.

**Plugs in.** A branch in `Registry.from_file` that reads a path that starts with `http://` or `https://` through `urllib.request`. About eight lines.

### Packs

**What.** A ruleset as a folder: `pack.json`, a folder per category with `category.json`, and a file per rule named by its code, so a rule set in git shows each change as a change to one file. `to_pack` wrote or updated one.

**At v0.6.0.** `queryearth/registry.py`: `_read_pack`, `Registry.to_pack`, `PACK`, `CATEGORY`. Tests: `tests/test_packs.py`.

**Plugs in.** A reader that maps each category path to a folder and each code's last part to a file name, turning the folder into the FeatureCollection `from_file` reads, and a writer from `to_feature`. Until then, a folder of Feature files converts to a rule file by gathering its Features, which is how CrocoDash's two packs were converted for the core.

### Features for AI agents

**What.** `describe()` told a person or a language model what a Registry can answer: its dimensions, its rules, and through `values(name)`, every value the rules give on a dimension. 0.6.0 rule files also declared their own dimensions, so `from_file` needed no Python.

**At v0.6.0.** `queryearth/registry.py`: `Registry.describe`, `Registry.values`, `Registry.from_file`; `queryearth/dimensions.py`: `describe_dimension`, `dimension_from`.

**Plugs in.** A `describe()` method on `Dimension` (its name, kind and, for an axis, unit), and `Registry.describe()` and `values()` over the rules' scopes. `docs/source/llms.txt`, the one-page guide for language models, is in the core already, and its test runs it as written.

## Parked

Kept at the tag, not planned.

- **Overlap amounts.** Area fraction and km², time overlap and fraction, the part of an axis range met, and `min_overlap`; a finding in the core just says the rule applied. `space.py`: `measure`, `area_km2`; `time.py`: `time_fraction`; `dimensions.py`: `DimMatch`, `AxisOverlap`; `objects.py`: `Match`.
- **Polar caps.** A grid that contains a pole became the polar cap beyond its outline. `converters.py`: `grid_outline`. The core keeps a box to ±90 working and refuses a ring around a pole with a hint (about seven lines in the core's `space._ring`).
- **A rule-set lint with z3.** Rules that can never apply, identical or nested scopes, conflicting pairs. Not in 0.6.0; from the z3 study, which found z3 too slow for matching, it belongs in CrocoDash's tests.
- **Rule-history fields.** `status`, `confidence`, `action`, `created`, `updated`, `withdrawn`, `supersedes` and `aliases`. `objects.py`: `Outcome`; `rules.py`: `Rule`; `registry.py`: `_active`. The core passes them through unread, except `withdrawn` and `supersedes`, which it refuses because they changed which rules apply.
- **Versions.** OSV-style version ranges as a dimension. `dimensions.py`: `Versions`, `VersionRange`.
- **query_points.** Masks and weighted shares over many points. `registry.py`: `Registry.query_points`, `PointResult`; `space.py`: `points_mask`.
- **Conditional findings.** A rule whose dimension the query left out was returned as conditional, hidden by default; the core treats it as not applying, as 0.6.0 did by default. `rules.py`: `match_scope`; `objects.py`: `Match.conditional_on`.
- **Alternatives within a dimension.** A list of axis ranges, and labels with `any_of` and `none_of`. `dimensions.py`: `Axis.parse_rule`, `Patterns`.
- **More dimension hooks.** `comparable`, `build` and `Prefilter`, `late`, `always`, `extent`. `dimensions.py`: `Dimension`, `Prefilter`; `registry.py`: `_prefilters`.
- **Record shorthands.** A `box` property, `time_start` and `time_end`, JSON-FG `date` and `timestamp` members, `x_*` extensions, levels as logging numbers. `rules.py`: `box_of`, `Rule._read`; `time.py`: `parse_time`; `objects.py`: `level_of`. The core refuses `box`, `time_start` and `time_end`.
- **The query object.** `Query` with a label and a context, and `Registry.default()`. `objects.py`: `Query`; `registry.py`: `Registry.default`.

## Dropped

- **Edge rules**, a rule that applies where a domain's edge meets its space: too confusing to read. CrocoDash writes its nine (OBC001 to OBC005, CLAUDE002 to CLAUDE005) as plain area rules now. The core refuses `"edge": true` so an old record is not read as an area rule.
- **changes**, structured edits for the caller to apply: folded into the message or instruction, as CrocoDash did for GRID001, POLAR001 and ITF001.
- **grid_outline**: lives in CrocoDash, as six lines for regional grids.
- **Computed rules and third-party rule kinds** (`ComputedRule`, `@registry.rule`, `RuleKind`): covered by defining a dimension; rules are always data.
