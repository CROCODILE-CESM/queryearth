"""Packs and records: the example pack and its four queries, loader checks, the
record parts of fixtures 17 and 27 of docs/reference/fixtures.md, and the
agreement between the loader and docs/reference/schema.json.
"""

import copy
import json
import logging
import shutil
from pathlib import Path

import numpy as np
import pytest

import queryearth as qe
from queryearth import space as sp

EXAMPLES = Path(__file__).resolve().parents[1] / "docs" / "reference" / "examples"
RULES = json.loads((EXAMPLES / "rules.geojson").read_text())
# Stand-ins for the region files the example pack names but does not include:
# boxes roughly where the IPCC AR6 African land regions and the Caspian Sea lie.
AR6 = {
    "SAH": (-20, 15, 35, 32),
    "WAF": (-20, 0, 15, 15),
    "CAF": (15, -10, 30, 15),
    "NEAF": (30, 5, 52, 15),
    "SEAF": (30, -10, 45, 5),
    "WSAF": (10, -35, 25, -10),
    "ESAF": (25, -35, 40, -10),
    "MDG": (43, -26, 51, -12),
}
NE = {"caspian_sea": (46, 36, 55, 47)}
KARIBA = sp.polygon([(26.7, -18.0), (26.9, -18.1), (29.0, -16.6), (28.8, -16.5)])
Y2013_2022 = qe.interval("2013-01-01", "2022-12-31")
CRU = {"product": "cru_ts", "variable": "pre", "version": "4.07"}


def boxes(regions, key):
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {key: name},
                "geometry": sp.box(*bounds).geometry.__geo_interface__,
            }
            for name, bounds in regions.items()
        ],
    }


def example_pack(tmp_path):
    """The example pack, with the two region files it names."""
    for name in ("pack.toml", "rules.geojson"):
        shutil.copy(EXAMPLES / name, tmp_path / name)
    (tmp_path / "regions").mkdir()
    (tmp_path / "regions" / "ar6_land.geojson").write_text(
        json.dumps(boxes(AR6, "abbrev"))
    )
    (tmp_path / "regions" / "ne_lakes.geojson").write_text(
        json.dumps(boxes(NE, "slug"))
    )
    return tmp_path


def example_registry(tmp_path):
    """The Registry of examples/README.md, with the simple CRU002 of usage.py."""
    registry = qe.Registry(
        "examples",
        axes=[
            qe.Axis("resolution", "km", "horizontal grid spacing"),
            qe.Axis("altitude_agl", "m", "height above ground level"),
        ],
        facets=qe.Registry.FACETS + ("activity", "basis_of_record"),
    )
    codes = registry.load_pack(example_pack(tmp_path))
    world = [(-180, -90), (180, -90), (180, 90), (-180, 90)]
    conus = [(-125, 24), (-66, 24), (-66, 50), (-125, 50)]
    registry.add(
        qe.Rule(
            code="NWM001",
            kind="warning",
            title="Outside the NWM retrospective lakes",
            message="Lake output covers 5,782 lakes in the contiguous United States.",
            level="error",
            action="do_not_use",
            scope=qe.Scope(
                space=sp.polygon({"type": "Polygon", "coordinates": [world, conus]}),
                facets={"product": ["nwm_retro"]},
            ),
        )
    )

    @registry.rule(
        "CROC104",
        kind="suggestion",
        space=sp.box(-180, 66.5, 180, 90),
        facets={"model": "mom6"},
        axes={"resolution": {"gt": 0.0}},
    )
    def arctic_time_step(query, match):
        """High-latitude domain: set the time step from the smallest cells"""
        seconds = 30.0 * match.axes["resolution"].lo
        why = "Set DT from the finest cells (illustrative scaling, not MOM6 guidance)."
        return {"suggestions": (qe.Suggestion("MOM_input", "DT", seconds, why),)}

    @registry.rule(
        "GEN001",
        kind="warning",
        level=logging.INFO,
        facets={"product": ["*"]},
        requires=["request_km2"],
    )
    def coarse_support(query, match):
        """The request is much smaller than the product cells that represent it"""
        if query.space is None or not query.space.area_km2:
            return None
        ratio = query.context["request_km2"] / query.space.area_km2
        return {"details": {"request_to_support": ratio}} if ratio < 0.1 else None

    class CruStations(
        qe.ComputedRule,
        code="CRU002",
        registry=registry,
        facets={"product": "cru_ts", "variable": "pre"},
        requires=["cru_ts.stn"],
    ):
        """CRU TS value from few or no stations"""

        def check(self, query, match):
            stn = query.context["cru_ts.stn"]
            zero = float((stn == 0).mean())
            if zero > 0:
                return {"level": logging.ERROR, "details": {"stn0_fraction": zero}}
            return float(stn.mean()) <= 2

    return registry, codes


