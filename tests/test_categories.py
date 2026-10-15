"""Categories of rules by code prefix, new codes, and writing and versioning rule files."""

import json

import pytest

import queryearth as qe
from queryearth import space as sp
from queryearth.rules import make_code, split_code

CATEGORIES = {"GRID": "Grid and numerics", "ITF": "Indonesian Throughflow"}


def rule(code, **fields):
    return qe.Rule(code=code, title=f"{code} title", message="m", **fields)


def write(path, data):
    path.write_text(json.dumps(data))
    return path


# ---- codes ---------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "code, parts",
    [("CRU001", ("CRU", 1)), ("ERA5-014", ("ERA5", 14)), ("ITF1234", ("ITF", 1234))],
)
def test_a_code_is_a_prefix_and_a_number(code, parts):
    assert split_code(code) == parts
    assert make_code(*parts) == code


@pytest.mark.parametrize("prefix", ["I", "itf", "ITF-", "ABCDEFGHIJKLM", 7])
def test_a_bad_prefix_is_refused(prefix):
    with pytest.raises(ValueError, match="not a code prefix"):
        make_code(prefix, 1)


# ---- categories -------------------------------------------------------------------------------
def test_a_registry_declares_its_categories():
    registry = qe.Registry("mine", categories=CATEGORIES)
    assert registry.categories == CATEGORIES
    registry.add(rule("ITF001"))
    with pytest.raises(qe.UnknownNameError, match="undeclared category 'OBC'"):
        registry.add(rule("OBC001"))


def test_without_categories_any_prefix_goes():
    registry = qe.Registry("mine")
    registry.add(rule("ITF001"))
    registry.add(rule("OBC001"))
    assert registry.categories == {}


def test_categories_are_declared_before_rules():
    registry = qe.Registry("mine")
    registry.add(rule("ITF001"))
    with pytest.raises(ValueError, match="before adding rules"):
        registry.add_category("ITF", "Indonesian Throughflow")


@pytest.mark.parametrize("title", ["", "  ", {"title": ""}])
def test_a_category_needs_a_title(title):
    with pytest.raises(ValueError, match="needs a title"):
        qe.Registry("mine", categories={"ITF": title})


@pytest.mark.parametrize("value", [None, 7, {"name": "x"}, {"title": "x", "kids": []}])
def test_a_category_is_a_title_or_a_title_and_parent(value):
    with pytest.raises(ValueError, match="is its title, or"):
        qe.Registry("mine", categories={"ITF": value})


def test_describe_gives_the_categories():
    assert (
        qe.Registry("mine", categories=CATEGORIES).describe()["categories"]
        == CATEGORIES
    )


# ---- next_code ----------------------------------------------------------------------------
def test_next_code_follows_the_highest_number_in_the_category():
    registry = qe.Registry("mine", categories=CATEGORIES)
    assert registry.next_code("ITF") == "ITF001"
    for code in ("ITF001", "ITF007", "GRID002"):
        registry.add(rule(code))
    assert registry.next_code("ITF") == "ITF008"
    assert registry.next_code("GRID") == "GRID003"


def test_next_code_skips_withdrawn_numbers():
    registry = qe.Registry("mine")
    registry.add(rule("ITF001"))
    registry.add(rule("ITF002", withdrawn="2026-01-01"))
    assert registry.next_code("ITF") == "ITF003"


def test_next_code_skips_codes_kept_as_aliases_or_superseded():
    registry = qe.Registry("mine")
    registry.add(rule("OBC006", aliases=["ITF009", "not a code"]))
    registry.add(rule("ITF001", supersedes=["ITF012"]))
    assert registry.next_code("ITF") == "ITF013"
    registry = qe.Registry("mine")
    registry.add(rule("OBC006", aliases=["ITF009"]))  # a rule moved out of ITF
    assert registry.next_code("ITF") == "ITF010"


def test_next_code_hyphenates_a_prefix_that_ends_in_a_digit():
    registry = qe.Registry("mine")
    registry.add(rule("ERA5-014"))
    assert registry.next_code("ERA5") == "ERA5-015"


def test_next_code_refuses_an_undeclared_category():
    with pytest.raises(qe.UnknownNameError):
        qe.Registry("mine", categories=CATEGORIES).next_code("OBC")


# ---- writing and reading files ------------------------------------------------------------
def full_registry():
    registry = qe.Registry(
        "mine", dimensions=[qe.Axis("resolution", "km")], categories=CATEGORIES
    )
    registry.add(rule("GRID001", scope=qe.Scope(dimensions={"resolution": {"lt": 10}})))
    registry.add(rule("ITF001", scope=qe.Scope(sp.box(115, -10, 120, -5), edge=True)))

    @registry.rule("GRID002")
    def computed(query, match):
        """Code, so it stays out of files"""
        return True

    return registry


def test_to_collection_writes_the_format_categories_dimensions_and_records():
    collection = full_registry().to_collection()
    assert list(collection) == [
        "type",
        "queryearth",
        "categories",
        "dimensions",
        "features",
    ]
    assert collection["queryearth"] == qe.FORMAT
    assert collection["categories"] == CATEGORIES
    assert collection["dimensions"] == [
        {"name": "resolution", "kind": "axis", "unit": "km"}
    ]
    assert [f["id"] for f in collection["features"]] == ["GRID001", "ITF001"]


