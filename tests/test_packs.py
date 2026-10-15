"""Packs: a ruleset as a folder, a folder per category and a file per rule."""

import json

import pytest

import queryearth as qe
from queryearth import space as sp

CATEGORIES = {
    "DOMAIN": "Domain design",
    "OBC": {"title": "Open boundaries", "parent": "DOMAIN"},
    "REGION": "Regions",
    "ITF": {"title": "Indonesian Throughflow", "parent": "REGION"},
}


def rule(code, **fields):
    return qe.Rule(code=code, title=f"{code} title", message="m", **fields)


def registry(categories=CATEGORIES):
    found = qe.Registry(
        "mine", dimensions=[qe.Axis("resolution", "km")], categories=categories
    )
    found.add(rule("OBC001", scope=qe.Scope(sp.box(0, 0, 10, 10), edge=True)))
    found.add(rule("OBC002"))
    found.add(rule("ITF001", scope=qe.Scope(dimensions={"resolution": {"gt": 5}})))
    found.add(rule("DOMAIN001"))
    return found


def files(folder):
    return sorted(
        p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file()
    )


# ---- writing and reading ----------------------------------------------------------------
def test_to_pack_lays_out_categories_as_folders(tmp_path):
    registry().to_pack(tmp_path / "mine")
    assert files(tmp_path / "mine") == [
        "DOMAIN/DOMAIN001.geojson",
        "DOMAIN/OBC/OBC001.geojson",
        "DOMAIN/OBC/OBC002.geojson",
        "DOMAIN/OBC/category.json",
        "DOMAIN/category.json",
        "REGION/ITF/ITF001.geojson",
        "REGION/ITF/category.json",
        "REGION/category.json",
        "pack.json",
    ]
    pack = json.loads((tmp_path / "mine" / "pack.json").read_text())
    assert pack == {
        "queryearth": qe.FORMAT,
        "dimensions": [{"name": "resolution", "kind": "axis", "unit": "km"}],
    }
    title = json.loads((tmp_path / "mine/DOMAIN/OBC/category.json").read_text())
    assert title == {"title": "Open boundaries"}


def test_a_pack_reads_back_as_the_registry_it_came_from(tmp_path):
    registry().to_pack(tmp_path / "mine")
    again = qe.Registry.from_file(tmp_path / "mine")
    assert again.name == "mine"
    assert again.categories == CATEGORIES  # alphabetical here, as declared there
    before = {f["id"]: f for f in registry().to_collection()["features"]}
    after = {f["id"]: f for f in again.to_collection()["features"]}
    assert after == before
    crossing = {f.code for f in again.query(space=sp.box(5, 5, 20, 20))}
    elsewhere = {f.code for f in again.query(space=sp.box(40, 40, 50, 50))}
    assert crossing - elsewhere == {"OBC001"}  # the edge rule; the rest apply anywhere
    assert again.query()[0].source == "mine/"


def test_a_pack_and_a_rule_file_merge(tmp_path):
    registry().to_pack(tmp_path / "mine")
    theirs = qe.Registry("theirs", categories={"CLAUDE": "Added by Claude"})
    theirs.add(rule("CLAUDE001"))
    theirs.to_file(tmp_path / "theirs.geojson")
    merged = qe.Registry.from_file(tmp_path / "mine", tmp_path / "theirs.geojson")
    assert len(merged.describe()["rules"]) == 5
    assert {f.code: f.source for f in merged.query()}["CLAUDE001"] == "theirs.geojson"


def test_load_reads_a_pack_too(tmp_path):
    registry().to_pack(tmp_path / "mine")
    empty = qe.Registry(
        "x", dimensions=[qe.Axis("resolution", "km")], categories=CATEGORIES
    )
    assert sorted(empty.load(tmp_path / "mine")) == [
        "DOMAIN001",
        "ITF001",
        "OBC001",
        "OBC002",
    ]


def test_each_point_is_written_on_one_line(tmp_path):
    found = registry()
    found.add(
        qe.Rule(code="OBC003", title="t", message="see [\n 1,\n 2\n] and [ 3, 4 ]")
    )
    found.to_pack(tmp_path / "mine")
    found.to_file(tmp_path / "mine.geojson")
    point, message = "[0.0, 0.0]", '"see [\\n 1,\\n 2\\n] and [ 3, 4 ]"'
    assert point in (tmp_path / "mine/DOMAIN/OBC/OBC001.geojson").read_text()
    assert message in (tmp_path / "mine/DOMAIN/OBC/OBC003.geojson").read_text()
    text = (tmp_path / "mine.geojson").read_text()
    assert point in text and message in text
    again = qe.Registry.from_file(tmp_path / "mine.geojson")
    assert again.to_collection() == found.to_collection()


