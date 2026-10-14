"""Records and rule files: Registry.load and Registry.add of GeoJSON, the loader
checks, the record parts of fixtures 17 and 27 of docs/reference/fixtures.md, and
Rule.to_feature round trips.
"""

import copy
import dataclasses
import json
from pathlib import Path

import pytest
import shapely

import queryearth as qe
from queryearth import space as sp

TOY = Path(__file__).resolve().parents[1] / "examples" / "toy" / "rules.geojson"
TOY_FEATURES = json.loads(TOY.read_text())["features"]


def record(code="TST001", **props):
    base = {"code": code, "title": "t", "message": "m"}
    return {"type": "Feature", "geometry": None, "properties": {**base, **props}}


def collection(features):
    return {"type": "FeatureCollection", "features": features}


def write(path, data):
    path.write_text(json.dumps(data))
    return path


def toy_registry():
    """The dimensions and groups the toy rules use, and a group for the tests'."""
    names = ("product", "variable", "model")
    labels = [qe.Labels(name) for name in names]
    return qe.Registry(
        "toy",
        dimensions=[qe.Axis("resolution", "km"), *labels],
        groups={"TOY": "Toy rules", "TST": "Test rules"},
    )


# ---- Registry.load ------------------------------------------------------------------
def test_load_adds_the_rules_of_one_file(tmp_path):
    registry = toy_registry()
    codes = registry.load(TOY)
    assert codes == [f["properties"]["code"] for f in TOY_FEATURES]
    (found,) = registry.query(dimensions={"resolution": 60.0})
    assert found.code == "TOY103" and found.source == "rules.geojson"
    single = write(tmp_path / "one.geojson", record("TST001"))  # a lone Feature
    assert registry.load(single) == ["TST001"]
    with pytest.raises(qe.LoadError, match="one.geojson: feature 0 .* already"):
        registry.load(single)
    assert len(registry._entries) == len(codes) + 1


def test_load_reports_every_problem_and_leaves_the_registry_unchanged(tmp_path):
    registry = qe.Registry("x", dimensions=[qe.Axis("resolution", "km")])
    registry.add(qe.Rule(code="OLD001", title="t", message="m"))
    deg = {"resolution": {"lt": 10, "unit": "deg"}}  # fixture 17
    features = [
        record("TST001"),
        record("TST002", dimensions={"colour": ["red"]}),
        record("TST003"),
        record("TST004", dimensions=deg),
        record("TST001"),
        record("TST006", region_ref="ar6:CAF"),
        "not a feature",
    ]
    with pytest.raises(qe.LoadError) as err:
        registry.load(write(tmp_path / "rules.geojson", collection(features)))
    problems = err.value.problems
    assert [p.split(":")[0] for p in problems] == ["rules.geojson"] * 5
    assert problems[0].startswith("rules.geojson: feature 1 (TST002): ")
    assert "undeclared dimension 'colour'" in problems[0]
    assert "feature 3 (TST004): " in problems[1] and "'deg'" in problems[1]
    assert "feature 4 (TST001): " in problems[2] and "already" in problems[2]
    assert "feature 5 (TST006): unknown members ['region_ref']" in problems[3]
    assert "feature 6 (None): a record is a GeoJSON Feature" in problems[4]
    assert [e.rule.code for e in registry._entries] == ["OLD001"]
    assert [f.code for f in registry.query()] == ["OLD001"]


def test_load_refuses_a_file_it_cannot_read(tmp_path):
    registry = qe.Registry("x")
    (tmp_path / "broken.geojson").write_text("{")
    (tmp_path / "binary.geojson").write_bytes(b"\xff\xfe\x00")
    write(tmp_path / "point.geojson", {"type": "Point", "coordinates": [0, 0]})
    write(tmp_path / "list.geojson", [record()])
    for name, text in [
        ("missing.geojson", "No such file"),
        ("broken.geojson", "Expecting"),
        ("binary.geojson", "decode"),
        ("point.geojson", "not a GeoJSON FeatureCollection"),
        ("list.geojson", "not a GeoJSON FeatureCollection"),
    ]:
        with pytest.raises(qe.LoadError, match=f"^{name}: .*{text}"):
            registry.load(tmp_path / name)
    assert not registry._entries


