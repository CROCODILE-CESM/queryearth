"""Packs and records: the example pack and its five queries, loader checks, the
record parts of fixtures 3, 15, 17 and 27 of docs/reference/fixtures.md, and the
agreement between the loader and docs/reference/schema.json.
"""

import copy
import json
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


def example_index(tmp_path):
    """The Index of examples/README.md, with the simple CRU002 of usage.py."""
    index = qe.Index(
        "examples",
        axes=[
            qe.Axis("resolution", "km", "horizontal grid spacing"),
            qe.Axis("altitude_agl", "m", "height above ground level"),
        ],
        facets=qe.Index.FACETS + ("activity", "basis_of_record"),
    )
    codes = index.load_pack(example_pack(tmp_path))
    index.add_product(
        qe.Product(
            name="nwm_retro",
            aliases=("NWM", "NWM v3.0"),
            variables=("inflow", "outflow", "water_sfc_elev"),
            coverage=qe.Coverage(
                space=sp.features([101, 102, 103], "hydrolakes"),
                time=qe.interval("1979-02-01", "2023-01-31"),
            ),
            resolution=(1.0, "km"),
            version="3.0",
        )
    )

    @index.rule(
        "CROC104",
        kind="recommendation",
        severity=qe.Severity.INFO,
        space=sp.lat_band(66.5, 90.0),
        facets={"model": "mom6"},
        axes={"resolution": {"gt": 0.0}},
    )
    def arctic_time_step(query, match):
        """High-latitude domain: set the time step from the smallest cells"""
        seconds = 30.0 * match.axes["resolution"].lo
        why = "Set DT from the finest cells (illustrative scaling, not MOM6 guidance)."
        return {"suggestions": (qe.Suggestion("MOM_input", "DT", seconds, why),)}

    @index.rule(
        "GEN001",
        kind="caveat",
        severity=qe.Severity.INFO,
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
        index=index,
        facets={"product": "cru_ts", "variable": "pre"},
        requires=["cru_ts.stn"],
    ):
        """CRU TS value from few or no stations"""

        def check(self, query, match):
            stn = query.context["cru_ts.stn"]
            zero = float((stn == 0).mean())
            if zero > 0:
                return {"severity": "severe", "details": {"stn0_fraction": zero}}
            return float(stn.mean()) <= 2

    return index, codes


def by_code(findings):
    return {f.code: f for f in findings}


# ---- the example pack -------------------------------------------------------------
def test_example_pack_loads(tmp_path):
    index, codes = example_index(tmp_path)
    assert codes == [f["properties"]["code"] for f in RULES["features"]]
    assert len(codes) == 14 and index._packs["examples"][0] == "BIO"
    cru = index.products["cru_ts"]
    assert cru.resolution == (0.5, "deg") and cru.calendar == "standard"
    assert len(cru.grid[0]) == 721 and len(cru.grid[1]) == 361
    assert cru.coverage.time.to_wire() == (("1901-01-01", "2022-12-31"),)
    assert index.products["era5"].coverage.time.to_wire() == (("1940-01-01", ".."),)
    ili = index.products["demo_ili"].coverage.space  # a box across the antimeridian
    assert ili.geometry.bounds == (-180.0, -25.0, 180.0, -10.0)
    rules = {e.rule.code: e.rule for e in index._entries}
    assert rules["ERA5-024"].scope.time.months == frozenset({12, 1, 2})
    assert rules["EPI001"].scope.time.to_wire() == (
        ("2021-02-01", "2021-03-31"),
        ("2021-09-01", "2021-10-31"),
    )
    assert "x_scope_note" in rules["ERA5-014"].extensions
    assert index.rule_counts()["cru_ts"] == 4  # CRU001, CRU004, CRU002 and GEN001
    with pytest.raises(qe.LoadError, match="already loaded"):
        index.load_pack(tmp_path)