def test_without_categories_each_prefix_gets_a_folder(tmp_path):
    plain = qe.Registry("plain")
    plain.add(rule("ITF001"))
    plain.add(rule("OBC001"))
    plain.to_pack(tmp_path / "plain")
    assert "ITF/ITF001.geojson" in files(tmp_path / "plain")
    assert qe.Registry.from_file(tmp_path / "plain").categories == {
        "ITF": "ITF",
        "OBC": "OBC",
    }


# ---- updating a pack ----------------------------------------------------------------------
def test_writing_again_removes_what_is_gone_and_keeps_other_files(tmp_path):
    folder = tmp_path / "mine"
    registry().to_pack(folder)
    (folder / "README.md").write_text("notes")
    (folder / "REGION" / "ITF" / "notes.txt").write_text("keep me")
    smaller = qe.Registry(
        "mine", dimensions=[qe.Axis("resolution", "km")], categories=CATEGORIES
    )
    smaller.add(rule("OBC001"))
    smaller.to_pack(folder)
    assert files(folder) == [
        "DOMAIN/OBC/OBC001.geojson",
        "DOMAIN/OBC/category.json",
        "DOMAIN/category.json",
        "README.md",
        "REGION/ITF/category.json",
        "REGION/ITF/notes.txt",
        "REGION/category.json",
        "pack.json",
    ]


def test_to_pack_refuses_a_folder_that_is_not_a_pack(tmp_path):
    (tmp_path / "busy").mkdir()
    (tmp_path / "busy" / "thesis.tex").write_text("x")
    with pytest.raises(ValueError, match="not empty and not a pack"):
        registry().to_pack(tmp_path / "busy")


# ---- problems ------------------------------------------------------------------------------
def test_every_layout_problem_is_reported_at_once(tmp_path):
    folder = tmp_path / "mine"
    registry().to_pack(folder)
    (folder / "DOMAIN/OBC/OBC002.geojson").rename(folder / "DOMAIN/OBC/OBC009.geojson")
    (folder / "REGION/ITF/ITF001.geojson").rename(folder / "DOMAIN/OBC/ITF001.geojson")
    (folder / "LOST").mkdir()
    (folder / "LOST" / "LOST001.geojson").write_text("{}")
    (folder / "DOMAIN/category.json").write_text('{"title": "Domain", "colour": "red"}')
    with pytest.raises(qe.LoadError) as err:
        qe.Registry.from_file(folder)
    assert sorted(err.value.problems) == sorted(
        [
            "mine/DOMAIN/category.json: has only ['title'], not "
            "{'title': 'Domain', 'colour': 'red'}",
            "mine/DOMAIN/OBC/ITF001.geojson: ITF001 is in the OBC folder; its code "
            "puts it in ITF",
            "mine/DOMAIN/OBC/OBC009.geojson: a rule file holds one rule, named by "
            "its code",
            "mine/LOST/: a category folder has a category.json",
        ]
    )


def test_a_folder_without_pack_json_is_not_a_pack(tmp_path):
    (tmp_path / "loose").mkdir()
    with pytest.raises(qe.LoadError, match="a pack has a pack.json"):
        qe.Registry.from_file(tmp_path / "loose")


def test_a_category_folder_needs_a_prefix_name(tmp_path):
    folder = tmp_path / "mine"
    registry().to_pack(folder)
    (folder / "REGION" / "ITF").rename(folder / "REGION" / "itf")
    with pytest.raises(qe.LoadError) as err:
        qe.Registry.from_file(folder)
    assert err.value.problems[0].startswith(
        "mine/REGION/itf/: 'itf' is not a code prefix"
    )


def test_folders_that_hold_no_rules_are_left_alone(tmp_path):
    folder = tmp_path / "mine"
    registry().to_pack(folder)
    (folder / "images").mkdir()
    (folder / "images" / "map.png").write_bytes(b"\x89PNG")
    assert len(qe.Registry.from_file(folder).describe()["rules"]) == 4


def test_pack_json_takes_only_its_own_members(tmp_path):
    folder = tmp_path / "mine"
    registry().to_pack(folder)
    (folder / "pack.json").write_text('{"queryearth": "0.6", "name": "mine"}')
    with pytest.raises(qe.LoadError, match="pack.json: has only"):
        qe.Registry.from_file(folder)


def test_a_pack_for_a_later_release_is_refused(tmp_path):
    folder = tmp_path / "mine"
    registry().to_pack(folder)
    (folder / "pack.json").write_text('{"queryearth": "9.0", "dimensions": []}')
    with pytest.raises(qe.LoadError, match="this file needs queryearth 9.0"):
        qe.Registry.from_file(folder)