# ---- Registry.add of a mapping ------------------------------------------------------
def test_add_takes_a_feature_or_a_whole_feature_collection():
    registry = qe.Registry("x")
    registry.add(
        record("TST001", box={"west": 170, "width": 20, "south": -20, "north": -10})
    )
    (found,) = registry.query(space=sp.point(-175, -15))
    assert found.code == "TST001" and found.source == "python"
    features = collection([record("TST002"), {}])
    with pytest.raises(qe.LoadError, match=r"collection: feature 1 \(None\)"):
        registry.add(features)
    assert [e.rule.code for e in registry._entries] == ["TST001"]
    features["features"].pop()
    registry.add(features)
    assert len(registry._entries) == 2


def test_time_start_and_time_end_are_the_fallback_time():
    registry = qe.Registry("x")
    registry.add(record(time_start="2000-01-01", time_end="2006-12-31"))
    (found,) = registry.query(time=("2006-12-31", "2007-12-31"))
    assert found.time_overlap == (("2006-12-31", "2006-12-31"),)
    with pytest.raises(ValueError, match="TST002: time_start"):
        registry.add(
            {
                **record("TST002", time_start="2000-01-01"),
                "time": {"date": "2000-01-01"},
            }
        )


# ---- records: rings, and fixtures 17 and 27 ---------------------------------------------
def test_a_ring_around_a_pole_is_a_load_error():
    ring = [[-180 + i, 70] for i in range(360)] + [[-180, 70]]
    feature = {**record(), "geometry": {"type": "Polygon", "coordinates": [ring]}}
    with pytest.raises(ValueError, match="TST001: .* close it along latitude 90"):
        qe.Registry("x").add(feature)
    feature["geometry"]["coordinates"] = [ring[:-1] + [[180, 70], [-180, 70]]]
    with pytest.raises(ValueError, match="TST001: the ring encloses no area"):
        qe.Registry("x").add(feature)  # -180 and 180 both listed: no turn, no area
    cap = [[-180, 70], [180, 70], [180, 90], [-180, 90], [-180, 70]]
    feature["geometry"]["coordinates"] = [cap]
    registry = qe.Registry("x")
    registry.add(feature)
    assert [f.code for f in registry.query(space=sp.point(123, 90))] == ["TST001"]


def test_fixture_17_axis_unit_in_a_record():
    registry = qe.Registry("x", dimensions=[qe.Axis("resolution", "km")])
    with pytest.raises(ValueError, match="TST001: resolution: unit 'deg'"):
        registry.add(record(dimensions={"resolution": {"lt": 10, "unit": "deg"}}))
    km = {"resolution": {"lt": 10, "unit": "km"}}
    registry.add(record("TST002", dimensions=km))


class Pfafstetter(qe.Dimension):
    """The basin dimension of section 4.13; parse_rule checks the record's value."""

    name = "basin"

    def parse_rule(self, value):
        if isinstance(value, str) or not all(
            isinstance(v, str) and v.isdigit() and "0" not in v for v in value
        ):
            raise ValueError(f"basins are a list of Pfafstetter codes, not {value!r}")
        return tuple(value)

    def parse_query(self, value):
        return str(value)

    def match(self, rule, query):
        hits = [b for b in rule if query.startswith(b) or b.startswith(query)]
        inside = any(query.startswith(b) for b in hits)
        return qe.DimMatch(tuple(hits), 1.0 if inside else None) if hits else None


def test_fixture_27_plugin_values_in_records_are_checked_by_the_plugin():
    registry = qe.Registry("glhe", dimensions=[Pfafstetter()])
    with pytest.raises(ValueError, match="TST001: basin: basins are a list"):
        registry.add(record(dimensions={"basin": "14"}))  # a string, not a list
    with pytest.raises(ValueError, match="TST001: basin: "):
        registry.add(record(dimensions={"basin": ["14", "0"]}))
    with pytest.raises(qe.UnknownNameError, match="basins"):
        registry.add(record(dimensions={"basins": ["14"]}))
    registry.add(record(dimensions={"basin": ["14", "62"]}))
    (found,) = registry.query(dimensions={"basin": "1423"})
    assert found.dimensions == {"basin": qe.DimMatch(("14",), 1.0)}


