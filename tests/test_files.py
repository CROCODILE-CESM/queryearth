"""Rule files: one GeoJSON FeatureCollection, read and written whole."""

import json

import pytest

import queryearth as qe
from queryearth import space as sp

DIMENSIONS = [qe.Axis("resolution", "km"), qe.Labels("ice")]
ARCTIC = {
    "type": "Feature",
    "geometry": {
        "type": "Polygon",
        "coordinates": [[[-180, 60], [180, 60], [180, 90], [-180, 90], [-180, 60]]],
    },
    "time": None,
    "properties": {
        "code": "POLAR001",
        "title": "Consider active sea ice",
        "message": "Sea ice forms poleward of 60 degrees.",
        "dimensions": {"ice": ["sice"]},
        "instruction": "Use CICE in the compset.",
        "references": [{"title": "Interview 1", "url": "https://example.org/1"}],
        "evidence": [{"quote": "sea ice matters up there"}],
    },
}


def write(path, *features):
    path.write_text(json.dumps({"type": "FeatureCollection", "features": features}))
    return path


def test_a_rule_file_reads_back_exactly_as_written(tmp_path):
    registry = qe.Registry(DIMENSIONS)
    registry.add(ARCTIC)
    registry.add(
        qe.Rule(
            "BERING001",
            "Bering Sea since 2000, coarse grids",
            "...",
            level="info",
            scope={
                "space": sp.box(165, 52, -160, 66),  # across the antimeridian
                "time": qe.interval("2000-01-01", ".."),
                "resolution": {"gt": 10},
            },
        )
    )
    registry.to_file(tmp_path / "rules.geojson")
    again = qe.Registry.from_file(tmp_path / "rules.geojson", dimensions=DIMENSIONS)
    again.to_file(tmp_path / "again.geojson")
    text = (tmp_path / "rules.geojson").read_text()
    assert (tmp_path / "again.geojson").read_text() == text
    assert '"queryearth": "0.7"' in text and "[165.0, 52.0]" in text
    query = dict(space=sp.point(-170, 60), resolution=25, ice="sice")
    query["time"] = qe.interval("2020-01-01", "2020-12-31")
    assert [r.code for r in again.query(**query)] == ["POLAR001", "BERING001"]


def test_properties_the_core_does_not_use_pass_through_unchanged(tmp_path):
    registry = qe.Registry.from_file(
        write(tmp_path / "in.geojson", ARCTIC), dimensions=DIMENSIONS
    )
    (rule,) = registry.rules
    assert set(rule.properties) == {"instruction", "references", "evidence"}
    registry.to_file(tmp_path / "out.geojson")
    (written,) = json.loads((tmp_path / "out.geojson").read_text())["features"]
    for key in ("instruction", "references", "evidence"):
        assert written["properties"][key] == ARCTIC["properties"][key]


def test_a_finding_prints_as_its_feature():
    registry = qe.Registry(DIMENSIONS)
    registry.add(ARCTIC)
    (finding,) = registry.query(space=sp.point(0, 70), ice="sice")
    printed = json.loads(json.dumps(registry.to_feature(finding)))
    assert printed["properties"] == {**ARCTIC["properties"], "level": "warning"}


def test_several_files_load_into_one_registry(tmp_path):
    claude = dict(ARCTIC, properties=dict(ARCTIC["properties"], code="CLAUDE001"))
    mine = write(tmp_path / "mine.geojson", ARCTIC)
    theirs = write(tmp_path / "claude.geojson", claude)
    registry = qe.Registry.from_file(mine, theirs, dimensions=DIMENSIONS)
    assert [r.code for r in registry.rules] == ["POLAR001", "CLAUDE001"]


def test_a_file_that_needs_a_later_queryearth_is_refused(tmp_path):
    path = tmp_path / "new.geojson"
    path.write_text(json.dumps({"type": "FeatureCollection", "queryearth": "0.8"}))
    with pytest.raises(ValueError, match="needs queryearth 0.8 or later"):
        qe.Registry.from_file(path)
    path.write_text(json.dumps({"type": "FeatureCollection", "queryearth": "0.6"}))
    assert qe.Registry.from_file(path).rules == []  # an older format reads as it is


def test_a_code_can_only_be_added_once(tmp_path):
    registry = qe.Registry(DIMENSIONS)
    registry.add(ARCTIC)
    with pytest.raises(qe.DuplicateCodeError, match="POLAR001"):
        registry.add(ARCTIC)
    twice = write(tmp_path / "twice.geojson", ARCTIC, ARCTIC)
    with pytest.raises(qe.DuplicateCodeError, match="twice.geojson: feature 1"):
        qe.Registry.from_file(twice, dimensions=DIMENSIONS)


def test_a_file_that_uses_an_undeclared_dimension_is_refused(tmp_path):
    path = write(tmp_path / "rules.geojson", ARCTIC)
    with pytest.raises(ValueError, match="feature 0: POLAR001: ice: undeclared"):
        qe.Registry.from_file(path)  # ice is not declared


def test_record_mistakes_are_refused_with_the_code(tmp_path):
    no_title = dict(ARCTIC, properties={"code": "X1", "message": "..."})
    typo = dict(ARCTIC, tme={"interval": ["2000-01-01", ".."]})
    edge = dict(ARCTIC, properties=dict(ARCTIC["properties"], edge=True))
    category = dict(ARCTIC, properties=dict(ARCTIC["properties"], category="POLAR"))
    for feature, problem in [
        (no_title, "needs a code, a title"),
        (typo, "unknown Feature members \\['tme'\\]"),
        (edge, "\\['edge'\\] changed which rules apply in queryearth 0.6"),
        (category, "category is the path of its code"),
    ]:
        with pytest.raises(ValueError, match=problem):
            qe.Registry.from_file(
                write(tmp_path / "bad.geojson", feature), dimensions=DIMENSIONS
            )
