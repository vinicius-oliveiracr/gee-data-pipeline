import pandas as pd
import geopandas as gpd

path = '/home/vinicius/projects/projects/gee-data-pipeline/saidas/subbacias_corrigidas_com_gcn.geojson'

gdf = gpd.read_file(path)

