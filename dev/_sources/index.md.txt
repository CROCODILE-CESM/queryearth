# queryearth

queryearth matches rules to a query. A rule says something worth knowing, such as "tidal mixing dominates here, so force tides", and is scoped by [dimensions](dimensions.md): where (space), when (time), and anything else that matters, such as grid resolution or forcing product. A query gives values on any of the dimensions and gets back the rules that apply. Rules live in GeoJSON [rule files](rules.md), so any GIS tool can show where they apply.

Space, time and numeric axes are the base dimensions, and labels come with them. Defining your own dimension is a few lines of Python, written on the same three-method class the built-in ones use: see [Dimensions](dimensions.md).

## Install

```bash
pip install queryearth
```

queryearth needs Python 3.11 or later, numpy, and shapely 2.1 or later.

## A first query

```python
import queryearth as qe
from queryearth import space as sp

registry = qe.Registry([qe.Axis("resolution", "km"), qe.Labels("product")])
registry.add(
    qe.Rule(
        code="GULF001",
        title="glorys is too fresh off the Mississippi",
        message="Near the delta, glorys surface salinity runs low.",
        scope={"space": sp.box(-92, 27, -87, 30.5), "product": "glorys"},
    )
)
registry.add(
    qe.Rule(
        code="GRID001",
        title="Turn off GM at high resolution",
        message="Below 8 km eddies are partly resolved: set THICKNESSDIFFUSE = False.",
        level="info",
        scope={"resolution": {"lt": 8}},
    )
)

findings = registry.query(
    space=sp.box(-98, 18, -80, 31),  # west, south, east, north
    time=qe.interval("2020-01-01", "2020-12-31"),
    resolution=(5, 9),  # the grid's smallest and largest cells, in km
    product="glorys",
)
print([rule.code for rule in findings])  # ['GULF001', 'GRID001'], warnings first
```

GULF001 applies because the query's box overlaps the rule's and the product is glorys; GRID001 because a grid from 5 to 9 km has cells below 8 km. Neither rule constrains time, so any time matches. See [Rules and queries](concepts.md) for the matching rule.

Language models and other programs: <a href="llms.txt">llms.txt</a> describes rule files and the API on one page.

```{toctree}
:maxdepth: 2

dimensions
concepts
rules
api
```
