import geopandas as gpd
from pyogrio import env
import json

shp = "52MI2500G.shp"  # ou seu GeoJSON se quiser checar

with env.set_gdal_config_options({"SHAPE_RESTORE_SHX": "YES"}):
    gdf = gpd.read_file(shp, engine="pyogrio")

print("CRS:", gdf.crs)
print("Bounds (sem CRS):", list(gdf.total_bounds))  # [xmin, ymin, xmax, ymax]