def by_code(findings):
    return {f.code: f for f in findings}


# ---- the example pack -------------------------------------------------------------
def test_example_pack_loads(tmp_path):
    registry, codes = example_registry(tmp_path)
    assert codes == [f["properties"]["code"] for f in RULES["features"]]
    assert len(codes) == 14 and registry._packs["examples"][0] == "BIO"
    rules = {e.rule.code: e.rule for e in registry._entries}
    assert rules["ERA5-024"].scope.time.months == frozenset({12, 1, 2})
    assert rules["EPI001"].scope.time.to_wire() == (
        ("2021-02-01", "2021-03-31"),
        ("2021-09-01", "2021-10-31"),
    )
    assert "x_scope_note" in rules["ERA5-014"].extensions
    (nwm001,) = registry.query(space=KARIBA, facets={"product": "nwm_retro"})
    assert nwm001.code == "NWM001" and nwm001.area_fraction == 1.0
    with pytest.raises(qe.LoadError, match="already loaded"):
        registry.load_pack(tmp_path)


def test_example_query_1_lake_kariba(tmp_path):
    registry, _ = example_registry(tmp_path)
    stn = np.array([[0, 3], [2, 4]])
    found = registry.query(
        space=KARIBA,
        time=Y2013_2022,
        facets=CRU,
        context={"cru_ts.stn": stn, "request_km2": KARIBA.area_km2},
        label="Kariba",
    )
    codes = [f.code for f in found]
    assert codes[:2] == ["CRU002", "CRU001"] and set(codes) <= {
        "CRU002",
        "CRU001",
        "GEN001",
    }
    cru002, cru001 = found[:2]
    assert cru002.level == logging.ERROR and cru002.details["stn0_fraction"]
    assert cru001.source == "examples"
    assert cru001.area_fraction == 1.0 and cru001.time_fraction == 1.0
    assert cru001.time_overlap == (("2013-01-01", "2022-12-31"),)
    hidden = registry.query(
        space=KARIBA, time=Y2013_2022, facets=CRU, include_conditional=True
    )
    assert by_code(hidden)["CROC102"].conditional_on == ("resolution",)


def test_example_query_2_arctic_mom6_domain(tmp_path):
    registry, _ = example_registry(tmp_path)
    domain = sp.box(-180, 70.6, 180, 90)  # an Arctic cap, closed along the pole
    q2 = {
        product: registry.query(
            space=domain,
            time=qe.interval("2020-01-01", "2020-12-31"),
            axes={"resolution": (8.0, 12.0)},
            facets={"model": "mom6", "product": product, "variable": variables},
            label="arctic-demo",
            include_conditional=True,
        )
        for product, variables in [
            ("glorys", ("thetao", "so")),
            ("era5", ("t2m", "skt")),
        ]
    }
    base = ["GEN001", "CROC101", "CROC102", "CROC104"]
    assert [f.code for f in q2["glorys"]] == base
    assert [f.code for f in q2["era5"]] == ["ERA5-024"] + base
    found = by_code(q2["era5"])
    assert found["CROC101"].area_fraction == 1.0
    assert [s.value for s in found["CROC101"].suggestions] == ["CICE", "EPSG:3995"]
    assert found["CROC104"].suggestions[0].value == 240.0
    assert found["CROC102"].axes["resolution"] == qe.AxisOverlap(8, 10, True, False)
    era5_024 = found["ERA5-024"]
    assert era5_024.area_fraction == 1.0 and era5_024.time_overlap == (
        ("2020-01-01", "2020-02-29"),
        ("2020-12-01", "2020-12-31"),
    )
    assert era5_024.matched_facets == {"product": ("era5",), "variable": ("skt",)}
    assert found["GEN001"].conditional_on == ("context:request_km2",)