# ---- the loader refuses broken records ------------------------------------------------
BAD = {
    "unknown property": {"colour": "red"},
    "a region_ref": {"region_ref": "ar6:CAF"},
    "level not info, warning or error": {"level": "critical"},
    "reviewed without references": {"status": "reviewed"},
    "box west out of range": {"box": {"west": 180, "width": 1, "south": 0, "north": 1}},
    "fixed and last_affected": {
        "dimensions": {"version": {"fixed": "2", "last_affected": "1"}}
    },
    "label any_of empty": {"dimensions": {"variable": {"any_of": []}}},
    "axis with lt and le": {"dimensions": {"resolution": {"lt": 1, "le": 2}}},
    "dimensions not an object": {"dimensions": [["variable", "pre"]]},
    "periods without time": {"periods": [["2000-01-01", "2000-12-31"]]},
    "supersedes a bad code": {"supersedes": ["cru001"]},
    "a calendar": {"calendar": "noleap"},
}
BAD_FEATURES = {
    "five digits after a letter prefix": record("ABC12001"),
    "box with a polygon": {
        **record(box={"west": 0, "width": 1, "south": 0, "north": 1}),
        "geometry": sp.box(0, 0, 1, 1).geometry.__geo_interface__,
    },
    "a month as a date": {**record(), "time": {"interval": ["2020-01", "2020-02"]}},
    "time_start with a time": {
        **record(time_start="2000-01-01"),
        "time": {"date": "2000-01-01"},
    },
    "place not null": {**record(), "place": {"type": "Point"}},
    "not a feature": {**record(), "type": "Point"},
}
BROKEN = {name: record(**props) for name, props in BAD.items()} | BAD_FEATURES


@pytest.mark.parametrize("name", list(BROKEN))
def test_loader_rejects_broken_records(name):
    dimensions = [qe.Axis("resolution", "km"), qe.Labels("variable")]
    registry = qe.Registry("x", dimensions=[*dimensions, qe.Versions("version")])
    with pytest.raises((ValueError, KeyError, TypeError)):
        registry.add(copy.deepcopy(BROKEN[name]))


@pytest.mark.parametrize("member", ["facets", "axes"])  # the members of 0.1.0
def test_old_scope_members_are_unknown_members(member):
    """Every dimension's value goes under "dimensions"."""
    registry = qe.Registry("x", dimensions=[qe.Labels("variable")])
    with pytest.raises(ValueError, match=rf"TST001: unknown members \['{member}'\]"):
        registry.add(record(**{member: {"variable": ["pre"]}}))


@pytest.mark.parametrize("member", ["kind", "suggestions"])  # the members of 0.1.0
def test_kind_and_suggestions_are_unknown_members(member):
    """A record has no kind, and lists any changes under "changes"."""
    value = "warning" if member == "kind" else [{"target": "a", "key": "b", "value": 1}]
    with pytest.raises(ValueError, match=rf"TST001: unknown members \['{member}'\]"):
        qe.Registry("x").add(record(**{member: value}))


# ---- Rule.to_feature ----------------------------------------------------------------
def assert_round_trip(rule):
    """from_feature(to_feature()) gives the rule back, and writing it again gives
    the same record. A Space compares by identity, so geometry is compared as a
    point set (the writer may add vertices along long edges)."""
    feature = rule.to_feature()
    again = qe.Rule.from_feature(json.loads(json.dumps(feature)))
    assert again.to_feature() == feature
    space, read = rule.scope.space, again.scope.space
    assert (space is None) == (read is None)
    if space is not None:
        assert shapely.equals(space.geometry, read.geometry)
        assert read.area_km2 == pytest.approx(space.area_km2, rel=1e-12)

    def spaceless(r):
        return dataclasses.replace(r, scope=dataclasses.replace(r.scope, space=None))

    assert spaceless(again) == spaceless(rule)
    return feature


