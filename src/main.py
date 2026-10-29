import sys
import logging
import re
from config import Config, DssConfig
from auth import initialize_gee
from geoprocessor import Geoprocessor
from data import PrecipitationDownloader
from dss_generator import DssGenerator
from hms_file_generator import HmsFileGenerator


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    force=True)

def gee_workflow(config: Config = None):
    logging.info("---Initializing hydrologic automation ---")

    try:
        if config is None:
            config = Config()

        initialize_gee(config)

        processor = Geoprocessor(config)

        gdf_wgs84 = processor.run_all()

        downloader = PrecipitationDownloader(config)
        downloader.download_data(gdf_wgs84)

        logging.info("\n GEE workflow finalized successfully.\n")
    except Exception as e:
        logging.error(f"Fatal error at workflow: {e}")
        raise e

    
def dss_workflow(dss_config: DssConfig = None):
    logging.info("DSS/HMS automation proccess initialized.\n")

    try:
        if dss_config is None:
            dss_config = DssConfig()

        dss_generator = DssGenerator(dss_config)
        gage_data_list = dss_generator.get_dss()

        if not gage_data_list:
            logging.warning("No gage data was created. Proccess will be interrupted.")
            return

        file_generator = HmsFileGenerator(dss_config)
        file_generator.update_basin_curve_numbers()
        file_generator.generate_gage_file(gage_data_list)

        subbasins_data = []
        seen_ids = set()
        for gage in gage_data_list:
            gage_name = gage.get("name")
            match = re.fullmatch(r"S_(\d+)", str(gage_name or ""))
            if not match:
                raise ValueError(
                    f"Unexpected gage name {gage_name!r}; expected S_<subbasin ID>."
                )

            subbasin_id = int(match.group(1))
            if subbasin_id in seen_ids:
                raise ValueError(f"Duplicate precipitation gage for S{subbasin_id}.")
            seen_ids.add(subbasin_id)

            subbasin_name = gage.get("subbasin")
            expected_subbasin_name = f"S{subbasin_id}"
            if subbasin_name != expected_subbasin_name:
                raise ValueError(
                    f"Gage {gage_name} belongs to {subbasin_name!r}; "
                    f"expected {expected_subbasin_name!r}."
                )

            expected_dss_path = dss_config.build_dss_pathname(subbasin_id)
            if gage.get("dss_path") != expected_dss_path:
                raise ValueError(
                    f"Gage {gage_name} references {gage.get('dss_path')!r}; "
                    f"expected {expected_dss_path!r}."
                )

            subbasins_data.append({
                "subbasin": subbasin_name,
                "gage": gage_name,
            })

        expected_ids = set(range(1, len(subbasins_data) + 1))
        if seen_ids != expected_ids:
            raise ValueError(
                "Precipitation gages must cover subbasins S1 through S<N>; "
                f"missing={sorted(expected_ids - seen_ids)}, "
                f"unexpected={sorted(seen_ids - expected_ids)}."
            )

        file_generator.generate_met_file(subbasins_data)
        file_generator.generate_control_file()

        file_generator.sync_hms_project()

        dss_config.export_to_hec_hms_dir()

        logging.info(f"Generating all files for {len(subbasins_data)} subbasins and {len(gage_data_list)} gages.")
        logging.info("Process finalized successfully.")

    except Exception as e:
        logging.error(f"An error has ocurred during workflow: {e}")
        raise e

if __name__ == "__main__":
    gee_workflow()
    dss_workflow()

    logging.info("\n ---- Full process finalized! ----")
