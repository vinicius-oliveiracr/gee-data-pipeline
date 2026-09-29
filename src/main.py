import sys
import logging
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

        logging.info("\n Script finalized successfully.")
    except Exception as e:
        logging.error(f"Fatal error at workflow: {e}")
        raise e

    
def dss_workflow(dss_config: DssConfig = None):
    logging.info("DSS/HMS automation proccess initialized.")

    try:
        if dss_config is None:
            dss_config = DssConfig()

        dss_generator = DssGenerator(dss_config)
        gage_data_list = dss_generator.get_dss()

        if not gage_data_list:
            logging.warning("No gage data was created. Proccess will be interrupted.")
            return

        file_generator = HmsFileGenerator(dss_config)
        file_generator.generate_gage_file(gage_data_list)
        file_generator.generate_met_file(gage_data_list)
        file_generator.generate_control_file()

        logging.info(f"Generating all files for {len(gage_data_list)} subbasins.")
        logging.info("Process finalized successfully.")

    except Exception as e:
        logging.error(f"An error has ocurred during workflow: {e}")
        raise e

if __name__ == "__main__":
    gee_workflow()
    dss_workflow()

    logging.info("\n ---- Full process finalized! ----")