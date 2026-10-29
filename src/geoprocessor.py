import geopandas as gpd
import rasterio
from rasterio.features import rasterize
from rasterio.transform import from_bounds
from rasterstats import zonal_stats
import os
import sys

class Geoprocessor:
    def __init__(self, config):
        self.config = config
        print("Geoprocessor initilized.")

    def run_all(self):
        try:
            gdf_wgs84 = self.process_geodataframe()
            self.run_zonal_stats(gdf_wgs84)

            return gdf_wgs84
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

        gdf_proj['gcn'] = gcn_values
        gdf_proj.to_file(self.config.gcn_geojson_path, driver="GeoJSON")
        print("Zonal statistics saved successfully.")
        