def test_example_query_1_lake_kariba(tmp_path):
    index, _ = example_index(tmp_path)
    stn = np.array([[0, 3], [2, 4]])
    found = index.query(
        space=KARIBA,
        time=Y2013_2022,
        requests=[qe.Request("CRUTS", variables=("pre",))],
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
    assert cru002.severity is qe.Severity.SEVERE and cru002.details["stn0_fraction"]
    assert cru001.assumed == ("space", "version") and cru001.source == "examples"
    assert cru001.area_fraction == 1.0 and cru001.time_fraction == 1.0
    assert cru001.time_overlap == (("2013-01-01", "2022-12-31"),)
    assert all(f.product == "cru_ts" and f.request == 0 for f in found)
    hidden = index.query(
        space=KARIBA,
        time=Y2013_2022,
        requests=[qe.Request("CRUTS", variables=("pre",))],
        include_conditional=True,
    )
    croc102 = by_code(hidden)["CROC102"]
    assert croc102.conditional_on == ("resolution",) and croc102.request is None


def polar_square(half_km=1500.0, n=41):
    """Cell corners of a square in a spherical Arctic polar stereographic grid."""
    k0 = (1.0 + np.sin(np.radians(71.0))) / 2.0  # true scale at 71N
    x, y = np.meshgrid(*[np.linspace(-half_km, half_km, n)] * 2)
    rho = np.hypot(x, y) / (2.0 * sp.R_KM * k0)
    return np.degrees(np.arctan2(x, -y)), 90.0 - 2.0 * np.degrees(np.arctan(rho))


def test_example_query_2_arctic_mom6_domain(tmp_path):
    index, _ = example_index(tmp_path)
    ring = sp.from_grid(*polar_square())
    found = index.query(
        space=ring,
        time=qe.interval("2020-01-01", "2020-12-31"),
        axes={"resolution": (8.0, 12.0)},
        facets={"model": "mom6"},
        requests=[
            qe.Request("glorys", variables=("thetao", "so")),
            qe.Request("era5", variables=("t2m", "skt")),
        ],
        label="arctic-demo",
        include_conditional=True,
    )
    assert [(f.code, f.request) for f in found] == [
        ("ERA5-024", 1),
        ("GEN001", 0),
        ("GEN001", 1),
        ("CROC101", None),
        ("CROC102", None),
        ("CROC104", None),
    ]
    found = by_code(found)
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
    index, _ = example_index(tmp_path)
    found = index.query(axes={"resolution": 8.0}, include_conditional=True)
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
    }
    assert by_code(found)["CROC102"].axes["resolution"] == qe.AxisOverlap(8, 8)


def test_example_query_4_bulk(tmp_path):
    index, _ = example_index(tmp_path)
    glon, glat = np.meshgrid(np.arange(-179.75, 180, 0.5), np.arange(-89.75, 90, 0.5))
    lon, lat = glon.ravel(), glat.ravel()
    cru = {"product": "CRUTS", "variable": "pre"}
    q4 = index.query_points(lon, lat, weights=np.cos(np.radians(lat)), facets=cru)
    assert set(q4.masks) == {("cru_ts", "CRU001"), ("cru_ts", "CRU004")}
    assert set(q4.skipped) == {("cru_ts", "CRU002"), ("cru_ts", "GEN001")}
    found = by_code(q4.findings)
    assert found["CRU004"].assumed == ("time", "version")
    assert found["CRU004"].time_overlap == (("2010-01-01", "2022-12-31"),)
    assert found["CRU001"].time_overlap == (("2000-01-01", "2022-12-31"),)
    assert q4.masks[("cru_ts", "CRU004")].sum() == 858
    assert found["CRU001"].area_fraction == q4.fractions[("cru_ts", "CRU001")] < 0.1
    weak = q4.any(qe.Severity.WARNING)
    union = q4.masks[("cru_ts", "CRU001")] | q4.masks[("cru_ts", "CRU004")]
    assert (weak == union).all() and weak.shape == lon.shape


def test_example_query_5_suitable(tmp_path):
    index, _ = example_index(tmp_path)
    stn = np.array([[0, 3], [2, 4]])
    ranked = index.suitable(
        qe.Query(space=KARIBA, time=Y2013_2022, context={"cru_ts.stn": stn}),
        variable="pre",
    )
    assert [s.product.name for s in ranked] == ["era5", "cru_ts"]
    assert ranked[0].score == (0.0, 0.0, 0.0) and ranked[0].findings == ()
    assert ranked[1].score[0] == 40.0
    assert [f.code for f in ranked[1].findings] == ["CRU002", "CRU001"]


# ---- loader checks (section 5.3) ----------------------------------------------------
def record(code="TST001", **props):
    base = {"code": code, "kind": "caveat", "title": "t", "message": "m"}
    base["severity"] = "warning"
    return {"type": "Feature", "geometry": None, "properties": {**base, **props}}


def write_pack(tmp_path, features, toml="", prefix='["TST"]', name="test"):
    (tmp_path / "pack.toml").write_text(
        f'[pack]\nname = "{name}"\nversion = "1"\ncode_prefix = {prefix}\n'
        f'files = ["rules.geojson"]\n{toml}'
    )
    collection = {"type": "FeatureCollection", "features": features}
    (tmp_path / "rules.geojson").write_text(json.dumps(collection))
    return tmp_path