def test_to_feature_round_trips_the_toy_records(tmp_path):
    rules = [qe.Rule.from_feature(f) for f in TOY_FEATURES]
    features = [assert_round_trip(rule) for rule in rules]
    path = write(tmp_path / "again.geojson", collection(features))
    assert toy_registry().load(path) == [rule.code for rule in rules]


def ring(*corners):
    return [list(c) for c in corners + corners[:1]]


EDGES = {
    "antimeridian polygon": {
        "geometry": {
            "type": "Polygon",
            "coordinates": [ring((170, 10), (-170, 10), (-170, 20), (170, 20))],
        }
    },
    "full-width box": {"box": {"west": -180, "width": 360, "south": 66.5, "north": 90}},
    "box wider than 180 degrees": {
        "box": {"west": -170, "width": 340, "south": -10, "north": 10}
    },
    "box across the antimeridian": {
        "box": {"west": 100, "width": 200, "south": -10, "north": 10}
    },
    "polygon with a hole": {
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                ring((0, 0), (10, 0), (10, 10), (0, 10)),
                ring((2, 2), (2, 4), (4, 4), (4, 2)),
            ],
        }
    },
    "pole cap": {
        "geometry": {
            "type": "Polygon",
            "coordinates": [ring((-180, 70), (180, 70), (180, 90), (-180, 90))],
        }
    },
    "recurrence and periods": {
        "time": {"interval": ["2000-01-01", "2010-12-31"]},
        "periods": [["2001-01-01", "2001-12-31"], ["2005-01-01", "2005-06-30"]],
        "recurrence": {"months": [12, 1, 2]},
    },
    "recurrence only": {"recurrence": {"months": [6]}},
    "open end": {"time": {"interval": ["2000-01-01", ".."]}},
    "open start": {"time": {"interval": ["..", "2009-12-31"]}},
    "periods with open ends": {
        "time": {"interval": ["..", ".."]},
        "periods": [["..", "2000-12-31"], ["2005-01-01", ".."]],
    },
    "timestamps": {
        "time": {"interval": ["2000-01-01T00:00:00Z", "2002-01-01T00:00:00Z"]},
        "periods": [
            ["2000-01-01T00:00:00Z", "2000-06-01T12:00:00Z"],
            ["2001-01-01T00:00:00Z", "2001-12-31T23:59:59Z"],
        ],
    },
    "time_start and time_end": {"time_start": "2000-01-01", "time_end": "2001-06-30"},
    "version ranges": {
        "dimensions": {
            "product": {"any_of": ["era5*"], "none_of": ["era5_land"]},
            "version": [{"introduced": "4.00", "fixed": "4.09"}, {"versions": ["X"]}],
        }
    },
    "non-default level": {
        "level": "error",
        "confidence": "likely",
        "status": "reviewed",
        "references": [{"title": "a made-up reference"}],
        "action": "do_not_use",
        "instruction": "Do not.",
        "min_overlap": 0.2,
    },
    "x_* extensions": {"x_note": {"a": [1, 2]}, "x_flag": True},
    "lifecycle": {
        "created": "2025-01-01",
        "withdrawn": "2026-01-01",
        "supersedes": ["TST002"],
        "aliases": ["OLD-1"],
        "evidence": [{"stations": 3}],
    },
    "changes with an axis and a plugin dimension": {
        "changes": [{"target": "a", "key": "b", "value": [1, None]}],
        "dimensions": {"resolution": {"lt": 10, "unit": "km"}, "basin": ["14"]},
    },
}


@pytest.mark.parametrize("name", list(EDGES))
def test_to_feature_round_trips(name):
    members = {k: v for k, v in EDGES[name].items() if k in ("geometry", "time")}
    props = {k: v for k, v in EDGES[name].items() if k not in members}
    rule = qe.Rule.from_feature({**record(**props), **members})
    feature = assert_round_trip(rule)
    if "box" in props:  # a box is written as its polygon
        assert "box" not in feature["properties"]
        box = props["box"]
        east = box["west"] + box["width"]
        expected = sp.box(box["west"], box["south"], east, box["north"])
        assert shapely.equals(rule.scope.space.geometry, expected.geometry)