def test_example_query_3_resolution_only(tmp_path):
    registry, _ = example_registry(tmp_path)
    found = registry.query(axes={"resolution": 8.0}, include_conditional=True)
    table = {f.code: f.conditional_on for f in found}
    space_time = ("space", "time")
    assert table == {
        "CROC102": (),
        "CROC101": ("space", "model"),
        "CROC104": ("space", "model"),
        "ERA5-001": ("time", "product", "version"),
        "GLORYS001": ("time", "product", "variable"),
        "CRU001": space_time + ("product", "variable", "version"),
        "CRU004": space_time + ("product", "variable", "version"),
        "ERA5-014": space_time + ("product", "variable"),
        "ERA5-023": space_time + ("product", "variable"),
        "ERA5-024": space_time + ("product", "variable"),
        "EPI001": space_time + ("product", "variable"),
        "BIO001": space_time + ("product", "basis_of_record"),
        "UAS001": space_time + ("altitude_agl", "activity"),
        "CRU002": ("product", "variable", "context:cru_ts.stn"),
        "GEN001": ("product", "context:request_km2"),
        "NWM001": ("space", "product"),
    }
    assert by_code(found)["CROC102"].axes["resolution"] == qe.AxisOverlap(8, 8)


def test_example_query_4_bulk(tmp_path):
    registry, _ = example_registry(tmp_path)
    glon, glat = np.meshgrid(np.arange(-179.75, 180, 0.5), np.arange(-89.75, 90, 0.5))
    lon, lat = glon.ravel(), glat.ravel()
    q4 = registry.query_points(
        lon,
        lat,
        weights=np.cos(np.radians(lat)),
        time=("1901-01-01", "2022-12-31"),
        facets=CRU,
    )
    assert set(q4.masks) == {"CRU001", "CRU004"}
    assert set(q4.skipped) == {"CRU002", "GEN001"}
    found = by_code(q4.findings)
    assert found["CRU004"].time_overlap == (("2010-01-01", "2022-12-31"),)
    assert found["CRU001"].time_overlap == (("2000-01-01", "2022-12-31"),)
    assert q4.masks["CRU004"].sum() == 858
    assert found["CRU001"].area_fraction == q4.fractions["CRU001"] < 0.1
    weak = q4.any(logging.WARNING)
    union = q4.masks["CRU001"] | q4.masks["CRU004"]
    assert (weak == union).all() and weak.shape == lon.shape


# ---- loader checks (section 5.3) ----------------------------------------------------
def record(code="TST001", **props):
    base = {"code": code, "kind": "warning", "title": "t", "message": "m"}
    return {"type": "Feature", "geometry": None, "properties": {**base, **props}}


def write_pack(tmp_path, features, toml="", prefix='["TST"]', name="test"):
    (tmp_path / "pack.toml").write_text(
        f'[pack]\nname = "{name}"\nversion = "1"\ncode_prefix = {prefix}\n'
        f'files = ["rules.geojson"]\n{toml}'
    )
    collection = {"type": "FeatureCollection", "features": features}
    (tmp_path / "rules.geojson").write_text(json.dumps(collection))
    return tmp_path


