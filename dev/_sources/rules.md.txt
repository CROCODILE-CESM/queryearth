# Writing rules

There are three ways to write a rule: a {class}`~queryearth.Rule` built in Python, a computed rule whose outcome depends on the request, or a record in a GeoJSON **pack**. All three end up on an {class}`~queryearth.Registry`.

## Rules in Python

```python
import queryearth as qe
from queryearth import space as sp

registry = qe.Registry("mine", axes=[qe.Axis("resolution", "km")])
registry.add(
    qe.Rule(
        code="MINE001",
        kind="caveat",
        title="Coastal values are interpolated",
        message="Within this box, values near the coast come from interpolation.",
        severity=qe.Severity.WARNING,
        action="use_with_caution",
        scope=qe.Scope(
            space=sp.box(-98, 18, -80, 31),
            facets={"variable": ["thetao", "so"]},
        ),
    )
)
```

`kind` is `"caveat"` or `"recommendation"`; a recommendation needs at least one {class}`~queryearth.Suggestion`. Adding a code that is already on the Registry raises `DuplicateCodeError`.

## Computed rules

A computed rule decides its outcome from the request, or from data the caller passes in `Query.context`. Register a function with `@registry.rule`; its docstring is the title:

```python
@registry.rule("MINE102", kind="recommendation", axes={"resolution": {"gt": 0}})
def time_step(query, match):
    """Set the time step from the finest cells"""
    finest_km = match.axes["resolution"].lo
    return {"suggestions": [qe.Suggestion("settings", "dt", 30.0 * finest_km)]}
```

The function runs only when the scope matches definitely. It returns `True` (one finding with the declared outcome), `False` or `None` (no finding), a mapping of `Finding` fields to override, or several such mappings. For a class-based rule, subclass {class}`~queryearth.ComputedRule` with the same keywords and define `check(self, query, match)`. `requires=["key"]` names `Query.context` keys the rule needs: without them, the finding is conditional. A `mask(lon, lat, query)` method lets the rule take part in {meth}`~queryearth.Registry.query_points`.

## Packs

A pack is a directory with a `pack.toml` and one or more GeoJSON FeatureCollections, loaded with {meth}`Registry.load_pack() <queryearth.Registry.load_pack>`. Loading never runs code. Every problem is reported at once in a `LoadError` that names the file, the feature's position and its code, and the Registry is left unchanged.

`pack.toml` declares the pack's name, version, the code prefixes it owns and its files. It also declares the axes, facets and products its records use, and any named regions:

```{literalinclude} ../../examples/toy/pack.toml
:language: toml
```

The axes and facets a pack declares must exist on the Registry it is loaded into. A product under `[products.<name>]` has `aliases`, `variables`, `resolution`, `version` and a `coverage` with a `time` range and, optionally, a `box`. Named regions go under `[regions.<namespace>]`, with a GeoJSON `file` and the `id_property` that names each region. Records then refer to them as `region_ref = "namespace:id"`.

### Records

Each rule is one GeoJSON Feature. Its `geometry` is a Polygon, a MultiPolygon or null (null means everywhere). Its time goes in the top-level JSON-FG `time` member: `{"interval": ["2000-01-01", "2003-12-31"]}`, `{"date": ...}`, `{"timestamp": ...}` or null. The rest is in `properties`:

| Group | Properties |
|---|---|
| Identity and outcome (required) | `code`, `kind` (`caveat` or `recommendation`), `title`, `message`, `severity` (`info`, `warning` or `severe`) |
| Advice | `instruction`, `confidence`, `action`, `source_severity`, and `suggestions` (required for a recommendation) |
| Scope | `facets`, `axes`, `dimensions` (for plugin dimensions), `region_ref` or `box` (`{west, width, south, north}`; geometry must then be null), `periods` (intervals inside `time`), `recurrence` (`{"months": [12, 1, 2]}`), and the fallback `time_start` and `time_end` |
| Emission | `min_overlap`, a threshold on the area fraction from 0 to 1 below which `emit()` stays quiet |
| Provenance | `evidence`, `references`, `aliases` |
| Lifecycle | `status` (`draft`, `reviewed` or `deprecated`; a reviewed record cites a reference), `created`, `updated`, `withdrawn` (kept for history, never matched), `supersedes` |
| Extensions | `x_*` fields, kept and ignored |

A record from the toy pack:

```json
{
  "type": "Feature",
  "id": "TOY002",
  "geometry": {
    "type": "Polygon",
    "coordinates": [[[165, 52], [-160, 52], [-160, 66], [165, 66], [165, 52]]]
  },
  "time": null,
  "properties": {
    "code": "TOY002",
    "kind": "caveat",
    "title": "toy_ocean is too warm in the Bering Sea in winter",
    "message": "From December to March, toy_ocean sea temperature in the Bering Sea runs about 1 K too warm.",
    "severity": "warning",
    "facets": {"product": ["toy_ocean"], "variable": ["thetao"]},
    "recurrence": {"months": [12, 1, 2, 3]},
    "status": "draft"
  }
}
```

Its ring crosses the antimeridian the way most tools write it, from 165 to -160, and queryearth splits it at ±180.

A single Feature or FeatureCollection can also be added directly with `Registry.add(mapping)`.
