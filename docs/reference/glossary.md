# Glossary

> **Frozen.** This file was frozen on 2026-10-13 at commit e5e9d0e. It records the design as it stood then and is no longer updated. The public docs in `docs/source` and `CLAUDE.md` describe the current package.

[Section 4.1 of design.md](../design.md#41-terms) defines queryearth's own terms. This file defines the other names the design document and its reference files use, for readers outside earth-system science.

**Geometry and software terms**

| Term | Meaning |
|---|---|
| Antimeridian | The meridian at 180 degrees longitude, where longitude jumps from +180 to -180. Shapes that cross it are the commonest source of silent errors. |
| CRS84 | Longitude and latitude in degrees on the WGS84 datum, longitude first: the coordinate system of GeoJSON. |
| EPSG:3995 | The code of the WGS 84 Arctic Polar Stereographic projection, a map projection centred on the North Pole that polar model grids often use. |
| Planar edge | A straight line between two vertices in longitude-latitude coordinates, as opposed to a great-circle arc on the sphere. |
| Winding number | How many times a ring goes around the pole: the sum of its longitude steps divided by 360. |
| Closed set | A shape that includes its boundary, so a point exactly on an edge counts as inside. |
| Envelope | The axis-aligned bounding box of a shape. |
| STRtree | shapely's packed R-tree (sort-tile-recursive), a spatial index that quickly finds the shapes whose envelopes meet a query. |
| Prepared geometry | A shape that shapely has preprocessed so that many repeated tests against it (covers, intersects) run faster. |
| GeoJSON, JSON-FG | GeoJSON (RFC 7946) is the JSON format for geographic features; OGC JSON-FG extends it, among other things with a `time` member. |
| JSON Schema | A JSON vocabulary for describing and validating the structure of JSON documents; this document uses the 2020-12 version. |
| CQL2 | OGC's Common Query Language, a filter language for spatial and temporal queries. |
| HEALPix, MOC | HEALPix divides the sphere into equal-area cells; a MOC (multi-order coverage map) stores a region as a set of such cells. |
| MCP | Model Context Protocol, a protocol through which AI agents call tools on a server. |
| fnmatch | Python's shell-style pattern matching, where `*` matches any run of characters. |
| PEP 440 | Python's standard for version numbers. Many product versions, such as `ERA5T`, do not follow it. |
| PROJ, pyproj | PROJ is the standard open-source library for map projections and geodesic calculations; pyproj is its Python interface. |
| regionmask | A Python package that turns region outlines into masks on a grid. |
| QGIS | A free desktop geographic information system that can display GeoJSON and JSON-FG files. |
| contextvars | The Python module for values that are local to a thread or an asyncio task. |

**Products, projects and models**

| Name | Meaning |
|---|---|
| CRU TS | The Climatic Research Unit gridded Time Series: monthly climate variables on a 0.5 degree land grid, interpolated from weather stations. Its `stn` variable counts the stations behind each value. |
| ERA5 | ECMWF's fifth-generation global atmospheric reanalysis, hourly from 1940, on a 0.25 degree grid. ERA5T is its preliminary near-real-time stream, and ERA5.1 a rerun of 2000 to 2006. |
| ERA5-Land | A land-surface reanalysis driven by ERA5, at 0.1 degree, from 1950. |
| ECMWF | The European Centre for Medium-Range Weather Forecasts, which produces ERA5. |
| GLORYS12 | A global ocean reanalysis at 1/12 degree from Copernicus Marine, starting in 1993. |
| GEBCO | The General Bathymetric Chart of the Oceans: a global grid of ocean depth and land elevation; `GEBCO_2024` names one release. |
| Argo | The global array of profiling floats that measure ocean temperature and salinity; it reached about 1,000 floats in early 2004. |
| NWM | The National Water Model, NOAA's hydrologic model of the contiguous United States; GLHE reads its retrospective version 3.0 lake output. |
| HydroLAKES | A global database of lake outlines, about 1.4 million lakes of at least 10 hectares. |
| DAHITI | The Database for Hydrological Time Series of Inland Waters: lake and river water levels from satellite altimetry. |
| GBIF | The Global Biodiversity Information Facility, which publishes species-occurrence records. |
| IPCC AR6 regions | The reference land and ocean regions of the IPCC Sixth Assessment Report, named by abbreviations such as CAF (Central Africa). |
| CF conventions | The Climate and Forecast metadata conventions for netCDF files; they define calendar names and time bounds variables such as `time_bnds`. |
| CESM, compset | The Community Earth System Model; a compset names the set of model components in a case. SICE is the stub sea-ice component, CICE the active sea-ice model. |
| MOM6, MOM_input | The Modular Ocean Model, version 6; `MOM_input` is its run-time parameter file, where `DT` is the time step. |
| Supergrid | MOM6's grid file layout, which stores points at twice the model resolution (cell corners, centres and edge midpoints). |
| CROCODILE | The NCAR project that builds tools for regional ocean modelling in CESM: CrocoDash, mom6_forge and the Regional Ocean Debugger. |
| CrocoDash | CROCODILE's Python package that sets up regional MOM6 cases in CESM, including their forcing products. |
| mom6_forge | CROCODILE's package for MOM6 horizontal grids, vertical grids and bathymetry. |
| Regional Ocean Debugger | A CROCODILE tool for diagnosing regional MOM6 runs, backed by a private knowledge base of expert interviews. |
| GLHE | The Global Lake Hydrology Explorer. Its parts, as this document uses them: CLAY, the driver and data-access layer; CALCITE, the event types and event bus; LIME, the Panel dashboard. |
| GLADE | NCAR's shared high-performance file system. |
| ED-318 | A EUROCAE standard, in GeoJSON, for geographical zones that restrict uncrewed aircraft. |
| UAS | Uncrewed aircraft system (a drone). |
| ILI | Influenza-like illness, a syndrome counted by disease-surveillance networks. |
