import geopandas as gpd
import numpy as np
import rasterio
from rasterio.features import rasterize
from rasterio.transform import from_bounds
from rasterstats import zonal_stats
import os
import sys
import sqlite3
from pathlib import Path
import pandas as pd

class Geoprocessor:
    def __init__(self, config):
        self.config = config
        print("Geoprocessor initilized.")

    def run_all(self):
        try:
            gdf_wgs84 = self.process_geodataframe()
            return self.run_zonal_stats(gdf_wgs84)
        except Exception as e:
            print(f"Fatal error in geoprocessing: {e}.")
            sys.exit(1)

    def process_geodataframe(self):
        gdf = gpd.read_file(self.config.shp_path)
        if "name" not in gdf.columns:
            raise ValueError("Subbasin shapefile must contain a 'name' field (S1, S2, ...).")

        names = gdf["name"].astype(str).str.strip()
        parsed_ids = names.str.extract(r"(?i)^S_?(\d+)$", expand=False)
        if parsed_ids.isna().any():
            invalid_names = names[parsed_ids.isna()].head(10).tolist()
            raise ValueError(
                "Subbasin names must use the S1, S2, ... format; invalid names: "
                + ", ".join(invalid_names)
            )

        subbasin_ids = parsed_ids.astype(int)
        if names.duplicated().any() or subbasin_ids.duplicated().any():
            raise ValueError("Subbasin names/IDs must be unique.")

        expected_ids = set(range(1, len(gdf) + 1))
        actual_ids = set(subbasin_ids)
        if actual_ids != expected_ids:
            raise ValueError(
                "Subbasin IDs must be contiguous from S1 to S<N>; "
                f"missing={sorted(expected_ids - actual_ids)}, "
                f"unexpected={sorted(actual_ids - expected_ids)}."
            )

        # Keep precipitation IDs tied to the HEC-HMS subbasin suffix, not
        # shapefile row order: S1 always maps to raster_val 1, S2 to 2, etc.
        gdf["name"] = [f"S{sub_id}" for sub_id in subbasin_ids]
        gdf["raster_val"] = subbasin_ids.to_numpy(dtype=np.int64)
        gdf_wgs84 = gdf.to_crs("EPSG:4326")
        gdf_wgs84['geometry'] = gdf_wgs84['geometry'].buffer(0)
        
        geojson_filename = "subbasins-pds.geojson"
        gdf_wgs84.to_file(geojson_filename, driver="GeoJSON")

        self.rasterize_gdf(gdf_wgs84)

        return gdf_wgs84
    
    def rasterize_gdf(self, gdf_wgs84):
        gdf_m = gdf_wgs84.to_crs(gdf_wgs84.estimate_utm_crs())

        subbasins_folder = os.path.join(self.config.exit_path, "shapefiles")
        os.makedirs(subbasins_folder, exist_ok=True)
        output_shp = os.path.join(subbasins_folder, "subbasins_UTM.shp")
        gdf_m.to_file(output_shp, driver = "ESRI Shapefile", encoding='utf-8')
        print(f"Shapefile saved in: {output_shp}")

        resolution = 1000
        minx, miny, maxx, maxy = gdf_m.total_bounds
        width = int((maxx - minx ) / resolution)
        height = int((maxy - miny) / resolution)
        transform = from_bounds(minx, miny, maxx, maxy, width, height)
        shapes = [(geom, value) for geom, value in zip(gdf_m.geometry, gdf_m['raster_val'])]

        raster = rasterize(
            shapes,
            out_shape=(height, width),
            transform= transform,
            fill = 0,
            dtype='uint16'
        )

        output_tif = f"{self.config.exit_path}/subbasin_mask.tif"

        with rasterio.open(
            output_tif, 'w', driver='GTiff',
            height=height, width=width, count=1,
            dtype= raster.dtype, crs=gdf_m.crs, transform=transform,
        ) as dst:
            dst.write(raster, 1)
        print(f"Raster file saved in {output_tif}.")

    def run_zonal_stats(self, gdf_wgs84):
        with rasterio.open(self.config.gcn_raster_path) as src:
            raster_crs = src.crs
            raster_nodata = src.nodata

        gdf_proj = gdf_wgs84.to_crs(raster_crs).copy()
        gcn_stats = zonal_stats(
            gdf_proj,
            self.config.gcn_raster_path,
            stats = ['mean'],
            nodata=raster_nodata,
        )

        gcn_values = [stat['mean'] for stat in gcn_stats]
        invalid_values = [value for value in gcn_values if value is None or not 0 < value <= 100]
        if invalid_values:
            raise ValueError(
                "GCN raster produced missing or out-of-range subbasin values: "
                f"{invalid_values}"
            )

        enriched = gdf_wgs84.copy()
        enriched["gcn"] = gcn_values
        sqlite_stats = self.read_kirpich_inputs(enriched["name"])
        enriched = enriched.merge(sqlite_stats, on="name", how="left", validate="one_to_one")

        if enriched[["longest_length_m", "longest_slope_m_m"]].isna().any().any():
            raise ValueError("SQLite data is missing for one or more subbasins.")

        enriched["tc_kirpich_min"] = (
            0.0195
            * enriched["longest_length_m"].pow(0.77)
            * enriched["longest_slope_m_m"].pow(-0.385)
        )
        # SCS Unit Hydrograph basin lag estimate: 0.6 * Tc.
        enriched["lag_scs_min"] = 0.6 * enriched["tc_kirpich_min"]

        enriched.to_file(self.config.gcn_geojson_path, driver="GeoJSON")
        print("Zonal statistics, SQLite attributes and Kirpich parameters saved successfully.")
        return enriched

    def read_kirpich_inputs(self, expected_names):
        sqlite_path = getattr(self.config, "sqlite_path", None)
        if not sqlite_path:
            raise ValueError("SQLITE_PATH must point to the HEC-HMS SQLite project database.")
        if not os.path.isfile(sqlite_path):
            raise FileNotFoundError(f"HEC-HMS SQLite database not found: {sqlite_path}")

        db_uri = Path(sqlite_path).resolve().as_uri() + "?mode=ro"
        with sqlite3.connect(db_uri, uri=True) as connection:
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            if "subbasin_statistics" not in tables:
                raise ValueError("SQLite database has no subbasin_statistics table.")
            stats = pd.read_sql_query(
                """SELECT subbasin_name AS name, longest_length, longest_slope,
                          length_units
                   FROM subbasin_statistics""",
                connection,
            )

        if stats["name"].isna().any():
            raise ValueError("SQLite subbasin_statistics contains missing names.")
        stats["name"] = stats["name"].astype(str).str.strip()
        if stats["name"].eq("").any() or stats["name"].duplicated().any():
            raise ValueError("SQLite subbasin_statistics contains empty or duplicate names.")
        stats["longest_length_m"] = pd.to_numeric(stats["longest_length"], errors="coerce")
        stats["longest_slope_m_m"] = pd.to_numeric(stats["longest_slope"], errors="coerce")
        units = stats["length_units"].astype(str).str.strip().str.lower()
        if not units.isin({"m", "meter", "meters", "metre", "metres"}).all():
            raise ValueError(
                "Kirpich implementation expects longest_length in meters; "
                f"SQLite units found: {sorted(units.unique().tolist())}."
            )
        if (
            stats["longest_length_m"].isna().any()
            or (stats["longest_length_m"] <= 0).any()
            or stats["longest_slope_m_m"].isna().any()
            or (stats["longest_slope_m_m"] <= 0).any()
        ):
            raise ValueError("Kirpich inputs must be numeric and strictly positive.")

        expected = set(expected_names.astype(str).str.strip())
        actual = set(stats["name"])
        if actual != expected:
            raise ValueError(
                "SQLite subbasins do not match the GeoDataFrame; "
                f"missing={sorted(expected - actual)}, unexpected={sorted(actual - expected)}."
            )
        return stats[["name", "longest_length_m", "longest_slope_m_m"]]
        
