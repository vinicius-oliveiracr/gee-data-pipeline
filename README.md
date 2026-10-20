Automated Precipitation Data Pipeline using Google Earth Engine's API

![Python](https://img.shields.io/badge/Python-3.x-blue) ![GEE](https://img.shields.io/badge/Google%20Earth%20Engine-API-green) ![ETL](https://img.shields.io/badge/Data%20Pipeline-ETL-orange) ![Geospatial](https://img.shields.io/badge/Geospatial-Data-lightgrey) ![Hydrology](https://img.shields.io/badge/Hydrological-Modeling-blueviolet)


This project focuses on the automation of a data pipeline for extracting, processing and preparing precipitation data using Google Earth Engine (GEE) API. It ingests geospatial basin data, processes time-series precipitation data, and generates structured outputs to be consumed by the HEC-HMS hydrological model.

The ultimate goal is to reduce manual effort, improve reproducibility and ensures a reliable data preparation workflow for hydrological modelling.

## Overview

The pipeline automates the following steps:

1. Ingestion of geospatial data, using basin's shapefile
2. Authentication and data extraction from Google Earth Engine
3. Download and processing of precipitation time-series data
4. Transformation and preparation of data from CSV to DSS, required by the hydrological model

To improve performance and avoid Google Earth Engine API limitations, the time range is split into 30-day intervals during data extraction.

## Tecnologies and Tools Used

- Python
- Google Earth Engine (Python API)
- Pandas
- Geopandas
- OAuth2 / Service Account authentication
- Geospatial data processing tools
- CSV data handling
- Git for Version Control

## Project Structure

- auth.py → Handles authentication using Google OAuth2 and service accounts
- config.py → Centralizes environment variables, configuration parameters, and worflow setup
- data.py → Implements data extraction and processing pipeline using GEE
- dss_generator.py → Transforms precipitation time-series data from CSV into DSS format for HEC-HMS. Handles temporal filtering, subbasin-based grouping, time-series construction, and automated generation of gage metadata for model integration.
- geoprocessor.py → Performs geospatial data preprocessing and feature engineering. Converts and validates basin geometries, generates raster masks for subbasins, and computes zonal statistics from auxiliary rasters, producing structured geospatial outputs consumed by downstream data extraction and modeling steps.
- hms_file_generator.py → Automates the generation of HEC-HMS input configuration files using templated workflows. Transforms structured pipeline outputs into gage, meteorological, and control files required for hydrological simulations.
- main.py → Pipeline orchestrator that manages end-to-end execution of geospatial ETL workflows, from data ingestion and transformation to generation of structured outputs for hydrological modeling systems.

## Key Features

- End-to-end automated geospatial ETL pipeline
- Scalable data extraction from Google Earth Engine
- Time-series processing and validation
- Automated generation of DSS and HEC-HMS input files
- Modular and reproducible architecture

## Precipitation cache and backups

The GEE extraction scale is configured with `PRECIPITATION_SCALE` (meters; defaults to `5000`). The cache manifest in `saidas/csv_blocks/cache_manifest.json` records the scale, date range, CHIRPS collection and band, block size, and a fingerprint of the subbasin geometries.

When these parameters change, existing precipitation blocks and the unified CSV are copied to a timestamped directory under `saidas/csv_backups/` before the precipitation blocks are re-extracted. The previous unified CSV stays available until all new blocks pass validation and the replacement is ready. When parameters are unchanged, no backup is created on a normal run. If a block is missing from the active cache, the pipeline can restore it from a backup only when its recorded extraction parameters match and the block passes daily coverage and value validation. If newly retrieved data changes the unified CSV, the prior unified CSV is backed up before replacement. A legacy cache without a manifest is treated as having unknown parameters and archived before reuse; blocks in such a backup cannot be safely reused automatically because their extraction settings are unknown.

## SRTM terrain export

The GEE workflow also downloads the `USGS/SRTMGL1_003` elevation band and mosaics it into `saidas/terrain/srtm_bacia.tif`. The export covers the basin shapefile bounds plus a 5,000 m margin and is reprojected to the estimated UTM CRS at 30 m resolution. The download uses small GeoTIFF tiles and does not change the existing `subbasins_UTM.shp` or `subbasin_mask.tif` outputs.

Optional environment variables:

- `SRTM_OUTPUT_PATH`: output GeoTIFF path; defaults to `EXIT_PATH/terrain/srtm_bacia.tif`.
- `SRTM_SCALE`: output resolution in meters; defaults to `30`.
- `SRTM_MARGIN_M`: margin around the input geometry bounds in meters; defaults to `5000`.

The GeoTIFF is an elevation input for HEC-HMS terrain processing. It does not by itself create the stream network, basin outlets, or downstream connections; prepare and review those in HEC-HMS before simulation.