def test_loader_reports_every_problem_and_leaves_the_index_unchanged(tmp_path):
    index = qe.Index("x", axes=[qe.Axis("resolution", "km")])
    index.add(qe.Rule(code="OLD001", kind="caveat", title="t", message="m"))
    features = [
        record("TST001"),
        record("TST002", facets={"product": ["nope"]}),
        record("OTH003"),
        record("TST004", axes={"resolution": {"lt": 10, "unit": "deg"}}),  # 17
        record("TST001"),
        record("TST006", region_ref="ar6:CAF"),
    ]
    with pytest.raises(qe.LoadError) as err:
        index.load_pack(write_pack(tmp_path, features))
    problems = err.value.problems
    assert [p.split(":")[0] for p in problems] == ["rules.geojson"] * 5
    assert problems[0].startswith("rules.geojson: feature 1 (TST002): ")
    assert "unknown product 'nope'" in problems[0]
    assert "feature 2 (OTH003): prefix 'OTH' is not one the pack owns" in problems[1]
    assert "feature 3 (TST004): " in problems[2] and "'deg'" in problems[2]
    assert "feature 4 (TST001): " in problems[3] and "already" in problems[3]
    assert "undeclared regions ['ar6:CAF']" in problems[4]
    assert [e.rule.code for e in index._entries] == ["OLD001"]
    assert index.query() and not index._packs


def test_pack_toml_must_agree_with_the_index(tmp_path):
    toml = '[axes.resolution]\nunit = "deg"\n[facets]\nnames = ["model", "colour"]\n'
    toml += '[dimensions]\nnames = ["basin"]\n'
    index = qe.Index("x", axes=[qe.Axis("resolution", "km")])
    with pytest.raises(qe.LoadError) as err:
        index.load_pack(write_pack(tmp_path, [record()], toml, '["TST", "QE"]'))
    text = "\n".join(err.value.problems)
    for expected in ("reserved", "'km', not 'deg'", "'colour'", "'basin'"):
        assert expected in text


def test_prefixes_are_exclusive_between_packs_and_product_names_are_global(
    tmp_path,
):
    index = qe.Index("x")
    first, second = tmp_path / "a", tmp_path / "b"
    first.mkdir()
    second.mkdir()
    product = '[products.cru_ts]\naliases = ["CRUTS"]\nversion = "4.07"\n'
    assert index.load_pack(write_pack(first, [record()], product)) == ["TST001"]
    with pytest.raises(qe.LoadError, match="claimed by pack 'test'"):
        index.load_pack(write_pack(second, [record("TST002")], name="other"))
    write_pack(second, [record("OTH002")], product, '"OTH"', "other")
    with pytest.raises(qe.LoadError, match="already name a declared product"):
        index.load_pack(second)
    write_pack(second, [record("OTH002")], "", '"OTH"', "other")
    assert index.load_pack(second) == ["OTH002"]
    assert index.products["cru_ts"].aliases == ("CRUTS",)
    index.add(qe.Rule(code="TST009", kind="caveat", title="t", message="m"))  # Python


def test_collection_header_must_agree_with_pack_toml(tmp_path):
    write_pack(tmp_path, [record()])
    collection = json.loads((tmp_path / "rules.geojson").read_text())
    collection["metadata"] = {"pack": "test", "version": "2", "code_prefix": "TST"}
    (tmp_path / "rules.geojson").write_text(json.dumps(collection))
    with pytest.raises(qe.LoadError, match="metadata disagrees"):
        qe.Index("x").load_pack(tmp_path)
    collection["metadata"]["version"] = "1"
    (tmp_path / "rules.geojson").write_text(json.dumps(collection))
    assert qe.Index("x").load_pack(tmp_path) == ["TST001"]


def test_add_takes_a_feature_or_a_whole_feature_collection():
    index = qe.Index("x")
    index.add(
        record("TST001", box={"west": 170, "width": 20, "south": -20, "north": -10})
    )
    (found,) = index.query(space=sp.point(-175, -15))
    assert found.code == "TST001" and found.source == "python"
    collection = {"type": "FeatureCollection", "features": [record("TST002"), {}]}
    with pytest.raises(qe.LoadError, match=r"collection: feature 1 \(None\)"):
        index.add(collection)
    assert [e.rule.code for e in index._entries] == ["TST001"]
    collection["features"].pop()
    index.add(collection)
    assert len(index._entries) == 2


