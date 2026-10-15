# Rule files

A rule file is one GeoJSON FeatureCollection with one Feature per rule:

```json
{
  "type": "FeatureCollection",
  "queryearth": "0.7",
  "features": [
    {
      "type": "Feature",
      "id": "REGION/POLAR/POLAR001",
      "geometry": {
        "type": "Polygon",
        "coordinates": [[[-180, 60], [180, 60], [180, 90], [-180, 90], [-180, 60]]]
      },
      "time": {"interval": ["1993-01-01", ".."]},
      "properties": {
        "code": "REGION/POLAR/POLAR001",
        "title": "Consider active sea ice",
        "message": "Part of this domain is poleward of 60 degrees, where sea ice forms in winter.",
        "level": "warning",
        "dimensions": {"ice": ["sice"], "resolution": {"gt": 10, "unit": "km"}},
        "instruction": "Use CICE in the compset.",
        "references": [{"title": "Expert interview 1", "url": "https://example.org/1"}]
      }
    }
  ]
}
```

- `geometry` is the rule's space: a Polygon, a MultiPolygon, or null for none. A ring that crosses ±180 is split there, so write a shape across the date line as it runs, such as from 170 to -170.
- `time` is the rule's time, as a JSON-FG time member: `{"interval": [start, end]}` with ISO 8601 dates or timestamps and `".."` for an open end, or null for none. An end date covers its whole day.
- `properties` holds `code`, `title` and `message`, all required, where the code may be a path whose part before the last slash is the rule's [category](concepts.md#categories); `level`, `"info"`, `"warning"` (the default) or `"error"`; and `dimensions`, the value on each other [dimension](dimensions.md), in the form that dimension's `to_json` writes.
- Every other property, here `instruction` and `references`, is kept as given and written back unchanged. A `category` property is refused, since the category is the code's path.
- `queryearth` names the release that last changed the file format. `to_file` writes it, and `from_file` refuses a file that needs a later queryearth than the one installed, saying to upgrade; a file without it is read as it is.

## Reading and writing

{meth}`Registry.from_file() <queryearth.Registry.from_file>` reads one or more rule files into one Registry. Declare every dimension the rules use other than space and time:

```python
dimensions = [qe.Axis("resolution", "km"), qe.Labels("ice")]
registry = qe.Registry.from_file("rules.geojson", "rules_claude.geojson", dimensions=dimensions)
```

A file is read whole or not at all. A problem raises `ValueError` naming the file, the Feature's position and its code: a record without a code, title or message; a Feature member other than `type`, `id`, `geometry`, `time`, `properties` and `bbox`; a value its dimension refuses; a dimension the Registry has not declared; or a code already read, which raises `DuplicateCodeError`.

{meth}`Registry.to_file() <queryearth.Registry.to_file>` writes every rule, in the order added, as indented JSON with each point on one line, and `from_file` reads it back. {meth}`Registry.to_feature() <queryearth.Registry.to_feature>` gives one rule's Feature. {meth}`Registry.add() <queryearth.Registry.add>` also takes a Feature as a mapping.

## Properties from queryearth 0.6

Rule files from queryearth 0.6 read as they are when they use only the members above; their other properties, such as `instruction`, `references` and `evidence`, pass through. A few 0.6 properties changed which rules apply, and are refused rather than passed through, so that an old rule never applies more widely than its author meant: `box`, `edge`, `periods`, `recurrence`, `time_start`, `time_end`, `withdrawn` and `supersedes`. The [growth path](https://github.com/CROCODILE-CESM/queryearth/blob/main/docs/growth.md) says where each lives at the tag v0.6.0.
