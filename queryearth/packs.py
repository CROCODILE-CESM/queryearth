"""Packs: a pack.toml and its FeatureCollections of rule records (section 5.4).

Loading never runs code. Every problem is reported at once, naming its file,
the feature's position and its code; a failed load leaves the Index as it was.
"""

from __future__ import annotations

import contextlib
import copy
import json
import tomllib
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any

from queryearth import space as sp
from queryearth.errors import LoadError, UnknownNameError
from queryearth.objects import Coverage, Product
from queryearth.rules import Rule, box_of, code_prefix
from queryearth.time import parse_time

if TYPE_CHECKING:
    from queryearth.index import Index

_ERRORS = (ValueError, TypeError, KeyError)
_TABLES = set("pack axes facets dimensions products regions".split())
_PACK = set("name version code_prefix license files".split())
_PRODUCT = set("aliases variables resolution version coverage".split())


@contextlib.contextmanager
def atomic(index: Index) -> Iterator[None]:
    """Restore the Index's declarations and rules if the block raises."""
    saved = {k: copy.copy(v) for k, v in vars(index).items()}
    try:
        yield
    except BaseException:
        vars(index).clear()
        vars(index).update(saved)
        raise


def add_mapping(index: Index, mapping: Mapping[str, Any]) -> None:
    """Index.add for one GeoJSON Feature, or a FeatureCollection added whole."""
    if mapping.get("type") != "FeatureCollection":
        index._add(Rule.from_feature(mapping, index), "python")
        return
    with atomic(index):
        problems = add_collection(index, mapping, "collection", "python", None)[1]
        if problems:
            raise LoadError(problems)


def add_collection(
    index: Index,
    collection: Any,
    where: str,
    source: str,
    prefixes: frozenset[str] | None,
) -> tuple[list[str], list[str]]:
    """Add every record of a FeatureCollection; returns (codes, problems).

    prefixes are the code prefixes a pack owns; None for rules added from
    Python, which may use any prefix but QE.
    """
    features = collection.get("features") if isinstance(collection, Mapping) else None
    if collection.get("type") != "FeatureCollection" or not isinstance(features, list):
        return [], [f"{where}: not a GeoJSON FeatureCollection"]
    codes, problems = [], []
    for i, feature in enumerate(features):
        props = feature.get("properties") if isinstance(feature, Mapping) else None
        code = props.get("code") if isinstance(props, Mapping) else None
        try:
            rule = Rule.from_feature(feature, index)
            prefix = code_prefix(rule.code)
            if prefixes is not None and prefix not in prefixes:
                raise ValueError(
                    f"prefix {prefix!r} is not one the pack owns, {sorted(prefixes)}"
                )
            index._add(rule, source)
            codes.append(rule.code)
        except _ERRORS as err:
            text = str(err).removeprefix(f"{code}: ")
            problems.append(f"{where}: feature {i} ({code}): {text}")
    return codes, problems


