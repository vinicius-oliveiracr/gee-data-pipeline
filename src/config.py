import inspect
import os
import sys
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
class Config:
    def __init__(self):

        self.old_gage_file = os.getenv("OLD_GAGE_FILE")
        self.dss_file = os.getenv("DSS_FILE")
        self.shp_path = os.getenv("FILE_PATH")
        self.exit_path = os.getenv("EXIT_PATH")
        self.gcn_raster_path = os.path.join(BASE_DIR, "assets", "GCN.tif")
        self.api_key = os.getenv("API_KEY")
        self.account = os.getenv("EE_ACCOUNT")
        self.private_key_path = os.getenv("PRIVATE_KEY_PATH")
        self.project_name = os.getenv("PROJECT_NAME")
        self.control_file = os.getenv("CONTROL_FILE")

        self.start_date = datetime(2018, 1, 1)
        self.end_date = datetime(2022, 12, 31)

        if not all([self.private_key_path, self.project_name, self.shp_path, self.exit_path]):
            print("ERROR: Essencial variables (PRIVATE_KEY_PATH, PROJECT_NAME, FILE_PATH, EXIT_PATH) not found in .env file.")
            sys.exit(1)


class DssConfig:
    def __init__(self):

        self.csv_file = os.getenv("CSV_FILE")
        self.dss_file = os.getenv("DSS_FILE")
        self.gage_file = os.getenv("GAGE_FILE")
        self.met_file = os.getenv("MET_FILE")
        self.control_file = os.getenv("CONTROL_FILE")
        self.start_date = datetime(2018, 1, 1)
        self.end_date = datetime(2022, 12, 31)

        if not all ([self.csv_file, self.dss_file, self.gage_file, self.met_file]):
            print("ERROR: Variables missing (CSV_FILE, DSS_FILE, GAGE_FILE, MET_FILE) at .env file.")

        self.B_PART = "PRECIP"
        self.C_PART = "PRECIP-INC"       
        self.E_PART = "1DAY"             
        self.F_PART = "GPM-CHIRPS"
        self.INTERVAL = 1                
        self.DATA_TYPE = "PER-INC"
        self.UNITS = "MM"

        self.MET_MODEL_NAME = "met_automatico"
        self.BASIN_MODEL_NAME = "ParaibaDoSul"
        self.CONTROL_NAME = "control_automatico"

        self.GAGE_TEMPLATE = inspect.cleandoc("""
     {% for g in gages %}
     Gage: {{ g.name }}
     Description: Gage gerado automaticamente via Python
     Last Modified Date: {{ g.date }}
     Last Modified Time: {{ g.time }}
     Reference Height Unit: Meters
     Reference Height: 10.0
     Units: MM
     Data Type: PER-INC
     Gage Type: Precipitation
     Precipitation Gage Type: External DSS
     External DSS File: {{ g.dss_file }}
     External DSS Pathname: {{ g.dss_path }}
     End:
     {% endfor %}""")

        self.MET_TEMPLATE = inspect.cleandoc("""
     Meteorology: {{ met_name }}
     Description: Met model gerado automaticamente
     Last Modified Date: {{ dt.strftime('%d %B %Y') }}
     Last Modified Time: {{ dt.strftime('%H:%M:%S') }}
     Version: 4.13
     Unit System: Metric
     Set Missing Data to Default: No
     Precipitation Method: Specified Hyetograph
     Use Basin Model: {{ basin_name }}
     End:

     {% for item in subbasins %}
     Subbasin: {{ item.subbasin }}
     Precipitation Gage: {{ item.gage }}
     End:
     {% endfor %}
    """)

        self.CONTROL_TEMPLATE = inspect.cleandoc(
     """Control: {{ control_name }}
     Last Modified Date: {{ dt.strftime('%d %B %Y') }}
     Last Modified Time: {{ dt.strftime('%H:%M') }}
     Version: 4.13
     Description: Automacao Python TCC
     Start Date: {{ start_date }}
     Start Time: 00:00
     End Date: {{ end_date }}
     End Time: 00:00
     Time Interval: 1440
     End:
     """)