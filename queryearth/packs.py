"""Packs: a pack.toml and its FeatureCollections of rule records (section 5.4).

Loading never runs code. Every problem is reported at once, naming its file,
the feature's position and its code; a failed load leaves the Registry as it was.
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
from queryearth.objects import LoadError, UnknownNameError
from queryearth.rules import Rule, code_prefix

if TYPE_CHECKING:
    from queryearth.registry import Registry

_ERRORS = (ValueError, TypeError, KeyError)
_TABLES = set("pack axes facets dimensions regions".split())
_PACK = set("name version code_prefix license files".split())


@contextlib.contextmanager
def atomic(registry: Registry) -> Iterator[None]:
    """Restore the Registry's declarations and rules if the block raises."""
    saved = {k: copy.copy(v) for k, v in vars(registry).items()}
    try:
        yield
    except BaseException:
        vars(registry).clear()
        vars(registry).update(saved)
        raise


def add_mapping(registry: Registry, mapping: Mapping[str, Any]) -> None:
    """Registry.add for one GeoJSON Feature, or a FeatureCollection added whole."""
    if mapping.get("type") != "FeatureCollection":
        registry._add(Rule.from_feature(mapping, registry), "python")
        return
    with atomic(registry):
        problems = add_collection(registry, mapping, "collection", "python", None)[1]
        if problems:
            raise LoadError(problems)


def add_collection(
    registry: Registry,
    collection: Any,
    where: str,
    source: str,
    prefixes: frozenset[str] | None,
) -> tuple[list[str], list[str]]:
    """Add every record of a FeatureCollection; returns (codes, problems).

    prefixes are the code prefixes a pack owns; None for rules added from
    Python, which may use any prefix.
    """
    features = collection.get("features") if isinstance(collection, Mapping) else None
    if collection.get("type") != "FeatureCollection" or not isinstance(features, list):
        return [], [f"{where}: not a GeoJSON FeatureCollection"]
    codes, problems = [], []
    for i, feature in enumerate(features):
        props = feature.get("properties") if isinstance(feature, Mapping) else None
        code = props.get("code") if isinstance(props, Mapping) else None
        try:
            rule = Rule.from_feature(feature, registry)
            prefix = code_prefix(rule.code)
            if prefixes is not None and prefix not in prefixes:
                raise ValueError(
                    f"prefix {prefix!r} is not one the pack owns, {sorted(prefixes)}"
                )
            registry._add(rule, source)
            codes.append(rule.code)
        except _ERRORS as err:
            text = str(err).removeprefix(f"{code}: ")
            problems.append(f"{where}: feature {i} ({code}): {text}")
    return codes, problems


def load_pack(registry: Registry, path: Any) -> list[str]:
    """Registry.load_pack: declare a pack's regions, add its records."""
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
    claimed = {p: n for n, owned in registry._packs.items() for p in owned}
    for problem in (
        set(meta) - _TABLES and f"unknown tables {sorted(set(meta) - _TABLES)}",
        set(pack) - _PACK and f"unknown [pack] keys {sorted(set(pack) - _PACK)}",
        not (isinstance(name, str) and name) and "[pack] needs a name",
        name in registry._packs and f"pack {name!r} is already loaded",
        not isinstance(pack.get("version"), str) and "[pack] needs a version",
        not prefixes and "[pack] needs a code_prefix",
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
    for group, n, unit in declared:  # they must agree with the Registry (Q13)
        try:
            dimension = registry._dimension(n, group)[0]
            if group == "axes" and dimension.unit != unit:
                raise ValueError(
                    f"axis {n!r} has unit {dimension.unit!r}, not {unit!r}"
                )
        except (UnknownNameError, ValueError) as err:
            problems.append(f"{toml.name}: does not agree with the Registry: {err}")
    root = toml.parent
    with atomic(registry):
        for namespace, table in meta.get("regions", {}).items():
            problems += _regions(registry, root, namespace, table)
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
                found, more = add_collection(registry, data, file.name, name, prefixes)
                codes += found
                problems += more
        if problems:
            raise LoadError(problems)
        registry._packs[name] = tuple(sorted(prefixes))
    return codes


def _regions(registry: Registry, root: Path, namespace: str, table: Any) -> list[str]:
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
        registry.add_regions(namespace, regions)
    except ValueError as err:
        problems.append(f"{file.name}: {err}")
    return problems
