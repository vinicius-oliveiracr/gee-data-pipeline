import inspect
import os
import sys
from dotenv import load_dotenv
from datetime import datetime
import logging

load_dotenv()
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def parse_date(date_val):
    if isinstance(date_val, str):
        try:
            return datetime.strptime(date_val, "%Y-%m-%d")
        except ValueError:
            raise ValueError(f"Invalid date format: {date_val}. Expected format: YYYY-MM-DD")

        
class Config:
    def __init__(self,
                 shp_path=None,
                 exit_path=None,
                 start_date=None,
                 end_date=None,
                 old_gage_file=None,
                 dss_file=None,
                 project_name=None,
                 control_file=None):

        self.shp_path = shp_path or os.getenv("FILE_PATH")
        self.exit_path = exit_path or os.getenv("EXIT_PATH")

        self.default_start = datetime(2018, 1, 1)
        self.default_end = datetime(2022, 12, 31)
        
        # Tratamento de erro na conversão de datas (onde um ValueError PODE acontecer)
        try:
            self.start_date = parse_date(start_date) if start_date else self.default_start
            self.end_date = parse_date(end_date) if end_date else self.default_end
        except ValueError as e:
            logging.error(f"Erro ao converter data: {e}")
            raise e

        self.old_gage_file = old_gage_file or os.getenv("OLD_GAGE_FILE")
        self.dss_file = dss_file or os.getenv("DSS_FILE")
        self.project_name = project_name or os.getenv("PROJECT_NAME")
        self.control_file = control_file or os.getenv("CONTROL_FILE")
        
        self.gcn_raster_path = os.path.join(BASE_DIR, "assets", "GCN.tif")
        self.api_key = os.getenv("API_KEY")
        self.account = os.getenv("EE_ACCOUNT")
        self.private_key_path = os.getenv("PRIVATE_KEY_PATH")

        # Validação explícita de presença de valores essenciais
        essential_vars = {
            "PRIVATE_KEY_PATH": self.private_key_path,
            "PROJECT_NAME": self.project_name,
            "FILE_PATH (shp_path)": self.shp_path,
            "EXIT_PATH": self.exit_path
        }
        
        missing = [key for key, value in essential_vars.items() if not value]
        if missing:
            logging.warning(f"Essential variables missing: {', '.join(missing)}")
            


class DssConfig:
    def __init__(self, 
                dss_file=None,
                gage_file=None,
                met_file=None,
                csv_file=None,
                control_file=None,
                start_date=None,
                end_date=None):
        self.default_start = datetime(2018, 1, 1)
        self.default_end = datetime(2022, 12, 31)
        self.csv_file = csv_file or os.getenv("CSV_FILE")
        self.dss_file = dss_file or os.getenv("DSS_FILE")
        self.gage_file = gage_file or os.getenv("GAGE_FILE")
        self.met_file = met_file or os.getenv("MET_FILE")
        self.control_file = control_file or os.getenv("CONTROL_FILE")
        self.start_date = parse_date(start_date) if start_date else self.default_start
        self.end_date = parse_date(end_date) if end_date else self.default_end

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