import arcpy
import os
import re

# ============================================================
# UNIT OPTIONS
# ============================================================
UNIT_OPTIONS = [
    "US Standard (acre-feet + gallons)",
    "Metric (cubic meters + liters)",
    "Engineering (cubic feet + gallons)"
]

# ============================================================
# HELPERS
# ============================================================
def get_unit_funcs(output_units):
    is_metric = "Metric" in output_units
    is_eng    = "Engineering" in output_units
    def primary(acft):
        if is_metric: return round(acft*1233.48,3),"cubic meters"
        if is_eng:    return round(acft*43560,1),"cubic feet"
        return round(acft,4),"acre-feet"
    def secondary(acft):
        if is_metric: return round(acft*1233480,0),"liters"
        return round(acft*325851,0),"gallons"
    return primary,secondary

def clip_dem(dem_path, template, ws, name="dem_clip"):
    out = os.path.join(ws, name)
    arcpy.management.Clip(
        in_raster=dem_path, rectangle="", out_raster=out,
        in_template_dataset=template, nodata_value="",
        clipping_geometry="ClippingGeometry",
        maintain_clipping_extent="NO_MAINTAIN_EXTENT"
    )
    return out

# ============================================================
class Toolbox(object):
    def __init__(self):
        self.label = "Surface Ponding Volume Tools"
        self.alias  = "SurfacePondingVolumeTools"
        self.tools  = [DepressionVolume]

