"""Groups in groups, a Registry made from several rule files, and files at URLs."""

import functools
import http.server
import json
import threading

import pytest

import queryearth as qe
from queryearth import space as sp

NESTED = {
    "DOMAIN": "Domain design",
    "OBC": {"title": "Open boundaries", "parent": "DOMAIN"},
    "TIDE": {"title": "Tidal boundaries", "parent": "OBC"},
    "REGION": "Regional advice",
}


def rule(code, **fields):
    return qe.Rule(code=code, title=f"{code} title", message="m", **fields)


def collection(groups, codes, dimensions=()):
    registry = qe.Registry("x", dimensions=dimensions, groups=groups)
    for code in codes:
        registry.add(rule(code))
    return registry.to_collection()


def write(path, data):
    path.write_text(json.dumps(data))
    return path


# ---- groups in groups -----------------------------------------------------------------
def test_groups_nest_to_any_depth():
    registry = qe.Registry("mine", groups=NESTED)
    assert registry.groups == NESTED
    assert registry.group_path("TIDE") == ["DOMAIN", "OBC", "TIDE"]
    assert registry.group_path("REGION") == ["REGION"]
    registry.add(rule("TIDE001"))
    registry.add(rule("DOMAIN001"))  # a parent group can hold rules too
    assert registry.next_code("TIDE") == "TIDE002"


def test_a_parent_is_declared_first():
    with pytest.raises(ValueError, match="declare its parent 'DOMAIN' first"):
        qe.Registry("mine", groups={"OBC": {"title": "o", "parent": "DOMAIN"}})


def test_group_path_refuses_an_undeclared_group():
    with pytest.raises(qe.UnknownNameError):
        qe.Registry("mine", groups=NESTED).group_path("ITF")


def test_nested_groups_round_trip_through_a_file(tmp_path):
    path = write(tmp_path / "nested.geojson", collection(NESTED, ["TIDE001"]))
    again = qe.Registry.from_file(path)
    assert again.groups == NESTED
    assert again.describe()["groups"] == NESTED


def test_load_compares_parents_but_not_titles(tmp_path):
    path = write(tmp_path / "nested.geojson", collection(NESTED, ["TIDE001"]))
    retitled = {**NESTED, "OBC": {"title": "Edges", "parent": "DOMAIN"}}
    assert qe.Registry("same", groups=retitled).load(path) == ["TIDE001"]
    moved = {**NESTED, "TIDE": {"title": "Tidal boundaries", "parent": "REGION"}}
    moved = dict(sorted(moved.items(), key=lambda kv: kv[0] != "REGION"))
    with pytest.raises(qe.LoadError) as err:
        qe.Registry("moved", groups=moved).load(path)
    assert err.value.problems == (
        "nested.geojson: group 'TIDE' sits in 'OBC' in the file, but in 'REGION' "
        "on registry 'moved'",
    )


# ---- several files ----------------------------------------------------------------------
def test_from_file_merges_several_files(tmp_path):
    km = [qe.Axis("resolution", "km")]
    mine = write(tmp_path / "mine.geojson", collection(NESTED, ["OBC001"], km))
    theirs = write(
        tmp_path / "theirs.geojson",
        collection({"CLAUDE": "Added by Claude"}, ["CLAUDE001"], km),
    )
    merged = qe.Registry.from_file(mine, theirs)
    assert merged.name == "mine+theirs"
    assert list(merged.groups) == [*NESTED, "CLAUDE"]
    assert [r["code"] for r in merged.describe()["rules"]] == ["OBC001", "CLAUDE001"]
    sources = {f.code: f.source for f in merged.query()}
    assert sources == {"OBC001": "mine.geojson", "CLAUDE001": "theirs.geojson"}


def test_files_must_agree_on_a_shared_dimension(tmp_path):
    one = write(
        tmp_path / "one.geojson", collection({}, [], [qe.Axis("resolution", "km")])
    )
    two = write(
        tmp_path / "two.geojson", collection({}, [], [qe.Axis("resolution", "m")])
    )
    with pytest.raises(qe.LoadError) as err:
        qe.Registry.from_file(one, two)
    (problem,) = err.value.problems
    assert problem.startswith("two.geojson: dimensions: 'resolution' is")


def test_files_must_agree_on_a_shared_group(tmp_path):
    one = write(tmp_path / "one.geojson", collection(NESTED, []))
    flat = {"REGION": "Regional advice", "TIDE": {"title": "t", "parent": "REGION"}}
    two = write(tmp_path / "two.geojson", collection(flat, []))
    with pytest.raises(qe.LoadError) as err:
        qe.Registry.from_file(one, two)
    assert err.value.problems == (
        "two.geojson: groups: group 'TIDE' sits in 'REGION' here, but in 'OBC' "
        "in an earlier file",
    )


def test_a_code_in_two_files_is_refused(tmp_path):
    one = write(tmp_path / "one.geojson", collection(NESTED, ["OBC001"]))
    two = write(tmp_path / "two.geojson", collection(NESTED, ["OBC001"]))
    with pytest.raises(qe.LoadError, match="two.geojson: feature 0 .* already"):
        qe.Registry.from_file(one, two)


def test_from_file_needs_a_file():
    with pytest.raises(TypeError):
        qe.Registry.from_file()


# ---- files at URLs ------------------------------------------------------------------
class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


@pytest.fixture
def served(tmp_path):
    """A local web server for tmp_path, as a raw GitHub or gist link would be."""
    handler = functools.partial(Quiet, directory=str(tmp_path))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def test_from_file_and_load_read_urls(tmp_path, served):
    write(tmp_path / "mine.geojson", collection(NESTED, ["OBC001"]))
    write(tmp_path / "more.geojson", collection(NESTED, ["OBC002"]))
    registry = qe.Registry.from_file(f"{served}/mine.geojson")
    assert registry.name == "mine"
    assert registry.load(f"{served}/more.geojson") == ["OBC002"]
    sources = {f.code: f.source for f in registry.query()}
    assert sources["OBC002"] == f"{served}/more.geojson"


def test_a_missing_url_is_a_load_error(served):
    with pytest.raises(qe.LoadError) as err:
        qe.Registry.from_file(f"{served}/nowhere.geojson")
    assert err.value.problems[0].startswith(f"{served}/nowhere.geojson: HTTP Error 404")


def test_a_query_string_does_not_name_the_registry(tmp_path, served):
    write(tmp_path / "mine.geojson", collection(NESTED, ["OBC001"]))
    assert qe.Registry.from_file(f"{served}/mine.geojson?raw=1").name == "mine"


def test_a_place_rule_from_a_url_still_matches(tmp_path, served):
    registry = qe.Registry("x", groups=NESTED)
    registry.add(rule("OBC001", scope=qe.Scope(sp.box(0, 0, 10, 10), edge=True)))
    write(tmp_path / "edge.geojson", registry.to_collection())
    again = qe.Registry.from_file(f"{served}/edge.geojson")
    assert [f.code for f in again.query(space=sp.box(5, 5, 20, 20))] == ["OBC001"]
