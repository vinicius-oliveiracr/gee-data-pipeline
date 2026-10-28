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

The GEE extraction scale is configured with `PRECIPITATION_SCALE` (meters; defaults to `5000`). The cache manifest in `saidas/csv_blocks/cache_manifest.json` records the scale, date range, CHIRPS collection and band, block size, and a fingerprint of the subbasin names, IDs, and geometries.

When these parameters change, existing precipitation blocks and the unified CSV are copied to a timestamped directory under `saidas/csv_backups/` before the precipitation blocks are re-extracted. The previous unified CSV stays available until all new blocks pass validation and the replacement is ready. When parameters are unchanged, no backup is created on a normal run. If a block is missing from the active cache, the pipeline can restore it from a backup only when its recorded extraction parameters match and the block passes daily coverage and value validation. If newly retrieved data changes the unified CSV, the prior unified CSV is backed up before replacement. A legacy cache without a manifest is treated as having unknown parameters and archived before reuse; blocks in such a backup cannot be safely reused automatically because their extraction settings are unknown.

## HEC-HMS subbasin shapefile input

Set `FILE_PATH` to the subbasin polygon shapefile exported from the intended HEC-HMS Basin Model. Keep the shapefile sidecar files (`.shp`, `.shx`, `.dbf`, and `.prj`) together. The input must contain a `name` field whose values exactly match the subbasin element names in the HEC-HMS `.basin` file, and its layer must have a defined CRS.

The pipeline assigns deterministic numeric `raster_val` IDs from sorted HEC-HMS names for raster masks, Google Earth Engine extraction, CSV, and DSS processing. The name-to-ID relationship is also included in the precipitation cache fingerprint. Gage and meteorology files use the original HEC-HMS names; the workflow has no fixed 60-subbasin limit. CHIRPS area means are used when available; if a small polygon has no contributing CHIRPS pixel for the mean reducer, the pipeline uses the pixel at an interior point and records `interior_pixel_fallback` in the CSV. This fallback does not increase CHIRPS spatial resolution.

The pipeline calculates precipitation and GCN values for the supplied polygons. It does not create HEC-HMS basin elements, terrain data, stream networks, outlets, or downstream connections; prepare and review those in HEC-HMS before simulation.

## HEC-HMS project outputs

When using `python src/gui.py`, select the target `.hms` project. The filename without its `.hms` extension is the canonical project name for generated files. For example, selecting `Bacia Norte.hms` produces `Bacia Norte.dss`, `Bacia Norte.gage`, `Bacia Norte.met`, and `Bacia Norte.control`. The DSS is exported to the project's `data/` directory, and the generated HEC-HMS references use that same filename. Intermediate output is kept in a project-specific folder under `saidas/hms_export/` to avoid collisions between projects.

The `.basin` filename is still selected by `BASIN_NAME` (default: `pds`), because its name is not necessarily the same as the `.hms` project filename. Configure `CSV_FILE`, `BASIN_NAME`, and the GEE settings in the environment as needed before running the workflow.