def load_pack(index: Index, path: Any) -> list[str]:
    """Index.load_pack: declare a pack's products and regions, add its records."""
    toml = Path(path)
    toml = toml / "pack.toml" if toml.is_dir() else toml
    try:
        meta = tomllib.loads(toml.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as err:
        raise LoadError([f"{toml}: {err}"]) from err
    problems: list[str] = []
    pack = meta.get("pack", {})
    name, prefixes = pack.get("name"), pack.get("code_prefix")
    prefixes = frozenset([prefixes] if isinstance(prefixes, str) else prefixes or ())
    claimed = {p: n for n, owned in index._packs.items() for p in owned}
    for problem in (
        set(meta) - _TABLES and f"unknown tables {sorted(set(meta) - _TABLES)}",
        set(pack) - _PACK and f"unknown [pack] keys {sorted(set(pack) - _PACK)}",
        not (isinstance(name, str) and name) and "[pack] needs a name",
        name in index._packs and f"pack {name!r} is already loaded",
        not isinstance(pack.get("version"), str) and "[pack] needs a version",
        not prefixes and "[pack] needs a code_prefix",
        "QE" in prefixes and "the code prefix QE is reserved",
        *(
            f"prefix {p!r} is claimed by pack {claimed[p]!r}"
            for p in prefixes & set(claimed)
        ),
    ):
        if problem:
            problems.append(f"{toml.name}: {problem}")
    declared = [
        ("axes", n, meta["axes"][n].get("unit")) for n in meta.get("axes", {})
    ] + [
        (group, n, None)
        for group, table in (("facets", "facets"), ("dims", "dimensions"))
        for n in meta.get(table, {}).get("names", ())
    ]
    for group, n, unit in declared:  # they must agree with the Index (Q13)
        try:
            dimension = index._dimension(n, group)[0]
            if group == "axes" and dimension.unit != unit:
                raise ValueError(
                    f"axis {n!r} has unit {dimension.unit!r}, not {unit!r}"
                )
        except (UnknownNameError, ValueError) as err:
            problems.append(f"{toml.name}: does not agree with the Index: {err}")
    root = toml.parent
    with atomic(index):
        for namespace, table in meta.get("regions", {}).items():
            problems += _regions(index, root, namespace, table)
        for slug, table in meta.get("products", {}).items():
            try:
                _product(index, slug, table)
            except _ERRORS as err:
                problems.append(f"{toml.name}: [products.{slug}]: {err}")
        codes: list[str] = []
        for pattern in pack.get("files", ()):
            files = sorted(root.glob(pattern))
            if not files:
                problems.append(f"{toml.name}: no file matches {pattern!r}")
            for file in files:
                try:
                    data = json.loads(file.read_text(encoding="utf-8"))
                except (OSError, ValueError) as err:
                    problems.append(f"{file.name}: {err}")
                    continue
                header = data.get("metadata", {}) if isinstance(data, Mapping) else {}
                stated = header.get("code_prefix", ())  # an ED-318-style header
                stated = frozenset([stated] if isinstance(stated, str) else stated)
                said = (header.get("pack"), header.get("version"), stated)
                if header and said != (name, pack.get("version"), prefixes):
                    problems.append(f"{file.name}: its metadata disagrees with [pack]")
                found, more = add_collection(index, data, file.name, name, prefixes)
                codes += found
                problems += more
        if problems:
            raise LoadError(problems)
        index._packs[name] = tuple(sorted(prefixes))
    return codes


def _regions(index: Index, root: Path, namespace: str, table: Any) -> list[str]:
    """Declare a [regions.<namespace>] file of named polygons; returns problems."""
    try:
        file = root / table["file"]
        features = json.loads(file.read_text(encoding="utf-8"))["features"]
    except (*_ERRORS, OSError) as err:
        return [f"pack.toml: [regions.{namespace}]: {err}"]
    regions, problems = {}, []
    for i, feature in enumerate(features):
        try:
            rid = str(feature["properties"][table["id_property"]])
            regions[rid] = sp.polygon(feature["geometry"])
        except _ERRORS as err:
            problems.append(f"{file.name}: feature {i}: {err}")
    try:
        index.add_regions(namespace, regions)
    except ValueError as err:
        problems.append(f"{file.name}: {err}")
    return problems


def _product(index: Index, slug: str, table: Any) -> None:
    """Declare one [products.<slug>]; product names are global in an Index."""
    if set(table) - _PRODUCT:
        raise ValueError(f"unknown keys {sorted(set(table) - _PRODUCT)}")
    coverage = table.get("coverage", {})
    keys = set(coverage)
    if keys - {"time", "box", "region_ref"} or {"box", "region_ref"} <= keys:
        raise ValueError("a coverage holds time, and a box or a region_ref")
    space = None
    if "box" in coverage:
        space = box_of(coverage["box"])
    elif "region_ref" in coverage:
        refs = coverage["region_ref"]
        space = index._region((refs,) if isinstance(refs, str) else tuple(refs), slug)
    time = None
    if "time" in coverage:
        time = parse_time({"interval": list(coverage["time"])})
    resolution = table.get("resolution")
    index.add_product(
        Product(
            slug,
            aliases=tuple(table.get("aliases", ())),
            variables=tuple(table.get("variables", ())),
            coverage=Coverage(space, time),
            resolution=None if resolution is None else tuple(resolution),
            version=table.get("version"),
        )
    )
