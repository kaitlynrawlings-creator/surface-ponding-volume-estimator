# Depression Volume Calculator
### ArcGIS Pro Python Toolbox

A custom ArcGIS Pro geoprocessing tool for estimating the volume of water pooled in a terrain depression and the time required to pump it out. Built for stormwater field operations and emergency response.

---

## Overview

Field crews responding to flooding need quick answers: *how much water is here, and how long will it take to pump out?* This tool answers both questions using LiDAR terrain analysis and straightforward pump time math.

Draw a polygon around the flooded area, enter a pump rate and optionally an observed water depth, and the tool returns volume estimates and pump-out time using the DEM terrain surface to calculate depression geometry.

---

## Requirements

- ArcGIS Pro 3.x
- Spatial Analyst extension
- 3D Analyst extension
- A bare-earth LiDAR DEM in a **projected coordinate system** (meters or feet as linear units — geographic coordinate systems will produce incorrect results)

---

## Installation

1. Download `DepressionVolume.pyt`
2. In ArcGIS Pro, open the **Catalog pane**
3. Right-click **Toolboxes** → **Add Toolbox**
4. Browse to and select `DepressionVolume.pyt`
5. The **Calculate Depression Volume** tool will appear under the toolbox

---

## Usage

### Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| Flooded Area Polygon | Yes | Draw a polygon on the map around the flooded area |
| DEM | Yes | Bare-earth LiDAR DEM raster |
| Pump Rate (GPM) | No | Pump rate in gallons per minute. Default: 500 GPM |
| Observed Water Depth (inches) | No | Observed depth of water in the field. Leave blank to calculate maximum possible volume |
| Output Unit System | No | US Standard (acre-feet + gallons), Metric (m³ + liters), or Engineering (ft³ + gallons) |
| Output Depression Polygon | Yes | Output feature class path |

### Output Fields

| Field | Description |
|-------|-------------|
| Vol_AcreFt / Vol_CubicM / Vol_CubicFt | Depression volume in selected unit system |
| Vol_Gallons / Vol_Liters | Depression volume in secondary units |
| AvgDepth_In | Average water depth across the flooded area (inches) |
| Area_Acres | Flooded area in acres |
| PumpTime_Hr | Estimated pump-out time in hours |
| PumpRate_GPM | Pump rate used for calculation |

### Two Modes

**No observed depth (default):**
Runs an ArcGIS Fill analysis on the clipped DEM to find all natural terrain depressions within the drawn polygon. Calculates the maximum volume each depression can hold before water would overflow. Best for getting a complete picture of all low spots in a drawn area.

**With observed depth:**
Sets the water surface at the minimum terrain elevation within the drawn polygon plus the entered depth. Calculates volume below that water surface. Use this mode when you are standing next to a specific flooded depression and can observe the water depth directly.

---

## Methodology

### Depression Volume (no observed depth)
The tool clips the DEM to the drawn polygon, runs the ArcGIS **Fill** tool to fill topographic depressions to their natural pour point, and subtracts the original DEM from the filled DEM to get depression depth at each cell. Volume is calculated using the **3D Analyst Surface Volume** tool:

```
Volume (m³) = Σ (depression_depth_i × cell_width × cell_height)
```

### Depression Volume (with observed depth)
The minimum terrain elevation within the drawn polygon is found and a water surface is set at that elevation plus the observed depth. All cells below the water surface are flooded, with depth equal to water surface minus terrain elevation.

```
water_surface = min_terrain_elevation + observed_depth
depression_depth = water_surface - terrain  [where terrain < water_surface]
```

### Pump Time
Pump time is calculated using straightforward algebra — no additional spatial operations:

```
Pump Time (hours) = Volume (gallons) / (Pump Rate (GPM) × 60)
```

---

## Limitations

- **Observed depth anchors to polygon minimum elevation.** The water surface is set relative to the lowest point in the drawn polygon. For best results, draw a tight polygon around one specific flooded area rather than a large polygon covering varied terrain. On sloped sites the polygon minimum may be far from where you are standing, producing unexpected results.

- **No-depth mode finds all terrain depressions, not just flooded areas.** Fill analysis identifies every topographic depression within the drawn polygon, including small LiDAR noise artifacts. In flat areas this may produce many small scattered polygons. Each one represents a real terrain depression.

- **Volume is terrain-based and static.** The tool does not account for subsurface drainage, infiltration during pumping, or inflow from upstream areas during an active storm event.

- **DEM resolution affects accuracy.** A 1-meter LiDAR DEM will produce more accurate volume estimates than a 10-meter NED DEM. Small depressions may not be captured at coarser resolutions.

- **Results are operational estimates, not engineering calculations.** For regulatory submissions or formal engineering reports, results should be verified by a licensed civil engineer using site-specific survey data.

---

## Validation

Pump time math has been verified against hand calculations across multiple pump rates:

| Pump Rate (GPM) | Volume (gallons) | Pump Time (hrs) | Hand Check |
|----------------|-----------------|-----------------|------------|
| 250 | 70,392 | 4.693 | 70,392 / (250 × 60) = 4.693 ✓ |
| 500 | 70,392 | 2.346 | 70,392 / (500 × 60) = 2.346 ✓ |
| 1000 | 70,392 | 1.173 | 70,392 / (1000 × 60) = 1.173 ✓ |

---

## Data Sources

The tool works with any bare-earth DEM. Recommended sources:

- **USGS 3D Elevation Program (3DEP)** — 1-meter and 1/3 arc-second LiDAR-derived DEMs covering most of the US. Available at [https://www.usgs.gov/3d-elevation-program](https://www.usgs.gov/3d-elevation-program)
- **Local government LiDAR** — Many counties and municipalities publish LiDAR datasets through their open data portals

---

## References

- Esri ArcGIS Pro Documentation. Surface Volume (3D Analyst). [https://pro.arcgis.com/en/pro-app/latest/tool-reference/3d-analyst/surface-volume.htm](https://pro.arcgis.com/en/pro-app/latest/tool-reference/3d-analyst/surface-volume.htm)
- Esri ArcGIS Pro Documentation. Fill (Spatial Analyst). [https://pro.arcgis.com/en/pro-app/latest/tool-reference/spatial-analyst/fill.htm](https://pro.arcgis.com/en/pro-app/latest/tool-reference/spatial-analyst/fill.htm)

---

## Author

Kaitlyn Rawlings  
GIS Analyst | Environmental Studies, University of Kansas  
[GitHub](https://github.com/yourusername)