def test_loader_reports_every_problem_and_leaves_the_registry_unchanged(tmp_path):
    registry = qe.Registry("x", axes=[qe.Axis("resolution", "km")])
    registry.add(qe.Rule(code="OLD001", kind="warning", title="t", message="m"))
    features = [
        record("TST001"),
        record("TST002", facets={"colour": ["red"]}),
        record("OTH003"),
        record("TST004", axes={"resolution": {"lt": 10, "unit": "deg"}}),  # 17
        record("TST001"),
        record("TST006", region_ref="ar6:CAF"),
    ]
    with pytest.raises(qe.LoadError) as err:
        registry.load_pack(write_pack(tmp_path, features))
    problems = err.value.problems
    assert [p.split(":")[0] for p in problems] == ["rules.geojson"] * 5
    assert problems[0].startswith("rules.geojson: feature 1 (TST002): ")
    assert "undeclared dimension 'colour'" in problems[0]
    assert "feature 2 (OTH003): prefix 'OTH' is not one the pack owns" in problems[1]
    assert "feature 3 (TST004): " in problems[2] and "'deg'" in problems[2]
    assert "feature 4 (TST001): " in problems[3] and "already" in problems[3]
    assert "undeclared regions ['ar6:CAF']" in problems[4]
    assert [e.rule.code for e in registry._entries] == ["OLD001"]
    assert registry.query() and not registry._packs


def test_pack_toml_must_agree_with_the_registry(tmp_path):
    toml = '[axes.resolution]\nunit = "deg"\n[facets]\nnames = ["model", "colour"]\n'
    toml += '[dimensions]\nnames = ["basin"]\n[products.cru_ts]\nversion = "4.07"\n'
    registry = qe.Registry("x", axes=[qe.Axis("resolution", "km")])
    with pytest.raises(qe.LoadError) as err:
        registry.load_pack(write_pack(tmp_path, [record()], toml))
    text = "\n".join(err.value.problems)
    for expected in ("['products']", "'km', not 'deg'", "'colour'", "'basin'"):
        assert expected in text


def test_prefixes_are_exclusive_between_packs(tmp_path):
    registry = qe.Registry("x")
    first, second = tmp_path / "a", tmp_path / "b"
    first.mkdir()
    second.mkdir()
    assert registry.load_pack(write_pack(first, [record()])) == ["TST001"]
    with pytest.raises(qe.LoadError, match="claimed by pack 'test'"):
        registry.load_pack(write_pack(second, [record("TST002")], name="other"))
    write_pack(second, [record("OTH002")], "", '"OTH"', "other")
    assert registry.load_pack(second) == ["OTH002"]
    registry.add(
        qe.Rule(code="TST009", kind="warning", title="t", message="m")
    )  # Python


def test_collection_header_must_agree_with_pack_toml(tmp_path):
    write_pack(tmp_path, [record()])
    collection = json.loads((tmp_path / "rules.geojson").read_text())
    collection["metadata"] = {"pack": "test", "version": "2", "code_prefix": "TST"}
    (tmp_path / "rules.geojson").write_text(json.dumps(collection))
    with pytest.raises(qe.LoadError, match="metadata disagrees"):
        qe.Registry("x").load_pack(tmp_path)
    collection["metadata"]["version"] = "1"
    (tmp_path / "rules.geojson").write_text(json.dumps(collection))
    assert qe.Registry("x").load_pack(tmp_path) == ["TST001"]