# ════════════════════════════════════════════════════════════
# TOOL — DEPRESSION VOLUME CALCULATOR
# ════════════════════════════════════════════════════════════
class DepressionVolume(object):
    def __init__(self):
        self.label = "Surface Ponding Volume Estimator"
        self.description = (
            "USE CASE: Field operations and emergency response. Draw a polygon around "
            "a flooded area to calculate how much water needs to be pumped out. "
            "Uses LiDAR terrain analysis to calculate depression volume within the drawn polygon. "
            "Enter an observed water depth for a more accurate estimate, or leave blank "
            "to calculate maximum possible volume based on terrain depressions."
        )
        self.canRunInBackground = False

    def getParameterInfo(self):
        # 0
        p_poly = arcpy.Parameter(displayName="Flooded Area Polygon",name="flooded_polygon",
            datatype="GPFeatureRecordSetLayer",parameterType="Required",direction="Input")
        p_poly.value = arcpy.FeatureSet()
        p_poly.filter.list = ["Polygon"]
        p_poly.description = "Draw a polygon around the flooded area on the map."
        # 1
        p_dem = arcpy.Parameter(displayName="DEM",name="dem_raster",
            datatype="GPRasterLayer",parameterType="Required",direction="Input")
        p_dem.description = (
            "Bare-earth Digital Elevation Model raster. Any resolution is accepted. "
            "Must be in a projected coordinate system with linear units (meters or feet) — "
            "geographic coordinate systems (degrees) will produce incorrect volume results."
        )
        # 2
        p_pump = arcpy.Parameter(displayName="Pump Rate (gallons per minute)",name="pump_rate_gpm",
            datatype="GPDouble",parameterType="Optional",direction="Input")
        p_pump.value = 500.0
        # 3
        p_depth = arcpy.Parameter(
            displayName="Observed Water Depth (inches) — default calculates maximum possible volume",
            name="observed_depth_in",datatype="GPDouble",parameterType="Optional",direction="Input")
        p_depth.value = None
        p_depth.description = (
            "Optional. Enter the observed water depth in inches at the flooded location. "
            "If entered, the tool sets the water surface at the polygon minimum elevation + "
            "observed depth. For best results draw a tight polygon around a single flooded "
            "depression — large polygons covering varied terrain will anchor the water surface "
            "to the lowest corner of the drawn area, which may not reflect where you are standing. "
            "If left blank, the tool uses terrain Fill analysis to calculate the maximum "
            "possible volume the depression can hold."
        )
        # 4
        p_units = arcpy.Parameter(displayName="Output Unit System",name="output_units",
            datatype="GPString",parameterType="Optional",direction="Input")
        p_units.filter.type = "ValueList"
        p_units.filter.list = UNIT_OPTIONS
        p_units.value = "US Standard (acre-feet + gallons)"
        # 5
        p_out = arcpy.Parameter(displayName="Output Depression Polygon",name="out_depression_polygon",
            datatype="DEFeatureClass",parameterType="Required",direction="Output")
        # Derived
        p_d0 = arcpy.Parameter(displayName="Volume (primary)",name="out_vol_primary",datatype="GPDouble",parameterType="Derived",direction="Output")
        p_d1 = arcpy.Parameter(displayName="Volume (secondary)",name="out_vol_secondary",datatype="GPDouble",parameterType="Derived",direction="Output")
        p_d2 = arcpy.Parameter(displayName="Pump Time (hours)",name="out_pump_hrs",datatype="GPDouble",parameterType="Derived",direction="Output")
        p_d3 = arcpy.Parameter(displayName="Depression Area (acres)",name="out_dep_acres",datatype="GPDouble",parameterType="Derived",direction="Output")
        p_d4 = arcpy.Parameter(displayName="Average Depth (inches)",name="out_avg_depth",datatype="GPDouble",parameterType="Derived",direction="Output")
        return [p_poly,p_dem,p_pump,p_depth,p_units,p_out,p_d0,p_d1,p_d2,p_d3,p_d4]

    def isLicensed(self):
        try:
            arcpy.CheckOutExtension("Spatial")
            arcpy.CheckOutExtension("3D")
        except Exception:
            return False
        return True

    def execute(self, parameters, messages):
        arcpy.env.overwriteOutput = True
        ws = arcpy.env.scratchGDB

        poly_input   = parameters[0].value
        dem_path     = parameters[1].valueAsText
        pump_gpm     = float(parameters[2].valueAsText or 500.0)
        obs_depth_in = float(parameters[3].valueAsText) if parameters[3].valueAsText else None
        obs_depth_ft = (obs_depth_in / 12.0) if obs_depth_in else None
        obs_depth_m  = (obs_depth_ft * 0.3048) if obs_depth_ft else None
        output_units = parameters[4].valueAsText or "US Standard (acre-feet + gallons)"
        dep_poly_out = parameters[5].valueAsText

        primary, secondary = get_unit_funcs(output_units)
        is_metric = "Metric" in output_units
        is_eng    = "Engineering" in output_units

        messages.addMessage("Depression Volume Calculator")
        messages.addMessage("="*55)

        # ── CRS check ───────────────────────────────────────────
        dem_sr = arcpy.Describe(dem_path).spatialReference
        if dem_sr.type == "Geographic":
            messages.addWarning(
                "  WARNING: DEM appears to be in a geographic coordinate system "
                "({} — units in degrees). Volume calculations require a projected "
                "coordinate system with linear units (meters or feet). Results will "
                "be incorrect. Reproject your DEM to an appropriate projected CRS "
                "before running this tool.".format(dem_sr.name)
            )
        else:
            messages.addMessage("  DEM CRS: {} ({})".format(dem_sr.name, dem_sr.linearUnitName))

        if obs_depth_in:
            messages.addMessage("  Observed depth: {} in ({:.2f} ft) — volume based on this depth".format(obs_depth_in, obs_depth_ft))
        else:
            messages.addMessage("  No observed depth — calculating maximum possible volume from terrain")

        # STEP 1: Clip DEM to polygon
        messages.addMessage("Step 1: Clipping DEM to flooded area...")
        poly_proj = os.path.join(ws,"dep_poly_proj")
        arcpy.management.Project(poly_input, poly_proj, dem_sr)
        dem_clip = clip_dem(dem_path, poly_proj, ws, "dep_dem_clip")

        # STEP 2: Fill sinks and determine depression extent
        messages.addMessage("Step 2: Identifying depression depth...")
        dem_fill = arcpy.sa.Fill(dem_clip)
        full_dep_depth = arcpy.sa.Minus(dem_fill, dem_clip)

        if obs_depth_m is not None:
            # Observed depth mode: water surface = polygon minimum elevation + observed depth.
            # NOTE: anchored to the lowest point in the drawn polygon. For best results
            # draw a tight polygon around one specific flooded area.
            elev_min = float(arcpy.management.GetRasterProperties(dem_clip, "MINIMUM").getOutput(0))
            water_surface = elev_min + obs_depth_m
            messages.addMessage("  Min terrain elev: {:.3f} {} | Water surface: {:.3f} {}".format(
                elev_min, dem_sr.linearUnitName, water_surface, dem_sr.linearUnitName))
            depth_from_surface = arcpy.sa.Minus(arcpy.sa.Float(water_surface), dem_clip)
            depression_depth = arcpy.sa.Con(
                arcpy.sa.GreaterThan(depth_from_surface, 0),
                depth_from_surface,
                0
            )
        else:
            # No observed depth: use Fill analysis to find natural depression extent
            depression_depth = full_dep_depth

        dep_depth_path = os.path.join(ws, "dep_depth")
        depression_depth.save(dep_depth_path)

        # STEP 3: Area
        messages.addMessage("Step 3: Calculating flooded area...")
        dep_binary = arcpy.sa.Con(arcpy.sa.GreaterThan(depression_depth, 0.01), 1)
        dep_binary_path = os.path.join(ws,"dep_binary")
        dep_binary.save(dep_binary_path)
        dep_scratch = os.path.join(ws,"dep_polygon_scratch")
        arcpy.conversion.RasterToPolygon(dep_binary_path, dep_scratch, "NO_SIMPLIFY")
        dep_area_m2    = sum([r[0] for r in arcpy.da.SearchCursor(dep_scratch,["SHAPE@AREA"])])
        dep_area_acres = dep_area_m2 / 4046.86
        messages.addMessage("  Flooded area: {:.3f} acres".format(dep_area_acres))

        # STEP 4: Volume
        messages.addMessage("Step 4: Calculating water volume...")
        sv = arcpy.ddd.SurfaceVolume(dep_depth_path,"","ABOVE",0,1)
        volume_m3 = 0.0
        for i in range(sv.messageCount):
            msg = sv.getMessage(i)
            if "Volume=" in msg:
                nums = re.findall(r"[\d]+\.?\d*", msg.split("Volume=")[-1])
                if nums: volume_m3 = float(nums[0]); break
        volume_acft = (volume_m3 * 35.3147) / 43560

        # STEP 5: Depth and pump time
        messages.addMessage("Step 5: Calculating depth and pump time...")
        try:
            mean_depth_m  = float(arcpy.management.GetRasterProperties(dep_depth_path,"MEAN").getOutput(0))
            mean_depth_ft = mean_depth_m * 3.28084
        except Exception:
            mean_depth_ft = 0.0

        volume_gallons = volume_acft * 325851
        pump_time_hrs  = volume_gallons / (pump_gpm * 60) if pump_gpm > 0 else 0

        # STEP 6: Save polygon
        messages.addMessage("Step 6: Saving output polygon...")
        vol_p, vol_p_unit = primary(volume_acft)
        vol_s, vol_s_unit = secondary(volume_acft)
        unit_sfx_p = "CubicM" if is_metric else ("CubicFt" if is_eng else "AcreFt")
        unit_sfx_s = "Liters" if is_metric else "Gallons"

        if arcpy.Exists(dep_poly_out): arcpy.management.Delete(dep_poly_out)
        arcpy.management.Dissolve(dep_scratch, dep_poly_out)

        for fname, ftype in [
            ("Vol_"+unit_sfx_p,"DOUBLE"),("Vol_"+unit_sfx_s,"DOUBLE"),
            ("AvgDepth_In","DOUBLE"),("Area_Acres","DOUBLE"),
            ("PumpTime_Hr","DOUBLE"),("PumpRate_GPM","DOUBLE"),
        ]:
            arcpy.management.AddField(dep_poly_out, fname, ftype)

        arcpy.management.CalculateField(dep_poly_out,"Vol_"+unit_sfx_p,str(vol_p))
        arcpy.management.CalculateField(dep_poly_out,"Vol_"+unit_sfx_s,str(vol_s))
        arcpy.management.CalculateField(dep_poly_out,"AvgDepth_In",str(round(mean_depth_ft*12,2)))
        arcpy.management.CalculateField(dep_poly_out,"Area_Acres",str(round(dep_area_acres,3)))
        arcpy.management.CalculateField(dep_poly_out,"PumpTime_Hr",str(round(pump_time_hrs,4)))
        arcpy.management.CalculateField(dep_poly_out,"PumpRate_GPM",str(pump_gpm))

        parameters[6].value  = vol_p
        parameters[7].value  = vol_s
        parameters[8].value  = round(pump_time_hrs,2)
        parameters[9].value  = round(dep_area_acres,3)
        parameters[10].value = round(mean_depth_ft*12,2)

        messages.addMessage("="*55)
        messages.addMessage("  DEPRESSION VOLUME RESULTS")
        messages.addMessage("  Area:       {:.3f} acres".format(dep_area_acres))
        messages.addMessage("  Avg depth:  {:.2f} in".format(mean_depth_ft*12))
        messages.addMessage("  Volume:     {} {} | {} {}".format(vol_p,vol_p_unit,int(vol_s),vol_s_unit))
        messages.addMessage("  Pump rate:  {} GPM".format(pump_gpm))
        messages.addMessage("  Pump time:  {:.2f} hours".format(pump_time_hrs))
        messages.addMessage("="*55)
        return