def test_time_start_and_time_end_are_the_fallback_time():
    index = qe.Index("x")
    index.add(record(time_start="2000-01-01", time_end="2006-12-31"))
    (found,) = index.query(time=("2006-12-31", "2007-12-31"))
    assert found.time_overlap == (("2006-12-31", "2006-12-31"),)
    with pytest.raises(ValueError, match="TST002: time_start"):
        index.add(
            {
                **record("TST002", time_start="2000-01-01"),
                "time": {"date": "2000-01-01"},
            }
        )


def test_record_polygons_are_built_on_first_use():  # section 9.2
    ring = [[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]
    fiji = [[170, -20], [-170, -20], [-170, -10], [170, -10], [170, -20]]
    index = qe.Index("x")
    for code, coords in (("TST001", ring), ("TST002", fiji)):
        geometry = {"type": "Polygon", "coordinates": [coords]}
        index.add({**record(code), "geometry": geometry})
    square, seam = (e.scope.space for e in index._entries)
    assert square.envelope == (0, 0, 10, 10) and "built" not in vars(square)
    assert not hasattr(seam, "envelope")  # crosses the seam: normalised at load
    assert [f.code for f in index.query(space=sp.point(-175, -15))] == ["TST002"]
    assert [f.code for f in index.query(space=sp.point(10, 5))] == ["TST001"]
    assert square.area_km2 == pytest.approx(sp.box(0, 0, 10, 10).area_km2, rel=1e-12)


# ---- fixtures 3, 15, 17 and 27 as records ---------------------------------------------
def test_fixture_3_seam_listed_twice_is_a_load_error():
    ring = [[-180 + i, 70] for i in range(361)] + [[-180, 70]]
    feature = {**record(), "geometry": {"type": "Polygon", "coordinates": [ring]}}
    with pytest.raises(ValueError, match="TST001: the ring encloses no area"):
        qe.Index("x").add(feature)
    feature["geometry"]["coordinates"] = [ring[:-2] + [ring[0]]]  # seam listed once
    index = qe.Index("x")
    index.add(feature)
    assert [f.code for f in index.query(space=sp.point(123, 90))] == ["TST001"]


def test_fixture_15_dates_in_records_follow_their_calendar():
    index = qe.Index("x")
    with pytest.raises(ValueError, match="noleap"):
        index.add(
            {**record("TST001", calendar="noleap"), "time": {"date": "2004-02-29"}}
        )
    index.add({**record("TST002", calendar="360_day"), "time": {"date": "2001-02-30"}})
    with pytest.raises(ValueError, match="360_day"):
        index.add(
            {**record("TST003", calendar="360_day"), "time": {"date": "2001-01-31"}}
        )


def test_fixture_17_axis_unit_in_a_record():
    index = qe.Index("x", axes=[qe.Axis("resolution", "km")])
    with pytest.raises(ValueError, match="TST001: resolution: unit 'deg'"):
        index.add(record(axes={"resolution": {"lt": 10, "unit": "deg"}}))
    index.add(record("TST002", axes={"resolution": {"lt": 10, "unit": "km"}}))


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
    index = qe.Index("glhe", dimensions=[Pfafstetter()])
    with pytest.raises(ValueError, match="TST001: dimension 'basin'"):
        index.add(record(dimensions={"basin": "14"}))  # a string, not a list
    with pytest.raises(ValueError, match="does not match"):
        index.add(record(dimensions={"basin": ["14", "0"]}))
    with pytest.raises(qe.UnknownNameError, match="basins"):
        index.add(record(dimensions={"basins": ["14"]}))
    index.add(record(dimensions={"basin": ["14", "62"]}))
    (found,) = index.query(dims={"basin": "1423"})
    assert found.dims == {"basin": qe.DimMatch(("14",), 1.0)}


# ---- the loader agrees with schema.json ----------------------------------------------
BAD = {
    "recommendation without suggestions": {"kind": "recommendation"},
    "unknown property": {"colour": "red"},
    "unknown severity": {"severity": "critical"},
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
}
BAD_FEATURES = {
    "reserved prefix QE": record("QE001"),
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
    index, codes = example_index(tmp_path)  # the loader accepts them as well
    assert len(codes) == 14


@pytest.mark.parametrize("name", [name for name, _ in bad_features()])
def test_loader_and_schema_reject_broken_records(tmp_path, name):
    feature = dict(bad_features())[name]
    assert not schema_validator().is_valid(feature)
    index = qe.Index("x", axes=[qe.Axis("resolution", "km")])
    index.add_regions("ar6", {"CAF": sp.box(15, -10, 30, 15)})
    with pytest.raises((ValueError, KeyError, TypeError)):
        index.add(copy.deepcopy(feature))
