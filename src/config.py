import inspect
import os
import shutil
import textwrap
from pathlib import Path
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
                hms_file = None,
                project_name=None,
                gage_file=None,
                met_file=None,
                basin_name=None,
                csv_file=None,
                control_file=None,
                start_date=None,
                end_date=None):
        self.default_start = datetime(2018, 1, 1)
        self.default_end = datetime(2022, 12, 31)
        self.csv_file = csv_file or os.getenv("CSV_FILE")
        self.dss_file = dss_file or os.getenv("DSS_FILE")
        self.hms_file = hms_file or os.getenv("HMS_FILE")
        self.project_name = project_name or os.getenv("HMS_PROJECT_NAME")
        self.gage_file = gage_file or os.getenv("GAGE_FILE")
        self.basin_name = basin_name or os.getenv("BASIN_NAME")
        self.met_file = met_file or os.getenv("MET_FILE")
        self.control_file = control_file or os.getenv("CONTROL_FILE")
        self.start_date = parse_date(start_date) if start_date else self.default_start
        self.end_date = parse_date(end_date) if end_date else self.default_end

        self.project_dir = os.path.dirname(self.hms_file)

        hms_basename = os.path.basename(self.hms_file)
        self.project_name = os.getenv("PROJECT_NAME", os.path.splitext(hms_basename)[0])
        
        self.dss_file = os.path.join(self.project_dir, "dados_chirps.dss")
        self.gage_file = os.path.join(self.project_dir, "precipitacao.gage")
        self.met_file = os.path.join(self.project_dir, "met_automatico.met")
        self.control_file = os.path.join(self.project_dir, "control_automatico.control")

        base_dir = Path(__file__).resolve().parent.parent
        self.local_output_dir = base_dir / "saidas" / "hms_export"
        self.local_output_dir.mkdir(parents=True, exist_ok=True)

        self.dss_file = str(self.local_output_dir / "dados_chirps.dss")
        self.gage_file = str(self.local_output_dir / "precipitacao.gage")
        self.met_file = str(self.local_output_dir / "met_automatico.met")
        self.control_file = str(self.local_output_dir / "control_automatico.control")

        if not all ([self.csv_file, self.dss_file, self.gage_file, self.met_file]):
            print("ERROR: Variables missing (CSV_FILE, DSS_FILE, GAGE_FILE, MET_FILE) at .env file.")

        self.B_PART = "PRECIP"
        self.C_PART = "PRECIP-INC"       
        self.E_PART = "1DAY"             
        self.F_PART = "GPM-CHIRPS"
        self.INTERVAL = 1                
        self.DATA_TYPE = "PER-INC"
        self.UNITS = "MM"

        self.met_model_name = "met_automatico"
        self.control_name = "control_automatico"
        self.GAGE_TEMPLATE = textwrap.dedent("""\
{% for gage in gages %}
Gage: {{ gage.name }}
     Gage: {{ gage.name }}
     Gage Type: Precipitation
     Last Modified Date: {{ date_str }}
     Last Modified Time: {{ time_str }}
     Reference Height Units: {{ gage.height_units | default('Meters') }}
     Reference Height: {{ gage.height | default('10.0') }}
     Data Source Type: Manual Entry
     Filename: {{ gage.dss_file }}
     Pathname: {{ gage.pathname }}
     Variant: Variant-1
        Start Time: {{ gage.start_time }}
        End Time: {{ gage.end_time }}
     End Variant: Variant-1
End:

{% endfor %}""")

        self.MET_TEMPLATE = textwrap.dedent("""
Meteorology: {{ met_name }}
     Description: Met model gerado automaticamente
     Last Modified Date: {{ date_str }}
     Last Modified Time: {{ time_str }}
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
{% endfor %}""")

        self.CONTROL_TEMPLATE = textwrap.dedent(
"""Control: {{ control_name }}
     Last Modified Date: {{ date_str }}
     Last Modified Time: {{ time_str }}
     Version: 4.13
     Description: Automacao Python TCC
     Start Date: {{ start_date }}
     Start Time: 00:00
     End Date: {{ end_date }}
     End Time: 00:00
     Time Interval: 1440
End:""")

    def export_to_hec_hms_dir(self):
        print(f"Copiando arquivos de saída para {self.project_dir}...")
        for src_file in self.local_output_dir.glob("*.*"):
            dest_file = os.path.join(self.project_dir, src_file.name)
            shutil.copy2(src_file, dest_file)
        print("✅ Files exported with success to HEC-HMS!")

    HMS_CONFIG = {
        "project_name": "tcc",
        "description": "automação hidrológica para o tcc",
        "version": "4.13",
        "filepath_separator": "\\",
        "dss_file": "tcc.dss",
        "timezone": "America/Sao_Paulo",
        "basin": {
            "name": "pds",
            "filename": "pds.basin"
        },
        "meteorology": {
            "name": "met_automatico",
            "filename": "met_automatico.met"
        },
        "control": {
            "name": "control_automatico",
            "filename": "control_automatico.control"
        },
        "gages": [f"S_{i}" for i in range(1, 61)],
        "gage_filename": "precipitacao.gage"
    }