def test_add_takes_a_feature_or_a_whole_feature_collection():
    registry = qe.Registry("x")
    registry.add(
        record("TST001", box={"west": 170, "width": 20, "south": -20, "north": -10})
    )
    (found,) = registry.query(space=sp.point(-175, -15))
    assert found.code == "TST001" and found.source == "python"
    collection = {"type": "FeatureCollection", "features": [record("TST002"), {}]}
    with pytest.raises(qe.LoadError, match=r"collection: feature 1 \(None\)"):
        registry.add(collection)
    assert [e.rule.code for e in registry._entries] == ["TST001"]
    collection["features"].pop()
    registry.add(collection)
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
    registry = qe.Registry("x", axes=[qe.Axis("resolution", "km")])
    with pytest.raises(ValueError, match="TST001: resolution: unit 'deg'"):
        registry.add(record(axes={"resolution": {"lt": 10, "unit": "deg"}}))
    registry.add(record("TST002", axes={"resolution": {"lt": 10, "unit": "km"}}))


class Pfafstetter:
    """The basin dimension of section 4.13."""

    name = "basin"
    schema = {"type": "array", "items": {"type": "string", "pattern": "^[1-9]+$"}}

    def parse_rule(self, value):
        return tuple(str(v) for v in value)

    def parse_query(self, value):
        return str(value)

    def match(self, rule, query):
        hits = [b for b in rule if query.startswith(b) or b.startswith(query)]
        inside = any(query.startswith(b) for b in hits)
        return qe.DimMatch(tuple(hits), 1.0 if inside else None) if hits else None


def test_fixture_27_plugin_values_in_records_pass_the_plugin_schema():
    registry = qe.Registry("glhe", dimensions=[Pfafstetter()])
    with pytest.raises(ValueError, match="TST001: dimension 'basin'"):
        registry.add(record(dimensions={"basin": "14"}))  # a string, not a list
    with pytest.raises(ValueError, match="does not match"):
        registry.add(record(dimensions={"basin": ["14", "0"]}))
    with pytest.raises(qe.UnknownNameError, match="basins"):
        registry.add(record(dimensions={"basins": ["14"]}))
    registry.add(record(dimensions={"basin": ["14", "62"]}))
    (found,) = registry.query(dims={"basin": "1423"})
    assert found.dims == {"basin": qe.DimMatch(("14",), 1.0)}


# ---- the loader agrees with schema.json ----------------------------------------------
BAD = {
    "suggestion without suggestions": {"kind": "suggestion"},
    "unknown property": {"colour": "red"},
    "level not info, warning or error": {"level": "critical"},
    "reviewed without references": {"status": "reviewed"},
    "box and region_ref": {
        "box": {"west": 0, "width": 1, "south": 0, "north": 1},
        "region_ref": "ar6:CAF",
    },
    "box west out of range": {"box": {"west": 180, "width": 1, "south": 0, "north": 1}},
    "fixed and last_affected": {
        "facets": {"version": {"fixed": "2", "last_affected": "1"}}
    },
    "facet as a bare string": {"facets": {"variable": "pre"}},
    "axis with lt and le": {"axes": {"resolution": {"lt": 1, "le": 2}}},
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


def schema_validator():
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads((EXAMPLES.parent / "schema.json").read_text())
    return jsonschema.Draft202012Validator(schema)


def bad_features():
    for name, props in BAD.items():
        yield name, record(**props)
    yield from BAD_FEATURES.items()


def test_loader_and_schema_accept_the_example_records(tmp_path):
    validator = schema_validator()
    assert validator.is_valid(RULES)
    for feature in RULES["features"]:
        assert validator.is_valid(feature), feature["properties"]["code"]
    registry, codes = example_registry(tmp_path)  # the loader accepts them as well
    assert len(codes) == 14


@pytest.mark.parametrize("name", [name for name, _ in bad_features()])
def test_loader_and_schema_reject_broken_records(tmp_path, name):
    feature = dict(bad_features())[name]
    assert not schema_validator().is_valid(feature)
    registry = qe.Registry("x", axes=[qe.Axis("resolution", "km")])
    registry.add_regions("ar6", {"CAF": sp.box(15, -10, 30, 15)})
    with pytest.raises((ValueError, KeyError, TypeError)):
        registry.add(copy.deepcopy(feature))