def test_to_feature_leaves_out_defaults():
    feature = {
        **record(status="draft", level="warning", confidence="unknown", dimensions={}),
        "time": None,
    }
    assert qe.Rule.from_feature(feature).to_feature() == {
        "type": "Feature",
        "id": "TST001",
        "geometry": None,
        "time": None,
        "properties": {
            "code": "TST001",
            "title": "t",
            "message": "m",
        },
    }


@pytest.mark.parametrize(
    "level, changes, written",
    [
        ("warning", 0, None),
        ("info", 0, "info"),
        ("info", 1, None),
        ("warning", 1, "warning"),
        ("error", 2, "error"),
    ],
)
def test_to_feature_writes_a_level_other_than_the_default(level, changes, written):
    """The default is warning without changes and info with them."""
    listed = [
        {"target": "a", "key": f"k{i}", "value": i, "rationale": ""}
        for i in range(changes)
    ]
    rule = qe.Rule.from_feature(record(level=level, changes=listed))
    assert rule.changes == tuple(qe.Change(**c) for c in listed)
    feature = assert_round_trip(rule)
    assert feature["properties"].get("level") == written
    assert feature["properties"].get("changes", []) == listed


def test_to_feature_of_a_rule_built_in_python():
    rule = qe.Rule(
        code="PY001",
        title="t",
        message="m",
        level="info",
        scope=qe.Scope(
            space=sp.box(-60, -10, -50, 0),
            time=qe.interval("2000-01-01", "2000-12-31"),
            dimensions={"product": "cru_ts"},  # the shorthand for one pattern
        ),
    )
    feature = rule.to_feature()
    assert feature["properties"]["dimensions"] == {"product": "cru_ts"}  # as given
    assert feature["properties"]["level"] == "info"
    assert feature["time"] == {"interval": ["2000-01-01", "2000-12-31"]}
    registry = qe.Registry("x", dimensions=[qe.Labels("product")])
    registry.add(feature)
    found = registry.query(
        space=sp.point(-55, -5),
        time=("2000-06-01", "2000-06-30"),
        dimensions={"product": "cru_ts"},
    )
    assert [f.code for f in found] == ["PY001"]
    assert assert_round_trip(qe.Rule.from_feature(feature)) == feature


def test_to_feature_and_from_feature_round_trip_every_kind_of_dimension():
    dimensions = {
        "resolution": {"ge": 4, "lt": 10, "unit": "km"},
        "product": {"any_of": ["era5*"], "none_of": ["era5_land"]},
        "variable": ["t?s", "pre"],
        "version": [{"introduced": "4.00", "fixed": "4.09"}, {"versions": ["X"]}],
        "basin": ["14", "62"],
    }
    rule = qe.Rule(
        code="ALL001",
        title="t",
        message="m",
        scope=qe.Scope(dimensions=dimensions),
    )
    feature = assert_round_trip(rule)
    assert feature["properties"]["dimensions"] == dimensions
    registry = qe.Registry(
        "all",
        dimensions=[
            qe.Axis("resolution", "km"),
            qe.Labels("product"),
            qe.Labels("variable"),
            qe.Versions("version"),
            Pfafstetter(),
        ],
    )
    registry.add(feature)
    query = {
        "resolution": 8,
        "product": "era5",
        "variable": ("tas", "t2m"),
        "version": "4.07",
        "basin": "1423",
    }
    (found,) = registry.query(dimensions=query)
    assert {name: m.fraction for name, m in found.dimensions.items()} == {
        "resolution": 1.0,
        "product": 1.0,
        "variable": 0.5,
        "version": 1.0,
        "basin": 1.0,
    }
    assert registry.query(dimensions={**query, "product": "era5_land"}) == []


def test_to_feature_refuses_what_a_record_cannot_hold():
    point = qe.Scope(space=sp.point(0, 0))
    rule = qe.Rule(code="PY002", title="t", message="m", scope=point)
    with pytest.raises(ValueError, match="PY002: a record's space is a polygon"):
        rule.to_feature()
    rule = qe.Rule(code="PY003", title="t", message="m", level=50)
    with pytest.raises(ValueError, match="PY003: a record's level is info"):
        rule.to_feature()
