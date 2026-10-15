"""Describing a Registry and reading files that declare their dimensions."""

import json
from pathlib import Path

import pytest

import queryearth as qe
from queryearth.dimensions import describe_dimension, dimension_from

TOY = Path(__file__).resolve().parents[1] / "examples" / "toy" / "rules.geojson"
TOY_DATA = json.loads(TOY.read_text())


def write(path, data):
    path.write_text(json.dumps(data))
    return path


def record(code, **props):
    base = {"code": code, "title": f"{code} title", "message": "m"}
    return {"type": "Feature", "geometry": None, "properties": {**base, **props}}


# ---- plain dimension descriptions ---------------------------------------------------
@pytest.mark.parametrize(
    "dimension, described",
    [
        (
            qe.Axis("resolution", "km"),
            {"name": "resolution", "kind": "axis", "unit": "km"},
        ),
        (
            qe.Axis("depth", "m", "water depth"),
            {
                "name": "depth",
                "kind": "axis",
                "unit": "m",
                "description": "water depth",
            },
        ),
        (qe.Labels("product"), {"name": "product", "kind": "labels"}),
        (qe.Versions("version"), {"name": "version", "kind": "versions"}),
    ],
)
def test_a_dimension_round_trips_through_its_plain_form(dimension, described):
    assert describe_dimension(dimension) == described
    assert dimension_from(described) == dimension


@pytest.mark.parametrize(
    "described",
    [
        {"name": "resolution", "kind": "axis"},  # an axis needs a unit
        {"name": "product", "kind": "labels", "unit": "km"},  # only an axis has one
        {"name": "basin", "kind": "pfafstetter"},  # plugins are declared in Python
        {"name": "product", "kind": "labels", "values": ["era5"]},
        ["product", "labels"],
    ],
)
def test_bad_plain_forms_are_refused(described):
    with pytest.raises(ValueError):
        dimension_from(described)


# ---- files that declare their dimensions ----------------------------------------------
def test_from_file_makes_a_registry_for_the_file():
    registry = qe.Registry.from_file(TOY)
    assert registry.name == "rules"
    codes = [r["code"] for r in registry.describe()["rules"]]
    assert codes == [f["properties"]["code"] for f in TOY_DATA["features"]]
    (found,) = registry.query(dimensions={"resolution": 60.0})
    assert found.code == "TOY103"


def test_from_file_says_how_to_declare_missing_dimensions(tmp_path):
    bare = {k: v for k, v in TOY_DATA.items() if k != "dimensions"}
    with pytest.raises(qe.LoadError) as err:
        qe.Registry.from_file(write(tmp_path / "bare.geojson", bare))
    assert err.value.problems[-1] == (
        'bare.geojson: declare the dimensions the rules use in the file\'s "dimensions" member'
    )


def test_from_file_refuses_bad_declarations(tmp_path):
    data = {**TOY_DATA, "dimensions": [{"name": "resolution", "kind": "axis"}]}
    with pytest.raises(qe.LoadError, match="dimensions: "):
        qe.Registry.from_file(write(tmp_path / "bad.geojson", data))


def test_a_file_must_declare_dimensions_as_the_registry_does(tmp_path):
    registry = qe.Registry("mine", dimensions=[qe.Axis("resolution", "km")])
    data = {
        "type": "FeatureCollection",
        "dimensions": [
            {"name": "resolution", "kind": "axis", "unit": "deg"},
            {"name": "product", "kind": "labels"},
        ],
        "features": [record("TST001")],
    }
    with pytest.raises(qe.LoadError) as err:
        registry.load(write(tmp_path / "other.geojson", data))
    assert err.value.problems == (
        "other.geojson: the file declares {'name': 'resolution', 'kind': 'axis', "
        "'unit': 'deg'}, registry 'mine' has {'name': 'resolution', 'kind': 'axis', "
        "'unit': 'km'}",
        "other.geojson: dimension 'product' is not declared on registry 'mine'",
    )
    assert registry.describe()["rules"] == []  # nothing was added
    data["dimensions"] = [
        {"name": "resolution", "kind": "axis", "unit": "km", "description": "x"}
    ]
    assert registry.load(write(tmp_path / "same.geojson", data)) == ["TST001"]


# ---- values and describe ----------------------------------------------------------------
def describe_registry():
    registry = qe.Registry(
        "described",
        dimensions=[
            qe.Axis("resolution", "km"),
            qe.Labels("product"),
            qe.Versions("version"),
        ],
    )
    registry.add(record("TST001", dimensions={"product": ["glorys", "era5*"]}))
    registry.add(
        record("TST002", dimensions={"product": "glorys", "resolution": {"lt": 8}})
    )
    registry.add(
        record(
            "TST003",
            dimensions={
                "product": {"any_of": ["era5"], "none_of": ["era5t"]},
                "resolution": [{"lt": 5}, {"gt": 50}],
            },
        )
    )

    @registry.rule("TST004", dimensions={"version": {"introduced": "4.00"}})
    def computed(query, match):
        """A computed rule"""
        return True

    return registry


def test_values_lists_what_the_rules_give_one_alternative_at_a_time():
    registry = describe_registry()
    assert registry.values("product") == [
        "glorys",
        "era5*",
        {"any_of": ["era5"], "none_of": ["era5t"]},
    ]
    assert registry.values("resolution") == [{"lt": 8}, {"lt": 5}, {"gt": 50}]
    assert registry.values("version") == [{"introduced": "4.00"}]
    with pytest.raises(qe.UnknownNameError):
        registry.values("variable")


def test_describe_is_json_ready_and_lists_dimensions_values_and_rules():
    described = describe_registry().describe()
    assert json.loads(json.dumps(described)) == described
    assert described["dimensions"] == [
        {"name": "resolution", "kind": "axis", "unit": "km"},
        {"name": "product", "kind": "labels"},
        {"name": "version", "kind": "versions"},
    ]
    assert described["values"]["resolution"] == [{"lt": 8}, {"lt": 5}, {"gt": 50}]
    assert described["rules"][0] == {
        "code": "TST001",
        "title": "TST001 title",
        "level": "warning",
        "category": None,
        "computed": False,
    }
    assert described["rules"][-1]["code"] == "TST004"
    assert described["rules"][-1]["computed"] is True


def test_describe_gives_a_file_its_dimensions_member():
    assert qe.Registry.from_file(TOY).describe()["dimensions"] == TOY_DATA["dimensions"]