def test_to_file_and_from_file_round_trip(tmp_path):
    path = tmp_path / "mine.geojson"
    full_registry().to_file(path)
    again = qe.Registry.from_file(path)
    assert again.categories == CATEGORIES
    assert again.to_collection() == full_registry().to_collection()
    domain = sp.box(117, -12, 125, 0)  # its west edge crosses ITF001
    assert [f.code for f in again.query(space=domain)] == ["ITF001"]


def test_a_registry_without_categories_writes_none():
    assert "categories" not in qe.Registry("bare").to_collection()


def test_a_file_needing_a_later_release_is_refused(tmp_path):
    collection = full_registry().to_collection()
    collection["queryearth"] = "9.1"
    path = write(tmp_path / "later.geojson", collection)
    for load in (qe.Registry.from_file, full_registry().load):
        with pytest.raises(qe.LoadError) as err:
            load(path)
        (problem,) = err.value.problems
        assert problem.startswith(
            "later.geojson: this file needs queryearth 9.1 or later"
        )
        assert f"reads files up to {qe.FORMAT}" in problem


@pytest.mark.parametrize("given", ["0.3", "0.4.2", qe.FORMAT])
def test_a_file_for_this_release_or_earlier_loads(tmp_path, given):
    collection = full_registry().to_collection()
    collection["queryearth"] = given
    assert qe.Registry.from_file(write(tmp_path / "ok.geojson", collection))


@pytest.mark.parametrize("given", ["four", "0", 0.4, "v0.4"])
def test_a_malformed_release_is_refused(tmp_path, given):
    collection = full_registry().to_collection()
    collection["queryearth"] = given
    with pytest.raises(qe.LoadError, match='"queryearth" is the release'):
        qe.Registry.from_file(write(tmp_path / "bad.geojson", collection))


def test_a_file_without_a_release_loads(tmp_path):
    collection = full_registry().to_collection()
    del collection["queryearth"]
    assert qe.Registry.from_file(write(tmp_path / "old.geojson", collection))


def test_load_needs_the_file_categories_declared_here(tmp_path):
    path = tmp_path / "mine.geojson"
    full_registry().to_file(path)
    other = qe.Registry(
        "other", dimensions=[qe.Axis("resolution", "km")], categories={"GRID": "Grid"}
    )
    with pytest.raises(qe.LoadError) as err:
        other.load(path)
    assert err.value.problems == (
        "mine.geojson: category 'ITF' is not declared on registry 'other'",
    )
    assert other.describe()["rules"] == []  # nothing added


def test_load_ignores_category_titles(tmp_path):
    path = tmp_path / "mine.geojson"
    full_registry().to_file(path)
    other = qe.Registry(
        "other",
        dimensions=[qe.Axis("resolution", "km")],
        categories={"GRID": "Grid", "ITF": "ITF"},
    )
    assert other.load(path) == ["GRID001", "ITF001"]
    assert other.categories == {"GRID": "Grid", "ITF": "ITF"}


def test_a_file_rule_outside_the_categories_is_refused(tmp_path):
    collection = full_registry().to_collection()
    collection["categories"] = {"GRID": "Grid and numerics"}
    with pytest.raises(qe.LoadError) as err:
        qe.Registry.from_file(write(tmp_path / "bad.geojson", collection))
    assert "undeclared category 'ITF'" in err.value.problems[0]


def test_from_file_reports_bad_categories(tmp_path):
    collection = full_registry().to_collection()
    collection["categories"] = {"itf": "lower case"}
    with pytest.raises(qe.LoadError) as err:
        qe.Registry.from_file(write(tmp_path / "bad.geojson", collection))
    assert err.value.problems[0].startswith(
        "bad.geojson: categories: 'itf' is not a code prefix"
    )


# ---- files from before 0.6 call categories "groups" -------------------------------------
@pytest.mark.parametrize("release", ["0.4", "0.5", None])
def test_an_older_file_with_groups_still_loads(tmp_path, release):
    collection = full_registry().to_collection()
    collection["groups"] = collection.pop("categories")
    if release is None:
        del collection["queryearth"]
    else:
        collection["queryearth"] = release
    path = write(tmp_path / "old.geojson", collection)
    assert qe.Registry.from_file(path).categories == CATEGORIES
    other = qe.Registry(
        "other", dimensions=[qe.Axis("resolution", "km")], categories=CATEGORIES
    )
    assert other.load(path) == ["GRID001", "ITF001"]


def test_groups_in_a_new_file_is_refused(tmp_path):
    collection = full_registry().to_collection()
    collection["groups"] = collection.pop("categories")
    with pytest.raises(qe.LoadError) as err:
        qe.Registry.from_file(write(tmp_path / "new.geojson", collection))
    assert err.value.problems[0] == (
        'new.geojson: categories: "groups" is called "categories" since queryearth 0.6'
    )


def test_groups_and_categories_together_is_refused(tmp_path):
    collection = full_registry().to_collection()
    collection["groups"] = collection["categories"]
    collection["queryearth"] = "0.5"
    with pytest.raises(qe.LoadError, match='"groups" is called "categories"'):
        full_registry().load(write(tmp_path / "both.geojson", collection))


def test_describe_gives_each_rule_its_category():
    registry = qe.Registry("mine", categories=CATEGORIES)
    registry.add(rule("ITF001"))
    assert registry.describe()["rules"][0]["category"] == "ITF"
    plain = qe.Registry("plain")
    plain.add(rule("ITF001"))
    assert plain.describe()["rules"][0]["category"] is None
